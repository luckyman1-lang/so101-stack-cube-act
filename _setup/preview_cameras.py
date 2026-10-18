"""实时预览所有摄像头画面（管理员权限运行）。

解决了什么问题：
    Windows 的摄像头索引是按枚举顺序分配的，光看索引号无法知道哪个是哪个。
    这个脚本会把【所有能出画面的摄像头】同时并排显示出来，
    画面标题里的数字就是索引号，一眼就能分辨：
        画面里是【桌面 + 机械臂】→ 你的 Orbbec
        画面里是【人脸】        → 笔记本内置摄像头

用法（必须【管理员身份】的 PowerShell，因为 Orbbec 需要提权）：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\preview_cameras.py"
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\preview_cameras.py" 0 1   # 只看指定索引

会弹出 rerun 窗口实时显示画面。按 Ctrl+C 退出。

注意：这里用的就是 lerobot 采集时会用的那个相机类（OpenCVCamera），
      所以你看到的画面 = 将来录进数据集的画面。
"""

import os
import sys
import time

os.environ.setdefault("LEROBOT_CV2_BACKEND", "DSHOW")

# rerun.exe 装在 python 的 Scripts 目录，加进 PATH 让 rr.spawn() 找得到
_scripts = os.path.join(os.path.dirname(sys.executable), "Scripts")
if os.path.isdir(_scripts):
    os.environ["PATH"] = _scripts + os.pathsep + os.environ.get("PATH", "")

SCAN_MAX = 8
WIDTH, HEIGHT, FPS = 640, 480, 30


def main() -> int:
    import rerun as rr

    from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig

    wanted = [int(a) for a in sys.argv[1:]] or list(range(SCAN_MAX))
    print(f"正在扫描索引: {wanted}（DSHOW 后端）")
    print()

    cameras: dict[int, OpenCVCamera] = {}
    for i in wanted:
        cam = OpenCVCamera(OpenCVCameraConfig(index_or_path=i, width=WIDTH, height=HEIGHT, fps=FPS))
        try:
            cam.connect(warmup=False)
            frame = cam.async_read(timeout_ms=2000)
        except Exception as e:
            print(f"  索引 {i}: 打不开（{type(e).__name__}）")
            continue
        mean = float(frame.mean())
        if mean <= 1.0:
            print(f"  索引 {i}: 能打开但画面全黑（均值 {mean:.2f}），跳过")
            cam.disconnect()
            continue
        h, w = frame.shape[:2]
        print(f"  索引 {i}: ✔ 有画面 {w}x{h}  均值={mean:.1f}")
        cameras[i] = cam

    if not cameras:
        print()
        print("✗ 没有找到任何能出画面的摄像头。")
        print("  检查：1) 相机是否插好  2) 是否用管理员权限运行  3) 微信等程序是否占用相机")
        return 1

    print()
    print(f"打开 rerun 窗口，共 {len(cameras)} 路画面：{sorted(cameras)}")
    print("窗口里每个画面的标题就是索引号 —— 找出『桌面+机械臂』那一路，记下它的数字。")
    print("按 Ctrl+C 退出。")
    print()

    rr.init("lerobot_camera_preview", spawn=True)

    rounds = 0
    t0 = time.time()
    try:
        while True:
            for i, cam in cameras.items():
                try:
                    frame = cam.async_read(timeout_ms=500)
                    rr.log(f"camera/idx{i}", rr.Image(frame))
                except Exception as e:
                    print(f"  索引 {i} 读帧出错: {type(e).__name__}: {e}", flush=True)
            rounds += 1
            if rounds % 60 == 0:
                dt = max(time.time() - t0, 1e-6)
                print(f"  已推流 {rounds} 轮，约 {rounds / dt:.1f} 轮/秒", flush=True)
    except KeyboardInterrupt:
        print()
        print("已退出预览。")
    finally:
        for cam in cameras.values():
            try:
                cam.disconnect()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
