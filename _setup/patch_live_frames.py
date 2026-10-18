"""给 record.py 加「推理时自动落盘相机画面」，方便外部实时观察机械臂状态。

只改两处：
1. 模块级加几个全局变量
2. record_loop 里 observation 之后加一段存图逻辑（守卫 `policy is not None`）

不影响手动录制（那时候 policy 是 None）。
"""

import io
import re

P = r"D:\LeRobot\lerobot\src\lerobot\record.py"

src = io.open(P, "r", encoding="utf-8", newline="").read()
NL = "\r\n" if "\r\n" in src else "\n"

if "_LIVE_FRAME_DIR" in src:
    print("补丁已存在，跳过")
    raise SystemExit(0)

# ---------- 1) 模块级全局变量（插在 record_loop 定义之前） ----------
anchor = "def record_loop("
assert src.count(anchor) == 1, "找不到 record_loop 定义"

globals_block = NL.join(
    [
        "# [本地改动] 推理时把相机画面落盘，方便外部（AGENT/人）实时观察机械臂。",
        "# 只在 policy 不为 None 时生效；手动录数据集（policy=None）完全不受影响。",
        "_LIVE_FRAME_DIR = r'D:\\LeRobot\\outputs\\live'",
        "_LIVE_SAVE_EVERY = 15          # 每多少帧存一张（30fps -> 2 张/秒）",
        "_LIVE_KEEP = 120              # 只在磁盘上保留最近多少张",
        "_live_frame_counter = 0",
        "",
        "",
    ]
)
src = src.replace(anchor, globals_block + anchor, 1)

# ---------- 2) record_loop 里插入存图 ----------
obs_anchor = "        observation = robot.get_observation()"
assert src.count(obs_anchor) == 1, "找不到 observation = robot.get_observation()"

inject = NL.join(
    [
        "        observation = robot.get_observation()",
        "",
        "        # [本地改动] 推理时落盘相机画面（供外部实时查看），不影响正常录制",
        "        if policy is not None:",
        "            global _live_frame_counter",
        "            _live_frame_counter += 1",
        "            if _LIVE_SAVE_EVERY and _live_frame_counter % _LIVE_SAVE_EVERY == 0:",
        "                try:",
        "                    import glob as _glob",
        "                    import os as _os",
        "",
        "                    import cv2 as _cv2",
        "",
        "                    _img = None",
        "                    for _k in ('observation.images.front', 'front'):",
        "                        if _k in observation:",
        "                            _img = observation[_k]",
        "                            break",
        "                    if _img is not None:",
        "                        _os.makedirs(_LIVE_FRAME_DIR, exist_ok=True)",
        '                        _cv2.imwrite(_os.path.join(_LIVE_FRAME_DIR, f"frame_{_live_frame_counter:06d}.jpg"), _img)',
        "                        if _LIVE_KEEP and _live_frame_counter % (_LIVE_SAVE_EVERY * 20) == 0:",
        '                            _files = sorted(_glob.glob(_os.path.join(_LIVE_FRAME_DIR, "frame_*.jpg")))',
        "                            for _f in _files[:-_LIVE_KEEP]:",
        '                                try:',
        "                                    _os.remove(_f)",
        "                                except OSError:",
        "                                    pass",
        "                except Exception:",
        "                    pass",
    ]
)
src = src.replace(obs_anchor, inject, 1)

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("补丁已应用")
print("  - 模块级: _LIVE_FRAME_DIR / _LIVE_SAVE_EVERY / _LIVE_KEEP / _live_frame_counter")
print("  - record_loop: observation 之后按守卫插入存图")
