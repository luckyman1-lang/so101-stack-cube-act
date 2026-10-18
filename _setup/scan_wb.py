"""色温扫描：关掉自动白平衡后，逐个色温拍一张，报告红块色相 H。

用法（需要管理员 PowerShell）：
    python _setup/scan_wb.py
    python _setup/scan_wb.py --temps 4000 4600 5200 5800 6400

目标：找到让红块 H 接近 21（录制时的值）的那个色温。
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

OUT = Path(r"D:\LeRobot\_setup\cam_snapshots\wb")


def red_hue(img):
    """返回画面中心区域里最像"红块"的那块的主色相（H）。"""
    h, w = img.shape[:2]
    # 只看纸面区域（中间偏上），避开桌面和背景
    roi = img[int(h * 0.30) : int(h * 0.75), int(w * 0.25) : int(w * 0.80)]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # 高饱和的块（红/紫蓝都算，我们要看它的 H 到底是多少）
    mask = cv2.inRange(hsv, np.array([0, 80, 40], np.uint8), np.array([180, 255, 255], np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None, None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 400:
        return None, None
    x, y, ww, hh = cv2.boundingRect(c)
    sub = hsv[y : y + hh, x : x + ww]
    pix = sub.reshape(-1, 3)
    med_h = float(np.median(pix[:, 0]))
    med_s = float(np.median(pix[:, 1]))
    return med_h, med_s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=1)
    ap.add_argument("--temps", type=int, nargs="+", default=[4000, 4600, 5200, 5800, 6400, 7000])
    ap.add_argument("--warmup", type=int, default=25)
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("[X] 相机打不开（需要管理员 PowerShell）")
        return 1
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # 先关自动白平衡
    ok = cap.set(cv2.CAP_PROP_AUTO_WB, 0)
    print(f"关闭自动白平衡: {ok}")
    print(f"当前 CAP_PROP_WB_TEMPERATURE = {cap.get(cv2.CAP_PROP_WB_TEMPERATURE)}")
    print()

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")

    print(f"{'色温':>6} {'set':>5} {'回读':>8} {'红块H':>7} {'S':>5}  判定")
    print("-" * 50)
    results = []
    for t in args.temps:
        ok = cap.set(cv2.CAP_PROP_WB_TEMPERATURE, float(t))
        for _ in range(args.warmup):
            cap.read()
            time.sleep(0.008)
        ret, frame = cap.read()
        if not ret:
            print(f"{t:>6} {str(ok):>5}   读取失败")
            continue
        back = cap.get(cv2.CAP_PROP_WB_TEMPERATURE)
        h, s = red_hue(frame)
        path = OUT / f"wb_{stamp}_{t}K.png"
        cv2.imwrite(str(path), frame)
        if h is None:
            verdict = "没检测到块"
        elif h < 15 or h > 165:
            verdict = "✅ 红（正常）"
        elif 15 <= h <= 35:
            verdict = "偏橙"
        elif 80 <= h <= 130:
            verdict = "❌ 偏蓝"
        else:
            verdict = "其他"
        hs = f"{h:.0f}" if h is not None else "?"
        ss = f"{s:.0f}" if s is not None else "?"
        print(f"{t:>6} {str(ok):>5} {back:>8.0f} {hs:>7} {ss:>5}  {verdict}")
        if h is not None:
            results.append((t, h))

    cap.release()
    print()
    print(f"图片已存到 {OUT}")
    if results:
        best = min(results, key=lambda kv: min(abs(kv[1]), abs(kv[1] - 180)))
        print(f"最接近红色的色温: {best[0]}K (H={best[1]:.0f})")
        print("参考：录制数据时红块 H≈21（橙红）")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
