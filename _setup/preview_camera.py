"""相机实时预览（管理员权限运行），方便边调整三脚架边看构图。

用法（必须【管理员身份】的 PowerShell）：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\preview_camera.py"

会弹出一个 rerun 窗口，实时显示相机画面。按 Ctrl+C 退出。

调整目标（画面里应该看到什么）：
    ✅ 桌面 + 机械臂本体 + 夹爪 + 抓取物所在的区域
    ❌ 不要出现：人、窗户、强光
判断标准：光看这个画面，就该能明白"机械臂要往哪抓"。
"""

import os
import sys
import time

os.environ.setdefault("LEROBOT_CV2_BACKEND", "DSHOW")

# 让 rr.spawn() 能找到 rerun 可执行文件（它装在 python 的 Scripts 目录）
_scripts = os.path.join(os.path.dirname(sys.executable), "Scripts")
if os.path.isdir(_scripts):
    os.environ["PATH"] = _scripts + os.pathsep + os.environ.get("PATH", "")

INDEX = int(sys.argv[1]) if len(sys.argv) > 1 else 0


def main() -> int:
    import rerun as rr

    from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig

    cfg = OpenCVCameraConfig(index_or_path=INDEX, width=640, height=480, fps=30)
    cam = OpenCVCamera(cfg)
    cam.connect()
    print(f"相机已连接（索引 {INDEX}）。正在打开 rerun 查看器窗口...")
    print("窗口里看到的就是采集时会录进数据集的画面。")
    print("调整三脚架：位置、高度、俯仰角。按 Ctrl+C 结束。")
    print()

    rr.init("lerobot_camera_preview", spawn=True)

    n = 0
    t0 = time.time()
    try:
        while True:
            frame = cam.async_read(timeout_ms=2000)
            rr.log("camera/front", rr.Image(frame))
            n += 1
            if n % 30 == 0:
                dt = max(time.time() - t0, 1e-6)
                print(f"  已推流 {n} 帧，约 {n / dt:.1f} FPS", flush=True)
    except KeyboardInterrupt:
        print()
        print("已退出预览。")
    finally:
        cam.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
