"""再给 record.py 加一处：每轮开始时存一张带轮次编号的起始帧。

输出：D:\\LeRobot\\outputs\\live_ep\\ep000_start.jpg, ep001_start.jpg, ...
这样跑 20 轮后就能把「第几轮」和「绿块在哪」对应起来，方便逐轮统计成功率。
"""

import io

P = r"D:\LeRobot\lerobot\src\lerobot\record.py"

src = io.open(P, "r", encoding="utf-8", newline="").read()
NL = "\r\n" if "\r\n" in src else "\n"

if "_LIVE_EP_DIR" in src:
    print("补丁已存在，跳过")
    raise SystemExit(0)

# 1) 追加常量（紧跟在已有的 _live_frame_counter 后面）
anchor = "_live_frame_counter = 0"
assert src.count(anchor) == 1, "找不到 _live_frame_counter 定义"
src = src.replace(
    anchor,
    anchor + NL + "_LIVE_EP_DIR = r'D:\\LeRobot\\outputs\\live_ep'  # 每轮起始帧",
    1,
)

# 2) 每轮开始（log_say Recording episode 之后）存一张
anchor2 = '        log_say(f"Recording episode {dataset.num_episodes}", cfg.play_sounds)'
assert src.count(anchor2) == 1, "找不到 log_say(Recording episode ...)"

inject = NL.join(
    [
        anchor2,
        "",
        "        # [本地改动] 每轮开始时存一张起始帧（带轮次编号），方便事后逐轮核对点位",
        "        try:",
        "            import os as _os_ep",
        "",
        "            import cv2 as _cv2_ep",
        "",
        "            _obs_ep = robot.get_observation()",
        "            _img_ep = None",
        "            for _k_ep in ('observation.images.front', 'front'):",
        "                if _k_ep in _obs_ep:",
        "                    _img_ep = _obs_ep[_k_ep]",
        "                    break",
        "            if _img_ep is not None:",
        "                _os_ep.makedirs(_LIVE_EP_DIR, exist_ok=True)",
        '                _cv2_ep.imwrite(_os_ep.path.join(_LIVE_EP_DIR, f"ep{dataset.num_episodes:03d}_start.jpg"), _img_ep)',
        "        except Exception:",
        "            pass",
    ]
)
src = src.replace(anchor2, inject, 1)

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("补丁已应用")
