"""分析一次 20 轮评测：逐轮判定绿块起始点位 + 是否叠放成功。

数据来源：
  * 起始帧：outputs/live_ep/epNNN_start.jpg（record.py 补丁存的）
  * 结束帧：datasets/<run>/videos/**/*.mp4 的最后一帧

检测策略（避开背景干扰）：
  先用白纸的高亮低饱和区域定 ROI，只在 ROI 内找红块/绿块。
"""

from __future__ import annotations

import sys
from pathlib import Path

import av
import cv2
import numpy as np

EP_DIR = Path(r"D:\LeRobot\outputs\live_ep")


def paper_roi(hsv):
    """返回白纸的包围盒 (x, y, w, h)；找不到就返回全图。"""
    paper = cv2.inRange(hsv, np.array([0, 0, 140], np.uint8), np.array([180, 55, 255], np.uint8))
    paper = cv2.morphologyEx(paper, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    cnts, _ = cv2.findContours(paper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 20000:
        return None
    return cv2.boundingRect(c)


def find_blob(img, roi, ranges, min_area=250, max_area=30000):
    x, y, w, h = roi
    sub = img[y : y + h, x : x + w]
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cnts:
        a = cv2.contourArea(c)
        if a < min_area or a > max_area:
            continue
        m = cv2.moments(c)
        if m["m00"] == 0:
            continue
        cx, cy = int(m["m10"] / m["m00"]) + x, int(m["m01"] / m["m00"]) + y
        if best is None or a > best[2]:
            best = (cx, cy, a)
    return best


RED_RANGES = [((0, 100, 60), (12, 255, 255)), ((168, 100, 60), (180, 255, 255))]
GREEN_RANGES = [((35, 70, 40), (85, 255, 255))]


def grab_last(mp4: Path):
    with av.open(str(mp4)) as c:
        st = c.streams.video[0]
        last = None
        for fr in c.decode(st):
            last = fr
        if last is None:
            return None
        return last.to_ndarray(format="bgr24")


def classify(g, r):
    """根据绿块相对红块的位置给出方位描述。"""
    dx, dy = g[0] - r[0], g[1] - r[1]
    hx = "左" if dx < -25 else ("右" if dx > 25 else "中")
    # 图像 y 越小 = 离相机越远
    vy = "后" if dy < -25 else ("前" if dy > 25 else "中")
    return hx + vy, (dx * dx + dy * dy) ** 0.5


def main(run_dir: str):
    vids = sorted(Path(run_dir).glob("videos/**/*.mp4"))
    starts = sorted(EP_DIR.glob("ep*_start.jpg"))
    print(f"起始帧 {len(starts)} 张，视频 {len(vids)} 个")
    print()
    hdr = f"{'轮':<5}{'绿块起始':>12}{'红块':>11}{'方位':>7}{'距px':>6}{'结束绿块':>12}{'末距':>6}  结果"
    print(hdr)
    print("-" * len(hdr) * 2)

    stats = {"成功": 0, "失败": 0}
    by_pos = {}

    n = min(len(starts), len(vids))
    for i in range(n):
        s_img = cv2.imread(str(starts[i]))
        e_img = grab_last(vids[i])
        if s_img is None or e_img is None:
            print(f"{i:<5} 读取失败")
            continue

        roi = paper_roi(cv2.cvtColor(s_img, cv2.COLOR_BGR2HSV))
        if roi is None:
            x, y, w, h = 0, 120, s_img.shape[1], 300
        else:
            x, y, w, h = roi
        roi_e = paper_roi(cv2.cvtColor(e_img, cv2.COLOR_BGR2HSV)) or (0, 120, e_img.shape[1], 300)

        gs = find_blob(s_img, roi, GREEN_RANGES)
        rs = find_blob(s_img, roi, RED_RANGES)
        ge = find_blob(e_img, roi_e, GREEN_RANGES)
        re_ = find_blob(e_img, roi_e, RED_RANGES)

        if not gs or not rs:
            print(f"{i:<5}  起始没检测到 绿={gs} 红={rs}")
            continue

        pos, d0 = classify(gs, rs)

        if ge and re_:
            de = ((ge[0] - re_[0]) ** 2 + (ge[1] - re_[1]) ** 2) ** 0.5
            # 成功判据：绿块中心离红块中心足够近（叠在上面），且比红块高（y 更小）
            ok = de < 70 and ge[1] <= re_[1] + 15
            res = "✅ 成功" if ok else "❌ 失败"
        else:
            de, res = -1, "❌ 未检出"

        stats["成功" if "成功" in res else "失败"] += 1
        by_pos.setdefault(pos, [0, 0])
        by_pos[pos][0 if "成功" in res else 1] += 1

        print(
            f"{i:<5}{str(gs):>12}{str(rs):>11}{pos:>7}{int(d0):>6}"
            f"{str(ge) if ge else '?':>12}{int(de) if de >= 0 else -1:>6}  {res}"
        )

    print()
    total = stats["成功"] + stats["失败"]
    if total:
        print(f"总体成功率: {stats['成功']}/{total} = {stats['成功'] / total * 100:.0f}%")
    print()
    print("按起始方位统计（方位 = 绿块相对红块）:")
    for pos, (ok, bad) in sorted(by_pos.items(), key=lambda kv: -(kv[1][0] + kv[1][1])):
        tot = ok + bad
        print(f"  {pos:<4} 成功 {ok}/{tot}  ({ok / tot * 100:.0f}%)")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main(sys.argv[1] if len(sys.argv) > 1 else r"D:\LeRobot\datasets\eval_stack_cube_v2_points20")
