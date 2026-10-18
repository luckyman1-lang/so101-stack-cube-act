"""抓一张 RGB-D 快照存盘，并把内参一起存成 json（后续脚本读 json，不再硬编码）。

比 cam_probe.py 轻：不做 profile 列举、不做稳定性采样，只取最新几帧。
需要【管理员】运行（UVC 控制通道对普通用户是封的）。

用法（管理员）：
    python _setup\\snap_rgbd.py --tag green
    ... --warmup 10 --frames 5   跳过前 10 帧，取第 5 帧

输出（_setup\\cam_snapshots\\）：
    snap_<tag>_rgb.png
    snap_<tag>_depth.npy
    snap_<tag>_meta.json     内参 / depth_scale / 对齐模式 / 设备信息
"""
import argparse
import datetime
import json
import os
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from cam_probe import color_to_numpy, is_admin, list_profiles, pick_profile  # noqa: E402

SNAP = os.path.join(HERE, "cam_snapshots")


class Tee:
    """同时写文件和原 stdout —— 提权运行时 stdout 不会回流到调用方，只能靠文件。"""

    def __init__(self, *files):
        self.files = files

    def write(self, s):
        for f in self.files:
            try:
                f.write(s)
                f.flush()
            except Exception:
                pass

    def flush(self):
        for f in self.files:
            try:
                f.flush()
            except Exception:
                pass


def _py(obj):
    """把 numpy 标量/数组递归转成 Python 原生类型，否则 json.dump 会报
    TypeError: Object of type float32 is not JSON serializable
    （Orbbec SDK 的 Intrinsic 字段和 transform 都是 numpy 类型）。"""
    if isinstance(obj, dict):
        return {k: _py(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_py(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _py(obj.tolist())
    if isinstance(obj, np.generic):
        return obj.item()
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="snap", help="文件名标签")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=15)
    ap.add_argument("--frames", type=int, default=5, help="连取几帧，用最后一帧")
    ap.add_argument("--out", default=SNAP)
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"snap_{args.tag}_{stamp}"

    logf = open(os.path.join(out, base + "_log.txt"), "w", encoding="utf-8")
    real_stdout = sys.stdout
    sys.stdout = Tee(logf, real_stdout)
    try:
        return _run(args, out, base, stamp)
    finally:
        sys.stdout = real_stdout
        try:
            logf.close()
        except Exception:
            pass


def _run(args, out, base, stamp):
    if not is_admin():
        print("[!] 非管理员，很可能在开流时 E_ACCESSDENIED。")
        print("    请用 snap_rgbd_admin.cmd 双击启动。")

    from pyorbbecsdk import Config, Context, OBAlignMode, Pipeline

    ctx = Context()
    devs = ctx.query_devices()
    n = devs.get_count()
    print(f"设备数: {n}")
    if n == 0:
        print("[x] 没有枚举到相机")
        return 2
    dev_name = dev_serial = "?"
    try:
        info = devs.get_device_by_index(0).get_device_info()
        dev_name = info.get_name()
        dev_serial = info.get_serial_number()
        print(f"  {dev_name}  serial={dev_serial}")
    except Exception as e:
        print(f"  读设备信息失败: {e}")

    pipeline = Pipeline()
    cc = list_profiles(pipeline, "COLOR_SENSOR")
    dc = list_profiles(pipeline, "DEPTH_SENSOR")
    cp = pick_profile(cc, args.width, args.height, args.fps, "COLOR")
    dp = pick_profile(dc, args.width, args.height, args.fps, "DEPTH")
    if cp is None or dp is None:
        print("[x] 拿不到 profile")
        return 3

    started = False
    aligned = None
    for mode in ("HW_MODE", "SW_MODE", None):
        try:
            try:
                pipeline.stop()
            except Exception:
                pass
            pipeline = Pipeline()
            cfg = Config()
            cfg.enable_stream(cp)
            cfg.enable_stream(dp)
            if mode is not None:
                cfg.set_align_mode(getattr(OBAlignMode, mode))
            pipeline.start(cfg)
            started, aligned = True, mode
            print(f"对齐: {mode or '未对齐'}  (start ok)")
            break
        except Exception as e:
            print(f"  {mode} 启动失败: {type(e).__name__}: {e}")
    if not started:
        print("[x] 启动失败")
        return 5

    try:
        # 丢弃 warmup
        for _ in range(args.warmup):
            pipeline.wait_for_frames(500)
        frames = None
        for _ in range(max(1, args.frames)):
            fs = pipeline.wait_for_frames(1000)
            if fs is not None and fs.get_color_frame() is not None and fs.get_depth_frame() is not None:
                frames = fs
        if frames is None:
            print("[x] 取不到成对帧")
            return 4

        color = frames.get_color_frame()
        depth = frames.get_depth_frame()
        cw, ch = color.get_width(), color.get_height()
        dw, dh = depth.get_width(), depth.get_height()
        scale = float(depth.get_depth_scale())
        bgr = color_to_numpy(color)
        d_np = np.frombuffer(depth.get_data(), dtype=np.uint16).reshape(dh, dw).copy()

        cam = pipeline.get_camera_param()
        ri = cam.rgb_intrinsic
        di = cam.depth_intrinsic
        meta = {
            "created": stamp,
            "device": dev_name,
            "serial": dev_serial,
            "align": aligned,
            "color_size": [cw, ch],
            "depth_size": [dw, dh],
            "depth_scale": scale,
            "depth_format": str(depth.get_format()),
            "color_format": str(color.get_format()),
            # 对齐后深度在彩色相机坐标系 -> 3D 反投影用 rgb_intrinsic
            "intrinsic_used_for_3d": "rgb_intrinsic",
            "rgb_intrinsic": {"fx": ri.fx, "fy": ri.fy, "cx": ri.cx, "cy": ri.cy,
                              "width": ri.width, "height": ri.height},
            "depth_intrinsic_raw": {"fx": di.fx, "fy": di.fy, "cx": di.cx, "cy": di.cy,
                                    "width": di.width, "height": di.height},
            "rgb_distortion": {"model": str(cam.rgb_distortion.model),
                               "k1": cam.rgb_distortion.k1, "k2": cam.rgb_distortion.k2,
                               "k3": cam.rgb_distortion.k3,
                               "p1": cam.rgb_distortion.p1, "p2": cam.rgb_distortion.p2},
            "transform_pos_mm": list(cam.transform.transform),
            "is_mirrored": bool(cam.is_mirrored),
        }

        import cv2

        p_rgb = os.path.join(out, base + "_rgb.png")
        p_dep = os.path.join(out, base + "_depth.npy")
        p_met = os.path.join(out, base + "_meta.json")
        if bgr is not None:
            cv2.imwrite(p_rgb, bgr)
        np.save(p_dep, d_np)
        with open(p_met, "w", encoding="utf-8") as f:
            json.dump(_py(meta), f, ensure_ascii=False, indent=2)

        valid = d_np[d_np > 0]
        print()
        print(f"彩色: {cw}x{ch}  深度: {dw}x{dh}  scale={scale}")
        print(f"深度有效: {valid.size / d_np.size * 100:.1f}%  "
              f"中位={np.median(valid) if valid.size else -1:.0f}mm")
        print(f"内参: fx={ri.fx:.2f} fy={ri.fy:.2f} cx={ri.cx:.2f} cy={ri.cy:.2f}")
        print()
        print("已存:")
        for p in (p_rgb, p_dep, p_met):
            print(f"  {p}")
        print()
        print(f">>> 完成。分析用： _setup\\analyze_snapshot.py --tag {args.tag}")
        return 0
    finally:
        try:
            pipeline.stop()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
