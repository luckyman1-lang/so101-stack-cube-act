"""统计所有 eval 数据集的成功率：逐轮判断绿块有没有叠到红块上。

判定方法（比之前可靠）：
  1. 从 mp4 解出每轮最后一帧（视频帧是标准 BGR）
  2. 用白纸 ROI 限定搜索范围，避免桌布/背景干扰
  3. 找红块和绿块，算中心距与相对高度
  4. 成功 = 绿块中心靠近红块，且比红块高（y 更小）

用法：
    python _setup/tally_eval.py
    python _setup/tally_eval.py --dataset eval_stack_cube_v2_points20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import av
import cv2
import numpy as np

DS_ROOT = Path(r"D:\LeRobot\datasets")


def paper_roi(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    paper = cv2.inRange(hsv, np.array([0, 0, 135], np.uint8), np.array([180, 60, 255], np.uint8))
    paper = cv2.morphologyEx(paper, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    cnts, _ = cv2.findContours(paper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 20000:
        return None
    return cv2.boundingRect(c)


def blob(bgr, roi, ranges, min_area=200, max_area=40000):
    x, y, w, h = roi
    sub = bgr[y : y + h, x : x + w]
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
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


RED = [((0, 110, 60), (12, 255, 255)), ((168, 110, 60), (180, 255, 255))]
GREEN = [((35, 80, 40), (85, 255, 255))]


def last_frame(mp4: Path):
    with av.open(str(mp4)) as c:
        st = c.streams.video[0]
        last = None
        for fr in c.decode(st):
            last = fr
        return last.to_ndarray(format="bgr24") if last is not None else None


def judge(bgr):
    """返回 (是否成功, 说明)。"""
    roi = paper_roi(bgr)
    if roi is None:
        h, w = bgr.shape[:2]
        roi = (int(w * 0.15), int(h * 0.28), int(w * 0.75), int(h * 0.55))
    g = blob(bgr, roi, GREEN)
    r = blob(bgr, roi, RED)
    if g is None or r is None:
        return None, f"检测失败(绿={g is not None}, 红={r is not None})"
    dist = ((g[0] - r[0]) ** 2 + (g[1] - r[1]) ** 2) ** 0.5
    # 叠上去时绿块中心接近红块中心，且明显更靠上（y 更小）
    ok = dist < 60 and g[1] < r[1] - 5
    return ok, f"距{dist:.0f}px dy={g[1] - r[1]:+d}"


def tally(ds: Path):
    vids = sorted(ds.glob("videos/**/*.mp4"))
    if not vids:
        print(f"  {ds.name}: 没有视频")
        return None
    ok = bad = unk = 0
    rows = []
    for i, v in enumerate(vids):
        img = last_frame(v)
        if img is None:
            rows.append((i, None, "读取失败"))
            unk += 1
            continue
        res, note = judge(img)
        if res is None:
            unk += 1
        elif res:
            ok += 1
        else:
            bad += 1
        rows.append((i, res, note))
    total = ok + bad
    rate = ok / total * 100 if total else 0
    print(f"  {ds.name}")
    print(f"    轮数 {len(vids)}   成功 {ok}   失败 {bad}   无法判定 {unk}   成功率 {rate:.0f}%")
    fails = [i for i, r, _ in rows if r is False]
    if fails:
        print(f"    失败轮次: {fails}")
    return dict(name=ds.name, episodes=len(vids), ok=ok, bad=bad, unk=unk, rate=rate)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="")
    args = ap.parse_args()

    if args.dataset:
        candidates = [DS_ROOT / args.dataset]
    else:
        candidates = [d for d in sorted(DS_ROOT.iterdir()) if (d / "videos").exists()]

    print("=" * 68)
    print("  评测成功率统计")
    print("=" * 68)
    results = []
    for d in candidates:
        if not d.is_dir():
            continue
        r = tally(d)
        if r:
            results.append(r)
        print()

    real = [r for r in results if r["name"].startswith("eval")]
    if real:
        tot_ok = sum(r["ok"] for r in real)
        tot = sum(r["ok"] + r["bad"] for r in real)
        print("=" * 68)
        print(f"  所有 eval 运行合计: {tot_ok}/{tot} = {tot_ok / tot * 100:.0f}%")
        print("=" * 68)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
