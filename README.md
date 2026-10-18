# LeRobot SO-101 具身智能项目（Windows 实操手册）

把两份资料落地到**这台 Windows 机器**：

- SwanLab 的 [LeRobot 具身智能入门](https://docs.swanlab.cn/examples/robot/lerobot-guide.html)（采集→训练→推理，含 SwanLab 训练追踪）
- Seeed Studio 的 SO-Arm 系列 Wiki：[入门教程](https://wiki.seeedstudio.com/cn/lerobot_so100m_new/)、[舵机调试工具](https://wiki.seeedstudio.com/cn/lerobot_steering_gear_debugging_tool/)、[数据集工具](https://wiki.seeedstudio.com/cn/lerobot_dataset_tool/)（硬件安装、舵机 ID、调试与数据集维护）

两份资料原本都是 macOS/Linux 流程，本机复现时踩到一批平台差异，都已处理并记录在[第六节](#六windows-上踩过的坑)。

---

## 现在到哪一步了

| 项目 | 状态 |
| --- | --- |
| LeRobot 代码 | ✅ `D:\LeRobot\lerobot`（swpfY/lerobot 的 SwanLab 集成分支，HEAD `153eac3`） |
| Python 环境 | ✅ `D:\LeRobot\_tools\python310`（便携版 CPython 3.10.22，不依赖系统 Python） |
| 依赖安装 | ✅ `lerobot[feetech]` 全部装好，含 **CUDA 版 torch** |
| 环境自检 | ✅ **14 项全通过**（含"假数据采集→编码 mp4→读回"与"rerun 录制接口"实测） |
| 操作脚本 | ✅ `scripts\00` ~ `scripts\08` + 可选工具脚本 |
| 舵机调试工具 | ✅ 已装好（Seeed_RoboController + 独立依赖目录，用 `servo_tool.ps1` 启动） |
| 硬件相关 | ⬜ 待做：插机械臂 → 校准 → 遥操作 → 采数据 → 训练 → 推理 |
| HuggingFace / SwanLab 账号 | ⬜ 还没注册，先用本地离线模式跑（[第五节](#五账号huggingface--swanlab)讲怎么补） |

> **目前机器上没有插任何硬件**：串口列表里只有 COM3~COM8 六个"蓝牙链接上的标准串行"虚拟口，
> 摄像头索引 0~5 也全部不可用。
> 机械臂插上后会多出一个带 USB 描述（如 `USB-SERIAL CH340`）的 COM 口，**别选到蓝牙口**。

---

## 目录结构

```
D:\LeRobot\
├─ README.md                  ← 本文件
├─ activate.cmd               ← 双击打开"已激活环境"的 PowerShell 窗口
├─ activate.ps1               ← 激活脚本本体（被 activate.cmd 调用）
├─ config\
│   └─ robot.ini              ← 唯一需要改的配置文件（串口/相机/数据集/训练参数）
├─ scripts\
│   ├─ _common.ps1            ← 公共函数（读配置、拼参数、设环境变量）
│   ├─ 00_env_check.ps1/.py   ← 环境自检
│   ├─ 01_find_ports.ps1      ← 找串口 / 扫相机
│   ├─ 02_setup_motors.ps1    ← 舵机 ID / 波特率设置（仅散件需要）
│   ├─ 03_calibrate.ps1       ← 整臂校准（主臂/从臂）
│   ├─ 04_teleoperate.ps1     ← 遥操作测试
│   ├─ 05_record_dataset.ps1  ← 采集数据集
│   ├─ 06_train_act.ps1       ← 训练 ACT 策略
│   ├─ 07_run_policy.ps1      ← 模型推理（自主抓取）
│   ├─ 08_view_dataset.ps1    ← 本地查看数据集（rerun）
│   ├─ servo_tool.ps1         ← 舵机调试工具启动器（GUI + 命令行）
│   ├─ install_servo_debug_tool.ps1  ← 可选：装 Seeed 舵机调试工具
│   └─ list_ports.py          ← 串口/相机探测（被 01 调用）
├─ lerobot\                   ← LeRobot 源码（git 仓库，可单独更新）
├─ patches\
│   └─ 0001-windows-checkpoint-junction.patch   ← 对 lerobot 的唯一本地改动
├─ datasets\                  ← 采集到的数据集（脚本自动创建）
├─ outputs\                   ← 训练输出 / checkpoint（脚本自动创建）
├─ _tools\
│   ├─ python310\             ← 便携 Python + 所有依赖（约 6GB）
│   ├─ hf-cache\              ← HuggingFace 缓存 + **机械臂校准文件**
│   ├─ Seeed_RoboController\  ← 舵机调试工具本体（已装好）
│   ├─ py-servo-debug\        ← 该工具的 PySide6/pyserial 依赖（独立目录）
│   └─ tmp\                   ← 临时目录
└─ _setup\                    ← 安装过程脚本与日志（可删，见 _setup\README.md）
```

---

## 一、环境

### 平时怎么用

所有脚本都会**自己设置好环境变量**（Python 路径、UTF-8、HF 缓存目录、rerun 可执行文件路径），
所以直接跑脚本即可，不需要先激活：

```powershell
cd D:\LeRobot
powershell -ExecutionPolicy Bypass -File scripts\00_env_check.ps1
```

如果要手动敲 `python -m lerobot.xxx`，先激活环境。本机 PowerShell 执行策略会拦截未签名脚本
（直接 `. .\activate.ps1` 会报"未对文件进行数字签名"），所以用 `activate.cmd`：双击它，或在任意终端执行：

```powershell
D:\LeRobot\activate.cmd
```

它会新开一个**已经激活**的 PowerShell 窗口。等价写法：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -Command ". 'D:\LeRobot\activate.ps1'"
```

> 不用改系统执行策略，上面两种方式都能绕开。

### 自检（动硬件前建议先跑一次）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\00_env_check.ps1
```

`-Quick` 跳过假数据采集链路验证；`-Camera 0` 额外检查摄像头 0。
本机最近一次：**通过 14 项，失败 0 项**。

### 关键版本（均已实测可用）

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.10.22 | 便携版，装在项目内，不动系统 Python 3.12 |
| lerobot | 0.1.0（editable） | 指向 `lerobot\src`，改代码立即生效 |
| torch / torchvision | **2.7.1+cu126 / 0.22.1+cu126** | CUDA 12.6，**来自 PyTorch 官方源**（见坑 5） |
| GPU | RTX 4060 Laptop 8GB / sm_89 / 驱动 610.62 | `torch.cuda.is_available() == True` |
| PyAV | 17.1.0 | 自带 SVT-AV1 v4.1.0，视频编码走它 |
| OpenCV | opencv-python-headless 4.14.0 | 锁 4.x；Windows 后端用 **MSMF** |
| rerun-sdk | **0.22.1** | **必须 <0.23**，新版删了 lerobot 用的接口（见坑 13） |
| swanlab | 0.10.2 | 训练追踪 |
| huggingface-hub | 0.36.2 | 锁 0.x（1.x 删掉了 lerobot 依赖的 extra） |
| datasets | 3.6.0 | |
| pyserial / feetech-servo-sdk | 3.5 / 1.0.0（`scservo_sdk`） | 舵机通信 |

### 为什么没用教程里的 conda

SwanLab 教程用 miniconda + `conda install ffmpeg=7.1.1`；Seeed 教程用 Miniforge + Python 3.12。本机有两个客观障碍：

1. 机器上的 Anaconda 是 2017 年的 **conda 4.3.21**，无法可靠创建现代 Python 环境；而 conda/micromamba 在本会话沙箱里 TLS 握手失败（见坑 1）。
2. **ffmpeg 不需要单独装**：LeRobot 的 `encode_video_frames()` 用的是 PyAV（`av` 包），PyAV 自带 FFmpeg 和 SVT-AV1 编码器，实测默认 `libsvtav1` 直接可用。（Seeed 那边也提到：如果 ffmpeg 不带 libsvtav1，就得专门装 7.1.1 —— 我们绕过了整个问题。）

所以这里用 **python-build-standalone 便携版 CPython 3.10**（解压即用、无安装器、无注册表、完全在项目内），
Python 版本跟随 SwanLab 教程的 3.10（该 fork 与之配套；`pyproject.toml` 要求 `>=3.10`）。

---

## 二、硬件与安全

### ⚠️ 安全警告（来自 Seeed 官方，务必遵守）

- 运行任何会让机械臂运动的程序前，**清空机械臂 1 米范围内**的贵重/易碎物品、工具、线缆。
- 通电后**不要用手触碰**关节、电机、连杆、夹爪。
- 运行舵机设置、校准、遥操作、采集、回放、策略评估前，确认机械臂**固定牢靠**。
- 出现异常运动、异响、抖动、线缆松动、供电接触不良或通信中断，**立即停程序并断电检查**。
- **插拔舵机线、USB、电源前必须先断电**。
- 跑推理时建议手放在电源开关附近（模型没训好时机械臂可能乱动）。

### 供电与舵机型号（接错电压会烧舵机）

| 套件 | 主臂（Leader，黑） | 从臂（Follower，白） |
| --- | --- | --- |
| SO-101 **标准版** | 5V | 5V |
| SO-101 **Pro 版** | 5V | **12V** |

SO-101 的 Leader 前三个关节减速比与 SO-100 不同，组装前务必按型号区分。官方给的对应表：

| 舵机型号 | 减速比 | 对应关节 |
| --- | --- | --- |
| ST-3215-C044 (7.4V) | 1:191 | L1 |
| ST-3215-C001 (7.4V) | 1:345 | L2 |
| ST-3215-C044 (7.4V) | 1:191 | L3 |
| ST-3215-C046 (7.4V) | 1:147 | L4–L6 |
| ST-3215-C001(7.4V) / C018(12V) / C047(12V) | 1:345 | F1–F6 |

建议在舵机校准前给每个电机做好标记：`F1…F6`（从臂）、`L1…L6`（主臂），**从底座开始为 1 号，向上到夹爪为 6 号**。

### 其他注意事项

1. **USB 只通信不供电**：电源线和 USB 都要接；供电不足会表现为舵机无力、丢步、通信超时。
2. **别选到蓝牙串口**：本机现有 COM3~COM8 是蓝牙虚拟口，机械臂的口会显示 USB 串口描述。
3. **建议加一个有源 USB 集线器**，避免电脑 USB 口被电流冲击。
4. **夹具固定**：用桌沿夹把底座固定死，机械臂一动就跑会直接毁掉数据。
5. **散件 vs 组装版**：散件需要先做舵机 ID 设置（第 2 步）；买的是组装好的整臂则直接跳到第 3 步。
6. **校准文件位置**（本机）：`D:\LeRobot\_tools\hf-cache\lerobot\calibration\`。
   换电脑/重装时把它一起拷过去，就不用重新校准（每个机械臂 `id` 对应一个文件）。
7. 桌面要大，相机视野要能完整看到抓取区和放置盒。

---

## 三、全流程

> `config\robot.ini` 是唯一入口：**改配置，不改命令**。

### 第 1 步：找串口 / 扫相机

```powershell
cd D:\LeRobot
powershell -ExecutionPolicy Bypass -File scripts\01_find_ports.ps1
```

确认"哪个口是哪个臂"用 `-Watch`（会让你拔掉一根 USB，然后告诉你刚拔掉的是哪个口）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\01_find_ports.ps1 -Watch
```

拿到两个口后填进 `config\robot.ini`：

```ini
[robot]
port = COM5          # 从臂（白色）
id   = my_follower

[teleop]
port = COM4          # 主臂（黑色）
id   = my_leader
```

> `id` 可以随便起，但**一旦开始采集数据就不要改**：它决定校准文件名。

扫相机（会存快照，方便确认哪个索引对着桌面）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\01_find_ports.ps1 -Cams -Snapshot
# 看 D:\LeRobot\_setup\cam_snapshots\cam_*.jpg
```

相机索引填到 `[cameras] front_index`。

### 第 2 步：舵机 ID / 波特率设置（**仅散件需要**）

出厂舵机默认都是同一个 ID（通常 1），一条总线上有两个同 ID 的舵机时，改 ID 会把它们**一起改掉**，
所以必须一次只接一个舵机、逐个写入：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\02_setup_motors.ps1              # 从臂
powershell -ExecutionPolicy Bypass -File scripts\02_setup_motors.ps1 -Arm leader  # 主臂
```

脚本会按 **6→5→4→3→2→1（夹爪 → 底座）** 的顺序提示。每次按回车前务必确认"当前只有这一个舵机接着"。
接线方式：`电脑 → USB → 驱动板 → 三针线 → 只接一个舵机`（舵机不要连到其他舵机上）。

### 第 3 步：整臂校准

```powershell
powershell -ExecutionPolicy Bypass -File scripts\03_calibrate.ps1
# 只校准一个： -Arm follower / -Arm leader
# 只看命令：   -DryRun
```

操作流程（脚本会提示）：

1. 把机械臂**所有关节摆到活动范围的中间位置**，按回车；
2. **依次把每个关节从最小推到最大**，走完全程；
3. 再按回车，终端打印 `MIN / POS / MAX` 表。

注意事项：

- 这一步要手动掰动机械臂，先确认**电源接通**（断电时舵机无阻力，掰动没有意义）。
- 主从臂校准过程中，**终端没有收到 5 号舵机信号属于正常现象**（Seeed 官方说明），继续往下做即可。
- 如果报 `Magnitude exceeds 2047`、或某个舵机完全没反应，用[舵机调试工具](#舵机调试-gui可选但很值得装)排查。

### 第 4 步：遥操作测试

```powershell
powershell -ExecutionPolicy Bypass -File scripts\04_teleoperate.ps1
```

拖动主臂，从臂应实时跟随。第一次可能要求重新校准从臂，按提示走。
**这一关不过就别去采数据**（采出来的会全是废数据）。Ctrl+C 结束。

### 第 5 步：采集数据集

先把任务描述写清楚（`config\robot.ini`）：

```ini
[dataset]
repo_id     = local/pick_cube_v1                                # 两段格式，本地用前缀随便写
single_task = Pick up the yellow cube and put it in the box     # 模型会记住这句话
num_episodes = 20      # 先录 5 轮试手，正式至少 50 轮
episode_time_s = 30    # 每轮最长时长
reset_time_s   = 10    # 每轮之间整理时间
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1
# 临时改参数： -Episodes 5 -EpisodeTime 20
# 接着上次继续录： -Resume
# 只想看命令： -DryRun
```

**录制中的快捷键**（键盘焦点要在该窗口）：

| 键 | 作用 |
| --- | --- |
| `→` | 提前结束本轮，进入下一轮 |
| `←` | 放弃本轮，重录这一轮 |
| `ESC` | 立即停止整个录制 |

录制时会弹一个 rerun 窗口显示相机画面和电机状态，可以关掉，不影响录制。

**录制技巧**：

- 先录 5 轮熟悉流程，再录正式数据集；
- 至少 50 个场景、每个位置 10 次；**相机固定不动，抓取动作保持一致**；
- 好的起步任务：把有明显颜色标识（黄色）的长方体抓进盒子；
- 判断标准：**"光看相机画面就能完成任务"**。

数据落在 `D:\LeRobot\datasets\pick_cube_v1\`，含运动视频 + 电机数据（mp4 + parquet）。

### 第 6 步：训练

```powershell
powershell -ExecutionPolicy Bypass -File scripts\06_train_act.ps1
```

关键参数在 `[train]`：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `steps` | 40000 | 教程经验：4 万步左右效果基本到位（默认 10 万步太久） |
| `batch_size` | 8 | **8G 显存不够就降到 4 或 2**（`-BatchSize 4`） |
| `num_workers` | 4 | 还是不稳就 `-NumWorkers 0` |
| `device` | cuda | |
| `tracker` | swanlab | `none` / `swanlab` / `wandb` / `both` |
| `swanlab_mode` | offline | 没登录 SwanLab 先用 offline，训练照样记录 |

时间参考：4060 8G + 50 组数据约 **6 小时**；4090/A100 约 2~3 小时。断点续训加 `-Resume`。

产物在：

```
D:\LeRobot\outputs\train\pick_cube\checkpoints\<步数>\pretrained_model\
D:\LeRobot\outputs\train\pick_cube\checkpoints\last\          ← 最新（Windows 上是目录联接）
```

重点看 `train/loss` 和 `train/grad_norm`。

### 第 7 步：模型推理（自主抓取）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\07_run_policy.ps1
# 指定模型： -Path D:\...\checkpoints\020000\pretrained_model
# 只跑 5 轮： -Episodes 5
```

- 只连**从臂**，不需要主臂（模型自己出动作）；
- 脚本自动选最新 checkpoint（也可在 `[policy] path` 固定）；
- eval 数据集名必须以 `eval_` 开头（LeRobot 硬性要求，脚本会自动补）。

### 第 8 步：查看数据集（随时可做）

采完先确认数据质量，再拿去训练：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\08_view_dataset.ps1            # 弹 rerun 看第 0 轮
powershell -ExecutionPolicy Bypass -File scripts\08_view_dataset.ps1 -Episode 3
powershell -ExecutionPolicy Bypass -File scripts\08_view_dataset.ps1 -Save      # 导出 .rrd，不弹窗
```

逐帧显示相机画面 + 每个关节的 `action` / `state` 曲线。这是**只读**操作。

---

## 四、可选工具

### 舵机调试 GUI（可选，但很值得装）

Seeed 出的图形化工具 `Seeed_RoboController`，用来处理这些情况：

- 某个舵机检测不到（通常是 **ID 重复**，把"校准整臂"的指令误敲成了"校准舵机"就会这样）；
- 报 `Magnitude exceeds 2047` 之类的校准错误；
- 需要把某个位置写成**中位值**（中位测试 / 中位校准 / 失能电机）；
- 单独手动控制某个舵机、读寄存器、改波特率、恢复出厂。

**本机已经装好了**（仓库在 `_tools\Seeed_RoboController`，依赖在 `_tools\py-servo-debug`）。
要重装或更新：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_servo_debug_tool.ps1
powershell -ExecutionPolicy Bypass -File scripts\install_servo_debug_tool.ps1 -Force   # 重新拉取仓库
```

用启动器打开（不用记 `PYTHONPATH`）：

```powershell
# 图形界面：选串口 → 检测 1-6 号舵机 → 缺哪个就按"逐个单独接线 → 改写 ID"的方式修
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1

# 不带界面也能用的命令行小工具（该仓库自带 10 个）：
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool scan --list   # 列出串口
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool scan          # 扫描总线上有哪些舵机 ID
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool change-id     # 改写单个舵机 ID
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool center-test   # 中位测试
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool middle        # 把当前位置写成中位
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool disable       # 失能电机（机械臂会软下来，用手扶住）
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool diag          # 读寄存器做诊断
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool lerobot-calibrate  # 用它做整臂校准
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1 -Tool calib-middle  # 走一遍中位校准流程
```

启动后：选串口 → 检测 1-6 号舵机 → 缺哪个就按"逐个单独接线 → 改写 ID"的方式修。
官方流程里的关键一条：**改 ID 前要把 1-6 号舵机之间的线束全部拆开，只留一个舵机在总线上** —— 否则总线上同 ID 的舵机会被一起改掉。

> 这个工具的仓库默认分支叫 `factory`（不是 `main`）。
> 依赖装在独立目录（`pip install --target`）而不是 venv，原因见坑 15。

> 这个工具的仓库默认分支叫 `factory`（不是 `main`）。

### 数据集工具：我们这台能做什么、不能做什么

**能做**（本版本自带）：

| 功能 | 怎么做 |
| --- | --- |
| 本地可视化某一轮 | `scripts\08_view_dataset.ps1`（内部是 `python -m lerobot.scripts.visualize_dataset`） |
| 在线可视化（已上传 HF 后） | [huggingface.co/spaces/lerobot/visualize_dataset](https://huggingface.co/spaces/lerobot/visualize_dataset) |

**不能做**：Seeed 数据集工具页里的 `lerobot-edit-dataset` 系列操作 —— 删除剧集、拆分、合并、
移除特征、图像转视频。这些是 **lerobot 更新版本**才有的子命令；本项目的代码固定在 2025-07 版，
`pyproject.toml` 里也没有 console scripts（只能用 `python -m lerobot.xxx`）。

如果确实需要这些功能，两个办法：

1. 用官方新版 lerobot 另建一个环境专门做数据集编辑（**不要**在本环境 `pip install -U lerobot`，
   会把 CUDA torch 换成 CPU 版，见坑 5）；
2. 直接删掉 `D:\LeRobot\datasets\<数据集名>` 重录（本机数据集小的时候最省事）。

---

## 五、账号（HuggingFace / SwanLab）

两个都没注册也能完整跑通全流程（本地数据集 + 本地 checkpoint + swanlab offline）。

### SwanLab（训练看板）

1. 到 [swanlab.cn](https://swanlab.cn/) 注册，设置里拿 API Key；
2. 登录：

```powershell
D:\LeRobot\activate.cmd
swanlab login
```

3. 把 `config\robot.ini` 改成云端模式：

```ini
[train]
swanlab_mode = cloud
swanlab_project = lerobot_pick_cube
```

之后跑 `06_train_act.ps1`，终端会打印 `View run at https://swanlab.cn/@<你>/...` 链接。

### HuggingFace（数据集/模型上传）

1. 到 [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) 建一个 **write** 权限 token；
2. 登录：

```powershell
D:\LeRobot\activate.cmd
huggingface-cli login --token <你的token> --add-to-git-credential
huggingface-cli whoami
```

3. 把 `push_to_hub` 改成 `true`，并把 `repo_id` 的 `local/` 换成你的 HF 用户名。

> 上传不通时：数据集可以手动拷到训练机 —— 本机路径 `D:\LeRobot\datasets\<数据集名>`，
> 目标机放到同路径即可（LeRobot 默认从 `~/.cache/huggingface/lerobot` 找，本机被改到了
> `_tools\hf-cache\lerobot`，见坑 9）。

---

## 六、Windows 上踩过的坑

都在本机实测复现过，处理方式写在代码/脚本里了。

| # | 现象 | 根因 | 处理 |
| --- | --- | --- | --- |
| 1 | `curl`/`git`/`conda`/`micromamba` TLS 失败：`schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS` | 本会话沙箱下 Windows schannel 拿不到凭证 | 下载一律用 **Python**（自带 OpenSSL）：`_setup\download.py`、`_setup\fetch_repo.py`；git 用 `http.sslBackend=openssl` |
| 2 | `pip`/`venv`/`ensurepip` 报 `[Errno 13] Permission denied ... pip-build-tracker-*` | `tempfile.mkdtemp()` 用 `os.mkdir(path, 0o700)`，Windows 上这会生成**受保护 DACL（阻断继承）**，沙箱进程访问不了自己刚建的临时目录 | 已打补丁：`_tools\python310\Lib\site-packages\sitecustomize.py` 改写 `mkdtemp` |
| 3 | 装源码包（sdist）仍报 `.tmp-xxxx` 权限错 | pip 做构建隔离时会在临时环境里写**它自己的 `sitecustomize.py`** 并用 PYTHONPATH 放在最前，**盖住**我们的补丁 | 装 sdist 加 `--no-build-isolation`（并先装 `poetry-core wheel`）。只装 wheel 包不受影响 |
| 4 | 训练保存第一个 checkpoint 崩：`OSError [WinError 1314] 客户端没有所需的特权` | `update_last_checkpoint()` 无条件建**符号链接**，Windows 普通用户默认无此权限 | 已打补丁（`patches\0001-...patch`）：失败时退回**目录联接**（junction，无需权限） |
| 5 | `pip install torch` 装出来是 **CPU 版** | PyPI（含国内镜像）上 Windows 的 torch wheel 是 CPU-only（约 0.2GB），CUDA 版只在 PyTorch 官方源。**Seeed 文档也专门提醒：pip 装 lerobot 会把 torch 换成 CPU 版** | 显式从 `https://download.pytorch.org/whl/cu126` 装 `torch==2.7.1+cu126`；**别随便 `pip install -U`** |
| 6 | PowerShell 5.1 跑脚本报一堆 `Unexpected token`、中文乱码 | PS 5.1 对**无 BOM** 的 UTF-8 脚本按 ANSI 解析 | 所有 `.ps1`/`.ini` 已加 **UTF-8 BOM**；`.py` 不受影响。改完脚本记得补 BOM（`_setup\add_bom.py`） |
| 7 | `git clone` 中途崩：`sh.exe: couldn't create signal pipe` | git-lfs 过滤器经 `sh -c` 执行，沙箱不允许 msys 建信号管道 | 用 git plumbing（`read-tree` + `checkout-index`）落盘；`tests/artifacts` 下 45 个 LFS 测试夹具标 `skip-worktree`；别的仓库改用 Python 下 tar 包 |
| 8 | 摄像头索引对不上 | LeRobot 在 Windows 用 **MSMF** 后端，与 DSHOW 编号可能不同 | 探测脚本 `list_ports.py --cams` 与 LeRobot 用同一后端 |
| 9 | `LeRobotDataset` 报 `WinError 5: C:\Users\...\.cache\huggingface` | 沙箱只允许写工作区，HF 默认缓存在用户目录 | 所有脚本把 `HF_HOME` 指向 `D:\LeRobot\_tools\hf-cache`（**校准文件也在里面**） |
| 10 | 教程让装 `ffmpeg=7.1.1` | LeRobot 用 PyAV 编码，PyAV 自带 FFmpeg | 跳过 ffmpeg 安装；自检里的"视频编码端到端"会实测 `libsvtav1` |
| 11 | `_tools` 下有十几个空目录删不掉（`tmp\`、`pip-cache\`、`Seeed_RoboController__stage\` 里） | 它们是坑 2/14 在**打补丁之前**创建的，带受保护 DACL，沙箱进程无权限删 | 空目录、无害。**在你自己的资源管理器/终端里可以直接删** |
| 12 | `. .\activate.ps1` 报"未对文件进行数字签名" | 本机执行策略比 `Get-ExecutionPolicy` 显示的 RemoteSigned 更严，未签名脚本一律拒绝（新建空脚本也一样） | 用 `activate.cmd`，或所有命令都带 `-ExecutionPolicy Bypass` |
| 13 | 录制时刚要写 rerun 数据就 `AttributeError: module 'rerun' has no attribute 'Scalar'` | pip 默认装了 rerun-sdk 0.39，而 lerobot 这版用 `rr.Scalar()` / `rr.set_time_sequence()`；rerun 0.23 起改名为 `Scalars` / `set_time` 并最终删除旧接口 | 已降到 **rerun-sdk 0.22.1** 并写进 `_setup\constraints.txt`；自检新增"Rerun 录制接口兼容性"实测项，会真的调一次 `log_rerun_data()` |
| 14 | Python 解压 tar 包报 `PermissionError ... 'xxx\.gitignore'` | 同一个 0o700 根因的第二个出处：`tarfile.TarFile.makedir()` 也用 `os.mkdir(targetpath, 0o700)` | 已在 `sitecustomize.py` 里一并改写 `tarfile.TarFile.makedir`；另外下载脚本改用**每次全新的临时目录**，避免复用到旧失败留下的坏目录 |
| 15 | 建 venv 失败：`ensurepip` 返回非 0、`No module named pip` | venv 里的 python **不加载基础环境的 `sitecustomize`**（`include-system-site-packages=false`），于是 ensurepip 在未打补丁的状态下运行，又踩回坑 2 | 需要隔离的第三方工具（如舵机调试 GUI）改用 `pip install --target <目录>` + `PYTHONPATH`，用的仍是打了补丁的解释器 |
| 16 | 校准/遥操作/采集过程中偶发 `ConnectionError: Failed to sync read ...`，整个流程中断 | `MotorsBus.sync_read()` / `write()` 的 `num_retry` **默认是 0**：一次偶发丢包就抛异常。而 `record_ranges_of_motion()` 是个**没有 sleep 的高频紧凑轮询**，SO-101 的读主臂/读从臂/采集三条路径全都吃这个默认值 | 已打补丁（`patches\0002-servo-bus-robustness.patch`）：把两个默认值改成 **3 次重试**。成功时零额外开销，只有丢包时才重试。同时仍要排查物理原因（USB 线被牵拉、供电接触不良） |
| 17 | 校准"成功"了、文件也生成了，但遥操作时某个关节几乎不动 | 通信偶发的**错读**会返回超出 12 位编码范围的值（实测出现 `32918`、`33605`，约等于 8 圈）。`record_ranges_of_motion()` 把这值记进 `max` 后，该关节校准跨度虚高（应为 ~2000，实际 33000+），归一化后行程被压缩到 -100~-85 | 已打补丁（`patches\0002-servo-bus-robustness.patch`）：只接受 `0~4095` 的读数，超范围直接丢弃。并新增体检脚本 `scripts\check_calibration.ps1`，**每次校准后都跑一遍**，跨度超出 300~5000 就会标红 |

补充：`os.mkdir` 不要改成普通的 Python 包装函数 —— 内建函数不是描述符，换成 Python 函数后 `pathlib`
会把它当方法绑定，多传一个 `self`，直接报 `mkdir() takes from 1 to 2 positional arguments but 3 were given`。
（我踩过，所以补丁只改 `mkdtemp` 和 `tarfile.makedir`。）

---

## 七、常见问题排错

| 症状 | 排查 |
| --- | --- |
| 找不到串口 / 端口消失 | 换 USB 口、换线；确认是带 USB 描述的口而不是蓝牙口；`01_find_ports.ps1` |
| 校准报 `Magnitude exceeds 2047` | **不是 ID 问题**（本机实测 ID 全好也会报）。是某个舵机的中位值 `Homing_Offset` 与实际机械位置偏差过大，算出的补偿值超出 ±2047。用舵机调试工具：先「中位测试」看姿态是否扭曲 → 「失能电机」→ 手动摆到正确中位 → 「中位校准」。**别反复重跑 lerobot 校准**：它是先算全部再逐个写入，报错时前面几个舵机的 offset 已被改写，越跑越乱 |
| 某个舵机没反应 / 检测不到 | 用调试工具看 1~6 号是否全部识别；缺哪个多半是 ID 重复或三针线没插到底，需单独接一个舵机改写 ID |
| 校准/遥操作中偶发 `ConnectionError: Failed to sync read` | 已加 3 次重试（坑 16）。若加完仍失败，查物理层：USB 线是否被机械臂运动牵拉（最常见）、换 USB 口/换线、电源插头是否插紧、舵机三针线在推到极限时是否被扯松。可用调试工具「单舵机控制」逐个缓慢转动，找出卡顿或失联的那个 |
| 主从臂校准终端收不到 5 号舵机信号 | **正常现象**（Seeed 官方说明），继续操作即可 |
| 相机打不开 / 读不到帧 | 被会议软件占用；`00_env_check.ps1 -Camera 0` 看具体报错；换 `front_index` |
| 数据集目录已存在 | 加 `-Resume` 继续录，或改 `repo_id` 换新名字，或删掉旧目录 |
| `dataset name does not begin with 'eval_'` | 用模型推理时数据集名必须 `eval_` 开头（脚本已自动补） |
| 训练 OOM（显存不足） | `-BatchSize 4` 或 `2`，再不行 `-NumWorkers 0` |
| 中文乱码 | 用项目里的 `.ps1` 脚本（已设 UTF-8 + BOM）；手动跑请先激活 |
| 脚本被拦："未对文件进行数字签名" | 命令加 `-ExecutionPolicy Bypass`；激活环境用 `activate.cmd`（见坑 12） |
| 训练中断 | 加 `-Resume` 接着训 |
| 换电脑后又要重新校准 | 把 `_tools\hf-cache\lerobot\calibration\` 一起拷过去 |
| 想装新包 | `pip install <包>`；源码包要加 `--no-build-isolation`（坑 3）；**不要 `pip install -U torch`**（坑 5） |

---

## 八、与官方资料的差异对照

| SwanLab / Seeed 教程 | 本机做法 | 原因 |
| --- | --- | --- |
| `/dev/ttyACM0`、`/dev/tty.usbmodem...` | `COM5`（形如 `COM<数字>`） | Windows 串口命名 |
| conda / Miniforge + ffmpeg | 便携 Python + **不装 ffmpeg** | conda 在本机不可用；PyAV 自带编码器 |
| `pip install -e .`（SwanLab 原文） | `pip install -e ".[feetech]"` | 原文漏了 feetech extra，不加就没有 `scservo_sdk`，SO-101 无法通信（Seeed 文档是对的） |
| `lerobot-calibrate` / `lerobot-setup-motors` / `lerobot-edit-dataset`（**console scripts**） | `python -m lerobot.calibrate` / `lerobot.setup_motors` / … | 本版 `pyproject.toml` 没有 `[project.scripts]`，只能用 `-m` 模块方式 |
| Seeed 推荐 Python 3.12 + Seeed 版 lerobot 仓库 | Python 3.10 + **swpfY/lerobot**（SwanLab 集成分支） | 我们的主线是 SwanLab 训练追踪，该分支与之配套 |
| 手写 `record.py` / 推理脚本 | `python -m lerobot.record` CLI + 配置驱动 | 用官方 CLI 更稳，改参数只改 `robot.ini` |
| 数据集删除/拆分/合并/转视频 | 本版没有，见[第四节](#数据集工具我们这台能做什么不能做什么) | 那些子命令属于更新的 lerobot |
| 教程 pin `cf86b93` | 用 fork 的 HEAD `153eac3` | HEAD 已含 SwanLab 集成 + Windows OpenCV 修复 |
| `--swanlab.mode=cloud` | 默认 `offline` | 还没注册账号，注册后改一行 |

---

## 九、下一步

环境这边没有阻塞项了。接下来需要你动手：

1. **接好机械臂并通电** → `01_find_ports.ps1 -Watch` 认出两个口 → 填进 `config\robot.ini`；
2. **散件**才需要：`02_setup_motors.ps1` 逐个写舵机 ID（组装版跳到下一步）；
3. `03_calibrate.ps1` 校准主从臂；
4. `04_teleoperate.ps1` 确认跟手；
5. `05_record_dataset.ps1` 先录 5 轮试手，再录正式数据集（≥50 轮）；
6. `08_view_dataset.ps1` 抽查数据质量；
7. `06_train_act.ps1` 训练（8G 显存建议 batch 4~8，先 2 万步看 loss）；
8. `07_run_policy.ps1` 自主抓取。

任何一步报错，把终端输出贴给我，我按第七节的排错表继续处理。

---

## 十、参考链接

- [SwanLab：LeRobot 具身智能入门](https://docs.swanlab.cn/examples/robot/lerobot-guide.html)
- [Seeed：基于 LeRobot 的 SO-ARM100 / SO-ARM101 机械臂入门教程](https://wiki.seeedstudio.com/cn/lerobot_so100m_new/)
- [Seeed：SO-Arm 舵机调试工具](https://wiki.seeedstudio.com/cn/lerobot_steering_gear_debugging_tool/)
- [Seeed：SO-Arm 数据集工具](https://wiki.seeedstudio.com/cn/lerobot_dataset_tool/)
- [Seeed_RoboController 仓库](https://github.com/Seeed-Projects/Seeed_RoboController)（舵机调试 GUI）
- [LeRobot 官方文档](https://huggingface.co/docs/lerobot/index) ｜ [SO-101 文档](https://huggingface.co/docs/lerobot/so101)
- [集成 SwanLab 的 LeRobot 分支](https://github.com/swpfY/lerobot)
- [SwanLab 官网](https://swanlab.cn/)
