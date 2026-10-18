# M2 运动学 · 启动包（给 B）

> 配套总计划：[PLAN_generalized_stacking.md](./PLAN_generalized_stacking.md) §6.2 M2
> 最后更新 2026-10-18 ｜ 状态：**代码已完成并通过自检，等队友接手扩展**

---

## 0. 一句话

你要做的事：**把「末端要去的三维点」翻译成「6 个舵机该转到多少度」，并且保证轨迹安全**。
代码骨架我已经写好并通过验证，你接手做扩展（安全层、真机对接、参数调优）。

---

## 1. 你需要什么

**不需要机械臂，不需要相机，不需要管理员权限。** 一台笔记本就够。

```powershell
# 只需要这一个包
& "D:\LeRobot\_tools\python310\python.exe" -m pip install mujoco
```

如果还没有仓库：整个 `D:\LeRobot` 目录拷给你的那一份里已经包含：

```
assets/so101_sim/          SO-101 官方 MJCF + URDF + 18 个 STL（19MB）
config/calibration_follower.json   从臂校准数据（行程限位）
kin/                       运动学模块（已写好）
tools/fake_perception.py   假感知数据生成器
```

**⚠️ 不要试图装 placo / pinocchio** —— 这两个是 LeRobot 官方 IK 的依赖，但它们在 Windows 上需要源码编译，实测装不上（`Failed to build 'pin'`）。所以 IK 是我们自己用 MuJoCo 雅可比写的。

---

## 2. 已经给你准备好的（不用重复劳动）

| 文件 | 作用 | 状态 |
|---|---|---|
| `kin/calibration.py` | 归一化值 ↔ 弧度换算 | ✅ 往返一致 |
| `kin/so101_model.py` | 加载 MJCF、FK、6×6 雅可比 | ✅ 已验证 |
| `kin/so101_ik.py` | DLS IK、增量式跟踪、轨迹插值 | ✅ 已验证 |
| `kin/verify_fk_ik.py` | 自检脚本（你的验收工具） | ✅ 全部通过 |
| `tools/fake_perception.py` | 假物体位姿，不用等相机 | ✅ |

**核心数字（实测，直接信）**

| 项 | 值 |
|---|---|
| 末端 IK 精度 | 中位 **0.075 mm**，max 0.100 mm |
| 抓取位姿收敛 | 8/8，位置误差 < 0.1mm |
| 增量式跟踪（30 点） | 0 失败，中位 0.028mm，关节跳变 1.51° |
| 真机可达区域 | X 0.14~0.32，Y −0.16~0.04，Z ≈ 0（米，基座系） |

---

## 3. 立刻验证（5 分钟）

在 `D:\LeRobot` 下：

```powershell
# 1. 换算层自检
& "D:\LeRobot\_tools\python310\python.exe" kin\calibration.py

# 2. 完整 M2 自检（这是你的验收脚本）
& "D:\LeRobot\_tools\python310\python.exe" -m kin.verify_fk_ik

# 3. 生成假感知数据
& "D:\LeRobot\_tools\python310\python.exe" tools\fake_perception.py --n 3 --seed 0
```

第 2 条最后一行应该是 `✅ 全部通过`。如果不是，先排查环境再往下做。

---

## 4. 三个已经踩过的坑（**必读**，不读会重复踩 2 天）

### 坑 1：不能用 MJCF 的关节 range 做换算

MJCF 的 range 是 CAD 理论值，真机行程是校准实测的，两者差得不少：

| 关节 | 校准换算出的真实角度 | MJCF 写的 | 差异 |
|---|---|---|---|
| shoulder_pan | ±111.0° | ±110.0° | 1° |
| **shoulder_lift** | **±104.0°** | **±100.0°** | **4°** ⚠️ |
| elbow_flex | ±96.8° | ±96.8° | 0° |
| wrist_flex | ±94.5° | ±95.0° | 0.5° |
| wrist_roll | ±167.6° | −157°~163° | 10° |
| **gripper** | **±63.0°** | **−10°~100°** | **73°** ❌ |

`shoulder_lift` 差 4° 在 20cm 臂展上就是 **14mm 末端误差**，直接把 IK 的 3mm 目标打破。

**正解**：弧度换算只用 `config/calibration_follower.json` 里的 `range_min/range_max`，MJCF 只提供连杆几何。`kin/calibration.py` 已经这么做了。

### 坑 2：SO-101 不是"夹爪竖直向下"抓取的

我最初的 IK 约束了 `site z 轴 = -Z`（竖直向下），结果**怎么调都差 15~53 度**。

后来用训练数据做 FK 反推才发现：

```
真机抓取时刻，site z 轴与「竖直向下的夹角」：中位 95°，p5~p95 = 92~98°
夹角 < 45° 的帧占比：0.0%
```

**SO-101 是水平前伸抓取的**（桌面臂的典型用法），竖直向下这个姿态根本不在它的正常范围里。

**正解**：
- 用 `grasp_pose_seed()` 做初值（真机抓取构型的中位数）
- **不约束姿态**，只用位置 IK，让冗余自由度自然决定姿态
- 实测这样 60/60 收敛，姿态与真机习惯偏差中位 0.89°

### 坑 3：不要每帧独立重启 IK，要增量式

单点 IK 从固定初值跳到远处目标时，可能切到另一个 IK 分支（"翻腕"），关节会突变几十度，真机上就是猛抽一下。

**正解**：用 `ik_track()` —— 上一帧的解作为下一帧的种子。实测沿 20cm 直线走 30 步，关节跳变只有 1.51°。

---

## 5. 你的任务清单

按顺序做，每步都有验收标准。

### T1 · 跑通自检（0.5 天）
- [ ] `python -m kin.verify_fk_ik` 输出 `✅ 全部通过`
- [ ] 读懂 `kin/so101_ik.py` 里的 `ik()` 和 `ik_track()`

### T2 · 真机 FK 校验（1 天，需要 A 配合或等 A 有硬件）

**这是最重要的一步**：确认 MJCF 的连杆几何和真机一致。

步骤（A 摆机械臂、你算 FK）：
1. 让 A 把机械臂摆 5 个互不相同的姿态
2. 每个姿态记录：6 个关节的归一化值（`lerobot` 的 `observation.state`）
3. 你用 `cal.norm_vec_to_rad()` + `m.fk()` 算出末端位置
4. A 用卷尺量「基座原点 → 夹爪指尖」的实际三维距离
5. 比对

**验收**：5 个姿态的 FK 预测与实测距离误差 **< 5 mm**。

> 如果误差 > 10mm，说明 MJCF 模型和真机不完全匹配（可能是 SO-101 版本差异）。这时要么用实测数据修正连杆长度，要么接受误差并在 M3 里靠视觉伺服兜底。**这个结论必须写回总计划。**

### T3 · 安全层（1~2 天）

新建 `kin/safety.py`：

```python
def check_joint_limits(q, limits, margin_rad=0.05) -> tuple[bool, str]:
    """检查关节是否越界（留余量）。"""

def check_speed(q_prev, q_next, dt, max_rad_s=1.2) -> tuple[bool, str]:
    """检查相邻两帧的速度是否超限。"""

def check_workspace(pos, z_min=0.0, z_max=0.25, r_max=0.35) -> tuple[bool, str]:
    """检查末端是否在工作空间内（防止撞桌面/伸太远）。"""

def slow_approach(q_from, q_to, n_steps=10) -> np.ndarray:
    """接触前的末段减速（最后 1cm 用更低速度）。"""
```

**验收**：给一批刻意越界的输入，全部被拦下且返回原因。

### T4 · 真机对接（1~2 天，需要 A 的机械臂）

把 `kin/` 的输出接到 LeRobot 的舵机总线上：

```python
from kin.calibration import Calibration
cal = Calibration.load()

# IK 输出是弧度，真机要归一化值
q_rad = ...                      # 来自 ik() 或 ik_track()
q_norm = cal.rad_vec_to_norm(q_rad)   # -> 6 维，臂关节 [-100,100]，夹爪 [0,100]
# 然后按 LeRobot 的方式下发给 bus
```

**注意**：
- 舵机是 1M baud，6 个关节一轮读写约 20~30ms，所以控制频率上限约 30~40Hz，`dt=0.02` 是合理默认
- 必须先做**软限位**（`cal.limits_rad()`），比 MJCF 的 range 更宽松但仍是硬边界

**验收**：机械臂能执行一条 20cm 直线轨迹，末端抖动看视频无明显抽动。

### T5 · 扩展：带姿态约束的 IK（可选，1 天）

如果你想让夹爪朝向可控（比如绕竖直轴转 90° 对齐方块），需要给 `ik()` 传 `target_rot`。但注意坑 2：**只在你确认姿态在可达范围内时才用**。

建议做法：先位置 IK 得到一个解，读出它的姿态，再以这个姿态为目标做一次带姿态的 IK —— 这样目标一定可达。

---

## 6. 接口约定

### 你要提供给 M3 / M4 的

```python
from kin import Calibration, So101Model, grasp_pose_seed, ik, ik_track, plan_joint_traj

cal = Calibration.load()
m = So101Model()

# 单点：给一个三维目标（基座系，米），返回 6 维关节角（弧度）
q, info = ik(m, [0.22, -0.05, 0.015], seed=grasp_pose_seed(), limits=cal.limits_rad())
# info: {"ok": bool, "iters": int, "pos_err": float(米), "rot_err": float(弧度), "reason": str}

# 路径：一串三维点，增量式求解
Q, infos = ik_track(m, waypoints, seed=q, limits=cal.limits_rad())

# 轨迹：两个关节角之间插值，自动限速
traj, meta = plan_joint_traj(q0, q1, max_vel_rad_s=1.2, dt=0.02)
```

### 关节顺序（**严格遵守**）

```
0 shoulder_pan   1 shoulder_lift   2 elbow_flex
3 wrist_flex     4 wrist_roll      5 gripper
```

### 单位换算（`kin/calibration.py` 已实现）

```
臂关节: 归一化 [-100, 100]  <->  弧度
夹爪:   归一化 [0, 100]     <->  弧度   (0=闭合, 100=全开)
零点:   归一化 0  <->  MJCF 弧度 0  （都是"行程中点"）
```

---

## 7. 验收标准（M2 完成的门槛）

| # | 项 | 标准 | 当前 |
|---|---|---|---|
| 1 | IK 位置精度 | 中位 < 0.5mm，max < 3mm | ✅ 0.075 / 0.100 |
| 2 | 抓取位姿收敛率 | ≥ 90% | ✅ 8/8 |
| 3 | FK/IK 往返一致 | < 1mm | ✅ 0.000 |
| 4 | 轨迹限速 | ≤ 1.2 rad/s | ✅ 1.19 |
| 5 | 增量跟踪关节跳变 | < 5°/步 | ✅ 1.51° |
| 6 | **真机 FK 校验** | **< 5mm** | ⬜ 待 T2 |
| 7 | 安全层拦截测试 | 100% | ⬜ 待 T3 |

前 5 项已经过了，**T2 和 T3 是你的主要工作**。

---

## 8. 下一步（M4 仿真环境）

M2 通过后，你直接进 M4：

```python
# assets/so101_sim/so101_new_calib_camera.xml 已经带腕部相机挂载
mujoco.MjModel.from_xml_path("assets/so101_sim/so101_new_calib_camera.xml")
```

**M4 的验收只有一个**：把 A 的感知代码（`_setup/analyze_snapshot.py` 里的平面拟合 + 凸起检测）**原样**跑在仿真渲染出来的 RGB-D 上，位姿误差 < 5mm。这条测的是"仿真像不像真机"，比肉眼判断可靠得多。

---

## 9. 有问题先看这几处

| 症状 | 先查 |
|---|---|
| `ModuleNotFoundError: kin` | 必须在 `D:\LeRobot` 目录下跑，或用 `python -m kin.xxx` |
| `找不到 MJCF` | 跑 `python _setup\verify_so101_sim.py` 检查资产 |
| IK 不收敛 | 检查目标点是否在 X 0.14~0.32 / Y −0.16~0.04 / Z ≈ 0 附近 |
| 姿态差几十度 | 你在强制竖直向下 —— 见坑 2 |
| 关节突变几十度 | 你在每帧独立求解 —— 见坑 3 |
| 角度算出来和 MJCF range 不符 | 见坑 1，用校准换算 |
