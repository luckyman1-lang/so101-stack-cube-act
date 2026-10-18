"""从 stack_cube_v2 的 100 轮里抽样抽帧，拼成一张网格图，用来肉眼检查数据质量。

用法：
    python _setup/sample_dataset_frames.py            # 抽 12 轮
    python _setup/sample_dataset_frames.py --n 16
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import av
import cv2
import numpy as np

ROOT = Path(r"D:\LeRobot\datasets\stack_cube_v2")
OUT = Path(r"D:\LeRobot\_setup\cam_snapshots\dataset_samples.png")

CAM_KEY = "observation.images.front"


def list_videos():
    vids = {}
    for p in sorted((ROOT / "videos").rglob("*.mp4")):
        # videos/<cam>/chunk-000/episode_000000.mp4
        ep = int(p.stem.split("_")[-1])
        vids[ep] = p
    return vids


def grab_frame(path: Path, which: str = "middle") -> np.ndarray | None:
    try:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            total = stream.frames or 0
            if which == "first":
                target = 0
            elif which == "last":
                target = max(total - 1, 0)
            else:
                target = total // 2 if total else 0
            idx = 0
            for frame in container.decode(stream):
                if idx >= target:
                    img = frame.to_ndarray(format="bgr24")
                    return img
                idx += 1
            # 没到 target 就取最后一帧
            return img if idx else None
    except Exception as exc:  # noqa: BLE001
        print(f"  [{path.name}] 读取失败: {type(exc).__name__}: {exc}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="抽多少轮")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    vids = list_videos()
    if not vids:
        print(f"在 {ROOT/'videos'} 下没找到 mp4")
        return

    eps = sorted(vids)
    pick = [eps[round(i * (len(eps) - 1) / max(args.n - 1, 1))] for i in range(args.n)]
    pick = sorted(set(pick))
    print(f"共 {len(eps)} 轮，抽 {len(pick)} 轮: {pick}")

    tiles = []
    labels = []
    for ep in pick:
        img = grab_frame(vids[ep], "middle")
        if img is None:
            continue
        tile = cv2.resize(img, (320, 240), interpolation=cv2.INTER_AREA)
        cv2.putText(tile, f"ep {ep}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        tiles.append(tile)
        labels.append(ep)

    if not tiles:
        print("一帧都没抽到")
        return

    cols = min(args.cols, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    grid = np.zeros((rows * 240, cols * 320, 3), np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        grid[r * 240 : (r + 1) * 240, c * 320 : (c + 1) * 320] = t

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), grid)
    print(f"拼图已保存: {out}  ({cols}x{rows} 张)")

    # 顺便在每帧里检测绿块/红块，判断位置是否真的有差异
    print()
    print("各抽样的绿块/红块位置（看点位是否真的不同）:")
    for ep in labels:
        img = grab_frame(vids[ep], "middle")
        if img is None:
            continue
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        out_parts = []
        for name, lo, hi in (
            ("红", (0, 80, 50), (12, 255, 255)),
            ("绿", (30, 35, 20), (95, 255, 255)),
        ):
            mask = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                out_parts.append(f"{name}: 未检测到")
                continue
            c = max(cnts, key=cv2.contourArea)
            if cv2.contourArea(c) < 150:
                out_parts.append(f"{name}: 太小")
                continue
            m = cv2.moments(c)
            out_parts.append(f"{name}({int(m['m10'] / m['m00'])},{int(m['m01'] / m['m00'])})")
        print(f"  ep {ep:>3}: " + "  ".join(out_parts))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
