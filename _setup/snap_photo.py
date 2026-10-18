"""拍照小工具：能开关自动白平衡 / 自动曝光，用来排查「画面偏蓝」这类问题。

用法：
    python _setup/snap_photo.py                      # 默认拍一张（自动白平衡）
    python _setup/snap_photo.py --no-awb             # 关自动白平衡（固定色温）
    python _setup/snap_photo.py --no-awb --no-ae     # 白平衡和曝光都固定
    python _setup/snap_photo.py --temp 4600          # 指定色温（单位 K）
    python _setup/snap_photo.py --burst 5            # 连拍 5 张
    python _setup/snap_photo.py --index 1 --warmup 30 # 指定相机索引 / 预热帧数
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

OUT_DIR = Path(r"D:\LeRobot\_setup\cam_snapshots")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=1, help="相机索引（Orbbec 是 1）")
    ap.add_argument("--backend", default="DSHOW", choices=["DSHOW", "MSMF", "ANY"])
    ap.add_argument("--warmup", type=int, default=20, help="正式拍之前先读多少帧让 AWB/AE 稳定")
    ap.add_argument("--no-awb", action="store_true", help="关闭自动白平衡")
    ap.add_argument("--no-ae", action="store_true", help="关闭自动曝光")
    ap.add_argument("--temp", type=int, default=0, help="色温（K），配合 --no-awb 使用")
    ap.add_argument("--burst", type=int, default=1, help="连拍张数")
    ap.add_argument("--tag", default="snap", help="文件名前缀")
    args = ap.parse_args()

    backend = {"DSHOW": cv2.CAP_DSHOW, "MSMF": cv2.CAP_MSMF, "ANY": cv2.CAP_ANY}[args.backend]
    cap = cv2.VideoCapture(args.index, backend)
    if not cap.isOpened():
        print(f"[X] 相机索引 {args.index} 打不开（{args.backend}）")
        print("    需要管理员权限的 PowerShell 才能打开 Orbbec")
        return 1

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # 白平衡 / 曝光控制（不同相机驱动支持程度不同，失败就跳过）
    def try_set(prop, value, name):
        ok = cap.set(prop, value)
        cur = cap.get(prop)
        print(f"  {name}: set({value}) -> {ok}  当前值 {cur}")

    if args.no_awb:
        try_set(cv2.CAP_PROP_AUTO_WB, 0, "自动白平衡")
        if args.temp:
            try_set(cv2.CAP_PROP_WB_TEMPERATURE, args.temp, "色温")
    if args.no_ae:
        try_set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25, "自动曝光")  # DSHOW: 0.25 = 手动

    print(f"  预热 {args.warmup} 帧 ...")
    for _ in range(args.warmup):
        cap.read()
        time.sleep(0.01)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved = []
    for i in range(args.burst):
        ret, frame = cap.read()
        if not ret:
            print(f"  [X] 第 {i+1} 张读取失败")
            continue
        name = f"{args.tag}_{stamp}" + (f"_{i+1}" if args.burst > 1 else "") + ".png"
        path = OUT_DIR / name
        cv2.imwrite(str(path), frame)
        saved.append(path)
        # 顺便报一下画面平均色（判断偏色）
        b, g, r = frame.mean(axis=(0, 1))
        print(f"  [OK] {name}   平均 B/G/R = {b:.1f}/{g:.1f}/{r:.1f}")
        if args.burst > 1:
            time.sleep(0.3)

    cap.release()
    if saved:
        print()
        print("保存路径:")
        for p in saved:
            print("  " + str(p))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
