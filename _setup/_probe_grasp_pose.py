"""验证：用「真实抓取构型」做种子 + 只约束位置的 IK，能否复现真机姿态？

背景（被数据打脸的地方）：
  最初假设抓取是"夹爪竖直向下"，于是 IK 里约束 site z 轴 = -Z。
  但用训练数据做 FK 反推后发现，真机抓取时 site z 轴与竖直向下的夹角
  **中位 95 度**（几乎水平），而且 0% 的帧落在 45 度以内。
  也就是说 SO-101 是**水平前伸**抓取的，竖直向下这个约束根本不在它的
  正常姿态空间里 —— 这才是姿态 IK 怎么调都差 15~50 度的真因。

于是换个思路：
  1. 从数据集里挑出"抓取时刻"（末端 Z 最低）的关节构型，当种子
  2. IK 只约束位置（3 维），让 DLS 在种子附近找最小关节变化解
  3. 检查解出的姿态是否落在真机姿态分布内
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kin.calibration import Calibration  # noqa: E402
from kin.so101_ik import ik  # noqa: E402
from kin.so101_model import JOINT_ORDER, So101Model  # noqa: E402

cal = Calibration.load()
m = So101Model()
lim = cal.limits_rad()
rng = np.random.default_rng(0)

files = sorted(glob.glob(r"D:\LeRobot\datasets\stack_cube_v2\data\**\*.parquet", recursive=True))

# ---------------------------------------------------------------- 提取抓取构型
grasp_q, grasp_p, grasp_ang = [], [], []
for f in files[:20]:
    df = pd.read_parquet(f)
    S = np.stack(df["observation.state"].values)
    qs, ps = [], []
    for s in S:
        q = cal.norm_vec_to_rad(s)
        p, r = m.fk(q)
        qs.append(q)
        ps.append(p)
    qs = np.array(qs)
    ps = np.array(ps)
    # 末端最低的 8 帧 ≈ 抓取/放置
    low = np.argsort(ps[:, 2])[:8]
    for i in low:
        q = qs[i]
        _, r = m.fk(q)
        grasp_q.append(q)
        grasp_p.append(ps[i])
        grasp_ang.append(np.degrees(np.arccos(np.clip(-r[2, 2], -1, 1))))

GQ = np.array(grasp_q)
GP = np.array(grasp_p)
GA = np.array(grasp_ang)
print(f"提取到 {len(GQ)} 个抓取时刻构型")
print(f"  末端位置: X {GP[:,0].min():.3f}~{GP[:,0].max():.3f}  "
      f"Y {GP[:,1].min():.3f}~{GP[:,1].max():.3f}  "
      f"Z {GP[:,2].min():.3f}~{GP[:,2].max():.3f}")
print(f"  z 轴倾角: 中位 {np.median(GA):.1f} deg  "
      f"p5 {np.percentile(GA,5):.1f}  p95 {np.percentile(GA,95):.1f}")
print()
print("  抓取构型的关节角中位数 (deg):")
med_q = np.median(GQ, axis=0)
for i, n in enumerate(JOINT_ORDER):
    print(f"    {n:<15}{np.rad2deg(med_q[i]):+8.1f}")

# ---------------------------------------------------------------- 复现测试
print()
print("=" * 62)
print(" 用抓取构型做种子，位置-only IK 复现")
print("=" * 62)

ok = 0
errs, ang_diffs, q_diffs = [], [], []
N = 60
for t in range(N):
    idx = rng.integers(0, len(GQ))
    q_ref = GQ[idx].copy()
    p_ref = GP[idx].copy()
    # 种子 = 真值 + 噪声（模拟"从别处过来"）
    seed = np.clip(q_ref + rng.normal(0, 0.12, 6), lim[:, 0], lim[:, 1])
    q_sol, info = ik(m, p_ref, target_rot=None, seed=seed, limits=lim,
                     max_iter=400, lam=0.05)
    if q_sol is None:
        continue
    p2, r2 = m.fk(q_sol)
    e = np.linalg.norm(p2 - p_ref) * 1000
    errs.append(e)
    _, r_ref = m.fk(q_ref)
    a_sol = np.degrees(np.arccos(np.clip(-r2[2, 2], -1, 1)))
    a_ref = np.degrees(np.arccos(np.clip(-r_ref[2, 2], -1, 1)))
    ang_diffs.append(abs(a_sol - a_ref))
    q_diffs.append(float(np.rad2deg(np.linalg.norm(q_sol - q_ref))))
    if e < 1.0:
        ok += 1

print(f"  位置收敛(<1mm): {ok}/{N}")
print(f"  位置误差      中位 {np.median(errs):.3f} mm  max {np.max(errs):.3f} mm")
print(f"  姿态角差      中位 {np.median(ang_diffs):.2f} deg  "
      f"p95 {np.percentile(ang_diffs, 95):.2f} deg")
print(f"  关节角差      中位 {np.median(q_diffs):.1f} deg")

# ---------------------------------------------------------------- 沿数据轨迹走
print()
print("=" * 62)
print(" 沿真实轨迹逐点 IK（模拟 M3 的轨迹跟踪）")
print("=" * 62)
df = pd.read_parquet(files[0])
S = np.stack(df["observation.state"].values)[::20]  # 抽稀
prev = None
worst = 0.0
fail = 0
for k, s in enumerate(S):
    q_ref = cal.norm_vec_to_rad(s)
    p_ref, _ = m.fk(q_ref)
    seed = prev if prev is not None else q_ref
    q_sol, info = ik(m, p_ref, target_rot=None, seed=seed, limits=lim,
                     max_iter=200, lam=0.05)
    if q_sol is None:
        fail += 1
        continue
    p2, _ = m.fk(q_sol)
    e = np.linalg.norm(p2 - p_ref) * 1000
    worst = max(worst, e)
    prev = q_sol
print(f"  跟踪 {len(S)} 个点，失败 {fail}，最大位置误差 {worst:.2f} mm")
print(f"  （用上一帧解做下一帧种子 = 增量式 IK，这是真机在线跑的正确方式）")
