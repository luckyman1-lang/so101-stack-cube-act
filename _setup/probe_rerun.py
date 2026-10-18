"""检查本机 rerun-sdk 0.39 是否还兼容 lerobot(2025-07) 用的那套 API。

录制时 `_init_rerun()` / `log_rerun_data()` 会用到 rr.init / rr.spawn / rr.Scalar / rr.Image，
数据集可视化脚本还会用 rr.set_time_sequence。rerun 0.21 之后这些接口有改名/移除，
所以必须实测一遍，不能想当然。
"""

import inspect
import os

import numpy as np
import rerun as rr

print("rerun version:", getattr(rr, "__version__", "?"))

print("\n== 1. lerobot 用到的符号是否存在 ==")
for name in ["init", "spawn", "save", "Scalar", "Scalars", "Image", "log", "set_time_sequence", "set_time"]:
    print(f"  rr.{name:<18} {'存在' if hasattr(rr, name) else '缺失'}")

print("\n== 2. 关键函数签名 ==")
for fn in ["init", "spawn"]:
    if hasattr(rr, fn):
        try:
            print(f"  rr.{fn}{inspect.signature(getattr(rr, fn))}")
        except Exception as e:
            print(f"  rr.{fn} 签名读取失败: {e}")

print("\n== 3. 实际调用 lerobot 的日志写法（不启动查看器）==")
out_dir = r"D:\LeRobot\_tools\tmp\rerun_probe"
os.makedirs(out_dir, exist_ok=True)
rrd = os.path.join(out_dir, "probe.rrd")

try:
    rr.init("lerobot_api_probe", spawn=False)
    print("  rr.init(..., spawn=False)            OK")
except Exception as e:
    print(f"  rr.init 失败: {type(e).__name__} {e}")

ok_scalar = ok_image = ok_time = False
try:
    rr.log("action/0", rr.Scalar(1.0))          # log_rerun_data 的写法
    ok_scalar = True
    print("  rr.log(path, rr.Scalar(v))           OK")
except Exception as e:
    print(f"  rr.Scalar 写法失败: {type(e).__name__} {e}")

try:
    rr.log("observation.front", rr.Image(np.zeros((8, 8, 3), dtype=np.uint8)), static=True)
    ok_image = True
    print("  rr.log(path, rr.Image(a), static=True)  OK")
except Exception as e:
    print(f"  rr.Image 写法失败: {type(e).__name__} {e}")

try:
    rr.set_time_sequence("frame_index", 0)      # visualize_dataset 的写法
    ok_time = True
    print("  rr.set_time_sequence(...)            OK")
except Exception as e:
    print(f"  rr.set_time_sequence 失败: {type(e).__name__} {e}")
    if hasattr(rr, "set_time"):
        try:
            rr.set_time("frame_index", sequence=0)
            print("  -> 改用 rr.set_time('frame_index', sequence=...)  OK")
        except Exception as e2:
            print(f"  -> rr.set_time 也失败: {type(e2).__name__} {e2}")

try:
    rr.save(rrd)
    print(f"  rr.save 写出 {os.path.getsize(rrd)} 字节 -> {rrd}")
except Exception as e:
    print(f"  rr.save 失败: {type(e).__name__} {e}")

print("\n== 4. lerobot 自己的 _init_rerun 是否可调用 ==")
from lerobot.utils.visualization_utils import _init_rerun, log_rerun_data

print("  import OK；注意 _init_rerun 会 rr.spawn 弹窗，这里只检查可导入性")
try:
    src = inspect.getsource(_init_rerun)
    print("  _init_rerun 源码里调用了:", [l.strip() for l in src.splitlines() if "rr." in l])
except Exception as e:
    print("  读取失败:", e)

print("\n结论:",
      "日志 API 兼容" if (ok_scalar and ok_image) else "日志 API 存在不兼容，需要处理",
      "|", "set_time_sequence 兼容" if ok_time else "set_time_sequence 需替换")
