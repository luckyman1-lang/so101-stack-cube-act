"""复刻 lerobot 的相机 connect 流程，逐步定位「色温设不进去」是哪一步的问题。

对应 camera_opencv.py 的 connect():
    cv2.setNumThreads(1)
    VideoCapture(index, DSHOW)
    set(FPS) / set(W,H)        <- _configure_capture_settings
    set(AUTO_WB, 0) / set(WB_TEMPERATURE)   <- 我们的补丁
    warmup: read() 若干帧

每一步之后都测一次红块色相，看哪一步把色温打回原形。
"""

from __future__ import annotations

import sys
import time

import cv2
import numpy as np

INDEX = 1
TEMP = 5800.0


def hue(img):
    h, w = img.shape[:2]
    roi = img[int(h * 0.30) : int(h * 0.75), int(w * 0.25) : int(w * 0.80)]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 80, 40], np.uint8), np.array([180, 255, 255], np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None, None
    c = max(cnts, key=cv2.contourArea)
    x, y, ww, hh = cv2.boundingRect(c)
    sub = hsv[y : y + hh, x : x + ww].reshape(-1, 3)
    return float(np.median(sub[:, 0])), float(np.median(sub[:, 1]))


def shot(cap, label, warm=0):
    for _ in range(warm):
        cap.read()
        time.sleep(0.01)
    for _ in range(5):
        cap.read()
    ret, frame = cap.read()
    if not ret:
        print(f"  {label:<38} 读取失败")
        return
    h, s = hue(frame)
    hs = f"{h:.0f}" if h is not None else "?"
    ss = f"{s:.0f}" if s is not None else "?"
    print(f"  {label:<38} H={hs:>5}  S={ss:>5}   wb_readback={cap.get(cv2.CAP_PROP_WB_TEMPERATURE):.0f}")


def main():
    print("复刻 lerobot connect 流程，逐步测色相")
    print("（目标 H≈21~24 = 正常红色；H≈95 = 偏蓝）")
    print()

    cv2.setNumThreads(1)
    cap = cv2.VideoCapture(INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("[X] 相机打不开（需要管理员 PowerShell）")
        return 1

    shot(cap, "0. 刚打开")

    cap.set(cv2.CAP_PROP_FPS, 30.0)
    shot(cap, "1. set(FPS,30) 之后")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640.0)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480.0)
    shot(cap, "2. set(640x480) 之后")

    ok_awb = cap.set(cv2.CAP_PROP_AUTO_WB, 0)
    shot(cap, f"3. set(AUTO_WB,0)={ok_awb} 之后")

    ok_t = cap.set(cv2.CAP_PROP_WB_TEMPERATURE, TEMP)
    shot(cap, f"4. set(WB_TEMP,{TEMP:.0f})={ok_t} 之后", warm=30)

    # 再设一次（有些驱动需要重复设）
    cap.set(cv2.CAP_PROP_WB_TEMPERATURE, TEMP)
    shot(cap, "5. 再 set(WB_TEMP) 一次 + 预热30", warm=30)

    # 试试先设色温再关 AWB
    cap.set(cv2.CAP_PROP_AUTO_WB, 1)
    time.sleep(0.3)
    cap.set(cv2.CAP_PROP_WB_TEMPERATURE, TEMP)
    cap.set(cv2.CAP_PROP_AUTO_WB, 0)
    shot(cap, "6. 先设色温再关AWB（AWB=1->设温->0）", warm=30)

    cap.release()
    print()
    print("结论：看哪一步之后 H 变成 20 左右，就是正确的设置顺序")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
