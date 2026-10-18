"""逐个索引拍快照，用来确认哪个索引对应哪个摄像头。

背景：之前误把「索引 0」当成 Orbbec，实际它是笔记本内置摄像头。
索引号是 Windows 按枚举顺序分配的，必须靠画面内容或插拔法区分。

用法（建议【管理员身份】运行，因为 Orbbec 需要提权）：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\snap_indices.py"
"""

import os
import sys

import cv2

OUT_DIR = r"D:\LeRobot\_setup\cam_snapshots"
MAX_INDEX = 8


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    print("逐个索引拍快照（DSHOW 后端）...")
    print("判读方法：画面里若是【桌面 + 机械臂】→ 那是 Orbbec；若是【人脸】→ 笔记本内置摄像头")
    print()

    found = []
    for i in range(MAX_INDEX):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        try:
            if not cap.isOpened():
                print(f"  索引 {i}: 打不开")
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            for _ in range(6):
                cap.read()
            ok, frame = cap.read()
            if not ok or frame is None:
                print(f"  索引 {i}: 打开但读不到帧")
                continue
            h, w = frame.shape[:2]
            mean = float(frame.mean())
            path = os.path.join(OUT_DIR, f"probe_idx{i}.png")
            cv2.imwrite(path, frame)
            note = "全黑" if mean <= 1.0 else "有画面"
            print(f"  索引 {i}: {w}x{h}  均值={mean:6.1f}  {note}   -> {path}")
            if mean > 1.0:
                found.append(i)
        finally:
            cap.release()

    print()
    print("=" * 60)
    print("能出画面的索引:", found if found else "无")
    print("请打开上面各个 probe_idxN.png，找出【桌面+机械臂】那张，它的 N 就是 Orbbec 的索引")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
