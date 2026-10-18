"""把数据集和模型上传到 HuggingFace Hub。

前置：
    pip install -U huggingface_hub
    hf auth login            # 或者 set HF_TOKEN=hf_xxx

用法：
    python _setup/upload_to_hf.py --user 你的HF用户名            # 全传
    python _setup/upload_to_hf.py --user 名字 --only model       # 只传模型
    python _setup/upload_to_hf.py --user 名字 --only dataset     # 只传数据集
    python _setup/upload_to_hf.py --user 名字 --dry-run          # 只看会传什么

说明：
  * 模型只传 pretrained_model（config.json + model.safetensors），
    不传 optimizer state，省 400 MB。
  * 数据集用 LeRobotDataset.push_to_hub，自动处理 meta/data/videos 结构和 LFS。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DATASET_DIR = Path(r"D:\LeRobot\datasets\stack_cube_v2")
EVAL_DIR = Path(r"D:\LeRobot\datasets\eval_stack_cube_v2_points20")
CKPT = Path(r"D:\LeRobot\outputs\train\stack_cube_v2\checkpoints\050000\pretrained_model")


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def check_auth():
    from huggingface_hub import HfApi

    api = HfApi()
    try:
        who = api.whoami()
        print(f"  已登录: {who.get('name')}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  未登录或网络不通: {type(exc).__name__}: {str(exc)[:120]}")
        print("  先执行:  hf auth login    （或设置环境变量 HF_TOKEN）")
        return False


def upload_model(user: str, repo_name: str, dry: bool):
    from huggingface_hub import HfApi

    repo_id = f"{user}/{repo_name}"
    print(f"\n[模型] {repo_id}")
    print(f"  来源: {CKPT}")
    if not CKPT.exists():
        print("  [X] 目录不存在")
        return False
    for f in sorted(CKPT.iterdir()):
        print(f"    {f.name:<24} {human(f.stat().st_size)}")
    total = dir_size(CKPT)
    print(f"  合计: {human(total)}")

    if dry:
        print("  (dry-run，跳过上传)")
        return True

    api = HfApi()
    api.create_repo(repo_id=repo_id, repo_type="model", exist_ok=True)
    api.upload_folder(
        folder_path=str(CKPT),
        repo_id=repo_id,
        repo_type="model",
        commit_message="ACT policy trained on SO-101 stacking (50k steps, 80% success)",
    )
    print(f"  完成: https://huggingface.co/{repo_id}")
    return True


def upload_dataset(user: str, repo_name: str, src: Path, dry: bool):
    repo_id = f"{user}/{repo_name}"
    print(f"\n[数据集] {repo_id}")
    print(f"  来源: {src}")
    if not src.exists():
        print("  [X] 目录不存在")
        return False
    total = dir_size(src)
    n_parquet = len(list(src.rglob("*.parquet")))
    n_mp4 = len(list(src.rglob("*.mp4")))
    print(f"  {n_parquet} 轮 / {n_mp4} 视频 / {human(total)}")

    if dry:
        print("  (dry-run，跳过上传)")
        return True

    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    # local/<name> 形式读回本地数据集，再推上去
    ds = LeRobotDataset(repo_id=f"local/{src.name}", root=str(src))
    ds.push_to_hub(repo_id=repo_id, private=False)
    print(f"  完成: https://huggingface.co/datasets/{repo_id}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True, help="你的 HuggingFace 用户名")
    ap.add_argument("--only", choices=["all", "model", "dataset"], default="all")
    ap.add_argument("--model-name", default="so101-stack-cube-act")
    ap.add_argument("--dataset-name", default="so101-stack-cube-100ep")
    ap.add_argument("--eval-dataset-name", default="so101-stack-cube-eval-20ep")
    ap.add_argument("--no-eval", action="store_true", help="不传 eval 评测数据")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=" * 66)
    print("  上传到 HuggingFace Hub")
    print("=" * 66)

    if not args.dry_run and not check_auth():
        return 1

    ok = True
    if args.only in ("all", "model"):
        ok = upload_model(args.user, args.model_name, args.dry_run) and ok
    if args.only in ("all", "dataset"):
        ok = upload_dataset(args.user, args.dataset_name, DATASET_DIR, args.dry_run) and ok
        if not args.no_eval and EVAL_DIR.exists():
            ok = upload_dataset(args.user, args.eval_dataset_name, EVAL_DIR, args.dry_run) and ok

    print()
    print("完成" if ok else "有失败项")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
