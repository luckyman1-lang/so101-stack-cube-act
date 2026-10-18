"""验证 lerobot 能否通过 DSHOW 后端、用原生 OpenCVCamera 读到 Orbbec 的画面。

这是「方案 A」的最终验证：如果这个脚本能读到彩色帧，说明 lerobot 的采集/训练链路
可以直接用这个相机（零适配代码），只需要填好 front_index。

必须【以管理员身份】运行（Orbbec 的相机访问需要提权）。

用法：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\test_lerobot_camera.py" [索引]
    默认索引 0
"""

import os
import sys

# 关键：让 lerobot 用 DSHOW 后端（默认是 MSMF，而 MSMF 打不开这台相机）
os.environ.setdefault("LEROBOT_CV2_BACKEND", "DSHOW")

INDEX = int(sys.argv[1]) if len(sys.argv) > 1 else 0
WIDTH, HEIGHT, FPS = 640, 480, 30


def main() -> int:
    import cv2
    import numpy as np

    from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig

    print(f"LEROBOT_CV2_BACKEND = {os.environ.get('LEROBOT_CV2_BACKEND')}")

    cfg = OpenCVCameraConfig(index_or_path=INDEX, width=WIDTH, height=HEIGHT, fps=FPS)
    print(f"配置: index={INDEX}  {WIDTH}x{HEIGHT}@{FPS}  color_mode={cfg.color_mode}")

    cam = OpenCVCamera(cfg)
    try:
        backend_name = cv2.videoio_registry.getBackendName(cam.backend)
    except Exception:
        backend_name = str(cam.backend)
    print(f"实际使用的 OpenCV 后端: {backend_name}")

    cam.connect()
    print("connect() 完成，is_connected =", cam.is_connected)

    frame = cam.async_read(timeout_ms=3000)
    print(f"async_read() 拿到帧: shape={frame.shape} dtype={frame.dtype}")
    print(f"  通道均值 = {[round(float(frame[:, :, i].mean()), 1) for i in range(frame.shape[2])]}")

    if float(frame.mean()) <= 1.0:
        print("  ✗ 画面全黑 —— 相机没真正出图")
        return 1

    # 连读 30 帧，看帧率是否稳定
    import time

    t0 = time.time()
    n = 30
    for _ in range(n):
        cam.async_read(timeout_ms=1000)
    dt = time.time() - t0
    print(f"  连读 {n} 帧耗时 {dt:.2f}s  → 约 {n / dt:.1f} FPS")

    out_dir = r"D:\LeRobot\_setup\cam_snapshots"
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"lerobot_cam{INDEX}.png")
    cv2.imwrite(out, frame[:, :, ::-1])  # lerobot 给的是 RGB，存图要转 BGR
    print(f"  快照已存: {out}")

    cam.disconnect()
    print("disconnect() 完成")
    print()
    print("=== 通过：lerobot 可以直接用这个相机（方案 A 成立）===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
