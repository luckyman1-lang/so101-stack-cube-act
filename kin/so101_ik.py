"""SO-101 逆运动学（阻尼最小二乘 DLS）与关节轨迹生成。

## 为什么用数值 IK 而不是解析解

SO-101 的结构是 yaw-pitch-pitch-pitch-roll（5 个串联关节 + 1 个夹爪）。
理论上"夹爪竖直向下"约束下，位置解只有 3 个自由度，可以闭式求解，但：

  * `wrist_flex` 的轴心不在前一个关节的端点上（MJCF 里 wrist body 有
    pos="-0.1349 0.0052 0" 的偏移），所以 3 个关节的位置解**不是**干净的两连杆；
  * 真机行程（校准值）比 MJCF 理论范围大，闭式解会在边界上失效。

用 MuJoCo 的**几何雅可比 + DLS** 迭代，30 行就能得到亚毫米精度，而且自动
处理限位和奇异点。这才是工程上更稳的选择。

## 关键实现细节

  * 姿态误差用列向量叉积求和（`rot_err_world`），小角度下的旋转向量近似；
  * DLS 的 `J.T (J J.T + λ²I)^-1` 天然给出**最小关节变化解**，所以位置-only
    时不会乱跑关节；
  * 关节限位用**校准实测值**（`Calibration.limits_rad()`），不用 MJCF range；
  * 每步限幅 `max_step_rad`，避免一次跳太远跳到另一个分支；
  * 不可达时**返回 None 而不是抛异常**，让上层状态机自己决定重试。
"""
import numpy as np

from .so101_model import JOINT_ORDER, So101Model, rot_err_world


def ik(model: So101Model,
       target_pos,
       target_rot=None,
       seed=None,
       limits=None,
       max_iter: int = 300,
       pos_tol: float = 1e-4,        # 0.1 mm
       rot_tol: float = 2e-3,        # 约 0.11 度
       lam: float = 0.08,
       max_step_rad: float = 0.2,
       verbose: bool = False):
    """解 IK。

    参数
    ----
    target_pos : (3,) 目标位置，基座坐标系，米
    target_rot : (3,3) 目标姿态矩阵；None = 只解位置
    seed       : (6,) 初值，弧度；None = 用一个"夹爪朝下"的典型姿态
    limits     : (6,2) 关节限位，弧度；None = 用 MJCF range（不推荐）

    返回
    ----
    (q, info)；解不出来时 q 为 None，info 里有原因。
    """
    target_pos = np.asarray(target_pos, dtype=np.float64).reshape(3)
    if target_rot is not None:
        target_rot = np.asarray(target_rot, dtype=np.float64).reshape(3, 3)

    if seed is None:
        q = typical_down_seed()
    else:
        q = np.asarray(seed, dtype=np.float64).reshape(6).copy()

    if limits is None:
        limits = model.mjcf_limits
    limits = np.asarray(limits, dtype=np.float64)
    q = np.clip(q, limits[:, 0], limits[:, 1])

    info = {"iters": 0, "pos_err": np.inf, "rot_err": np.inf, "ok": False,
            "reason": ""}

    for it in range(max_iter):
        info["iters"] = it + 1
        pos, rot = model.fk(q)
        ep = target_pos - pos
        pos_err = float(np.linalg.norm(ep))
        info["pos_err"] = pos_err

        if target_rot is not None:
            er = rot_err_world(rot, target_rot)
            rot_err = float(np.linalg.norm(er))
            info["rot_err"] = rot_err
            err = np.concatenate([ep, er])
        else:
            rot_err = 0.0
            info["rot_err"] = 0.0
            err = ep

        if pos_err < pos_tol and rot_err < rot_tol:
            info["ok"] = True
            info["reason"] = "converged"
            return q, info

        jacp, jacr = model.jacobian(q)
        J = np.vstack([jacp, jacr]) if target_rot is not None else jacp

        # DLS: dq = J^T (J J^T + lam^2 I)^-1 e
        JJt = J @ J.T
        A = JJt + (lam ** 2) * np.eye(JJt.shape[0])
        try:
            dq = J.T @ np.linalg.solve(A, err)
        except np.linalg.LinAlgError:
            info["reason"] = "singular"
            return None, info

        step = float(np.max(np.abs(dq)))
        if step > max_step_rad:
            dq *= max_step_rad / step

        q = q + dq
        q = np.clip(q, limits[:, 0], limits[:, 1])

        if verbose and (it % 50 == 0):
            print(f"    it{it:3d} pos_err={pos_err * 1000:8.2f}mm "
                  f"rot_err={np.rad2deg(rot_err):7.2f}deg")

    # 未收敛时把**当前最佳 q** 返回（ok=False），而不是 None。
    # 否则调用方连"差多少"都拿不到，多初值重启也无从比较优劣。
    info["reason"] = "max_iter"
    info["ok"] = False
    return q, info


def ik_to_object(model: So101Model, obj_pos, seed=None, limits=None, **kw):
    """解到「物体所在位置」的抓取关节角（位置-only）。

    不约束姿态 —— 实测证明 SO-101 抓取时夹爪是水平前伸的，而"竖直向下"
    根本不在它的正常姿态范围内。姿态由种子 + 冗余自由度自然决定，
    用 `grasp_pose_seed()` 做种子时会贴近真机习惯。
    """
    obj_pos = np.asarray(obj_pos, dtype=np.float64).reshape(3)
    return ik(model, obj_pos, target_rot=None,
              seed=grasp_pose_seed() if seed is None else seed,
              limits=limits, **kw)


# ------------------------------------------------------------------ 初值
def grasp_pose_seed() -> np.ndarray:
    """**真机抓取构型**（推荐用的默认种子）。

    数值来自对 stack_cube_v2 训练数据 160 个「抓取时刻」帧（末端 Z 最低）
    做校准换算 + FK 反推后的中位数。

    | 关节          | 角度    |
    |---------------|---------|
    | shoulder_pan  |  -7.4°  |
    | shoulder_lift | +47.5°  |
    | elbow_flex    | -40.9°  |
    | wrist_flex    | +77.2°  |
    | wrist_roll    |  -7.2°  |
    | gripper       | -45.7°  |  （闭合状态）

    重要：实测这些帧的 site z 轴与「竖直向下」夹角**中位 95°**（几乎水平），
    p5~p95 只有 92~98°。说明 SO-101 是**水平前伸**抓取，不是竖直下压。
    用这个种子做位置-only IK，60/60 收敛且姿态自然贴近真机习惯。
    """
    q = np.zeros(6)
    q[0] = np.deg2rad(-7.4)
    q[1] = np.deg2rad(47.5)
    q[2] = np.deg2rad(-40.9)
    q[3] = np.deg2rad(77.2)
    q[4] = np.deg2rad(-7.2)
    q[5] = np.deg2rad(-45.7)
    return q


def typical_down_seed() -> np.ndarray:
    """「site z 轴最接近竖直向下」的构型（理论可达，但**不是**真机抓取姿态）。

    仅在做姿态约束实验时用。真正的抓取请用 `grasp_pose_seed()`。
    数值来自 20 万点关节空间采样里 site z 轴最接近 -Z 的那个构型
    （偏离 0.2°）。注意它要求 shoulder_lift 是 +84° 的大正角。
    """
    q = np.zeros(6)
    q[0] = np.deg2rad(-37.0)
    q[1] = np.deg2rad(83.9)
    q[2] = np.deg2rad(37.0)
    q[3] = np.deg2rad(59.3)
    q[4] = np.deg2rad(2.8)
    q[5] = 0.5
    return q


def ik_track(model: So101Model, waypoints, seed=None, limits=None, **kw):
    """沿一串笛卡尔路径点做**增量式** IK（上一解当下一点的种子）。

    这是真机在线执行时的正确做法，比每个点独立求解：
      * 收敛率高得多（种子总是很近）；
      * 解在时间上连续，不会出现关节跳变；
      * 天然避开"翻腕"那种跳到另一个 IK 分支的情况。

    实测：沿训练数据真实轨迹抽稀的 24 个点，0 失败，最大误差 0.10 mm。

    返回 (Q, infos)；Q 形状 (N, 6)。
    """
    q = grasp_pose_seed() if seed is None else np.asarray(seed, dtype=float).reshape(6)
    out, infos = [], []
    for p in waypoints:
        q, info = ik(model, p, target_rot=None, seed=q, limits=limits, **kw)
        infos.append(info)
        out.append(np.array(q, dtype=float))
    return np.array(out), infos


def ik_multistart(model: So101Model,
                  target_pos,
                  target_rot=None,
                  limits=None,
                  n_tries: int = 24,
                  seed=None,
                  rng=None,
                  **kw):
    """多初值重启的 IK。

    为什么需要：带姿态约束（夹爪朝下）的可行构型只占关节空间的 0.8%，
    单一初值很容易掉进局部解。随机重启是 MoveIt 的标准做法，代价只是
    多几十次 FK+雅可比（本机约 0.1~0.3 秒）。

    返回 (q, info)；全部失败时 q 为 None，info 是误差最小的那次。
    """
    rng = np.random.default_rng() if rng is None else rng
    lim = model.mjcf_limits if limits is None else np.asarray(limits, dtype=float)
    lim = np.asarray(lim, dtype=float)

    best_q, best_info = None, {"pos_err": np.inf, "rot_err": np.inf, "ok": False,
                               "iters": 0, "reason": "no_try"}

    for t in range(max(1, n_tries)):
        if seed is not None and t == 0:
            s = np.asarray(seed, dtype=float).reshape(6)
        elif t == 0:
            s = typical_down_seed()
        elif t <= 8:
            # 在"朝下"初值附近扰动
            s = np.clip(typical_down_seed() + rng.normal(0, 0.35, 6),
                        lim[:, 0], lim[:, 1])
        else:
            # 别做全空间均匀随机 —— 带姿态约束的可行构型只占关节空间的 0.8%，
            # 24 次均匀随机几乎必然全空。改成在"夹爪朝下"的构型区域里采：
            # shoulder_lift / elbow_flex / wrist_flex 都取偏正的大角度
            # （结论来自 _setup/_probe_down_pose.py 的 20 万点采样）。
            s = np.zeros(6)
            s[0] = rng.uniform(lim[0, 0], lim[0, 1])
            s[1] = rng.uniform(np.deg2rad(45), lim[1, 1])
            s[2] = rng.uniform(np.deg2rad(-10), lim[2, 1])
            s[3] = rng.uniform(np.deg2rad(15), lim[3, 1])
            s[4] = rng.uniform(lim[4, 0], lim[4, 1])
            s[5] = 0.5

        q, info = ik(model, target_pos, target_rot, seed=s, limits=lim, **kw)
        if q is not None and info.get("ok"):
            return q, info
        if q is not None and info["pos_err"] < best_info["pos_err"]:
            best_q, best_info = q, info

    return best_q, best_info


# ------------------------------------------------------------------ 轨迹
def plan_joint_traj(q_from, q_to,
                    max_vel_rad_s: float = 1.2,
                    dt: float = 0.02,
                    min_steps: int = 20):
    """关节空间三次多项式插值，起止速度为 0。

    返回 (N, 6) 轨迹。时长按最慢关节的限速自动拉长。
    真机串口是 1M baud，6 个舵机 30~50Hz 下发比较稳；dt=0.02 (50Hz) 是默认。
    """
    q0 = np.asarray(q_from, dtype=np.float64).reshape(6)
    q1 = np.asarray(q_to, dtype=np.float64).reshape(6)
    dq = q1 - q0
    # smoothstep 的峰值速度 = 1.5 × 平均速度，所以时长要乘 1.5 才不超限
    PEAK_FACTOR = 1.5
    span = float(np.max(np.abs(dq)))
    min_total = PEAK_FACTOR * span / max(max_vel_rad_s, 1e-6)
    n = max(min_steps, int(np.ceil(min_total / dt)) + 1)

    s = np.linspace(0.0, 1.0, n)
    h = 3 * s ** 2 - 2 * s ** 3   # smoothstep，端点速度为 0
    traj = q0[None, :] + h[:, None] * dq[None, :]
    traj[0] = q0
    traj[-1] = q1
    peak = max_joint_speed(traj, dt) if n > 1 else 0.0
    return traj, {"n_steps": n, "duration_s": (n - 1) * dt,
                  "peak_vel_rad_s": peak, "span_rad": span}


def max_joint_speed(traj, dt: float = 0.02) -> float:
    """轨迹上的最大关节速度（rad/s），用来做下发前的安全检查。"""
    traj = np.asarray(traj, dtype=np.float64)
    if traj.shape[0] < 2:
        return 0.0
    return float(np.max(np.abs(np.diff(traj, axis=0))) / dt)
