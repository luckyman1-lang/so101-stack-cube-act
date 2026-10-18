"""探测从臂 wrist_flex 的真实物理范围（对比校准文件）。

用法（管理员 PowerShell）：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\probe_range.py"

流程：
    1. 脚本先关闭所有舵机的扭矩（这样你才能用手推动机械臂）
    2. 提示你把 wrist_flex 推到【一个方向的物理极限】→ 回车
    3. 提示你推到【另一个方向的物理极限】→ 回车
    4. 打印真实范围，并和校准文件对比，给出建议

⚠ 关闭扭矩后机械臂会失去支撑，请先用手扶住！
"""

import sys

MOTOR = "wrist_flex"


def main() -> int:
    from lerobot.robots.so101_follower.so101_follower import SO101Follower, SO101FollowerConfig

    dev = SO101Follower(SO101FollowerConfig(port="COM11", id="my_follower"))
    try:
        dev.bus.connect()
    except Exception as e:
        print(f"✗ 连不上从臂: {type(e).__name__}: {str(e)[:120]}")
        print("  检查：从臂 5V 电源、USB 线、是否有其他程序占着 COM11")
        return 1

    try:
        cal = dev.bus.calibration.get(MOTOR)
        print("=" * 64)
        print(f"  目标关节: {MOTOR}")
        if cal:
            print(f"  校准文件范围: {cal.range_min} ~ {cal.range_max}  (跨度 {cal.range_max - cal.range_min})")
        else:
            print("  ⚠ 校准文件里没有这个关节")
        print("=" * 64)
        print()
        print("⚠ 即将关闭所有舵机扭矩 —— 机械臂会失去支撑，请先用手扶住！")
        input("准备好后按回车继续...")

        for m in dev.bus.motors:
            dev.bus.write("Torque_Enable", m, 0, normalize=False)
        print("✔ 扭矩已全部关闭，机械臂现在是软的。")
        print()

        input(f"请把 {MOTOR} 推到【一个方向的物理极限】（有阻力就停，别硬顶），然后按回车: ")
        a = dev.bus.read("Present_Position", MOTOR, normalize=False)
        print(f"  记录位置 A = {a}")
        print()

        input(f"请把 {MOTOR} 推到【另一个方向的物理极限】，然后按回车: ")
        b = dev.bus.read("Present_Position", MOTOR, normalize=False)
        print(f"  记录位置 B = {b}")
        print()

        lo, hi = min(a, b), max(a, b)
        print("=" * 64)
        print(f"  实测物理范围 : {lo} ~ {hi}   (跨度 {hi - lo})")
        if cal:
            print(f"  校准文件范围 : {cal.range_min} ~ {cal.range_max}   (跨度 {cal.range_max - cal.range_min})")
        print("=" * 64)

        if cal:
            need_lo = lo < cal.range_min - 20
            need_hi = hi > cal.range_max + 20
            if need_lo or need_hi:
                print()
                print("→ 实测范围比校准文件【大】，说明校准时没推到头。")
                print(f"   建议把范围改成: {max(lo, 0)} ~ {min(hi, 4095)}")
                print("   （我可以帮你写进舵机；或者重新校准一次）")
            else:
                print()
                print("→ 实测范围和校准文件基本一致。")
                print("   那'卡住'就是正常到了物理极限，操作时别推过头即可。")
        print()
        print("完成后可直接关闭窗口（会自动断开并保持扭矩关闭）。")
        return 0
    finally:
        try:
            dev.bus.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
