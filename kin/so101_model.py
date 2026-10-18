"""SO-101 的 MuJoCo 模型封装：正运动学（FK）与几何雅可比。

设计约束（都是被实测数据逼出来的）：
  * 只用 MJCF 提供**连杆几何**，关节数值一律来自校准换算（见 kin/calibration.py），
    因为 MJCF 的 range 和真机行程差最多 73 度。
  * 因此本模块算 FK 时**不做限位裁剪**（只跑 mj_kinematics + mj_comPos，
    不跑 mj_step），这样 q 落在 MJCF 理论 range 之外也能正确算出几何位置。
  * 末端参考点是 MJCF 里内置的 `gripperframe` site，
    在 gripper body 系下位于 z = -0.0981274 m（约等于夹爪指尖）。

坐标系约定：全部在 **base（机械臂基座）坐标系**，右手系，单位米。
            相机坐标系（x 右 / y 下 / z 前）的转换在 perception 层做。
"""
import os

import mujoco
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_XML = os.path.join(ROOT, "assets", "so101_sim", "so101_new_calib.xml")

JOINT_ORDER = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]


def rot_err_world(r_cur: np.ndarray, r_tgt: np.ndarray) -> np.ndarray:
    """世界系姿态误差（3 维旋转向量近似）。

    用列向量叉积求和，是 MuJoCo 官方示例里的做法，在小角度下线性近似
    旋转向量，配合 DLS 迭代足够稳。
    """
    e = np.zeros(3)
    for i in range(3):
        e += np.cross(r_cur[:, i], r_tgt[:, i])
    return 0.5 * e


def rot_from_up_and_forward(up: np.ndarray, forward_hint: np.ndarray) -> np.ndarray:
    """构造一个旋转矩阵：给定末端的「上方向」和「前方向」提示。

    返回的 R 的**第 3 列**对齐 `up`（MuJoCo 里 site 的 z 轴 = 夹爪伸出的方向），
    第 1 列尽量对齐 `forward_hint` 在垂直于 up 平面上的投影。
    """
    z = np.asarray(up, dtype=float)
    z /= np.linalg.norm(z)
    x = np.asarray(forward_hint, dtype=float)
    x = x - z * float(z @ x)
    n = np.linalg.norm(x)
    if n < 1e-9:
        x = np.array([1.0, 0.0, 0.0]) - z * z[0]
        n = np.linalg.norm(x)
    x /= n
    y = np.cross(z, x)
    return np.column_stack([x, y, z])


class So101Model:
    """薄封装，避免每个脚本重复写 MuJoCo 样板代码。"""

    def __init__(self, xml_path: str = DEFAULT_XML, ee_site: str = "gripperframe"):
        if not os.path.exists(xml_path):
            raise FileNotFoundError(
                f"找不到 MJCF: {xml_path}\n"
                f"先跑: & {os.path.join(ROOT, '_tools', 'python310', 'python.exe')} "
                f"_setup\\fetch_so101_sim.py")
        self.xml_path = xml_path
        self.model = mujoco.MjModel.from_xml_path(xml_path)
        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)

        self.site_name = ee_site
        self.site_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, ee_site)
        if self.site_id < 0:
            raise ValueError(f"MJCF 里没有 site '{ee_site}'")

        # LeRobot 关节名 -> MuJoCo qpos 下标（不要假设顺序一致）
        self.qpos_adr = {}
        for name in JOINT_ORDER:
            jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0:
                raise ValueError(f"MJCF 里没有关节 '{name}'")
            self.qpos_adr[name] = int(self.model.jnt_qposadr[jid])

        # MJCF 自带的执行器下标（仿真时用）
        self.act_id = {}
        for name in JOINT_ORDER:
            aid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            if aid >= 0:
                self.act_id[name] = int(aid)

        # MJCF 理论限位（仅作参考对照，IK 不要用）
        self.mjcf_limits = np.zeros((6, 2))
        for i, name in enumerate(JOINT_ORDER):
            jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            lo, hi = self.model.jnt_range[jid]
            self.mjcf_limits[i] = (lo, hi)

    # ------------------------------------------------------------------ 内部
    def _write_q(self, q_vec_rad) -> np.ndarray:
        q = np.asarray(q_vec_rad, dtype=np.float64).reshape(-1)
        if q.size != 6:
            raise ValueError(f"期望 6 维关节角，得到 {q.size}")
        self.data.qpos[:] = 0.0
        for i, name in enumerate(JOINT_ORDER):
            self.data.qpos[self.qpos_adr[name]] = q[i]
        # 只算几何，不跑物理，所以超限也照算
        mujoco.mj_kinematics(self.model, self.data)
        mujoco.mj_comPos(self.model, self.data)
        return q

    # ------------------------------------------------------------------ FK
    def fk(self, q_vec_rad) -> tuple[np.ndarray, np.ndarray]:
        """返回 (位置 (3,), 旋转矩阵 (3,3))。基座坐标系，米。"""
        self._write_q(q_vec_rad)
        pos = self.data.site_xpos[self.site_id].copy()
        rot = self.data.site_xmat[self.site_id].reshape(3, 3).copy()
        return pos, rot

    def fk_all_sites(self, q_vec_rad) -> dict:
        """所有 site 的位姿，调试用。"""
        self._write_q(q_vec_rad)
        out = {}
        for i in range(self.model.nsite):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_SITE, i) or f"site{i}"
            out[name] = {
                "pos": self.data.site_xpos[i].copy(),
                "rot": self.data.site_xmat[i].reshape(3, 3).copy(),
            }
        return out

    def jacobian(self, q_vec_rad) -> tuple[np.ndarray, np.ndarray]:
        """返回 (jacp, jacr)，各 (3, nv)。端点=site。"""
        self._write_q(q_vec_rad)
        jacp = np.zeros((3, self.model.nv))
        jacr = np.zeros((3, self.model.nv))
        mujoco.mj_jacSite(self.model, self.data, jacp, jacr, self.site_id)
        return jacp, jacr

    def jacobian6(self, q_vec_rad) -> np.ndarray:
        """(6, nv) 的 [平移; 旋转] 雅可比。"""
        jacp, jacr = self.jacobian(q_vec_rad)
        return np.vstack([jacp, jacr])

    # ------------------------------------------------------------------ 工具
    def gripper_axis_rot(self, axis_dir, forward_hint=(1.0, 0.0, 0.0)) -> np.ndarray:
        """构造让 site 的 z 轴对准 `axis_dir` 的旋转矩阵。"""
        return rot_from_up_and_forward(np.asarray(axis_dir, dtype=float),
                                       np.asarray(forward_hint, dtype=float))

    def gripper_down_rot(self, yaw_rad: float = 0.0) -> np.ndarray:
        """夹爪竖直向下（site z 轴 = -Z）。

        ⚠️ **不要用它做真机抓取目标**。实测训练数据里，抓取时刻 site z 轴与
        竖直向下的夹角中位是 95°（p5~p95 = 92~98°），也就是说 SO-101 实际是
        **水平前伸**抓取，竖直向下这个姿态不在它的正常使用范围内。强行约束
        会让 IK 差 15~50 度且位置残差到几十毫米。
        真正该用的是 `kin.so101_ik.grasp_pose_seed()` 做种子 + 位置-only IK。

        这里保留只是为了做姿态可达性实验（例如 _setup/_probe_down_pose.py）。
        """
        up = np.array([0.0, 0.0, -1.0])
        fwd = np.array([np.cos(yaw_rad), np.sin(yaw_rad), 0.0])
        return rot_from_up_and_forward(up, fwd)

    def describe(self) -> str:
        lines = [f"MJCF: {self.xml_path}",
                 f"nq={self.model.nq} nv={self.model.nv} nu={self.model.nu} "
                 f"nbody={self.model.nbody} ngeom={self.model.ngeom}",
                 f"末端 site: {self.site_name} (id={self.site_id})", "",
                 f"{'joint':<15}{'qpos_adr':>10}{'mjcf_lo':>10}{'mjcf_hi':>10}"]
        lines.append("-" * 46)
        for i, n in enumerate(JOINT_ORDER):
            lines.append(f"{n:<15}{self.qpos_adr[n]:>10}"
                         f"{np.rad2deg(self.mjcf_limits[i, 0]):>10.1f}"
                         f"{np.rad2deg(self.mjcf_limits[i, 1]):>10.1f}")
        return "\n".join(lines)


if __name__ == "__main__":
    m = So101Model()
    print(m.describe())
    print()
    print("== 零位姿态 FK ==")
    zero = np.zeros(6)
    p, r = m.fk(zero)
    print(f"  pos = {np.round(p, 4)} m  ({np.round(p * 100, 1)} cm)")
    print("  rot =")
    for row in r:
        print("    ", np.round(row, 4))

    print()
    print("== 各 site 位置（零位） ==")
    for name, d in m.fk_all_sites(zero).items():
        print(f"  {name:<18} {np.round(d['pos'], 4)}")

    print()
    print("== 关节逐个 +20 度，看末端位移 ==")
    for i, name in enumerate(JOINT_ORDER):
        q = np.zeros(6)
        q[i] = np.deg2rad(20)
        p2, _ = m.fk(q)
        d = np.linalg.norm(p2 - p) * 1000
        print(f"  {name:<15} 末端移动 {d:7.1f} mm")
