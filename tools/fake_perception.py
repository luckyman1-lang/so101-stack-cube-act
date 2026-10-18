"""假感知数据生成器 —— M1（感知）的替身。

用途：队友 B 在 M2/M4/M5 阶段不需要等相机和标定，用这个生成符合
接口约定的物体位姿，直接把 M3 的状态机、M4 的仿真、M5 的训练跑起来。

约定（与 docs/PLAN_generalized_stacking.md §8.1 一致）：
  * 坐标系：**机械臂基座系**，单位米，右手系，Z 向上，桌面 = Z=0
  * 位置范围来自训练数据实测（stack_cube_v2 反推）：
        X 0.14~0.32   Y -0.16~0.04   Z ≈ 0（桌面）
  * 方块边长 30mm，抓取点取方块中心高度 z ≈ 0.015

用法：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" tools\\fake_perception.py
    ... --n 3 --seed 0                     3 个物体，固定随机种子
    ... --out fake_objs.json               写文件
    ... --cam                              额外给一组"相机坐标系"的值
                                           （用一条假设的外参，仅占位）

程序内用法：
    from tools.fake_perception import sample_scene
    scene = sample_scene(n=2, seed=0)
"""
import argparse
import json
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 训练数据实测的可抓取区域（末端 Z 最低那批帧的分布）
REACH_X = (0.14, 0.32)
REACH_Y = (-0.16, 0.04)
CUBE_MM = 30.0
TOP_Z = 0.030          # 方块顶面高度
GRASP_Z = 0.015        # 抓取点（方块高度中部）

# 一条**占位的**相机->基座外参（等 M0 标定后替换）
# 相机在基座前上方，光轴朝桌面
T_PLACEHOLDER = np.array([
    [1.0, 0.0, 0.0, -0.05],
    [0.0, 0.0, -1.0, 0.28],
    [0.0, 1.0, 0.0, 0.32],
    [0.0, 0.0, 0.0, 1.0],
])


def sample_scene(n: int = 1, seed=None, ensure_separation: float = 0.05) -> dict:
    """在可达区域内随机撒 n 个方块，返回标准接口结构。"""
    rng = np.random.default_rng(seed)
    objs = []
    tries = 0
    while len(objs) < n and tries < 2000:
        tries += 1
        x = float(rng.uniform(*REACH_X))
        y = float(rng.uniform(*REACH_Y))
        # 别和已有物体贴太近（否则真实抓取会互相干扰）
        if any(np.hypot(x - o["pos_base"][0], y - o["pos_base"][1]) < ensure_separation
               for o in objs):
            continue
        objs.append({
            "id": len(objs) + 1,
            "class": "RED" if len(objs) == 0 else "GREEN",
            "confidence": float(rng.uniform(0.85, 1.0)),
            "pos_base": [round(x, 4), round(y, 4), GRASP_Z],
            "top_z": TOP_Z,
            "size_mm": [CUBE_MM, CUBE_MM],
            "height_mm": CUBE_MM,
            "yaw_rad": 0.0,
            "depth_mad_mm": float(rng.uniform(1.5, 3.5)),
            "n_pixels": int(rng.integers(400, 1400)),
        })

    # 第一个当"目标块"（红），其余当"待抓取块"（绿）
    return {
        "source": "fake_perception (M1 替身，非真实相机数据)",
        "timestamp": None,
        "frame_id": "base",
        "objects": objs,
        "table_plane": {"normal": [0.0, 0.0, 1.0], "d": 0.0},
        "note": "pos_base = 机械臂基座系，米。pos_cam 需 M0 手眼外参才能填。",
    }


def to_cam_frame(scene: dict, T_base_cam=None) -> dict:
    """把 pos_base 转成 pos_cam（相机光学系 x右 y下 z前）。

    T_base_cam 是「相机->基座」的 4x4 变换；不传就用占位值。
    真正的值要 M0 用 ArUco 标定后写入 config/hand_eye.json。
    """
    T = np.eye(4) if T_base_cam is None else np.asarray(T_base_cam, dtype=float)
    T_inv = np.linalg.inv(T)
    out = json.loads(json.dumps(scene))
    for o in out["objects"]:
        p = np.array(o["pos_base"] + [1.0])
        pc = T_inv @ p
        o["pos_cam"] = [round(float(v), 4) for v in pc[:3]]
    out["note"] += " pos_cam 用的是【占位外参】，M0 标定后必须替换。"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default="")
    ap.add_argument("--cam", action="store_true", help="额外输出相机系坐标")
    ap.add_argument("--indent", type=int, default=2)
    args = ap.parse_args()

    scene = sample_scene(n=args.n, seed=args.seed)
    if args.cam:
        scene = to_cam_frame(scene)

    text = json.dumps(scene, ensure_ascii=False, indent=args.indent)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"已写入 {args.out}")
        print(f"  {len(scene['objects'])} 个物体: "
              f"{[o['class'] for o in scene['objects']]}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
