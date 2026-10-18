"""Orbbec 相机独立测试（可在管理员权限下运行）。

背景：普通权限下 pyorbbecsdk 报
    OBError: Send control transfer failed!, propertyId: 1000
    MFCreateDeviceSource ... HResult 0x80070005 拒绝访问
失败点在 dl.get_device_by_index(0) —— 即 SDK 通过 WINUSB 接口(MI_06)
做 USB 控制传输被挡住，而三个 UVC 接口是通的。

用法（建议以管理员身份运行 PowerShell）：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\test_orbbec.py"
"""

import os
import sys
import traceback

OUT_DIR = r"D:\LeRobot\_setup\cam_snapshots"


def step(n, title):
    print()
    print(f"--- {n}. {title} ---")


def main() -> int:
    import pyorbbecsdk as ob
    from pyorbbecsdk import Config, Context, OBSensorType, Pipeline

    print("pyorbbecsdk SDK 版本:", ob.get_version())

    step(1, "枚举设备")
    ctx = Context()
    dl = ctx.query_devices()
    n = dl.get_count()
    print("  设备数:", n)
    if n == 0:
        print("  ✗ 没检测到设备 —— 检查 USB 线/口")
        return 1

    dev = None
    try:
        dev = dl.get_device_by_index(0)
        print("  ✔ 取到设备对象")
    except Exception as e:
        print(f"  ✗ 取设备对象失败: {type(e).__name__}: {e}")
        print("     （这一步走不过去，后面都不用试了）")

    if dev is not None:
        step(2, "读设备信息")
        try:
            info = dev.get_device_info()
            for meth, label in (
                ("get_name", "名称"),
                ("get_pid", "PID"),
                ("get_serial_number", "序列号"),
                ("get_firmware_version", "固件版本"),
                ("get_connection_type", "连接方式"),
            ):
                try:
                    v = getattr(info, meth)()
                    if meth == "get_pid":
                        v = hex(v)
                    print(f"    {label}: {v}")
                except Exception as e:
                    print(f"    {label}: 读取失败 ({type(e).__name__})")
        except Exception as e:
            print(f"  get_device_info 失败: {type(e).__name__}: {e}")

    step(3, "打开彩色流")
    pipe = None
    try:
        pipe = Pipeline()
        cfg = Config()
        pl = pipe.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
        print("  可用彩色配置数:", pl.get_count())
        for i in range(min(pl.get_count(), 12)):
            p = pl.get_stream_profile_by_index(i)
            print(
                f"    {i}: {p.get_width()}x{p.get_height()}@{p.get_fps()}  "
                f"{ob.convert_format_to_string(p.get_format())}"
            )
        prof = pl.get_default_video_stream_profile()
        cfg.enable_stream(prof)
        pipe.start(cfg)
        print("  ✔ pipeline 启动成功")
    except Exception as e:
        print(f"  ✗ 启动失败: {type(e).__name__}: {e}")
        return 1

    step(4, "取帧")
    try:
        import cv2
        import numpy as np

        frames = pipe.wait_for_frames(5000)
        if frames is None:
            print("  ✗ 5 秒内没等到帧")
            return 1
        cf = frames.get_color_frame()
        print("  ✔ 拿到帧集，彩色帧:", cf is not None)
        if cf is None:
            return 1
        w, h, fmt = cf.get_width(), cf.get_height(), cf.get_format()
        fs = ob.convert_format_to_string(fmt)
        print(f"    {w}x{h}  格式={fs}")
        data = np.frombuffer(cf.get_data(), dtype=np.uint8)
        print("    字节数:", data.size)
        low = fs.lower()
        if "mjpg" in low or "jpeg" in low:
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        elif "rgb" in low:
            img = data.reshape((h, w, 3))[:, :, ::-1]
        elif "bgr" in low:
            img = data.reshape((h, w, 3))
        else:
            img = data.reshape((h, w, max(1, data.size // (w * h))))
        if img is None:
            print("    解码失败")
            return 1
        means = [round(float(img[:, :, i].mean()), 1) for i in range(min(3, img.shape[2]))]
        print("    图像:", img.shape, " 通道均值:", means)
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, "orbbec_admin_test.png")
        cv2.imwrite(out, img)
        print("    快照:", out)
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        try:
            pipe.stop()
        except Exception:
            pass

    print()
    print("=== 全部通过：SDK 能正常取到彩色流 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
