"""环境自检：确认这套 LeRobot 在本机 Windows 上能跑通。

用法：
    python 00_env_check.py                 # 基础检查（不碰硬件，几十秒）
    python 00_env_check.py --dataset       # 额外验证"采集数据"整条链路（推荐，不需要机械臂）
    python 00_env_check.py --camera 0      # 额外检查摄像头 0 能否连续读帧

退出码 0 = 全部通过；非 0 = 有失败项。
"""

import argparse
import os
import shutil
import sys
import tempfile
import time

OK, FAIL, WARN = "OK", "FAIL", "WARN"
_results = []


def head(text: str) -> None:
    print()
    print("=" * 62)
    print(f"  {text}")
    print("=" * 62)


def check(name: str, fn, required: bool = True):
    """跑一个检查项。required=False 时失败只记 WARN。"""
    try:
        info = fn()
        _results.append((OK if required else OK, name, info))
        print(f"  [OK]   {name}" + (f"  ->  {info}" if info else ""))
        return True
    except Exception as e:
        level = FAIL if required else WARN
        _results.append((level, name, f"{type(e).__name__}: {e}"))
        print(f"  [{level}] {name}  ->  {type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------- 各项检查
def c_python():
    return f"{sys.version.split()[0]}  ({sys.executable})"


def c_lerobot():
    import lerobot

    path = getattr(lerobot, "__file__", "?")
    version = getattr(lerobot, "__version__", None)
    if version is None:
        try:
            from lerobot.__version__ import __version__ as version  # type: ignore
        except Exception:
            version = "unknown"
    return f"version={version}  from {path}"


def c_entrypoints():
    import importlib

    mods = [
        "lerobot.calibrate",
        "lerobot.teleoperate",
        "lerobot.record",
        "lerobot.find_port",
        "lerobot.find_cameras",
    ]
    missing = []
    for m in mods:
        try:
            importlib.import_module(m)
        except Exception as e:
            missing.append(f"{m}({type(e).__name__})")
    if missing:
        raise RuntimeError("导入失败: " + ", ".join(missing))
    return f"{len(mods)} 个入口模块都可导入"


def c_torch():
    import torch

    line = f"torch {torch.__version__}"
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        free, total = torch.cuda.mem_get_info(0)
        line += f" | CUDA 可用: {name} 显存 {total / 1024**3:.1f}GB(空闲 {free / 1024**3:.1f}GB)"
        cap = torch.cuda.get_device_capability(0)
        line += f" sm_{cap[0]}{cap[1]}"
    else:
        line += " | 警告: CUDA 不可用，训练/推理会退回 CPU（很慢）"
    x = torch.randn(64, 64, device="cuda" if torch.cuda.is_available() else "cpu")
    _ = (x @ x).sum().item()
    return line


def _av_codecs() -> set:
    import av

    for attr in ("codecs_available",):
        if hasattr(av, attr):
            return set(getattr(av, attr))
    try:
        from av.codec import codecs_available  # type: ignore

        return set(codecs_available)
    except Exception:
        return set()


def c_av():
    import av

    codecs = _av_codecs()
    wanted = ["libsvtav1", "libx264", "libx265"]
    have = [c for c in wanted if c in codecs]
    if not codecs:
        return f"PyAV {av.__version__}（无法列出编码器）"
    missing = [c for c in wanted if c not in codecs]
    line = f"PyAV {av.__version__} | 可用编码器: {', '.join(have) or '无'}"
    if missing:
        line += f" | 缺少: {', '.join(missing)}"
    return line


def c_video_encode(tmp: str):
    """用 LeRobot 自己的编码函数，把若干 PNG 编成 mp4（默认 libsvtav1）。"""
    import numpy as np
    from PIL import Image

    from lerobot.datasets.video_utils import encode_video_frames

    frames_dir = os.path.join(tmp, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    for i in range(12):
        arr = np.zeros((64, 96, 3), dtype=np.uint8)
        arr[:, :, 0] = (i * 20) % 256
        arr[:, :, 1] = 40
        Image.fromarray(arr).save(os.path.join(frames_dir, f"frame_{i:06d}.png"))

    video = os.path.join(tmp, "out.mp4")
    encode_video_frames(frames_dir, video, 30, overwrite=True)
    size = os.path.getsize(video)
    if size < 100:
        raise RuntimeError(f"生成的视频只有 {size} 字节，编码异常")
    return f"默认编码器(libsvtav1)成功，输出 {size / 1024:.1f}KB"


def c_dataset(tmp: str):
    """不接机械臂，用假数据走一遍 LeRobotDataset 采集 -> 落盘 -> 读回。"""
    import numpy as np

    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    n_joints = 6
    feat_names = [f"j{i}.pos" for i in range(n_joints)]
    features = {
        "action": {"dtype": "float32", "shape": (n_joints,), "names": feat_names},
        "observation.state": {"dtype": "float32", "shape": (n_joints,), "names": feat_names},
        "observation.images.front": {
            "dtype": "video",
            "shape": (48, 64, 3),
            "names": ["height", "width", "channels"],
        },
    }

    root = os.path.join(tmp, "ds_root")
    ds = LeRobotDataset.create(
        repo_id="envcheck/tiny",
        fps=30,
        features=features,
        root=root,
        robot_type="envcheck",
        use_videos=True,
        image_writer_threads=2,
    )

    n_frames = 20
    for i in range(n_frames):
        ds.add_frame(
            {
                "action": np.full(n_joints, i * 0.01, dtype=np.float32),
                "observation.state": np.full(n_joints, i * 0.02, dtype=np.float32),
                "observation.images.front": np.full((48, 64, 3), (i * 11) % 256, dtype=np.uint8),
            },
            task="env check",
        )
    ds.save_episode()

    videos = [p for p in _walk(root) if p.endswith(".mp4")]
    parquets = [p for p in _walk(root) if p.endswith(".parquet")]
    if not videos:
        raise RuntimeError(f"没有生成 mp4（目录：{root}）")
    if not parquets:
        raise RuntimeError(f"没有生成 parquet（目录：{root}）")

    # 读回，顺便验证视频解码
    ds2 = LeRobotDataset("envcheck/tiny", root=root)
    item = ds2[0]
    keys = sorted(k for k in item if k.startswith("observation") or k == "action")

    vsize = sum(os.path.getsize(p) for p in videos)
    return (
        f"{n_frames} 帧 -> {len(videos)} 个 mp4({vsize / 1024:.1f}KB) + {len(parquets)} 个 parquet；"
        f"读回成功，字段 {keys}"
    )


def _walk(root: str):
    out = []
    for base, _dirs, files in os.walk(root):
        for f in files:
            out.append(os.path.join(base, f))
    return out


def c_cv2():
    import cv2

    return f"opencv-python {cv2.__version__}"


def c_serial():
    import serial
    from serial.tools import list_ports

    ports = {p.device: (p.description or "") for p in list_ports.comports()}
    if not ports:
        return "pyserial 可用，但当前没有检测到串口（机械臂 USB 没插？）"
    detail = "; ".join(f"{d}({desc})" for d, desc in sorted(ports.items()))
    return f"pyserial {serial.__version__} | 串口: {detail}"


def c_feetech():
    import scservo_sdk  # feetech-servo-sdk 提供的模块名

    return f"scservo_sdk 可用（{getattr(scservo_sdk, '__file__', '')}）"


def c_swanlab():
    import swanlab

    ver = getattr(swanlab, "__version__", "?")
    return f"swanlab {ver}（未登录也能用 swanlab_mode=offline 本地记录）"


def c_rerun():
    import rerun

    return f"rerun-sdk {getattr(rerun, '__version__', '?')}"


def c_rerun_api(tmp: str):
    """实测 lerobot 录制/可视化真正用到的那几个 rerun 调用。

    rerun 0.23 起把 rr.Scalar 改成了 rr.Scalars、rr.set_time_sequence 改成了 rr.set_time，
    本项目对应的 lerobot 版本还在用旧接口 —— 装到新版会在录制时直接 AttributeError，
    所以这里不能只 import，必须真的调一遍。
    """
    import numpy as np
    import rerun as rr

    from lerobot.utils.visualization_utils import log_rerun_data

    needed = ["init", "spawn", "save", "Scalar", "Image", "set_time_sequence"]
    missing = [n for n in needed if not hasattr(rr, n)]
    if missing:
        raise RuntimeError(
            f"rerun {rr.__version__} 缺少 lerobot 需要的接口 {missing}；"
            "本项目需要 rerun-sdk<0.23（新版改了 API）"
        )

    rr.init("envcheck_rerun", spawn=False)
    # log_rerun_data 是录制时 --display_data=true 实际走的那条路径
    log_rerun_data(
        {"front": np.zeros((8, 8, 3), dtype=np.uint8), "j0.pos": 0.1},
        {"j0.pos": 0.2},
    )
    out = os.path.join(tmp, "rerun_api.rrd")
    rr.save(out)
    if not os.path.exists(out):
        raise RuntimeError("rr.save 没有写出 .rrd 文件")
    return f"rerun-sdk {rr.__version__}，log_rerun_data() 实测通过（写出 {os.path.getsize(out)}B）"


def c_hf():
    import huggingface_hub as hf

    token = None
    try:
        token = hf.get_token()
    except Exception:
        pass
    return f"huggingface_hub {hf.__version__} | token: {'已登录' if token else '未登录（push_to_hub=false 时不影响）'}"


def c_camera(index: int):
    import cv2
    import numpy as np

    backend = cv2.CAP_MSMF if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    try:
        if not cap.isOpened():
            raise RuntimeError(f"摄像头 {index} 打不开")
        got = 0
        last = None
        t0 = time.time()
        for _ in range(30):
            ok, frame = cap.read()
            if ok and frame is not None:
                got += 1
                last = frame
        if got == 0:
            raise RuntimeError("一帧都没读到")
        dt = max(time.time() - t0, 1e-6)
        h, w = last.shape[:2]
        return f"摄像头 {index}: 读到 {got}/30 帧, {w}x{h}, 约 {got / dt:.1f} FPS"
    finally:
        cap.release()


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="LeRobot Windows 环境自检")
    ap.add_argument("--dataset", action="store_true", help="额外验证采集数据链路（用假数据，不需要机械臂）")
    ap.add_argument("--camera", type=int, default=None, help="额外检查指定摄像头索引")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="envcheck-")
    print(f"临时目录：{tmp}")

    head("1. 基础环境")
    check("Python", c_python)
    check("LeRobot 包", c_lerobot)
    check("命令行入口模块", c_entrypoints)

    head("2. 计算设备")
    check("PyTorch / CUDA（训练和推理的关键）", c_torch)

    head("3. 视频与数据（采集数据的成败关键）")
    check("PyAV 编码器", c_av)
    check("视频编码端到端", lambda: c_video_encode(tmp))
    check("OpenCV", c_cv2)

    head("4. 硬件相关依赖")
    check("串口 pyserial", c_serial)
    check("Feetech 舵机 SDK", c_feetech)

    head("5. 训练追踪与工具")
    check("SwanLab", c_swanlab, required=False)
    check("Rerun 可视化", c_rerun, required=False)
    check("Rerun 录制接口兼容性（录制时会用到）", lambda: c_rerun_api(tmp))
    check("HuggingFace Hub", c_hf, required=False)

    if args.dataset:
        head("6. 采集链路（假数据，不需要机械臂）")
        check("LeRobotDataset 写入+读回", lambda: c_dataset(tmp))

    if args.camera is not None:
        head("7. 摄像头")
        check(f"摄像头 {args.camera}", lambda: c_camera(args.camera))

    shutil.rmtree(tmp, ignore_errors=True)

    head("结果汇总")
    n_fail = sum(1 for lvl, _, _ in _results if lvl == FAIL)
    n_warn = sum(1 for lvl, _, _ in _results if lvl == WARN)
    for lvl, name, info in _results:
        if lvl != OK:
            print(f"  [{lvl}] {name}  ->  {info}")
    print(f"\n  通过 {sum(1 for lvl, _, _ in _results if lvl == OK)} 项，"
          f"警告 {n_warn} 项，失败 {n_fail} 项")
    if n_fail == 0:
        print("\n  环境自检通过，可以往下走了：01_find_ports -> 02_setup_motors(仅散件) -> 03_calibrate -> 04_teleoperate -> 05_record_dataset -> 06_train_act -> 07_run_policy")
    else:
        print("\n  有失败项，先解决它们再往下走（把上面的 [FAIL] 行发给你的助手）。")
    return n_fail


if __name__ == "__main__":
    sys.exit(main())
