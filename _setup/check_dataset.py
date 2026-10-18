"""检查刚录制的 LeRobot 数据集：结构 / 元数据 / 帧数 / 动作分布 / 画面抽样。"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"D:\LeRobot\datasets\stack_cube_v1")
SNAP = Path(r"D:\LeRobot\_setup\cam_snapshots")
SNAP.mkdir(parents=True, exist_ok=True)


def sec(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main() -> int:
    if not ROOT.exists():
        print(f"✗ 数据集目录不存在: {ROOT}")
        return 1

    # ---------- 1. 目录结构 ----------
    sec("一、目录结构")
    total = 0
    for p in sorted(ROOT.rglob("*")):
        if p.is_file():
            sz = p.stat().st_size
            total += sz
            rel = str(p.relative_to(ROOT))
            if sz > 1024 * 1024:
                print(f"  {rel:<60} {sz / 1024 / 1024:8.2f} MB")
            else:
                print(f"  {rel:<60} {sz / 1024:8.1f} KB")
    print(f"  {'总计':<60} {total / 1024 / 1024:8.2f} MB")

    # ---------- 2. 元数据 ----------
    sec("二、元数据 meta/info.json")
    info = json.loads((ROOT / "meta" / "info.json").read_text(encoding="utf-8"))
    for k in (
        "codebase_version", "robot_type", "total_episodes", "total_frames",
        "total_tasks", "total_videos", "total_chunks", "fps", "splits",
    ):
        if k in info:
            print(f"  {k:<18} {info[k]}")

    feats = info.get("features", {})
    print(f"\n  特征 ({len(feats)} 项):")
    for name, spec in feats.items():
        print(f"    {name:<34} dtype={spec.get('dtype')}  shape={spec.get('shape')}")

    # ---------- 3. parquet 数据 ----------
    sec("三、逐轮数据（parquet）")
    pq_files = sorted((ROOT / "data").rglob("*.parquet"))
    print(f"  parquet 文件数: {len(pq_files)}")
    if not pq_files:
        print("  ✗ 没有 parquet 文件！")
        return 1

    df0 = pd.read_parquet(pq_files[0])
    print(f"  列名: {list(df0.columns)}")

    total_rows = 0
    per_ep = []
    for f in pq_files:
        df = pd.read_parquet(f)
        total_rows += len(df)
        eps = sorted(int(x) for x in df["episode_index"].unique()) if "episode_index" in df.columns else [-1]
        per_ep.append((f.name, len(df), eps))
    for name, n, eps in per_ep:
        print(f"    {name:<32} {n:5d} 帧   episode_index={eps}")
    print(f"  合计 {total_rows} 帧")

    # ---------- 4. 动作/状态分布 ----------
    sec("四、动作 / 状态分布（判断各关节是否都动了）")
    df_all = pd.concat([pd.read_parquet(f) for f in pq_files], ignore_index=True)

    for col in ("action", "observation.state"):
        if col not in df_all.columns:
            continue
        arr = np.stack(df_all[col].values)
        if arr.ndim != 2:
            print(f"  {col}: 形状 {arr.shape}，跳过")
            continue
        print(f"\n  {col}  形状={arr.shape}")
        print(f"    {'关节':<6}{'min':>10}{'max':>10}{'跨度':>10}{'std':>10}  判定")
        for j in range(arr.shape[1]):
            lo, hi = float(arr[:, j].min()), float(arr[:, j].max())
            span = hi - lo
            std = float(arr[:, j].std())
            verdict = "OK" if span > 1.0 else "⚠ 几乎没动"
            print(f"    {j:<6}{lo:10.2f}{hi:10.2f}{span:10.2f}{std:10.2f}  {verdict}")

    # ---------- 5. 视频文件 ----------
    sec("五、视频文件")
    vids = sorted((ROOT / "videos").rglob("*.mp4"))
    print(f"  mp4 文件数: {len(vids)}")
    for v in vids:
        print(f"    {str(v.relative_to(ROOT)):<60} {v.stat().st_size / 1024 / 1024:8.2f} MB")

    # ---------- 6. 抽样看画面 ----------
    sec("六、抽样画面（从视频里取几帧）")
    try:
        import cv2

        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        ds = LeRobotDataset(repo_id="local/stack_cube_v1", root=str(ROOT))
        print(f"  LeRobotDataset 加载成功: {ds.num_episodes} 轮 / {ds.num_frames} 帧 / {ds.fps} fps")

        n = len(ds)
        picks = sorted({0, n // 4, n // 2, 3 * n // 4, n - 1})
        tiles = []
        for idx in picks:
            item = ds[idx]
            for key in item:
                if key.startswith("observation.images."):
                    t = item[key]
                    arr = t.permute(1, 2, 0).numpy()
                    if arr.dtype != np.uint8:
                        arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
                    tiles.append((idx, arr))
                    break
        if tiles:
            h, w = tiles[0][1].shape[:2]
            row = [np.hstack([t[1][:, :, ::-1] for t in tiles])]
            grid = np.vstack(row)
            out = SNAP / "dataset_samples.png"
            cv2.imwrite(str(out), grid)
            print(f"  抽样索引: {[t[0] for t in tiles]}")
            print(f"  拼图已存: {out}")
            for idx, arr in tiles:
                print(f"    索引 {idx:5d}: 画面均值 {arr.mean():6.1f}")
    except Exception as e:
        import traceback
        print(f"  抽样失败: {type(e).__name__}: {e}")
        traceback.print_exc()

    print()
    print("=" * 70)
    print("  检查完成")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
