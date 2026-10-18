"""单独测试从臂舵机 4（wrist_flex）能否正常运动。

用法（管理员 PowerShell）：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\test_motor4.py"

会做这些：
    1. 连接从臂，确认只让 wrist_flex 使能
    2. 依次发送几个目标位置（在校准范围内），读回实际位置
    3. 判断舵机是否真的在动、有没有卡住/保护

⚠ 测试会让 wrist_flex 运动，请确保周围没有障碍物、手离开该关节！
"""

import sys
import time

MOTOR = "wrist_flex"
TARGETS = [2400, 2000, 2600, 2200, 2500]


def main() -> int:
    import serial

    for port in ("COM10", "COM11"):
        try:
            s = serial.Serial(port, 1000000, timeout=0.1)
            s.close()
        except Exception:
            print(f"✗ {port} 被占用 —— 请先关掉遥操作/录制程序")
            return 1

    from lerobot.robots.so101_follower.so101_follower import SO101Follower, SO101FollowerConfig

    dev = SO101Follower(SO101FollowerConfig(port="COM11", id="my_follower"))
    dev.bus.connect()

    try:
        cal = dev.bus.calibration.get(MOTOR)
        if cal:
            print(f"校准范围: {cal.range_min} ~ {cal.range_max}")
        print()

        # 只让目标舵机使能，其余保持关闭（避免整臂乱动）
        for m in dev.bus.motors:
            dev.bus.write("Torque_Enable", m, 1 if m == MOTOR else 0, normalize=False)
        time.sleep(0.3)

        start = dev.bus.read("Present_Position", MOTOR, normalize=False)
        temp = dev.bus.read("Present_Temperature", MOTOR, normalize=False)
        load0 = dev.bus.read("Present_Load", MOTOR, normalize=False)
        print(f"起始位置: {start}   温度 {temp}   负载(raw) {load0}")
        print()
        print(f"{'目标':>6}{'实际':>8}{'偏差':>8}{'负载%':>8}{'温度':>7}  结论")
        print("-" * 58)

        moved = 0
        for t in TARGETS:
            dev.bus.write("Goal_Position", MOTOR, t, normalize=False)
            time.sleep(0.9)
            pos = dev.bus.read("Present_Position", MOTOR, normalize=False)
            temp = dev.bus.read("Present_Temperature", MOTOR, normalize=False)
            load = dev.bus.read("Present_Load", MOTOR, normalize=False)
            load_pct = abs(load & 0x3FF) / 10.24
            delta = pos - t
            if abs(delta) <= 30:
                verdict = "✔ 到位"
                moved += 1
            elif abs(delta) < 200:
                verdict = "△ 差一点"
            else:
                verdict = "✗ 没动/被限位"
            print(f"{t:>6}{pos:>8}{delta:>8}{load_pct:>7.1f}%{temp:>7}  {verdict}")

        print()
        print("=" * 58)
        if moved == len(TARGETS):
            print(f"  ✔ {MOTOR} 能正常跟随所有目标 → 舵机硬件没问题")
            print("     那'卡住'的原因在范围限制或主从差异，不是舵机坏")
        elif moved == 0:
            print(f"  ✗ {MOTOR} 完全不动 → 舵机可能故障 / 被限位 / 通信失败")
        else:
            print(f"  △ {MOTOR} 部分目标没到位（{moved}/{len(TARGETS)}）→ 可能是局部卡阻或负载过大")
        print("=" * 58)
        return 0
    finally:
        # 断开时 disable_torque（配置里为 True），机械臂会松下来
        try:
            dev.bus.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
