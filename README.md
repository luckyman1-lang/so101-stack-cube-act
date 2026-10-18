# SO-101 双臂机器人「堆叠方块」技能学习

用一对 SO-101 机械臂（leader 主臂 + follower 从臂）采集人类示教数据，
训练 **ACT（Action Chunking Transformer）** 模仿学习策略，让从臂**自主**把绿色方块叠到红色方块上。

> 从零搭建环境 → 标定 → 遥操作 → 采数据 → 训练 → 实机部署，全流程在 Windows + RTX 4060 Laptop 上跑通。

---

## 📊 关键结果

| 指标 | 数值 |
|---|---|
| **实机成功率** | **16 / 20 = 80%**（绿块位于训练点位 A，1.4cm 立方体） |
| 训练数据 | 100 轮示教 / **24,059 帧** / 409 MB / 4 个方块点位各 25 轮 |
| 训练规模 | ACT，**50,000 步**，batch 8，**52M 参数** |
| 训练 loss | 9.71（step 100）→ **0.077**（step 50,000） |
| 离线动作精度 | 逐帧预测 MAE **1.19**（动作空间范围 200，误差 **0.6%**） |
| 训练耗时 | **2.4 小时**（多进程加载数据后 0.17 秒/步） |
| 单次推理耗时 | 约 20 秒/轮（含相机与舵机 I/O） |

**失败模式**：4 次失败均为"绿块被推到红块旁、未叠正"，属于**抓取/放置精度**问题，而非策略完全失效。

---

## 🎯 任务定义

```
初始状态：红块固定在白纸中央，绿块放在 4 个预设点位之一
目标状态：绿块稳稳叠在红块正上方
观测：单目 RGB 640×480（30fps）+ 从臂 6 个关节位置
动作：从臂 6 个关节的目标位置（归一化到 -100~100）
```

**是纯视觉-本体感觉策略**：ACT 不使用语言指令、不显式建模物体 3D 位置，
完全从像素和关节状态中隐式学习"看到什么 → 做什么"。

---

## 🔧 系统架构

```
     人类示教                  数据采集                  策略学习                自主执行
  ┌──────────┐            ┌──────────┐            ┌──────────┐            ┌──────────┐
  │ 主臂 leader│──遥操作──▶│ 从臂 follower│           │   ACT    │            │ 从臂 follower│
  │  (COM10)  │            │  (COM11)  │──视频+状态──▶│ ResNet18 │──动作序列──▶│  (COM11)  │
  └──────────┘            └─────┬────┘            │+Transformer│          └─────┬────┘
                                │                 └──────────┘                  │
                          ┌─────▼─────┐                                         │
                          │ Orbbec 相机 │◀──────────── 观测（图像）───────────────┘
                          │  Gemini 2  │
                          └────────────┘
```

**硬件清单**

| 部件 | 型号 / 规格 |
|---|---|
| 机械臂 | SO-101 × 2（leader 黑色主臂 / follower 白色从臂） |
| 舵机 | Feetech STS3215 × 12，1 Mbps 半双工串口，12 位编码器 |
| 通信 | CH343 USB 转串口（主臂 COM10 / 从臂 COM11） |
| 相机 | Orbbec Gemini 2（USB 3.0，UVC 接口） |
| 算力 | RTX 4060 Laptop 8GB，Windows 11 |

**软件栈**

```
LeRobot (fork)  +  PyTorch 2.7.1 + CUDA 12.6
ACT 策略：ResNet18 视觉骨干 + Transformer 编解码器 + VAE
数据格式：LeRobotDataset v2.1（parquet 元数据 + mp4 视频）
训练追踪：SwanLab 0.10.2（offline 模式）
```

---

## 🚀 复现步骤

### 0. 环境

```powershell
# 便携 Python 3.10 + 依赖（详见 docs/操作手册.md）
powershell -ExecutionPolicy Bypass -File scripts\00_env_check.ps1
```

**关键环境变量**（`scripts\_common.ps1` 统一设置，Windows 下必需）：

```powershell
$env:HF_HOME                = "<root>\_tools\hf-cache"        # 别写 C:\Users
$env:TORCH_HOME             = "<root>\_tools\torch-cache"     # ResNet 权重
$env:LEROBOT_CV2_BACKEND    = "DSHOW"                         # Orbbec 只有 DSHOW 出图
$env:LEROBOT_CAM_AWB        = "off"                           # 固定白平衡
$env:LEROBOT_CAM_AWB_TEMP   = "5800"                          # 实测最接近录制时色相
```

### 1. 标定（关键，决定成败）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\03_calibrate.ps1
```

**核心要求**：**主臂和从臂摆成完全相同的中间姿态**。
`Homing_Offset` 的物理含义是"校准时那个姿态的编码 − 2047"，
只有两臂姿态一致，主从才能正确对应。

**验收标准**：两臂摆同样姿态时，6 个关节的归一化值差值 **< 5**。

### 2. 遥操作验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts\04_teleoperate.ps1
```

**验收标准**：主从增益 **0.95~1.05**（实测 5 个关节 0.98~1.01，夹爪 1.19）。

### 3. 采集数据

```powershell
# 每个点位 25 轮，4 个点位共 100 轮
powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1 -Episodes 25 -NoRerun
powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1 -Episodes 25 -NoRerun -Resume   # 换点位继续
```

**录制按键**：`→` 结束本轮 / `←` 重录 / `空格` 暂停 / `ESC` 停止

**数据设计**：绿块放在红块的 **4 个方位**（右前 / 左 / 右后 / 左后），
每个方位 25 轮 —— 让策略见到"目标在不同位置"的多样性，而不是死记一个位置。

### 4. 训练

```powershell
# 必须 -NoRerun（本机 rerun 会崩）；-SaveFreq 2000 便于随时中断续训
powershell -ExecutionPolicy Bypass -File scripts\06_train_act.ps1 -Steps 50000 -SaveFreq 2000
```

**实测速度**（RTX 4060 Laptop 8G，batch 8）：

| 配置 | 数据加载 | GPU 计算 | 合计 | 50000 步 |
|---|---|---|---|---|
| `num_workers=0` | 0.179 s | 0.162 s | 0.34 s/步 | 5.7 小时 |
| **`num_workers=4`** | **0.000 s** | 0.162 s | **0.17 s/步** | **2.4 小时** |

### 5. 实机部署

```powershell
# 只连从臂，模型自己出动作
powershell -ExecutionPolicy Bypass -File scripts\07_run_policy.ps1 -Episodes 5 -EpisodeTime 40 -ResetTime 90 -RunTag demo -NoRerun
```

| 参数 | 作用 |
|---|---|
| `-Episodes` | 跑几轮 |
| `-EpisodeTime` | 每轮最长秒数 |
| `-ResetTime` | 每轮之间整理期（换方块位置，期间机械臂不动） |
| `-RunTag` | 数据存到 `eval_<名字>_<tag>`，**每次独立保存不覆盖** |

---

## 🧠 工程难点与解决（项目最有价值的部分）

在 Windows 上跑 LeRobot + 真实硬件，遇到并解决了 **10 个非文档化的坑**，
全部整理成可复用的补丁（`patches/`，共 10 个）：

| # | 问题 | 根因 | 解决 |
|---|---|---|---|
| 1 | 训练保存 checkpoint 报 `WinError 1314` | Windows 创建符号链接需要管理员特权 | 检测失败后**自动改用目录联接（junction）** |
| 2 | 舵机偶发 `Failed to sync read` | `num_retry=0`，一次失败直接抛错 | 读写重试 3 次 |
| 3 | 偶发 `Missing motor IDs` | 个别舵机单次读型号失败被判定为缺失 | 存在性检查加重试（注意：真过载时不能掩盖） |
| 4 | 舵机位置读到 33815 / 33605（超 12 位） | 舵机内部计数器 bit15 异常 | `Present_Position > 4095` 时 `& 0x0FFF` |
| 5 | Orbbec 相机在 lerobot 里扫不到 | lerobot 默认用 MSMF，Orbbec 只支持 DSHOW | 相机后端可用环境变量覆盖 |
| 6 | 训练结束卡在连 HuggingFace 超时 | `push_to_hub=True` 默认值 | 加 `--policy.push_to_hub=false` |
| 7 | `PermissionError [Errno 13]` 加载模型配置 | lerobot 用独占 `NamedTemporaryFile`，draccus 再 open 同文件 | 改为直接 `draccus.decode(dict)`，不落临时文件 |
| 8 | SwanLab 0.10.2 `'Run' object has no attribute 'public'` | 上游按旧版 API 写的 | 适配 `.id`、`step` 转 int |
| 9 | 录制中途卡死无法退出 | 只有 ESC 停止，没有暂停 | 加**空格暂停**（暂停期间不采帧、不发指令、时间补偿） |
| 10 | 空 episode 触发 `ValueError` | 一开始就按 `→` 会保存 0 帧 | 空轮保护：丢弃并重录 |

**还有三个"看起来是 bug、其实是误判"的排查经验**：

- **`is_calibrated=False` 会静默触发重新标定**，把你刚写进去的校准文件覆盖掉 →
  排查时必须用 `bus.read_calibration()` 逐字段比对，不能只看这个布尔值。
- **相机自动白平衡（AWB）会在两次开相机之间漂移**：录数据时红块 H≈21（橙红），
  推理时漂成 H≈100（偏蓝）→ 固定 AWB + 实测色温 5800K。
- **调试用的存图脚本把 RGB 当 BGR 写盘**，导致"红块变紫蓝"的假象，
  白排查了半天 —— **模型的输入一直是正常的**，只是调试图错了。

### 一个反面教材（已回滚）

曾试图把 `Homing_Offset` 的编解码从"11 位符号-幅度"改成"12 位补码"（看起来更规范），
结果导致：**舵机位置读数跳到 4762、反复过载、主从完全不对应、遥控手感崩坏**。

**教训**：lerobot 对这个寄存器是"自己写、自己读"，用同一种（哪怕不规范的）编码恰好自洽；
任何单边修改都会打破自洽，让**舵机的实际行为**错乱。
回滚到官方原版后立刻恢复正常 —— 补丁留在 `patches/0006-REVERTED-DO-NOT-APPLY-*` 作为记录。

---

## 📈 评测方法（三层）

| 层级 | 方法 | 目的 | 本项目结果 |
|---|---|---|---|
| **L1** | 训练 loss | 只在训练集上拟合得好 | 0.077（低，但不代表泛化） |
| **L2** | 离线动作预测 | 逐帧独立预测 vs 真值 | **MAE 1.19 / 200（0.6%）** |
| **L3** | **实机闭环** | **唯一真实指标** | **80%（16/20）** |

**L2 的实现有个坑**：不能用 `policy.select_action()` 逐帧评估 ——
它内部有**动作队列**，第一次预测出 100 步 chunk 后，后续调用直接出队不再推理，
导致评估结果完全错位（MAE 会从 1.19 虚高到 33）。
正确做法是每帧调用 `predict_action_chunk(...)[:, 0]`。

---

## ⚠️ 已知限制（诚实说明）

1. **只认训练过的 4 个点位** —— 模仿学习的能力边界 = 数据覆盖范围。
   绿块放到完全没见过的位置，策略会僵住或乱走。
2. **对环境变化敏感** —— 相机位置、光照、色温变化都会掉点。
   （这也是为什么要把 AWB 固定、色温锁死）
3. **无语言理解** —— ACT 是单任务策略，不能说"把蓝块放到绿块上"。
4. **没有闭环纠错** —— 一旦第一帧判断偏移，后续会一路偏到底。
5. **单目视觉 + 无深度** —— 遮挡时容易失手。

**下一步可以做的**：补录更多点位的数据（提升泛化）、
换成带语言条件的 VLA 模型（如 π0 / GR00T）、加腕部相机消除遮挡。

---

## 📁 仓库结构

```
.
├── README.md                  # 本文件：项目总览
├── AGENTS.md                  # 给 AI agent 的操作指南 + 踩坑记录
├── scripts/                   # 全流程 PowerShell 脚本（15 个）
│   ├── _common.ps1            #   环境变量 + 公共函数
│   ├── 00_env_check.ps1       #   环境自检（14 项）
│   ├── 01_find_ports.ps1      #   串口发现
│   ├── 03_calibrate.ps1       #   标定
│   ├── 04_teleoperate.ps1     #   遥操作
│   ├── 05_record_dataset.ps1  #   数据采集
│   ├── 06_train_act.ps1       #   ACT 训练
│   ├── 07_run_policy.ps1      #   实机推理
│   └── servo_tool.ps1         #   舵机调试 GUI 启动器
├── patches/                   # 10 个 Windows 适配补丁（含 1 个已回滚的反面教材）
├── _setup/                    # 60+ 个诊断/分析工具（Python）
│   ├── watch_train.py         #   训练进度监控（解析日志，替代 SwanLab 面板）
│   ├── eval_offline.py        #   L2 离线动作预测评估
│   ├── tally_eval.py          #   实机成功率统计
│   ├── scan_wb.py             #   相机色温扫描（定位偏色）
│   ├── upload_to_hf.py        #   上传数据集/模型到 HuggingFace
│   └── sample_dataset_frames.py  # 数据集抽帧可视化
├── config/robot.ini           # 全部可调参数（端口/相机/数据集/训练超参）
├── docs/操作手册.md            # 详细操作手册（按键、参数、排错）
├── kin/                       # 运动学（FK/IK 验证，为后续仿真准备）
├── assets/so101_sim/          # URDF / MJCF 模型
└── tools/                     # 进度看板、假感知假机器人的干跑工具
```

---

## 🎓 这个项目体现了什么

- **完整闭环能力**：从零搭环境到实机部署，中间每个环节都亲自跑通
- **硬件 + 软件 + 算法**：串口协议、舵机标定、相机驱动、数据格式、模型训练、实机部署
- **系统性排查**：10 个 Windows 兼容性问题，每个都定位到根因并做成可复用补丁
- **实证精神**：每个结论都有数据支撑（增益 0.99、MAE 1.19、80% 成功率），
  并且**记录了自己判断错的地方**（12 位补码补丁、BGR 存图误判）
- **工程化**：参数全部集中到配置文件、诊断工具 60+ 个、踩坑记录文档化

---

## 📄 License

本项目代码 MIT。LeRobot 上游遵循其原始协议（Apache-2.0）。
数据集与模型权重仅用于学习研究，请勿用于商业用途。
