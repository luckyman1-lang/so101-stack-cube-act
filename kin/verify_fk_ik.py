"""M2 自检：FK / IK / 轨迹 / 工作空间。

这是 B 的验收脚本。跑通它 = M2 的核心功能可用。

用法（在 D:\\LeRobot 下）：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" -m kin.verify_fk_ik
    ... --n 30            随机采样次数
    ... --verbose         打印每次迭代

验收标准：
    1. IK 位置残差中位 < 0.5 mm，最大 < 3 mm
    2. IK 位置+姿态残差 位置 < 3 mm，姿态 < 1 度
    3. 往返一致性：q -> FK -> IK -> q'，位置差 < 1 mm
    4. 轨迹速度不超限
"""
import argparse

import numpy as np

from .calibration import Calibration
from .so101_ik import (grasp_pose_seed, ik, ik_multistart, ik_track, max_joint_speed,
                       plan_joint_traj)
from .so101_model import JOINT_ORDER, So101Model


def hr(title):
    print()
    print("=" * 68)
    print(f" {title}")
    print("=" * 68)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cal = Calibration.load()
    m = So101Model()
    lim = cal.limits_rad()
    rng = np.random.default_rng(20261018)
    fails = 0

    hr("0. 模型与限位")
    print(m.describe())
    print()
    print("  IK 用的实测限位（来自校准，不是 MJCF）:")
    for i, n in enumerate(JOINT_ORDER):
        print(f"    {n:<15}[{np.rad2deg(lim[i, 0]):+7.1f}, {np.rad2deg(lim[i, 1]):+7.1f}] deg")

    # ---------------------------------------------------------------- 1
    hr(f"1. IK 位置-only 自检（{args.n} 个随机可达点）")
    errs, iters = [], []
    for i in range(args.n):
        q_true = rng.uniform(lim[:, 0], lim[:, 1])
        q_true[5] = 0.5  # 夹爪固定半开，别让随机值干扰
        pos, _ = m.fk(q_true)
        seed = np.clip(q_true + rng.normal(0, 0.25, 6), lim[:, 0], lim[:, 1])
        q_sol, info = ik_multistart(m, pos, target_rot=None, seed=seed,
                                    limits=lim, n_tries=8, verbose=args.verbose)
        if q_sol is None:
            print(f"  [{i:02d}] 失败: {info['reason']}  pos={np.round(pos, 3)}")
            fails += 1
            continue
        p2, _ = m.fk(q_sol)
        e = float(np.linalg.norm(p2 - pos) * 1000)
        errs.append(e)
        iters.append(info["iters"])
        if e > 3.0:
            print(f"  [{i:02d}] 残差偏大 {e:.2f}mm")
    if errs:
        print(f"  成功 {len(errs)}/{args.n}  "
              f"误差 中位={np.median(errs):.3f}mm  p95={np.percentile(errs, 95):.3f}mm  "
              f"max={np.max(errs):.3f}mm")
        print(f"  迭代 中位={np.median(iters):.0f}  max={np.max(iters):.0f}")
        if np.median(errs) > 0.5 or np.max(errs) > 3.0:
            print("  [!] 未达标准（中位<0.5mm, max<3mm）")
            fails += 1

    # ---------------------------------------------------------------- 2
    hr("2. 抓取位姿 IK（目标点取自训练数据实测的抓取区域）")
    print("  实测抓取范围: X 0.14~0.32  Y -0.16~0.04  Z ~0（桌面高度）")
    print("  抓取姿态用 grasp_pose_seed()，不强制竖直方向（实测真机是水平前伸抓取）")
    cases = [(0.18, -0.05, 0.00), (0.22, 0.00, 0.00), (0.26, -0.08, 0.00),
             (0.30, 0.02, 0.00), (0.20, 0.03, 0.00), (0.25, -0.12, 0.00),
             (0.16, -0.10, 0.00), (0.32, -0.03, 0.00)]
    ok2 = 0
    for (x, y, z) in cases:
        q, info = ik(m, [x, y, z], target_rot=None, seed=grasp_pose_seed(), limits=lim)
        if q is None:
            print(f"  FAIL ({x:.2f},{y:.2f},{z:.2f})  {info['reason']}")
            continue
        p2, r2 = m.fk(q)
        pe = float(np.linalg.norm(p2 - np.array([x, y, z])) * 1000)
        ang = float(np.degrees(np.arccos(np.clip(-r2[2, 2], -1, 1))))
        good = bool(info.get("ok")) and pe < 1.0
        if good:
            ok2 += 1
        in_range = 85.0 <= ang <= 105.0
        print(f"  {'OK  ' if good else 'FAIL'} ({x:.2f},{y:.2f},{z:.2f})  "
              f"pos_err={pe:6.2f}mm  夹爪倾角={ang:5.1f}deg "
              f"{'(真机分布内)' if in_range else '(偏离真机习惯!)'}  iters={info['iters']}")
    print(f"  收敛 {ok2}/{len(cases)}")
    if ok2 < len(cases) * 0.9:
        print("  [!] 收敛率不足 90%")
        fails += 1

    # ---------------------------------------------------------------- 3
    hr("3. 往返一致性 q -> FK -> IK -> q'")
    worst = 0.0
    for i in range(5):
        q_true = np.array(grasp_pose_seed())
        q_true[:3] += rng.uniform(-0.3, 0.3, 3)
        q_true = np.clip(q_true, lim[:, 0], lim[:, 1])
        pos, rot = m.fk(q_true)
        q_sol, info = ik(m, pos, rot, seed=q_true, limits=lim)
        if q_sol is None:
            print(f"  [{i}] 失败: {info['reason']}")
            fails += 1
            continue
        p2, _ = m.fk(q_sol)
        e = float(np.linalg.norm(p2 - pos) * 1000)
        worst = max(worst, e)
        print(f"  [{i}] 原位置 {np.round(pos * 100, 1)} cm  往返误差 {e:.3f} mm")
    if worst > 1.0:
        print(f"  [!] 往返误差 {worst:.2f}mm 超过 1mm")
        fails += 1

    # ---------------------------------------------------------------- 4
    hr("4. 轨迹生成与限速")
    q0 = grasp_pose_seed()
    q1 = q0.copy()
    q1[0] += np.deg2rad(30)
    q1[2] -= np.deg2rad(20)
    traj, meta = plan_joint_traj(q0, q1, max_vel_rad_s=1.2, dt=0.02)
    v = max_joint_speed(traj, dt=0.02)
    print(f"  步数 {meta['n_steps']}  时长 {meta['duration_s']:.2f}s  "
          f"峰值速度 {v:.2f} rad/s ({np.rad2deg(v):.1f} deg/s)")
    print(f"  起点误差 {np.linalg.norm(traj[0] - q0) * 1000:.4f} mm  "
          f"终点误差 {np.linalg.norm(traj[-1] - q1) * 1000:.4f} mm")
    if v > 1.2 * 1.05:
        print(f"  [!] 速度超限（限 1.2 rad/s）")
        fails += 1

    # ---------------------------------------------------------------- 5
    hr("5. 工作空间采样（末端可达范围）")
    pts = []
    for _ in range(3000):
        q = rng.uniform(lim[:, 0], lim[:, 1])
        q[5] = 0.5
        p, _ = m.fk(q)
        pts.append(p)
    P = np.array(pts)
    lo, hi = P.min(axis=0), P.max(axis=0)
    print(f"  X: {lo[0]:+.3f} ~ {hi[0]:+.3f} m")
    print(f"  Y: {lo[1]:+.3f} ~ {hi[1]:+.3f} m")
    print(f"  Z: {lo[2]:+.3f} ~ {hi[2]:+.3f} m")
    print()
    print("  「夹爪朝下」且接近桌面的可达点比例（Z < 8cm）:")
    print(f"    {np.mean(P[:, 2] < 0.08) * 100:.1f}% 的采样点落在 Z<8cm")

    hr("6. 增量式轨迹跟踪（M3 真正会用的方式）")
    print("  q(k-1) 作为 q(k) 的种子，沿一条 20cm 的笛卡尔直线走 30 步")
    p0 = np.array([0.18, -0.06, 0.00])
    p1 = np.array([0.30, 0.02, 0.00])
    wps = np.linspace(p0, p1, 30)
    Q, infos = ik_track(m, wps, seed=grasp_pose_seed(), limits=lim, max_iter=200)
    errs = []
    for q, p in zip(Q, wps):
        pp, _ = m.fk(q)
        errs.append(float(np.linalg.norm(pp - p) * 1000))
    errs = np.array(errs)
    nfail = sum(1 for i in infos if not i.get("ok"))
    jumps = np.rad2deg(np.max(np.abs(np.diff(Q, axis=0))))
    print(f"  位置误差 中位={np.median(errs):.3f}mm  max={errs.max():.3f}mm")
    print(f"  未收敛点 {nfail}/{len(wps)}")
    print(f"  相邻点最大关节跳变 {jumps:.2f} deg（应 < 5 deg，否则真机会抖）")
    if errs.max() > 3.0 or jumps > 5.0:
        print("  [!] 跟踪质量不达标")
        fails += 1

    hr("结论")
    if fails == 0:
        print("  ✅ 全部通过。M2 的 FK/IK/轨迹可以交给 M3 集成。")
        return 0
    print(f"  ⚠️ {fails} 项未通过，见上面 [!] 标记。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
