"""LeRobot 归一化关节值 <-> MuJoCo 弧度 的精确换算。

## 为什么不能直接用 MJCF 的关节 range

MJCF 里的关节范围来自 CAD 理论值，而真机行程是**校准实测**的。用本机校准
文件换算出来的真实角度对比 MJCF：

    关节            校准跨度(编码)   换算角度      MJCF 范围      差异
    shoulder_pan      2526          ±111.0 deg    ±110.0 deg    1 deg
    shoulder_lift     2366          ±104.0 deg    ±100.0 deg    4 deg   <-- 要命
    elbow_flex        2202           ±96.8 deg     ±96.8 deg    0 deg
    wrist_flex        2151           ±94.5 deg     ±95.0 deg    0.5 deg
    wrist_roll        3814          ±167.6 deg   -157~163 deg   10 deg
    gripper           1433           ±63.0 deg    -10~100 deg    73 deg  <-- 完全不一致

`shoulder_lift` 差 4 度，在 20cm 臂展上约等于 **14mm 末端位置误差**，直接
把 IK 的 3mm 目标打破。所以：

  * **弧度换算只用校准数据**（range_min/range_max），
  * **MJCF 只提供连杆几何**（FK），不参与关节数值换算，
  * IK 的关节限位用校准算出的实测范围，不用 MJCF 的 range。

## 归一化约定（来自 lerobot/motors/motors_bus.py）

    RANGE_M100_100（5 个臂关节）:  norm in [-100, 100] -> 编码 [range_min, range_max]
    RANGE_0_100   （gripper）   :  norm in [0, 100]    -> 编码 [range_min, range_max]

    归一化 0  <->  编码中点 (range_min+range_max)/2  <->  MJCF 弧度 0
    （因为 LeRobot 的"新校准"把虚拟零位设在行程中点，与 MJCF new_calib 一致）

## 已知不一致

gripper 的 MJCF 关节范围（-10~100 deg）和真机舵机行程（±63 deg）差 73 度。
这不影响 IK（夹爪不参与位置），但**在 MuJoCo 里做仿真时夹爪开合会看得不对**。
M4 建仿真时必须重新标夹爪连杆，或者接受它只是个近似。
"""
import json
import os

import numpy as np

ENCODER_BITS = 4096
TWO_PI = 2.0 * np.pi

_THIS = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(os.path.dirname(_THIS), "config", "calibration_follower.json")


class Calibration:
    """从臂校准表。负责 归一化值 <-> 弧度 的双向换算。"""

    def __init__(self, data: dict):
        self.raw = data
        self.joint_order: list[str] = list(data["joint_order"])
        self.joints: dict = data["joints"]
        self.encoder_bits = int(data.get("encoder_bits", ENCODER_BITS))
        # 每个关节的编码中点与跨度
        self.mid = {}
        self.span = {}
        for name, j in self.joints.items():
            rmin = float(j["range_min"])
            rmax = float(j["range_max"])
            if rmax == rmin:
                raise ValueError(f"{name}: range_min == range_max，校准无效")
            self.mid[name] = (rmin + rmax) / 2.0
            self.span[name] = rmax - rmin

    # ---------------------------------------------------------------- 载入
    @classmethod
    def load(cls, path: str = DEFAULT_PATH) -> "Calibration":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    # ---------------------------------------------------------------- 换算
    def norm_to_enc(self, joint: str, norm: float) -> float:
        """归一化值 -> 舵机编码（浮点）。"""
        mode = self.joints[joint].get("norm_mode", "m100_100")
        if mode == "0_100":
            n = float(np.clip(norm, 0.0, 100.0))
            return self.mid[joint] - self.span[joint] / 2.0 + n / 100.0 * self.span[joint]
        n = float(np.clip(norm, -100.0, 100.0))
        return self.mid[joint] + n / 100.0 * (self.span[joint] / 2.0)

    def norm_to_rad(self, joint: str, norm: float) -> float:
        """归一化值 -> 弧度（相对行程中点）。"""
        enc = self.norm_to_enc(joint, norm)
        return (enc - self.mid[joint]) * TWO_PI / self.encoder_bits

    def rad_to_norm(self, joint: str, rad: float) -> float:
        """弧度 -> 归一化值。"""
        enc = self.mid[joint] + rad * self.encoder_bits / TWO_PI
        mode = self.joints[joint].get("norm_mode", "m100_100")
        if mode == "0_100":
            return (enc - (self.mid[joint] - self.span[joint] / 2.0)) / self.span[joint] * 100.0
        return (enc - self.mid[joint]) / (self.span[joint] / 2.0) * 100.0

    # ---------------------------------------------------------------- 批量
    def norm_vec_to_rad(self, norm_vec) -> np.ndarray:
        """6 维归一化 -> 6 维弧度（按 joint_order）。"""
        v = np.asarray(norm_vec, dtype=np.float64).reshape(-1)
        if v.size != len(self.joint_order):
            raise ValueError(f"期望 {len(self.joint_order)} 维，得到 {v.size}")
        return np.array([self.norm_to_rad(j, v[i])
                         for i, j in enumerate(self.joint_order)], dtype=np.float64)

    def rad_vec_to_norm(self, rad_vec) -> np.ndarray:
        v = np.asarray(rad_vec, dtype=np.float64).reshape(-1)
        return np.array([self.rad_to_norm(j, v[i])
                         for i, j in enumerate(self.joint_order)], dtype=np.float64)

    # ---------------------------------------------------------------- 限位
    def limits_rad(self) -> np.ndarray:
        """(6,2) 实测关节限位，弧度。IK 用这个，不用 MJCF 的 range。"""
        out = []
        for j in self.joint_order:
            lo = self.norm_to_rad(j, 0.0) if self.joints[j].get("norm_mode") == "0_100" \
                else self.norm_to_rad(j, -100.0)
            hi = self.norm_to_rad(j, 100.0)
            out.append((min(lo, hi), max(lo, hi)))
        return np.array(out, dtype=np.float64)

    # ---------------------------------------------------------------- 报告
    def report(self) -> str:
        lines = []
        lines.append(f"{'joint':<15}{'span(enc)':>10}{'deg':>9}{'rad':>9}"
                     f"{'mid(enc)':>10}{'norm0(enc)':>12}")
        lines.append("-" * 66)
        for j in self.joint_order:
            sp = self.span[j]
            deg = sp / self.encoder_bits * 360.0
            lines.append(f"{j:<15}{sp:>10.0f}{deg:>9.1f}"
                         f"{np.deg2rad(deg):>9.3f}{self.mid[j]:>10.1f}{self.mid[j]:>12.1f}")
        lim = self.limits_rad()
        lines.append("")
        lines.append("IK 用实测限位 (rad):")
        for i, j in enumerate(self.joint_order):
            lines.append(f"  {j:<15}[{lim[i,0]:+.4f}, {lim[i,1]:+.4f}]  "
                         f"({np.rad2deg(lim[i,0]):+.1f} deg, {np.rad2deg(lim[i,1]):+.1f} deg)")
        return "\n".join(lines)


# -------------------------------------------------------------------- 便捷函数
def gripper_norm_to_rad_open_close(norm: float, cal: Calibration) -> float:
    """LeRobot 夹爪归一化（0=闭合, 100=全开）-> 弧度（真机口径）。"""
    return cal.norm_to_rad("gripper", norm)


def gripper_norm_to_mjcf(norm: float) -> float:
    """LeRobot 夹爪归一化 -> MJCF gripper 关节弧度。

    ⚠️ 只用于**仿真显示**。MJCF 的 gripper 范围是 -0.17453~1.74533 rad，
    和真机舵机行程（±1.1 rad）差了 73 度，两者不可互算，这里只做线性近似。
    """
    return -0.17453 + (float(np.clip(norm, 0, 100)) / 100.0) * (1.74533 + 0.17453)


if __name__ == "__main__":
    cal = Calibration.load()
    print(cal.report())
    print()
    print("自检：几个关键点往返换算")
    tests = [("shoulder_lift", 0.0), ("shoulder_lift", 100.0), ("shoulder_lift", -100.0),
             ("wrist_flex", 80.0), ("gripper", 0.0), ("gripper", 100.0)]
    for j, n in tests:
        r = cal.norm_to_rad(j, n)
        n2 = cal.rad_to_norm(j, r)
        print(f"  {j:<15} norm={n:>7.1f} -> rad={r:+.4f} ({np.rad2deg(r):+.1f} deg) "
              f"-> norm={n2:>7.2f}")
