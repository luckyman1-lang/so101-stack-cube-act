"""调试：带姿态约束的 IK 为什么不收敛？

对最接近成功的那个目标点 (0.28, 0, 0.08) 扫参数：
  位置误差单位是米（1e-2 量级），旋转误差单位是弧度（1e-1 量级），
  两者量纲不同，DLS 里必须分别加权，否则旋转会压过位置。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kin.calibration import Calibration  # noqa: E402
from kin.so101_ik import typical_down_seed  # noqa: E402
from kin.so101_model import So101Model, rot_err_world  # noqa: E402

m = So101Model()
cal = Calibration.load()
lim = cal.limits_rad()
R_down = m.gripper_down_rot(0.0)

TARGETS = [(0.28, 0.0, 0.08), (0.25, 0.05, 0.05), (0.20, 0.0, 0.03)]


def ik_custom(target, q0, lam, step, wp, wr, iters=900):
    target = np.asarray(target, dtype=float)
    q = np.clip(q0.copy(), lim[:, 0], lim[:, 1])
    for _ in range(iters):
        pos, rot = m.fk(q)
        ep = (target - pos)
        er_raw = rot_err_world(rot, R_down)
        if np.linalg.norm(ep) < 1e-4 and np.linalg.norm(er_raw) < 2e-3:
            break
        jacp, jacr = m.jacobian(q)
        J = np.vstack([jacp * wp, jacr * wr])
        e = np.concatenate([ep * wp, er_raw * wr])
        JJt = J @ J.T + (lam ** 2) * np.eye(6)
        try:
            dq = J.T @ np.linalg.solve(JJt, e)
        except np.linalg.LinAlgError:
            break
        s = float(np.max(np.abs(dq)))
        if s > step:
            dq *= step / s
        q = np.clip(q + dq, lim[:, 0], lim[:, 1])
    pos, rot = m.fk(q)
    return (np.linalg.norm(target - pos) * 1000,
            np.rad2deg(np.linalg.norm(rot_err_world(rot, R_down))))


print("目标 (0.28, 0.00, 0.08)，初值 = typical_down_seed")
print("%-8s%-8s%-8s%-14s" % ("lam", "wp", "wr", "结果"))
print("-" * 40)
best = None
for lam in (0.02, 0.05, 0.12, 0.3):
    for wp, wr in ((1.0, 0.02), (1.0, 0.1), (1.0, 0.3), (1.0, 1.0), (1.0, 3.0)):
        pe, re = ik_custom(TARGETS[0], typical_down_seed(), lam, 0.3, wp, wr)
        flag = "OK" if (pe < 1.0 and re < 0.5) else ""
        print("%-8.2f%-8.2f%-8.2f%8.2fmm %7.2fdeg %s" % (lam, wp, wr, pe, re, flag))
        if best is None or (pe + re * 5) < best[0]:
            best = (pe + re * 5, lam, wp, wr, pe, re)

print()
print("最佳:", "lam=%.2f wp=%.1f wr=%.2f -> %.2fmm %.2fdeg"
      % (best[1], best[2], best[3], best[4], best[5]))
lam, wp, wr = best[1], best[2], best[3]

print()
print("用最佳参数跑三个目标:")
for t in TARGETS:
    pe, re = ik_custom(t, typical_down_seed(), lam, 0.3, wp, wr)
    print("  %s -> pos_err=%7.2fmm rot_err=%6.2fdeg" % (str(t), pe, re))

print()
print("同一目标、多个随机初值（限位内均匀）:")
rng = np.random.default_rng(0)
for t in TARGETS:
    ok = 0
    best_pe = np.inf
    for _ in range(30):
        q0 = rng.uniform(lim[:, 0], lim[:, 1])
        q0[5] = 0.5
        pe, re = ik_custom(t, q0, lam, 0.3, wp, wr)
        best_pe = min(best_pe, pe)
        if pe < 1.0 and re < 0.5:
            ok += 1
    print("  %s -> 成功 %d/30, 最佳 pos_err=%.2fmm" % (str(t), ok, best_pe))
