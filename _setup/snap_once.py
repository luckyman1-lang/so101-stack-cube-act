"""交互式连拍：摆好绿块后按回车拍一张，自动编号，不会互相覆盖。

必须【管理员身份】的 PowerShell 运行（Orbbec 相机需要提权）。

用法：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\snap_once.py"
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\snap_once.py" 1   # 指定索引

流程：
    1. 相机保持打开，终端显示提示
    2. 你摆好一个位置 → 按回车 → 拍一张
    3. 换位置 → 再按回车 → 拍下一张
    4. 输入 q 回车退出

照片存到 _setup\\cam_snapshots\\layout_01.png, layout_02.png ...
"""

import os
import sys

import cv2

INDEX = int(sys.argv[1]) if len(sys.argv) > 1 else 1
OUT_DIR = r"D:\LeRobot\_setup\cam_snapshots"


def next_index() -> int:
    """找一个还没被占用的编号。"""
    i = 1
    while os.path.exists(os.path.join(OUT_DIR, f"layout_{i:02d}.png")):
        i += 1
    return i


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    cap = cv2.VideoCapture(INDEX, cv2.CAP_DSHOW)
    try:
        if not cap.isOpened():
            print(f"✗ 打不开索引 {INDEX}")
            print("  1) Orbbec 需要管理员权限，请用管理员身份运行")
            print("  2) 索引可能变了，跑 _setup\\preview_cameras.py 确认")
            return 1

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # 预热：让自动曝光稳定下来
        for _ in range(15):
            cap.read()

        n = next_index()
        print(f"相机已打开（索引 {INDEX}）。照片会从 layout_{n:02d}.png 开始编号。")
        print("摆好绿块 → 按回车拍照；输入 q 退出。")
        print()

        while True:
            try:
                cmd = input(f"[第 {n} 张] 摆好后按回车拍照，输入 q 退出: ").strip()
            except EOFError:
                break
            if cmd.lower() in ("q", "quit", "exit"):
                break

            for _ in range(8):      # 丢帧，等曝光/画面稳定
                cap.read()
            ok, frame = cap.read()
            if not ok or frame is None:
                print("  ✗ 读帧失败，再试一次")
                continue

            path = os.path.join(OUT_DIR, f"layout_{n:02d}.png")
            cv2.imwrite(path, frame)
            print(f"  ✔ 已保存 {os.path.basename(path)}  均值={frame.mean():.1f}")
            n += 1

        print()
        print("已退出。把 _setup\\cam_snapshots 里新生成的 layout_*.png 告诉我就行。")
        return 0
    finally:
        cap.release()


if __name__ == "__main__":
    sys.exit(main())
