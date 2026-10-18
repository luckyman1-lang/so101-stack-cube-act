"""用训练数据反推：真机抓取时，夹爪到底有多"竖直"？

这比任何理论推导都可靠。做法：
  1. 读 stack_cube_v2 的 parquet，取 observation.state（真机真实关节读数）
  2. 用校准换算成弧度
  3. 用 MuJoCo FK 算末端位置和 site 的 z 轴
  4. 统计 z 轴与「竖直向下」的夹角、末端轨迹范围

如果真机的倾斜角本来就很大（比如 30~45 deg），那 IK 里就不该强求 0 deg，
M3 的姿态约束应该按数据来定，而不是拍脑袋。
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kin.calibration import Calibration  # noqa: E402
from kin.so101_model import JOINT_ORDER, So101Model  # noqa: E402

cal = Calibration.load()
m = So101Model()

files = sorted(glob.glob(r"D:\LeRobot\datasets\stack_cube_v2\data\**\*.parquet", recursive=True))
print(f"episodes: {len(files)}")

# 取前 8 个 episode 看统计
sample = files[:8]
allP = []
allZ = []
allQ = []
for f in sample:
    df = pd.read_parquet(f)
    S = np.stack(df["observation.state"].values)
    for s in S:
        q = cal.norm_vec_to_rad(s)
        p, r = m.fk(q)
        allP.append(p)
        allZ.append(r[:, 2])
        allQ.append(q)

P = np.array(allP)
Z = np.array(allZ)
Q = np.array(allQ)
print(f"样本帧数: {len(P)}")

dots = -Z[:, 2]  # z 轴 · (0,0,-1)
ang = np.degrees(np.arccos(np.clip(dots, -1.0, 1.0)))

print()
print("== site z 轴与「竖直向下」的夹角（0 = 完全朝下）==")
for name, v in (("min", ang.min()), ("p5", np.percentile(ang, 5)),
                ("中位", np.median(ang)), ("p95", np.percentile(ang, 95)),
                ("max", ang.max())):
    print(f"  {name:<6}{v:7.1f} deg")

print()
print("  夹角 < 15 deg 的帧占比: %.1f%%" % (np.mean(ang < 15) * 100))
print("  夹角 < 30 deg 的帧占比: %.1f%%" % (np.mean(ang < 30) * 100))
print("  夹角 < 45 deg 的帧占比: %.1f%%" % (np.mean(ang < 45) * 100))

print()
print("== 末端位置范围（基座坐标系，米）==")
for k, name in enumerate("XYZ"):
    print(f"  {name}: {P[:, k].min():+.3f} ~ {P[:, k].max():+.3f} "
          f"(p5={np.percentile(P[:, k], 5):+.3f}, p95={np.percentile(P[:, k], 95):+.3f})")

print()
print("== 每个 episode 的末端轨迹跨度 ==")
idx = 0
for f in sample[:5]:
    df = pd.read_parquet(f)
    S = np.stack(df["observation.state"].values)
    Ps = []
    for s in S:
        q = cal.norm_vec_to_rad(s)
        p, _ = m.fk(q)
        Ps.append(p)
    Ps = np.array(Ps)
    span = Ps.max(0) - Ps.min(0)
    print(f"  {os.path.basename(f)[:12]}  {len(S):4d} 帧  "
          f"起点 {np.round(Ps[0] * 100, 1)}  终点 {np.round(Ps[-1] * 100, 1)}  "
          f"跨度 {np.round(span * 100, 1)} cm")
    idx += 1

print()
print("== 关节角实际使用范围（度）==")
print("%-15s%10s%10s%10s" % ("joint", "min", "max", "span"))
print("-" * 45)
for i, n in enumerate(JOINT_ORDER):
    lo = np.rad2deg(Q[:, i].min())
    hi = np.rad2deg(Q[:, i].max())
    print("%-15s%10.1f%10.1f%10.1f" % (n, lo, hi, hi - lo))

# 抓取瞬间：末端 Z 最低的那些帧
lowz = np.argsort(P[:, 2])[:200]
print()
print("== 末端最低的 200 帧（≈抓取/放置时刻）的姿态 ==")
print(f"  Z 范围 {P[lowz, 2].min():.3f} ~ {P[lowz, 2].max():.3f} m")
print(f"  z 轴倾角 中位 {np.median(ang[lowz]):.1f} deg  "
      f"p5 {np.percentile(ang[lowz], 5):.1f}  p95 {np.percentile(ang[lowz], 95):.1f}")
print(f"  X 范围 {P[lowz, 0].min():.3f} ~ {P[lowz, 0].max():.3f}")
print(f"  Y 范围 {P[lowz, 1].min():.3f} ~ {P[lowz, 1].max():.3f}")
