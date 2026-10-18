"""探测 Orbbec Gemini 2：枚举设备 -> 取一帧 D2C 对齐 RGB-D -> 存图 + 报内参。

背景（2026-10-18 实测确认）：
  * 普通权限下能"枚举到 1 个设备"，但一读设备信息/开流就 E_ACCESSDENIED：
        MFCreateDeviceSource(...) returned: HResult 0x80070005
    -> 相机必须【管理员】运行。用同目录 probe_camera_admin.cmd 双击启动。
  * 管理员下实测：Orbbec Gemini 2 / serial=AYGKC520QFP / fw=1.4.98 / pid=0x0670

用法（管理员 PowerShell）：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" _setup\\cam_probe.py
    ... --warmup 30       丢弃前 30 帧（自动曝光收敛）
    ... --frames 10       额外采样 10 帧测深度稳定性

输出（_setup\\cam_snapshots\\）：
    probe_rgb.png / probe_depth.png / probe_depth.npy / probe_report.txt
"""
import argparse
import datetime
import os
import sys
import traceback

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cam_snapshots")
LOG = []


def log(msg: str = "") -> None:
    print(msg)
    LOG.append(str(msg))


def is_admin() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def enum_devices():
    from pyorbbecsdk import Context

    ctx = Context()
    devs = ctx.query_devices()
    n = devs.get_count()
    log(f"枚举到的设备数: {n}")
    readable = 0
    for i in range(n):
        try:
            d = devs.get_device_by_index(i)
            info = d.get_device_info()
            log(f"  [{i}] name={info.get_name()}  serial={info.get_serial_number()}  "
                f"fw={info.get_firmware_version()}  pid=0x{info.get_pid():04x}")
            readable += 1
        except Exception as e:
            log(f"  [{i}] 读设备信息失败: {type(e).__name__}: {e}")
            log("       -> 能枚举但打不开，几乎一定是权限不足（需要管理员）")
    log(f"可读设备数: {readable}/{n}")
    return n


def list_profiles(pipeline, sensor_name: str):
    """返回 [(w, h, fps, fmt, StreamProfile), ...]"""
    from pyorbbecsdk import OBSensorType

    st = getattr(OBSensorType, sensor_name)
    plist = pipeline.get_stream_profile_list(st)
    if plist is None:
        return []
    out = []
    for i in range(plist.get_count()):
        sp = plist.get_stream_profile_by_index(i)
        try:
            v = sp.as_video_stream_profile()
            out.append((v.get_width(), v.get_height(), v.get_fps(), v.get_format(), sp))
        except Exception:
            out.append((0, 0, 0, None, sp))
    return out


def pick_profile(cands, width, height, fps, tag):
    if not cands:
        log(f"  {tag}: 没有可用 profile")
        return None
    log(f"  {tag} 可用 profile ({len(cands)}):")
    for w, h, f, fmt, _ in cands[:12]:
        log(f"     {w}x{h}@{f}  fmt={fmt}")
    exact = [c for c in cands if c[0] == width and c[1] == height and c[2] == fps]
    if exact:
        c = exact[0]
        log(f"  {tag} 选用(精确匹配): {c[0]}x{c[1]}@{c[2]} fmt={c[3]}")
        return c[4]
    # 退而求其次：分辨率最接近且 fps 匹配
    same_fps = [c for c in cands if c[2] == fps] or cands
    c = min(same_fps, key=lambda x: abs(x[0] - width) + abs(x[1] - height))
    log(f"  {tag} 选用(最接近): {c[0]}x{c[1]}@{c[2]} fmt={c[3]}")
    return c[4]


def main() -> int:
    global OUT_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--frames", type=int, default=10)
    ap.add_argument("--serial", default="")
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()
    OUT_DIR = os.path.abspath(args.out)
    os.makedirs(OUT_DIR, exist_ok=True)

    log("=" * 68)
    log(f"Orbbec Gemini 2 探测  {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    log(f"进程管理员权限: {is_admin()}")
    log(f"输出目录: {OUT_DIR}")
    log("=" * 68)

    pipeline = None
    try:
        n = enum_devices()
        if n == 0:
            log("")
            log("!! 设备数为 0，排查：")
            log("   1. 相机没插好 / USB 线只供电不传数据")
            log("   2. 被别的进程占着（残留 python / Orbbec Viewer）")
            log("   3. USB 端口是 USB2（Gemini 2 要 USB3）")
            return 2
        if not is_admin():
            log("!! 非管理员，大概率会在开流时 E_ACCESSDENIED。请用 probe_camera_admin.cmd。")

        from pyorbbecsdk import Config, OBAlignMode, Pipeline

        pipeline = Pipeline()
        color_cands = list_profiles(pipeline, "COLOR_SENSOR")
        depth_cands = list_profiles(pipeline, "DEPTH_SENSOR")
        cp = pick_profile(color_cands, args.width, args.height, args.fps, "COLOR")
        dp = pick_profile(depth_cands, args.width, args.height, args.fps, "DEPTH")
        if cp is None or dp is None:
            log("!! 拿不到 color/depth 的 profile，放弃")
            return 3

        # D2C 对齐：让每个彩色像素都有对应深度（后面要做 像素 -> 3D）
        # 逐个尝试，start 失败就换下一种，避免白跑一次
        started = False
        aligned = None
        for mode_name in ("HW_MODE", "SW_MODE", None):
            try:
                try:
                    pipeline.stop()
                except Exception:
                    pass
                pipeline = Pipeline()
                cfg = Config()
                cfg.enable_stream(cp)
                cfg.enable_stream(dp)
                if mode_name is not None:
                    cfg.set_align_mode(getattr(OBAlignMode, mode_name))
                pipeline.start(cfg)
                started, aligned = True, mode_name
                log(f"对齐模式: {mode_name or '未对齐'}  (start 成功)")
                break
            except Exception as e:
                log(f"  以 {mode_name or '未对齐'} 启动失败: {type(e).__name__}: {e}")
        if not started:
            log("!! 三种对齐模式都启动失败，相机可能被别的进程占着")
            return 5
        log("pipeline 已启动，开始取帧 ...")

        frames = None
        tries = 0
        while tries < 60:
            tries += 1
            fs = pipeline.wait_for_frames(1000)
            if fs is None:
                if tries % 10 == 0:
                    log(f"  第 {tries} 次 wait_for_frames 超时")
                continue
            if fs.get_color_frame() is not None and fs.get_depth_frame() is not None:
                frames = fs
                break
        if frames is None:
            log("!! 取不到同时含 color+depth 的帧")
            return 4
        log(f"  第 {tries} 次取到成对帧")

        color = frames.get_color_frame()
        depth = frames.get_depth_frame()
        cw, ch = color.get_width(), color.get_height()
        dw, dh = depth.get_width(), depth.get_height()
        scale = float(depth.get_depth_scale())
        log("")
        log(f"color : {cw}x{ch}  fmt={color.get_format()}")
        log(f"depth : {dw}x{dh}  fmt={depth.get_format()}")
        log(f"depth scale = {scale}   (乘 scale 得到毫米)")
        if aligned and (dw, dh) != (cw, ch):
            log(f"  注意: 对齐后尺寸仍不同 (depth {dw}x{dh} vs color {cw}x{ch})，"
                "说明对齐可能没生效")

        d_np = np.frombuffer(depth.get_data(), dtype=np.uint16).reshape(dh, dw).copy()
        valid = d_np[d_np > 0]
        log(f"深度统计: min={d_np.min()} max={d_np.max()} "
            f"有效(>0)={valid.size / d_np.size * 100:.1f}%  "
            f"中位={np.median(valid) if valid.size else -1:.0f} (原始单位)")
        if valid.size:
            mm = valid.astype(np.float64) * scale
            log(f"  换算毫米: p2={np.percentile(mm, 2):.0f} p50={np.percentile(mm, 50):.0f} "
                f"p98={np.percentile(mm, 98):.0f}")

        c_np = color_to_numpy(color)
        if c_np is not None:
            log(f"彩色数组: {c_np.shape} dtype={c_np.dtype}")

        # 深度时间稳定性
        if args.frames > 1 and aligned:
            log("")
            log(f"深度稳定性采样 {args.frames} 帧 ...")
            acc = []
            for _ in range(args.frames):
                fs2 = pipeline.wait_for_frames(1000)
                if fs2 is None:
                    continue
                d2 = fs2.get_depth_frame()
                if d2 is None:
                    continue
                acc.append(np.frombuffer(d2.get_data(), dtype=np.uint16)
                           .reshape(d2.get_height(), d2.get_width()).astype(np.float32))
            if len(acc) >= 2:
                stack = np.stack(acc)
                m = stack > 0
                both = np.all(m, axis=0)
                if both.any():
                    std = np.std(stack[:, both], axis=0) * scale
                    log(f"  逐像素时域 std: 中位={np.median(std):.2f} mm  "
                        f"p95={np.percentile(std, 95):.2f} mm")
                    log("  (这决定了 14mm 方块可达的定位精度上限)")

        # 内参
        log("")
        log("相机参数:")
        try:
            cam = pipeline.get_camera_param()
            for name in ("rgb_intrinsic", "depth_intrinsic"):
                k = getattr(cam, name, None)
                if k is None:
                    continue
                log(f"  {name}: fx={k.fx:.3f} fy={k.fy:.3f} cx={k.cx:.3f} cy={k.cy:.3f} "
                    f"({k.width}x{k.height})")
            tr = getattr(cam, "transform", None)
            if tr is not None:
                log(f"  transform.rot     = {tr.rot}")
                log(f"  transform.pos     = {tr.transform}")
            log(f"  is_mirrored       = {getattr(cam, 'is_mirrored', 'n/a')}")
            for name in ("rgb_distortion", "depth_distortion"):
                dd = getattr(cam, name, None)
                if dd is None:
                    continue
                log(f"  {name}: model={dd.model} k1={dd.k1:.5f} k2={dd.k2:.5f} "
                    f"k3={dd.k3:.5f} p1={dd.p1:.5f} p2={dd.p2:.5f}")
        except Exception as e:
            log(f"  读内参失败: {type(e).__name__}: {e}")

        np.save(os.path.join(OUT_DIR, "probe_depth.npy"), d_np)
        save_depth_png(d_np, scale, os.path.join(OUT_DIR, "probe_depth.png"))
        save_rgb_png(c_np, os.path.join(OUT_DIR, "probe_rgb.png"))
        log("")
        log(f"已存 probe_rgb.png / probe_depth.png / probe_depth.npy -> {OUT_DIR}")
        log("")
        log(">>> 结论: 深度相机可用，M0 的深度反投影路线成立。")
        return 0

    except Exception:
        log("!! 异常:")
        log(traceback.format_exc())
        return 1
    finally:
        try:
            if pipeline is not None:
                pipeline.stop()
        except Exception:
            pass
        rep = os.path.join(OUT_DIR, "probe_report.txt")
        with open(rep, "w", encoding="utf-8") as f:
            f.write("\n".join(LOG))
        print(f"\n报告已写入: {rep}")


def color_to_numpy(fr):
    """Gemini 的 color 可能是 MJPG / YUYV / RGB。统一转 BGR。"""
    import cv2

    w, h = fr.get_width(), fr.get_height()
    fmt = str(fr.get_format())
    buf = np.frombuffer(fr.get_data(), dtype=np.uint8)
    if "MJPG" in fmt or "MJPEG" in fmt:
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if "YUYV" in fmt or "YUY2" in fmt:
        return cv2.cvtColor(buf.reshape(h, w, 2), cv2.COLOR_YUV2BGR_YUYV)
    if "UYVY" in fmt:
        return cv2.cvtColor(buf.reshape(h, w, 2), cv2.COLOR_YUV2BGR_UYVY)
    if "RGB" in fmt:
        return cv2.cvtColor(buf.reshape(h, w, 3), cv2.COLOR_RGB2BGR)
    if "BGR" in fmt:
        return buf.reshape(h, w, 3)
    try:
        return buf.reshape(h, w, 3)
    except Exception:
        return None


def save_depth_png(d_np, scale, path):
    import cv2

    mm = d_np.astype(np.float32) * float(scale)
    valid = mm[mm > 0]
    if valid.size == 0:
        return
    lo, hi = np.percentile(valid, 2), np.percentile(valid, 98)
    norm = np.zeros_like(d_np, dtype=np.uint8)
    m = d_np > 0
    if hi > lo:
        norm[m] = np.clip((mm[m] - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
    vis = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    vis[~m] = 0
    cv2.imwrite(path, vis)
    log(f"  深度伪彩 2%~98% 分位: {lo:.0f} ~ {hi:.0f} mm")


def save_rgb_png(c_np, path):
    import cv2

    if c_np is not None:
        cv2.imwrite(path, c_np)


if __name__ == "__main__":
    sys.exit(main())
