"""验证两处"没有硬件也能测"的关键点：

1) checkpoint 的 last 链接：Windows 上符号链接没权限，补丁是否成功退回目录联接，
   并且能重复调用（第二次要先删掉旧联接）。
2) 脚本拼出来的 --robot.cameras 参数，draccus 能不能解析成 OpenCVCameraConfig。
"""

import os
import shutil
from pathlib import Path

print("=" * 60)
print("1) checkpoint last 链接（symlink -> junction 回退）")
print("=" * 60)

from lerobot.utils.train_utils import update_last_checkpoint

base = Path(r"D:\LeRobot\_tools\tmp\ckpt_test")
shutil.rmtree(base, ignore_errors=True)
(base / "checkpoints" / "005000").mkdir(parents=True)

update_last_checkpoint(base / "checkpoints" / "005000")
last = base / "checkpoints" / "last"
print("  第一次: exists =", last.exists(), "| is_dir =", last.is_dir(), "| is_symlink =", last.is_symlink())

(base / "checkpoints" / "010000").mkdir()
update_last_checkpoint(base / "checkpoints" / "010000")
print("  第二次(先删旧联接): checkpoints 下 =", sorted(p.name for p in (base / "checkpoints").iterdir()))

# 顺着 last 能读到最新 checkpoint 的内容，才说明 resume / 推理能找到模型
(base / "checkpoints" / "010000" / "marker.txt").write_text("newest", encoding="utf-8")
got = (last / "marker.txt").read_text(encoding="utf-8")
print("  通过 last 读到最新 checkpoint 内容:", got, "->", "OK" if got == "newest" else "FAIL")

print()
print("=" * 60)
print("2) draccus 解析脚本拼出的摄像头参数")
print("=" * 60)

import draccus

# 注册 'opencv' 这个 choice（record.py / teleoperate.py 里也会 import 它，
# 不 import 的话 CameraConfig 的 registry 里没有 opencv）
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig

cam_arg = "{front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}"
cfg = draccus.parse(
    SO101FollowerConfig,
    args=["--port=COM9", "--id=test_arm", f"--cameras={cam_arg}"],
)
print("  port    :", cfg.port)
print("  id      :", cfg.id)
for name, cam in cfg.cameras.items():
    print(f"  camera[{name}]: type={cam.type} index_or_path={cam.index_or_path} "
          f"{cam.width}x{cam.height}@{cam.fps} color={cam.color_mode}")

assert cfg.port == "COM9"
assert cfg.cameras["front"].index_or_path == 0
assert cfg.cameras["front"].width == 640
print("  -> OK")

# 顺便验证双摄像头拼接格式（front + wrist）
cam2 = ("{front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, "
        "wrist: {type: opencv, index_or_path: 1, width: 320, height: 240, fps: 30}}")
cfg2 = draccus.parse(SO101FollowerConfig, args=["--port=COM9", "--id=t", f"--cameras={cam2}"])
print("  双摄: ", {k: (v.index_or_path, v.width, v.height) for k, v in cfg2.cameras.items()}, "-> OK")

shutil.rmtree(base, ignore_errors=True)
