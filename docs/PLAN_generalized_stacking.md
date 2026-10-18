# SO-101 任意位置物块堆叠 · 项目计划

> 版本 v1.0 ｜ 最后更新 2026-10-18 ｜ 当前阶段：**M0 收尾 / M1 已验证**
> 仓库根目录：`D:\LeRobot`（Windows）

---

## 1. 一句话目标

让 SO-101 从「只能堆 4 个固定点位」升级为「**相机视野内任意位置的方块都能抓起来，叠到指定目标块上**」。

---

## 2. 为什么现在做不到（问题诊断）

现有模型是 **ACT（行为克隆）**，训练集 100 轮、4 个点位各 25 轮。

它的输入只有：

```
observation.images.front   (480×640×3, 单目 RGB)
observation.state          (6 维关节角)
```

**没有任何「物体在哪」的显式变量**。位置信息完全隐含在图像特征激活里。方块出现在训练分布外时，激活模式是没见过的组合 → 输出退化到最近的训练模式。

三个必须纠正的认知：

| 常见误解 | 实际情况 |
|---|---|
| 「再训久一点就好了」 | loss 0.077 已经**过拟合**，再训 5 万步只会更牢地记住这 4 个点 |
| 「模型容量不够」 | ACT 52M 参数对这种任务绰绰有余 |
| 「要靠强化学习解决任意位置」 | **不是。** 「任意位置」是几何问题，靠感知 + 逆运动学解；RL 解决的是接触时刻的精细控制 |

---

## 3. 现状盘点

### 3.1 已完成

| 项 | 状态 | 关键数据 |
|---|---|---|
| 环境搭建 | ✅ | Python 3.10.22 便携版，torch 2.7.1+cu126，RTX 4060 Laptop 8G |
| 主从臂校准 | ✅ | 6 关节增益 0.99~1.19 |
| 遥操作 | ✅ | 正常 |
| 数据采集 | ✅ | 100 轮 / 24059 帧 / 409 MB（4 点位 × 25 轮） |
| ACT 训练 | ✅ | 50000 步，loss 0.077，25 个 checkpoint |
| **推理验证基线段** | ⬜ | **还没跑过**，必须先有基线数字 |
| 深度相机接入 | ✅ | 见 §3.3 |
| SO-101 仿真模型 | ✅ | 官方 URDF/MJCF 已落地并验证 |

### 3.2 硬件拓扑

| 项 | 值 |
|---|---|
| leader（主臂，黑） | `COM10`，id `my_leader` |
| follower（从臂，白） | `COM11`，id `my_follower` |
| 舵机 | Feetech STS3215，1,000,000 baud，12 位（0~4095） |
| 相机 | Orbbec Gemini 2，serial `AYGKC520QFP`，USB3 |
| 工作方块 | **30mm 见方** |

### 3.3 已实测并固化的技术参数（重要，后续全靠这些）

**相机（Orbbec Gemini 2，实测 2026-10-18）**

| 项 | 值 |
|---|---|
| 彩色流 | 640×480@30，RGB888 |
| 深度流 | 640×480@30，Y16（`HW_MODE` D2C 对齐后） |
| depth scale | **1.0**（原始单位 = 毫米） |
| RGB 内参 | `fx=516.821 fy=517.180 cx=321.623 cy=238.932` |
| Depth 原生内参 | `fx=306.016 cx=316.869`（**640×400，不要用**） |
| 深度有效像素 | 70.1% |
| 深度时域噪声 | 中位 **0.30 mm** |
| 顶面深度 MAD | **2~3 mm** |
| 权限要求 | **必须管理员**（UVC 控制通道，普通用户 `E_ACCESSDENIED 0x80070005`） |

> ⚠️ 对齐后深度帧已被重投影到**彩色相机坐标系**，3D 反投影必须用 `rgb_intrinsic`，用 `depth_intrinsic` 会整体偏移。

**感知链路验证结果（真实场景实测）**

| 指标 | 实测 | 真值 | 误差 |
|---|---|---|---|
| 方块高度 | 27.7 / 25.9 mm | 30 mm | ±4 mm |
| 方块边长（平面内测量） | 29.7 mm | 30 mm | −1% |
| 3D 位置（两种独立方法交叉验证） | 差 **0.8 / 1.5 mm** | — | ✅ |
| 红块分类 | `red=1.00` | — | ✅ |
| 绿块分类 | `green=0.90` | — | ✅ |

**SO-101 仿真模型（官方 [TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100)）**

已落地到 `assets/so101_sim/`，28 个文件 / 19 MB 网格：

```
so101_new_calib.xml              MJCF 主轴（新校准，与 LeRobot 约定一致）
so101_new_calib_camera.xml       MJCF + 腕部相机挂载
so101_new_calib.urdf / .urdf(camera)
scene.xml / joints_properties.xml / README.md
assets/  18 个 STL
```

关节名与 LeRobot **完全一致**：`shoulder_pan / shoulder_lift / elbow_flex / wrist_flex / wrist_roll / gripper`

---

## 4. 目标验收标准

| 级别 | 标准 | 对应模块 |
|---|---|---|
| 最低 | 视野内随机 20 个位置，成功率 ≥ 75% | M3 |
| 目标 | 成功率 ≥ 85%，平均耗时 < 25s，无碰撞/过载 | M3 |
| 增强 | 加 RL 后成功率 ≥ 90%，且可通过开关 A/B 对照证明增益 | M6 |
| 全程 | 任何单模块可独立关闭/回退，不影响其余模块 | 架构要求 |

---

## 5. 技术架构

```
┌──────────────────────────────────────────────────────────────┐
│ L4 任务层   状态机：找目标块 → 抓 → 找目标位 → 对齐 → 放 → 退  │
├──────────────────────────────────────────────────────────────┤
│ L3 技能层   抓取 / 转移 / 释放 技能原语                        │  ← RL 在此增强
├──────────────────────────────────────────────────────────────┤
│ L2 运动层   目标位姿 → IK → 关节轨迹 → 限速下发                │
├──────────────────────────────────────────────────────────────┤
│ L1 感知层   RGB-D → 桌面平面 → 物体凸起 → 3D 位姿              │
├──────────────────────────────────────────────────────────────┤
│ L0 硬件层   follower 6 舵机 + Orbbec Gemini 2                  │
└──────────────────────────────────────────────────────────────┘
```

**设计原则**：每层可独立验证、可独立回退。L1 挂了不影响 L2；L3 的 RL 关了还能走纯解析轨迹。

**关键技术判断**：SO-101 在「夹爪竖直向下」约束下，真正决定末端位置的只有 3 个关节（shoulder_pan + shoulder_lift + elbow_flex），**存在闭式解析解**（yaw + 两连杆余弦定理）。用 numpy 20 行即可，不需要 placo/pinocchio（这两个在 Windows 上装不上，见 §12 R4）。

---

## 6. 模块拆分

### 6.1 模块总表

| 编号 | 模块 | 依赖 | 主责 | 工期 | 状态 |
|---|---|---|---|---|---|
| **M0** | 标定与地基 | — | A | 1~2 天 | 🟡 进行中 |
| **M1** | 感知（RGB-D → 3D） | M0 | A | 2~3 天 | 🟢 **核心已验证** |
| **M2** | 运动学（FK/IK/轨迹） | — | B | 3~5 天 | ⬜ 未开始 |
| **M3** | 真机通用堆叠（集成） | M1 + M2 | A+B | 3~5 天 | ⬜ |
| **M4** | MuJoCo 仿真环境 | M2 | B | 3~5 天 | ⬜ |
| **M5** | 仿真 RL 训练 | M4 | B | 5~10 天 | ⬜ |
| **M6** | sim2real 迁移 | M3 + M5 | A+B | 3~5 天 | ⬜ |
| **M7** | 评估与固化 | M6 | A | 1~2 天 | ⬜ |

> 状态图例：⬜ 未开始 ｜ 🟡 进行中 ｜ 🟢 已验证 ｜ 🔴 阻塞 ｜ ✅ 完成

### 6.2 各模块详细说明

---

#### M0 · 标定与地基 ｜ A ｜ 1~2 天

**目标**：钉死「相机像素 → 机械臂基座坐标」的变换链。

| 步骤 | 产出 | 验收 |
|---|---|---|
| 相机权限与取流（✅ 已做） | `_setup/cam_probe.py` | 深度可用、内参已知 |
| **相机视角调整** | — | 光轴与桌面法向夹角 **从 63.3° 降到 25~35°**（更俯视） |
| 机械臂基座 ↔ 相机外参标定 | `config/hand_eye.json` | 用 ArUco 板，重投影误差 < 3mm |
| 桌面坐标系建立 | — | 桌子平面 + 原点 + 轴向定义 |
| 畸变系数验证 | — | 当前 `k1=39.8` 不符合 OpenCV 约定，需实测确认是否可忽略 |

> 🔴 **当前阻塞点**：相机 63.3° 斜视导致顶面投影仅 60×40px，尺寸测不准、且堆叠时会遮挡。必须调整。

---

#### M1 · 感知 ｜ A ｜ 2~3 天 ｜ 🟢 核心已验证

**目标**：输入一帧 RGB-D，输出桌面所有候选物体的 3D 位姿。

**已验证的完整流水线**（代码原型在 `_setup/analyze_snapshot.py`）：

```
1. 工作区深度限制     180~600 mm            （排除近处盲区与背景）
2. 桌面平面拟合       RANSAC(300 iter) + SVD 精化，子采样 6000 点
3. 物体 = 桌上凸起    高度 8~80 mm，面积 200~12000 px
4. 顶面层提取         height > h_top − 6 mm   ← 必须用绝对落差
5. 深度取样           顶面 bbox 中心 55% ROI 的【中位数】
6. 3D 定位            图像反投影 + 点云中位数，两者交叉校验
7. 尺寸              投影到桌面平面内测量，MAD 剔除飞点
8. 颜色              只用于分类红/绿，不参与定位
```

**踩过并已修掉的 5 个坑**（这些坑不写下来一定会重踩）：

| # | 坑 | 现象 | 正解 |
|---|---|---|---|
| 1 | HSV 边界膨胀 | 30mm 方块量成 36.3mm（+21%） | 定位改用深度，颜色只分类 |
| 2 | 凸起 bbox 含侧壁 | 30mm 量成 65mm | 只取 `height > h_top−6mm` 的顶面层 |
| 3 | 相对阈值切顶面 | 顶面被切成 80×39，长宽比 2.05 | 改**绝对落差**（斜视时同一水平面 p10~p90 有 20mm 正常跨度） |
| 4 | 像素反推尺寸 | 30mm 量成 43.8×20.7 | 投影到桌面平面内测 |
| 5 | 边缘 mixed-pixel | 整片 mask 深度 std 25mm | 只取中心 ROI，std 降到 4mm / MAD 3mm |

**待办**：

- [ ] 封装为 `perception/detect.py`，输出标准化 JSON
- [ ] 多目标 + 目标选择策略（选最近的红块？选指定的绿块？）
- [ ] 遮挡场景处理（堆叠第二层时）
- [ ] 补上「相机外参」转换（相机系 → 基座系）

---

#### M2 · 运动学 ｜ B ｜ 3~5 天 ｜ ⬜ 不需要硬件

**目标**：`IK(目标位姿) → 6 维关节角`，且轨迹安全。

| 步骤 | 说明 | 验收 |
|---|---|---|
| 加载官方 MJCF | `assets/so101_sim/so101_new_calib.xml` | 6 关节，nq=6 |
| FK | MuJoCo `mj_forward` 或手写 DH | 与真机读数一致 |
| **解析 IK** | yaw = atan2(y,x) + 两连杆余弦定理 | 收敛，残差 < 3mm |
| DLS 精化 | 处理腕部偏移/连杆误差，3~5 次迭代 | 亚毫米 |
| 关节限位 + 奇异点 | 软限位、肘部奇异、不可达回退 | 不越限 |
| 轨迹生成 | 关节空间三次插值，按串口带宽限速 | 无突变 |
| 安全层 | 速度限幅、电流监控（`error` 位）、看门狗、急停 | 不过载 |

**已知必须处理的 3 个坑**：

| 坑 | 说明 |
|---|---|
| **夹爪映射不一致** | LeRobot 是线性 0=闭 / 100=开；MJCF 是 hinge `−0.17453 ~ 1.74533 rad`（−10°~100°）。不换算会撞限位 |
| **elbow_flex 有 5° 偏移** | MJCF 注释明写 `5-degree calibration offset applied to joint range`，FK 校验会第一时间撞上 |
| **校准约定** | 必须用 `new_calib`（零点=行程中点，与 LeRobot 一致），`old_calib` 会全盘偏移 |

**官方给的舵机真实参数**（直接可用，不用猜）：

```xml
damping 0.60   frictionloss 0.052   armature 0.028
position: kp=998.22  kv=2.731  forcerange ±2.94 N·m   (按舵机 kp=16 换算)
backlash ±0.5°  →  约 ±1.3mm @ 15cm 臂展
```

---

#### M3 · 真机通用堆叠（集成） ｜ A+B ｜ 3~5 天

**状态机**：

```
IDLE → DETECT → APPROACH(预抓取, 上方 8cm)
     → DESCEND → GRASP(夹紧 + 小抬升验证)
     → LIFT → TRANSFER(到目标块上方)
     → ALIGN(深度闭环, 目标居中, 迭代 2~3 次) → PLACE(下降到接触 +2mm)
     → RELEASE → RETREAT → 检查高度 → DONE
```

**三个关键实现点**：

1. **视觉伺服对齐**：ALIGN 阶段不一次性开到目标点，而是「移动 → 重新检测 → 修正」迭代 2~3 次。这是纯几何法能达到 85% 的核心技巧，能吃掉标定误差和舵机回差。
2. **抓取成功检测**：抬升后重新检测目标是否跟着上来，失败重试（最多 3 次）。
3. **安全距离**：下降留 3mm 余量，靠视觉闭环逼近，不靠开环精确。

**验收**：随机 20 个位置，成功率 ≥ 75%，平均 < 25s，无碰撞/过载。

---

#### M4 · MuJoCo 仿真环境 ｜ B ｜ 3~5 天 ｜ ⬜ 不需要硬件

| 组件 | 内容 |
|---|---|
| 场景 | 官方 MJCF + 桌面 + 红/绿方块 + RGB-D 虚拟相机 |
| 域随机化 | 光照强度/色温、桌面纹理、相机内外参 ±2mm/±0.5°、摩擦 0.4~1.2、质量 ±20%、关节阻尼/回差、控制延迟 0~40ms |
| Gym 接口 | `obs = {depth, rgb, qpos, ee_pose, obj_pose}`，`action = 末端位姿增量(3D) + 夹爪(1D)` |
| 显存约束 | 无渲染 16~32 并行；开渲染 ≤ 4（8G 显存） |

**验收**：把 M1 感知代码**原样**跑在仿真数据上，位姿误差 < 5mm。这条测的是「仿真像不像」，比肉眼判断可靠。

---

#### M5 · 仿真 RL 训练 ｜ B ｜ 5~10 天

**三级递进，没通过不做下一级**：

| 级别 | 内容 | 通过标准 |
|---|---|---|
| 5A | 状态 RL（物体位姿 + 关节角 → 笛卡尔增量） | 仿真成功率 ≥ 90%，证明环境和算法没错 |
| 5B | **Residual RL**（基底 = M3 解析轨迹，学 ±1.5cm 修正 + 夹爪时机） | 仿真成功率 ≥ 95%，残差 RMS < 8mm |
| 5C | 视觉 RL（depth 256×256 小 CNN） | 仅当 5A/5B 都通过才做；8G 可能扛不住 |

**算法**：SAC（连续动作、样本效率高），不用 PPO（要的 step 太多）。

**RL 应该学什么**（解析法做不好、行为克隆也学不好的部分）：

| 学什么 | 为什么解析法不行 |
|---|---|
| 抓取下压深度 + 夹紧时机 | 需要接触反馈 |
| 释放高度 + 释放后抬升速度 | 「放早了歪、放晚了夹爪带倒」 |
| 舵机回差 + 重力下垂补偿 | 与具体姿态强相关，难建模 |

**不要做的**：端到端视觉 RL 直接上真机。8G 显存 + 廉价舵机 + 14~30mm 小方块，大概率失败且不可调试。

---

#### M6 · sim2real ｜ A+B ｜ 3~5 天

| 步骤 | 要点 |
|---|---|
| 冻结策略 | 导出纯前向（numpy 或 onnx），去掉训练依赖 |
| 真机部署 | 解析基底 + RL 修正，**修正量硬限幅 ±1.5cm** |
| 安全边界 | 超限退回基底；碰撞/过载触发即停 |
| 校准对齐 | 用 50~100 轮真机数据微调输入归一化（不微调网络） |
| **A/B 对照** | 同批 20 个位置，开/关 RL 各跑一遍 |

**验收**：真机成功率 ≥ 85%（相对 M3 提升 ≥ 10 个百分点）。**如果没提升，明确放弃 RL，保留 M3**——这不是失败，是科学结论，还省了维护成本。

---

#### M7 · 评估与固化 ｜ A ｜ 1~2 天

100 次统计评测、成功率/耗时报告、更新 `AGENTS.md`、封装成 `scripts/11_pick_place_general.ps1`。

---

## 7. 分工方案：两条并行线

```
        时间 →
A  ┌─ M0 标定 ──┬─ M1 感知 ─────────────────┐
                 │                            ├─ M3 集成 ──┬─ M6 sim2real ── M7
B  └─ M2 运动学 ─┴─ M4 仿真 ── M5 RL ─────────┘            │
                                                           
    ↑ 关键：B 的两条线都【不需要机械臂硬件】，一台笔记本就能干
```

### 分工矩阵（建议，可按实际技能调整）

| 角色 | 负责模块 | 需要硬件 | 核心技能 |
|---|---|---|---|
| **A** | M0、M1、M3、M7 | ✅ 机械臂 + 相机 | 计算机视觉、标定、系统集成 |
| **B** | M2、M4、M5、协助 M3/M6 | ❌ 只需笔记本 | 机器人运动学、MuJoCo、强化学习 |
| **共同** | M3、M6 | ✅ | 联调、真机测试 |

**这个分法的好处**：

- B **完全不需要机械臂**：M2 用官方 MJCF 在 MuJoCo 里验证 FK/IK，M4/M5 是纯仿真。一台普通笔记本就能开始，不用等 A 腾出机械臂。
- 两条线在 M3 才汇合，之前互不阻塞。
- A 的 M0/M1 是 B 的输入，但通过 §8 的接口约定解耦——B 可以先用假的 3D 位姿数据开发。

---

## 8. 接口约定（并行开发的关键）

并行开发必须先把接口钉死，否则 M3 汇合时会互相返工。

### 8.1 A → B：感知输出

```json
{
  "timestamp": 1760000000.123,
  "frame_id": "gemini2",
  "objects": [
    {
      "id": 3,
      "class": "RED",              // RED | GREEN | UNKNOWN
      "confidence": 1.00,
      "pos_cam": [0.0687, 0.0004, 0.2190],   // 米，相机光学系 (x右 y下 z前)
      "pos_base": [0.21, -0.05, 0.03],       // 米，机械臂基座系（M0 标定后填）
      "size_mm": [30.0, 30.0],               // 顶面边长，平面内测量
      "height_mm": 27.7,                     // 高出桌面
      "yaw_rad": 0.0,                        // 绕桌面法向的朝向（方块对称，0/90 二选一）
      "depth_mad_mm": 2.0,                   // 质量指标
      "n_pixels": 642
    }
  ],
  "table_plane": {
    "normal": [-0.022, -0.893, -0.450],
    "d": 0.1266
  }
}
```

### 8.2 B → A：运动学接口

```python
# 单位：米 / 弧度
def fk(qpos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """6 维关节角 -> (位置 xyz, 旋转矩阵 3x3)。在基座坐标系。"""

def ik(target_pos: np.ndarray,
       target_rot: np.ndarray | None = None,   # None = 夹爪竖直向下
       seed: np.ndarray | None = None) -> np.ndarray | None:
    """目标位姿 -> 6 维关节角。不可达返回 None，不抛异常。"""

def plan_joint_traj(q_from: np.ndarray, q_to: np.ndarray,
                    max_vel_rad_s: float = 1.2) -> np.ndarray:
    """关节空间三次插值，返回 (N, 6) 轨迹点，满足速度限幅。"""
```

### 8.3 关节名与顺序（**必须严格遵守**）

```
0 shoulder_pan   1 shoulder_lift   2 elbow_flex
3 wrist_flex     4 wrist_roll      5 gripper
```

夹爪换算（LeRobot ↔ MJCF）：

```python
# LeRobot: 0 = 全闭, 100 = 全开
# MJCF   : -0.17453 rad (闭) ~ 1.74533 rad (开)
def lerobot_to_mjcf(g: float) -> float:
    return -0.17453 + (g / 100.0) * (1.74533 + 0.17453)

def mjcf_to_lerobot(q: float) -> float:
    return (q + 0.17453) / (1.74533 + 0.17453) * 100.0
```

---

## 9. 时间线

| 周 | A | B | 里程碑 |
|---|---|---|---|
| 第 1 周 | M0 标定 + 相机视角 | M2 FK/IK | G1：IK 精度 < 3mm |
| 第 2 周 | M1 感知封装 | M2 轨迹 + 安全层 | G2：感知 3D 误差 < 5mm |
| 第 3 周 | M3 集成调试 | M4 仿真环境 | G3：**真机任意位置成功率 ≥ 75%** |
| 第 4 周 | M3 打磨 + 基线评测 | M5A 状态 RL | G4：仿真成功率 ≥ 90% |
| 第 5~6 周 | 协助 M5B | M5B Residual RL | G5：仿真 ≥ 95% |
| 第 7 周 | M6 sim2real 联调 | M6 sim2real 联调 | G6：**真机 ≥ 85%，A/B 对照完成** |
| 第 8 周 | M7 固化 + 文档 | M7 协助 | ✅ 交付 |

**关键 Gate**：G3（真机 75%）一旦达成，需求已满足。G4~G6 是增强项，可根据时间决定是否继续。

---

## 10. 环境搭建

### 10.1 有硬件的一方（A）

```powershell
# 1. 环境自检
powershell -ExecutionPolicy Bypass -File scripts\00_env_check.ps1

# 2. 找串口
powershell -ExecutionPolicy Bypass -File scripts\01_find_ports.ps1

# 3. 遥操作验证
powershell -ExecutionPolicy Bypass -File scripts\04_teleoperate.ps1

# 4. 推理基线（必须先跑，拿到固定点位的成功率）
powershell -ExecutionPolicy Bypass -File scripts\07_run_policy.ps1 -Episodes 10 -NoRerun

# 5. 相机探测（必须管理员！）
#    双击 _setup\probe_camera_admin.cmd
#    或管理员 PowerShell:
#    & "D:\LeRobot\_tools\python310\python.exe" _setup\cam_probe.py
```

**必须知道的 4 件事**：
1. 解释器固定用 `D:\LeRobot\_tools\python310\python.exe`（便携版，不要用系统 Python）
2. 所有脚本 source `scripts\_common.ps1`（设 `HF_HOME` / `TORCH_HOME` / `LEROBOT_CV2_BACKEND`）
3. **相机必须管理员**，普通权限会 `E_ACCESSDENIED 0x80070005`
4. 录制/可视化**一律加 `-NoRerun`**（本机 GPU 上 rerun 会崩）

### 10.2 只有笔记本的一方（B）—— 不需要机械臂！

```powershell
# 1. 只需要这些包（pip 走 aliyun 源）
& "D:\LeRobot\_tools\python310\python.exe" -m pip install mujoco scipy
#    mujoco 3.16.0 有 cp310 win_amd64 wheel，18.7MB，可直接装
#    ⚠️ placo / pinocchio 装不上（需源码编译），不要浪费时间——IK 自己写

# 2. 仿真资产已就位，校验完整性
& "D:\LeRobot\_tools\python310\python.exe" _setup\verify_so101_sim.py

# 3. 加载模型自检
& "D:\LeRobot\_tools\python310\python.exe" -c "import mujoco; m=mujoco.MjModel.from_xml_path(r'D:\LeRobot\assets\so101_sim\so101_new_calib.xml'); print('nq',m.nq,'nu',m.nu)"

# 4. 用假的感知数据开发（不等 A 的相机）
#    按 §8.1 的 JSON 结构自己造几个物体位姿
```

**B 不需要的东西**：机械臂、相机、串口、管理员权限、GPU（M2/M4 阶段）。

---

## 11. 协作规范

### 11.1 目录约定

```
D:\LeRobot\
├── perception\          # A 负责：感知
│   ├── camera.py        #   RGB-D 取流（管理员）
│   ├── detect.py        #   平面拟合 + 凸起检测 + 3D
│   └── calib.py         #   手眼标定
├── kin\                 # B 负责：运动学
│   ├── so101_ik.py      #   解析 IK + DLS
│   ├── traj.py          #   轨迹生成
│   └── safety.py        #   限幅/看门狗/急停
├── sim\                 # B 负责：仿真
│   ├── env.py           #   gymnasium 环境
│   ├── domain_rand.py   #   域随机化
│   └── train_rl.py      #   SAC 训练
├── skills\              # 共同：技能层
│   └── pick_place.py    #   状态机
├── config\
│   ├── robot.ini        # 现有
│   ├── hand_eye.json    # M0 产出
│   └── calibration.json # M2 产出
├── assets\so101_sim\    # ✅ 官方模型已就位
├── _setup\              # 诊断工具（不参与主流程）
└── docs\                # 文档
```

### 11.2 分支策略

| 分支 | 用途 |
|---|---|
| `main` | 可运行版本，只在 Gate 通过时合并 |
| `feat/perception` | A |
| `feat/kinematics` | B |
| `feat/sim-rl` | B |

**规则**：`perception/` 只由 A 改，`kin/` + `sim/` 只由 B 改，`skills/` 和 `config/` 改前先在群里说一声。

### 11.3 每日同步

每人每天在进度看板上更新三件事：

1. 昨天完成了什么
2. 今天要做什么
3. 有没有阻塞

---

## 12. 风险登记

| # | 风险 | 影响 | 缓解 | 状态 |
|---|---|---|---|---|
| R1 | 深度相机不可用 | 全局降级 | — | ✅ **已消除**（实测可用，噪声 0.3mm） |
| R2 | 没有 SO-101 URDF，仿真失真 | M4~M6 白做 | — | ✅ **已消除**（官方 MJCF 已落地验证） |
| R3 | 舵机重复定位精度不够 | 纯几何法上限低 | — | ⬇️ 实测回差 ±0.5° ≈ ±1.3mm，比预期宽松 |
| R4 | `placo`/`pinocchio` 装不上 | HIL-SERL / aloha 全堵死 | 自研 numpy IK | ✅ 已确认并纳入 M2 |
| **R5** | **相机视角 63.3° 太斜** | **尺寸测不准、堆叠遮挡** | **抬高相机到 25~35°** | 🔴 **当前阻塞 M0** |
| R6 | 夹爪 0~100 ↔ rad 映射不一致 | 撞限位 | §8.3 换算函数 | 🟡 已知，待实现 |
| R7 | `elbow_flex` 5° 偏移 | FK 校验必撞 | M2 显式补偿 | 🟡 已知，待实现 |
| R8 | 结构光边缘 mixed-pixel | 深度噪声大 | 只取顶面中心 ROI（已验证） | ✅ 已解决 |
| R9 | 8G 显存 | 视觉 RL 只能小规模 | 5A/5B 用状态输入 | 🟡 |
| R10 | 舵机 ID3 历史故障 | 中途阻塞 | 备件；安全层限流 | 🟡 长期 |
| R11 | 队友环境差异 | 无法复现 | §10.2 固定解释器路径 + 资产随 git 走 | 🟡 |
| R12 | 背景杂物干扰 | 误检 | 高度过滤 + 面积上下限（已验证） | ✅ 规则已验证 |

---

## 13. 附录：常用命令速查

```powershell
# 环境自检
powershell -ExecutionPolicy Bypass -File scripts\00_env_check.ps1

# 遥操作
powershell -ExecutionPolicy Bypass -File scripts\04_teleoperate.ps1

# 录制数据（-NoRerun 必加；-Resume 续录）
powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1 -Episodes 25 -NoRerun

# 训练（沙箱里 -NumWorkers 必须 0，管理员下用 4）
powershell -ExecutionPolicy Bypass -File scripts\06_train_act.ps1 -Steps 50000 -SaveFreq 2000

# 推理
powershell -ExecutionPolicy Bypass -File scripts\07_run_policy.ps1 -Episodes 5 -NoRerun

# 相机探测（必须管理员）
#   双击 _setup\probe_camera_admin.cmd

# 拍一张 RGB-D 快照（必须管理员）
#   双击 _setup\snap_rgbd_admin.cmd

# 分析最新快照（普通权限即可）
& "D:\LeRobot\_tools\python310\python.exe" _setup\analyze_snapshot.py --tag live

# 校验仿真资产
& "D:\LeRobot\_tools\python310\python.exe" _setup\verify_so101_sim.py
```

---

## 14. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-18 | v1.0 | 初版。M0/M1 已完成核心验证；补充实测参数、接口约定、分工方案 |

---

## 15. 待决策

- [ ] **相机视角调整**：M0 的阻塞点，需尽快定方案
- [ ] 是否保留 ACT 模型作为失败恢复的 fallback
- [ ] 是否给 SO-101 加腕部相机（官方已有支架 STL，成本 ~150 元，精度可提升一档）
- [ ] M5C（视觉 RL）做不做
