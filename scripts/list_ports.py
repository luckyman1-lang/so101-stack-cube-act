"""列出 Windows 串口 / 识别机械臂端口 / 扫描摄像头索引。

用法：
    python list_ports.py              # 只列出当前串口
    python list_ports.py --watch      # 交互：拔掉一根 USB，自动告诉你那是哪个口
    python list_ports.py --cams       # 扫描摄像头索引 0..5（与 LeRobot 相同的 MSMF 后端）
    python list_ports.py --cams --snapshot   # 顺便各存一张图，方便确认哪个是前置相机
"""

import argparse
import os
import sys
import time

SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_setup", "cam_snapshots")


def serial_snapshot() -> dict:
    from serial.tools import list_ports

    return {p.device: (p.description or "", p.hwid or "") for p in list_ports.comports()}


def _port_num(dev: str) -> int:
    digits = "".join(ch for ch in dev if ch.isdigit())
    return int(digits) if digits else 0


def show_serial(snap: dict) -> None:
    if not snap:
        print("  （没有检测到任何串口）")
        return
    for dev in sorted(snap, key=_port_num):
        desc, _hwid = snap[dev]
        print(f"  {dev:<8} {desc}")


def cmd_list() -> int:
    print("当前串口：")
    show_serial(serial_snapshot())
    print("\n提示：如果两个机械臂都插着，先拔掉一个再运行 --watch，就能知道哪个是哪个。")
    return 0


def cmd_watch() -> int:
    before = serial_snapshot()
    print("当前串口：")
    show_serial(before)
    if not before:
        print("\n现在一个串口都没有。请先插上机械臂 USB 再运行本命令。")
        return 0

    input("\n拔掉【其中一个】机械臂的 USB 线，然后按回车继续...")
    time.sleep(1.2)
    after = serial_snapshot()
    gone = sorted(set(before) - set(after), key=_port_num)

    print()
    if len(gone) == 1:
        dev = gone[0]
        print(f">>> 刚拔掉的是：{dev}   （{before[dev][0]}）")
        print("    记到 config\\robot.ini 里（从臂填 [robot] port，主臂填 [teleop] port）。")
    elif not gone:
        print(">>> 没检测到变化。可能拔错了线，或者系统还没刷新，请重插后再试一次。")
    else:
        print(f">>> 同时消失了多个串口：{gone}")
        print("    可能有别的串口设备也断了，请一次只拔一根。")

    print("\n（插回 USB 后可重新运行本脚本查看全部串口）")
    return 0


def cmd_cams(max_index: int, snapshot: bool) -> int:
    try:
        import cv2
    except Exception as e:  # pragma: no cover
        print(f"打不开 OpenCV：{e}")
        return 1

    backend = cv2.CAP_MSMF if sys.platform == "win32" else cv2.CAP_ANY
    print(f"扫描摄像头索引 0..{max_index - 1}（后端 {cv2.videoio_registry.getBackendName(backend)}，与 LeRobot 一致）\n")

    found = []
    out_dir = None
    if snapshot:
        out_dir = os.path.abspath(SNAP_DIR)
        os.makedirs(out_dir, exist_ok=True)

    for i in range(max_index):
        cap = cv2.VideoCapture(i, backend)
        try:
            if not cap.isOpened():
                print(f"  [{i}] 不可用")
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                print(f"  [{i}] 能打开但读不到画面（可能被其它程序占用）")
                continue
            h, w = frame.shape[:2]
            print(f"  [{i}] 可用   分辨率 {w}x{h}")
            found.append(i)
            if out_dir:
                path = os.path.join(out_dir, f"cam_{i}.jpg")
                cv2.imwrite(path, frame)
                print(f"        已存快照：{path}")
        finally:
            cap.release()

    print()
    if found:
        print(f"可用索引：{found}")
        print("把前置相机填到 config\\robot.ini 的 [cameras] front_index。")
        if snapshot:
            print(f"打开 {out_dir} 看图片，确认哪个索引对着桌面。")
    else:
        print("没有可用摄像头。检查：USB 是否插好 / 是否被其它程序（会议软件等）占用。")
    # 探测本身成功就算成功（"没找到"是正常结果，不该让调用方以为脚本崩了）
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="串口与摄像头探测工具")
    ap.add_argument("--watch", action="store_true", help="交互识别刚拔掉的是哪个串口")
    ap.add_argument("--cams", action="store_true", help="扫描摄像头索引")
    ap.add_argument("--max-index", type=int, default=6, help="扫描的摄像头索引上限（默认 6）")
    ap.add_argument("--snapshot", action="store_true", help="给每个可用摄像头存一张快照")
    args = ap.parse_args()

    if args.cams:
        return cmd_cams(args.max_index, args.snapshot)
    if args.watch:
        return cmd_watch()
    return cmd_list()


if __name__ == "__main__":
    sys.exit(main())
