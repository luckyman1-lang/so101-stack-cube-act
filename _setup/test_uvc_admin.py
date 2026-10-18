"""以管理员权限验证 Orbbec(Gemini 2) 的 UVC 接口能否输出彩色画面。

背景：
  * 普通权限下用 DSHOW 能打开某个索引，但画面全黑
  * 而 Orbbec SDK 必须用管理员权限才能建立控制通道（已验证）
  → 所以怀疑 UVC 接口的黑帧也是权限导致的。本脚本在管理员权限下重测。

用法（必须用【管理员身份】打开 PowerShell）：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\test_uvc_admin.py"

输出会告诉我们：
  1) 哪些索引能出【真正的彩色画面】(不是全黑/不是灰度)
  2) 用的是哪个后端 (MSMF / DSHOW)
  → 若 MSMF 就能出图，lerobot 可【零代码改动】直接用；
     若只有 DSHOW 能出图，也只需几行改动。
"""

import os
import sys

import cv2
import numpy as np

OUT_DIR = r"D:\LeRobot\_setup\cam_snapshots"
BACKENDS = ((cv2.CAP_MSMF, "MSMF"), (cv2.CAP_DSHOW, "DSHOW"))
MAX_INDEX = 12


def describe(frame: np.ndarray) -> tuple[bool, bool, str]:
    """返回 (是否为有效画面, 是否为灰度, 说明)"""
    mean_all = float(frame.mean())
    if mean_all <= 1.0:
        return False, True, f"全黑 (均值 {mean_all:.2f})"
    if frame.ndim == 3 and frame.shape[2] >= 3:
        b, g, r = [float(frame[:, :, i].mean()) for i in range(3)]
        is_gray = abs(b - g) < 1.5 and abs(g - r) < 1.5
        kind = "灰度/红外" if is_gray else "彩色"
        return True, is_gray, f"{kind} (B={b:.0f} G={g:.0f} R={r:.0f})"
    return True, True, f"单通道 {frame.shape}"


def try_index(index: int, backend: int, backend_name: str) -> dict | None:
    cap = cv2.VideoCapture(index, backend)
    try:
        if not cap.isOpened():
            return None
        result = None
        # 先按默认设置读，再试显式设置 MJPG + 常见分辨率
        attempts = [("默认", None)]
        attempts += [("MJPG/640x480", ("MJPG", 640, 480)), ("MJPG/1280x720", ("MJPG", 1280, 720))]
        for label, setup in attempts:
            if setup is not None:
                fourcc, w, h = setup
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            for _ in range(6):      # 丢掉前几帧，等曝光稳定
                cap.read()
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            valid, is_gray, desc = describe(frame)
            aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"    索引 {index:>2} [{backend_name}] {label:<14} -> {aw}x{ah}  {desc}")
            if valid and not is_gray and result is None:
                os.makedirs(OUT_DIR, exist_ok=True)
                path = os.path.join(OUT_DIR, f"uvc_{backend_name}_idx{index}.png")
                cv2.imwrite(path, frame)
                result = {"index": index, "backend": backend_name, "size": (aw, ah), "path": path}
        return result
    finally:
        cap.release()


def main() -> int:
    print("提示：本脚本必须在管理员权限下运行，否则结果和普通权限一样（全黑）")
    print()
    good = []
    for backend, name in BACKENDS:
        print(f"===== {name} 后端，扫描索引 0~{MAX_INDEX - 1} =====")
        any_opened = False
        for i in range(MAX_INDEX):
            r = try_index(i, backend, name)
            if r is not None:
                any_opened = True
                good.append(r)
        if not any_opened:
            print("    （没有任何索引能打开）")
        print()

    print("=" * 60)
    if good:
        print("找到可用的彩色画面：")
        for g in good:
            print(f"  ✔ 索引 {g['index']}  后端 {g['backend']}  {g['size'][0]}x{g['size'][1]}")
            print(f"     快照: {g['path']}")
        print()
        msmf = [g for g in good if g["backend"] == "MSMF"]
        if msmf:
            print("★ 结论：MSMF 后端就能出图 → lerobot 可【零代码改动】，只填 front_index 即可")
        else:
            print("★ 结论：只有 DSHOW 能出图 → 需要让 lerobot 改用 DSHOW（约 5 行改动）")
    else:
        print("✗ 没有找到任何可用的彩色画面（所有索引要么打不开，要么全黑/灰度）")
        print("  → 方案 A(UVC 直读) 确认走不通，改走方案 B(pyorbbecsdk 适配器)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
