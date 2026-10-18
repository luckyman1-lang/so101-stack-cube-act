"""探测：夹爪竖直向下时，末端到底能到哪儿？

背景：ik() 位置-only 能到 0.07mm，但一带上"夹爪朝下"的姿态约束就全崩
（pos_err 50~200mm）。先别急着改算法，先确定这个约束下工作空间到底多大。

做法：在实测关节限位内随机采样 30 万个关节构型，用 FK 算 site 的 z 轴，
筛出 z 轴接近 (0,0,-1) 的那些，看它们的末端位置分布。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kin.calibration import Calibration  # noqa: E402
from kin.so101_model import JOINT_ORDER, So101Model  # noqa: E402

N = 200_000

cal = Calibration.load()
m = So101Model()
lim = cal.limits_rad()
rng = np.random.default_rng(7)

print(f"采样 {N} 个构型 ...")
# 关节 6 (gripper) 不影响位置，固定
Q = rng.uniform(lim[:, 0], lim[:, 1], size=(N, 6))
Q[:, 5] = 0.5

pos = np.zeros((N, 3))
zdot = np.zeros(N)   # site z 轴 与 (0,0,-1) 的点积，1 = 完全朝下
zaxis = np.zeros((N, 3))

# 逐个算太慢，这里直接批量写 qpos 循环（6 自由度，MuJoCo 单次 ~10us）
for i in range(N):
    p, r = m.fk(Q[i])
    pos[i] = p
    zaxis[i] = r[:, 2]
    zdot[i] = -r[2, 2]   # r[:,2] · (0,0,-1) = -r[2,2]

print()
print("site z 轴与「竖直向下」的点积分布:")
for th in (0.99, 0.95, 0.90, 0.80, 0.70, 0.50):
    frac = float(np.mean(zdot > th))
    print(f"  >{th:.2f}: {frac * 100:6.2f}%  ({int(frac * N)} 个)")

for th in (0.95, 0.90):
    sel = zdot > th
    if sel.sum() < 100:
        continue
    P = pos[sel]
    print()
    print(f"== 夹爪朝下 (点积>{th}) 的末端可达范围，{int(sel.sum())} 个样本 ==")
    for k, name in enumerate("XYZ"):
        print(f"  {name}: {P[:, k].min():+.3f} ~ {P[:, k].max():+.3f} m "
              f"(p5={np.percentile(P[:, k], 5):+.3f} p95={np.percentile(P[:, k], 95):+.3f})")
    print()
    print("  桌面上方 0~10cm 且朝下的样本数:")
    for zlo, zhi in ((0.0, 0.05), (0.05, 0.10), (0.10, 0.15)):
        band = sel & (pos[:, 2] > zlo) & (pos[:, 2] < zhi)
        print(f"    Z in [{zlo:.2f},{zhi:.2f}): {int(band.sum()):6d} 个 "
              f"({band.sum() / N * 100:.2f}%)")
        if band.sum() > 50:
            B = pos[band]
            print(f"       X {B[:,0].min():+.3f}~{B[:,0].max():+.3f}  "
                  f"Y {B[:,1].min():+.3f}~{B[:,1].max():+.3f}")

# 顺便看：完全竖直向下有多难
best = np.argmax(zdot)
print()
print(f"最接近朝下的构型: 点积={zdot[best]:.4f} "
      f"(={np.rad2deg(np.arccos(np.clip(zdot[best], -1, 1))):.1f} deg 偏离)")
print(f"  位置 {np.round(pos[best], 4)} m")
print("  关节角 (deg):", np.round(np.rad2deg(Q[best]), 1))
