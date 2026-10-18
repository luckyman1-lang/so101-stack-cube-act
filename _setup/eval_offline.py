"""离线评估：用训练好的 ACT 在数据集上预测动作，和真实动作对比。

这不是"验证集精度"（我们的数据全用于训练），而是检查：
  * 模型能否在任意帧给出合理的动作（不是只会头几帧）
  * 动作序列是否平滑（相邻预测的抖动 = 推理时会抖）
  * 各关节的预测误差分布

用法：
    python _setup/eval_offline.py
    python _setup/eval_offline.py --episodes 8 --frames 6
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

POLICY = Path(
    r"D:\LeRobot\outputs\train\stack_cube_v2\checkpoints\last\pretrained_model"
)
DATASET_ROOT = Path(r"D:\LeRobot\datasets\stack_cube_v2")
REPO_ID = "local/stack_cube_v2"

JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=6, help="抽多少轮")
    ap.add_argument("--frames", type=int, default=5, help="每轮抽多少帧（等间隔）")
    args = ap.parse_args()

    print("加载数据集 ...")
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    ds = LeRobotDataset(REPO_ID, root=str(DATASET_ROOT))
    print(f"  {ds.num_episodes} 轮 / {ds.num_frames} 帧")

    print("加载模型 ...")
    # 不能用 ACTPolicy.from_pretrained：
    # lerobot 的 PreTrainedConfig.from_pretrained 在 Windows 上会先开一个独占的
    # tempfile.NamedTemporaryFile，再把文件名交给 draccus 去 open 读 -> 必然
    # PermissionError [Errno 13]。这里直接用 config.json + safetensors 手工装配。
    import json as _json

    import draccus
    from safetensors.torch import load_file
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy

    cfg_dict = _json.loads((POLICY / "config.json").read_text(encoding="utf-8"))
    cfg_dict.pop("type", None)
    with draccus.config_type("json"):
        config = draccus.decode(ACTConfig, cfg_dict)
    policy = ACTPolicy(config)
    state = load_file(str(POLICY / "model.safetensors"))
    missing, unexpected = policy.load_state_dict(state, strict=False)
    if missing:
        print(f"  ⚠ 缺失权重 {len(missing)} 项: {missing[:3]}")
    if unexpected:
        print(f"  ⚠ 多余权重 {len(unexpected)} 项: {unexpected[:3]}")
    policy.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    policy.to(device)
    print(f"  设备 {device}  权重 {len(state)} 个张量")

    # 找出每轮在数据集里的帧索引范围
    import json

    info = json.loads((DATASET_ROOT / "meta" / "info.json").read_text(encoding="utf-8"))
    chunks = info.get("chunks_size", 1000)
    ep_meta = info.get("episodes")
    print()
    print(f"{'轮':>4} {'帧':>5} {'MSE':>9} {'MAE':>8}  各关节 MAE（{', '.join(j[:4] for j in JOINTS)}）")
    print("-" * 100)

    eps = list(range(0, ds.num_episodes, max(1, ds.num_episodes // args.episodes)))[: args.episodes]
    all_err = []
    per_joint = [[] for _ in JOINTS]

    for ep in eps:
        # 该轮的全局帧索引范围：用 dataset 的 episode_data_index 更稳妥
        try:
            idx = ds.episode_data_index["from"][ep].item(), ds.episode_data_index["to"][ep].item()
        except Exception:
            continue
        lo, hi = idx
        n = hi - lo
        picks = [lo + int(n * (k + 1) / (args.frames + 1)) for k in range(args.frames)]

        errs = []
        for gi in picks:
            if gi >= hi:
                continue
            item = ds[int(gi)]
            # 只把 observation.* 喂给模型：推理时不该有 action（ACT 的 VAE encoder
            # 只在训练时用 batch["action"]，且形状是 (B, chunk_size, D)）。
            batch = {}
            for k, v in item.items():
                if isinstance(v, torch.Tensor) and k.startswith("observation"):
                    batch[k] = v.unsqueeze(0).to(device)
            true_raw = item.get("action")
            if true_raw is None:
                continue
            true = true_raw.unsqueeze(0).to(device)
            with torch.no_grad():
                # 不能用 select_action：它内部有 action queue，第一次预测出 100 步
                # chunk 后，后续调用直接出队而不重新预测。评估时每帧都是独立状态，
                # 必须每次重新前向，所以取 predict_action_chunk 的第 0 步。
                chunk = policy.predict_action_chunk(batch)  # (1, chunk_size, D)
                pred = chunk[:, 0]  # (1, D)
            n_dim = min(pred.shape[1], true.shape[1])
            e = (pred[:, :n_dim] - true[:, :n_dim]).abs().cpu().numpy()[0]
            errs.append(e)
            for j in range(min(len(JOINTS), e.shape[0])):
                per_joint[j].append(float(e[j]))

        if not errs:
            continue
        E = np.stack(errs)
        mse = float((E ** 2).mean())
        mae = float(E.mean())
        all_err.append(E)
        detail = " ".join(f"{x:5.1f}" for x in E.mean(axis=0)[: len(JOINTS)])
        print(f"{ep:>4} {len(errs):>5} {mse:>9.4f} {mae:>8.4f}  {detail}")

    if not all_err:
        print("没有成功评估任何帧")
        return

    E = np.concatenate(all_err, axis=0)
    print("-" * 100)
    print(f"总体   {len(E)} 帧   MSE {float((E**2).mean()):.4f}   MAE {float(E.mean()):.4f}")
    print()
    print("各关节 MAE（动作空间是归一化后的 -100~100 量级）:")
    for j, name in enumerate(JOINTS):
        if j < E.shape[1]:
            v = E[:, j]
            print(f"  {name:<14} MAE {float(v.mean()):6.2f}   P90 {float(np.percentile(v, 90)):6.2f}   max {float(v.max()):6.2f}")
    print()
    print("参考：动作范围约 200（-100~100），MAE < 5 算贴合，> 15 说明这一帧学得不好")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
