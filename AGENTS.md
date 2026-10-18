# AGENTS.md — LeRobot SO-101 堆叠方块项目

> 给 AI agent / 未来自己的操作指南。**先读完"绝对不能碰"和"已知坑"两节再动手。**
> 人类向的完整手册见 `README.md`（31KB，更啰嗦但更全）。

---

## 1. 这个项目在做什么

用一对 SO-101 机械臂（leader 主臂 + follower 从臂）通过 LeRobot 的 **ACT** 策略，
学习 **"把绿色方块抓起来叠到红色方块上"** 这个单一技能。

**当前进度（2026-10-17）**

| 阶段 | 状态 |
|---|---|
| 环境搭建 | ✅ 完成（14/14 自检通过） |
| 校准 | ✅ 完成（主从 6 关节增益 0.99~1.19） |
| 遥操作 | ✅ 验证正常 |
| 数据采集 | ✅ 100 轮 / 24059 帧 / 409 MB（4 个点位各 25 轮） |
| 训练 | ✅ 50000 步完成，loss 0.077，25 个 checkpoint / 14.4 GB |
| **推理验证** | ⬜ **下一步，还没做** |

---

## 2. 硬件拓扑

| 项 | 值 |
|---|---|
| leader（主臂，黑色/CEO） | `COM10`，id `my_leader` |
| follower（从臂，白色） | `COM11`，id `my_follower` |
| 舵机 | Feetech STS3215，1,000,000 baud，12 位编码（0~4095） |
| 舵机 ID | 1=shoulder_pan, 2=shoulder_lift, 3=elbow_flex, 4=wrist_flex, 5=wrist_roll, 6=gripper |
| 相机 | Orbbec Gemini 2（VID 2BC5 / PID 0670），USB3 |
| 已知坏过的舵机 | 从臂 ID3（elbow_flex）多次出现多圈累积 + 反复过载，见 §7.4 |

---

## 3. 环境（必须知道的三件事）

**解释器**：`D:\LeRobot\_tools\python310\python.exe`（便携版 Python 3.10.22）

**所有脚本都 source `scripts\_common.ps1`**，它设定了：

```powershell
$env:HF_HOME                 = '<root>\_tools\hf-cache'
$env:HF_LEROBOT_CALIBRATION  = '<root>\_tools\hf-cache\lerobot\calibration'
$env:TORCH_HOME              = '<root>\_tools\torch-cache'   # 默认会写 C:\Users，写不进去
$env:LEROBOT_CV2_BACKEND     = 'DSHOW'                       # MSMF 扫不到 Orbbec
```

**没有账号也没有外网到 huggingface.co**：
- 训练必须带 `--policy.push_to_hub=false`，否则训练结束时会卡在连 HF 超时
- 数据集 `repo_id` 用 `local/xxx`，只在本地

---

## 4. 常用命令

```powershell
# 环境自检
powershell -ExecutionPolicy Bypass -File scripts\00_env_check.ps1

# 找串口
powershell -ExecutionPolicy Bypass -File scripts\01_find_ports.ps1

# 校准（主从各一次；关键：两臂摆成完全相同的姿态）
powershell -ExecutionPolicy Bypass -File scripts\03_calibrate.ps1

# 遥操作验证
powershell -ExecutionPolicy Bypass -File scripts\04_teleoperate.ps1

# 录制（-NoRerun 必加；-Resume 接着已有数据集继续）
powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1 -Episodes 25 -NoRerun
powershell -ExecutionPolicy Bypass -File scripts\05_record_dataset.ps1 -Episodes 25 -NoRerun -Resume

# 训练（参数含义见 §6）
powershell -ExecutionPolicy Bypass -File scripts\06_train_act.ps1 -Steps 50000 -SaveFreq 2000

# 推理（只连从臂，模型自己出动作）
powershell -ExecutionPolicy Bypass -File scripts\07_run_policy.ps1 -Episodes 5

# 舵机调试 GUI（只能用户自己开，agent 的环境起不来窗口）
powershell -ExecutionPolicy Bypass -File scripts\servo_tool.ps1
```

**辅助脚本（`_setup\`，都是我自己写的诊断工具）**

| 脚本 | 用途 |
|---|---|
| `watch_train.py` | 解析训练日志，显示进度/loss/ETA（`--loop` 常驻，`--plot` 存曲线） |
| `sample_dataset_frames.py` | 从数据集 mp4 抽帧拼图，检查画面质量 |
| `check_layout.py` | 拍照 + HSV 检测红/绿方块 + 距离判定 |
| `snap_once.py` | 交互式连拍，存到 `_setup\cam_snapshots\` |
| `patch_swanlab_021.py` / `patch_swanlab_step.py` | SwanLab 0.10.2 兼容补丁（已应用） |

---

## 5. ⛔ 绝对不能碰

**① `lerobot\src\lerobot\motors\feetech\feetech.py` — 保持官方原版，不要改**

曾经把 `Homing_Offset` 的读写改成"12 位补码"（见 `patches\0006-REVERTED-...`），
结果：舵机位置读数跳到 4762、反复过载、主从不一致、遥控手感崩坏。
**回滚到官方版本后遥控立刻恢复正常。**

**教训**：`Homing_Offset` 在 lerobot 里是"自己写自己读"，用同一种（哪怕不规范的）编码
恰好自洽。任何单边修改都会打破自洽，让舵机实际行为错乱。

**② 不要用 Seeed GUI 的「中位校准」按钮**

它会改写舵机 `Homing_Offset`，直接破坏 lerobot 校准。只能用它做：扫描、读寄存器、
单舵机控制、失能电机。

**③ 不要用 rerun 可视化（录制/查看数据集时）**

本机 GPU 上 rerun 会崩：
```
forrtl: error (200): program aborting due to window-CLOSE event
wgpu_hal::vulkan::conv Unrecognized present mode 1000361000
```
所以录制一律加 `-NoRerun`。想看数据就抽帧拼图（`sample_dataset_frames.py`）。

**④ 相机和串口操作需要管理员权限**

普通权限下 `cv2.VideoCapture(1, CAP_DSHOW)` 打不开 Orbbec；
`Get-PnpDevice`、`fsutil`、`Get-CimInstance Win32_LogicalDisk`、`powercfg` 也可能被拒。

---

## 6. 训练参数与实测数据

**`06_train_act.ps1` 参数**

| 参数 | 默认 | 说明 |
|---|---|---|
| `-Steps` | config 里 `train.steps` | 训练步数 |
| `-BatchSize` | 8 | 8G 显卡 batch 8 够用（显存约 4.6G） |
| `-NumWorkers` | config 里 `train.num_workers` | **见下方警告** |
| `-SaveFreq` | 10000 | **想中途能停就设 2000** |
| `-LogFreq` | 100 | 日志间隔 |
| `-Resume` | — | 从最近 checkpoint 续训 |
| `-DryRun` | — | 只打印命令 |

**⚠️ `-NumWorkers` 的坑**

- **在 DSH 沙箱里跑**：必须 `0`。多进程要开命名管道，沙箱禁止 →
  `PermissionError [WinError 5]` 崩在 `multiprocessing/connection.py Pipe`
- **用户自己在管理员 PowerShell 里跑**：用 `4`，快一倍
  - `data_s` 从 0.18 → 0.000
  - 每步 0.34s → 0.17s
  - 50000 步：5.7 小时 → 2.4 小时

**实测基准（RTX 4060 Laptop 8G，batch 8，ACT 52M 参数）**

```
updt_s（GPU 前向+反向）  ≈ 0.162 s
data_s（workers=0）      ≈ 0.179 s   -> 合计 0.34 s/步
data_s（workers=4）      ≈ 0.000 s   -> 合计 0.17 s/步
loss: 9.7 (step 100) -> 2.4 (500) -> 0.3 (6000) -> 0.077 (50000)
```

**训练前务必关掉休眠**，否则会白等：
```powershell
powercfg /change standby-timeout-ac 0    # 管理员
```
（曾因 5 分钟休眠，17:51→18:59 一小时只走了 3 步，`updt_s:41`）

---

## 7. 已知坑与解法

### 7.1 校准：主从臂必须摆成"完全相同的姿态"

`Homing_Offset` 的物理含义是"校准时那个中位姿态的编码 - 2047"。
**只有两臂摆成相同姿态，offset 才能互相抵消**，否则底座会差几十度（曾差 67 归一化单位 ≈ 120°）。

**手动调 offset 绕过校准是不可行的** —— 实测舵机的 offset→Present 关系非线性：
```
offset 变化 -846  ->  Present 变化 +1490   （比例 1.76，不是 1:1）
```

**验收标准**：两臂摆成相同姿态时，6 个关节的归一化差值 < 5。

### 7.2 `is_calibrated = False` 会触发自动重校准

`connect()` 时若发现舵机 EEPROM 与校准文件不一致，会直接进入校准流程。
**危险**：如果你只是想"用现有校准"，它会把你刚写进去的值覆盖掉。

**如果必须在写入后立刻验证**：用 `bus.read_calibration()` 逐字段比对，别只看 `is_calibrated`。

### 7.3 串口间歇性失联 / `Missing motor IDs`

原因包括：`num_retry=0`（已打补丁）、舵机过载（error 位非 0）、内核句柄未释放（只能重启电脑）。

**诊断顺序**：
```python
# 1. 底层 ping，看 comm 和 error 两个返回值（只看 comm 会漏掉过载！）
model, comm, err = pk.ping(ph, mid)
if err & 0x20: print('过载')
# 2. 读电压/温度/负载
# 3. 检查是否有残留 python 进程占着串口
```

### 7.4 从臂 ID3（elbow_flex）历史故障

**症状**：`Present_Position` 超过 4095（如 4762/4749）、负载 100%、`error=32`（过载）、反复失联。

**结论**：断电重启只能清 error 位，**多圈计数清不掉**（存在 EEPROM）。
这是硬件层面的位置计数器错乱，软件无解。**换舵机**是唯一根治方案。

**临时缓解**：把 offset 设成正数（如 1024）让 Present 落回范围内 —— 能被 lerobot 识别、
能参与遥操作，但该关节的归一化是"假的"，精度不可靠。

### 7.5 相机与画面质量

- Orbbec 只在 `CAP_DSHOW` 后端 + 管理员权限下出图
- **HSV 检测阈值宁宽勿窄**：绿块在高光/阴影下 V 值会掉到 20~60，
  用 `(30,35,20)-(95,255,255)`；红块用 `(0,80,50)-(12,255,255)` + `(160,80,50)-(180,255,255)`
- **俯视图带直尺**比相机的斜视图准得多 —— 相机斜视会把"远侧"物体透视压缩，
  同一个 8~9cm 的距离在画面里可能只显示 3cm。**涉及距离判断时优先要高角度俯拍照 + 直尺**

### 7.6 SwanLab 0.10.2 不兼容

已打补丁 `patches\0007-swanlab-021-compat.patch`：`run.public.run_id` → `run.id`、
`experiment_url` 加兜底、`log(step=...)` 的 step 转 int。

**网页面板用不了**：`swanlab watch` 需要 `swanboard` 包，PyPI/清华源里已经没有这个包了。
**替代方案**：用 `_setup\watch_train.py` 解析日志。

### 7.7 PowerShell 脚本必须带 UTF-8 BOM

`edit` 工具改 `.ps1` 文件会**丢掉 BOM**，导致 PowerShell 用 GBK 解 UTF-8 中文 →
启动就报 `Unexpected token '璁粌'` 或满屏乱码。

**改完 `.ps1` 必须检查**：
```powershell
$b = [System.IO.File]::ReadAllBytes($path)
if ($b[0] -ne 0xEF) { [System.IO.File]::WriteAllBytes($path, ([byte[]](0xEF,0xBB,0xBF)) + $b) }
```

### 7.8 日志解析（`watch_train.py` 踩过的坑）

`Tee-Object` 输出的日志有三个陷阱：
1. **编码是 UTF-16 LE**（不是 UTF-8）
2. **按窗口宽度硬折行**：`updt_s:0.184` 会变成 `updt_s:0.1` + `184`
3. **step 用 K/M 缩写**：`step:6000` 显示为 `step:6K`

所以正则必须容忍折行 + 支持 K/M 后缀，速度优先用每步的 `updt_s+data_s` 中位数
（而不是首尾时间戳差，否则休眠会被算进去）。

---

## 8. 数据与模型现状

**数据集**：`datasets\stack_cube_v2`（100 轮 / 24059 帧 / 409 MB / 30fps）

| 段 | 点位 | 轮数 | 帧数范围 | 平均 |
|---|---|---|---|---|
| 0–24 | A 右前 | 25 | 271–472 | 337 |
| 25–49 | B 左侧 | 25 | 138–376 | 206 |
| 50–74 | C 右后 | 25 | 146–378 | 201 |
| 75–99 | D 左后 | 25 | 160–275 | 219 |

- 单任务描述：`Stack the green cube on top of the red cube`
- 红块边长约 **1.4cm**，绿块同尺寸；中心距约 2~3cm（相机斜视会看成 1~3cm，实际够用）
- 抽样验证过：4 个点位互不相同，**每轮都以成功堆叠结束**

**模型**：`outputs\train\stack_cube_v2\checkpoints\last\pretrained_model`
- 50000 步，loss 0.077，`model.safetensors` 201 MB
- 25 个 checkpoint，共 14.4 GB（可清理中间的，只留 last 和 050000）

**旧数据**：`datasets\stack_cube_v1`（5 轮旧格式，可删）

---

## 9. 补丁清单（`patches\`）

| 补丁 | 内容 | 状态 |
|---|---|---|
| `0001-windows-checkpoint-junction` | 符号链接没权限时改用目录联接（junction） | ✅ 必需 |
| `0002-servo-bus-robustness` | `sync_read`/`write` 加 `num_retry=3` | ✅ 必需 |
| `0003-camera-dshow-backend` | 相机后端可用环境变量覆盖 | ✅ 必需 |
| `0004-record-keyboard-and-guards` | 空格暂停 + 空 episode 保护 | ✅ 必需 |
| `0005-servo-position-overflow-guard` | `Present_Position > 4095` 时 `& 0x0FFF` | ✅ 必需 |
| `0006-REVERTED-DO-NOT-APPLY-...` | Homing_Offset 12 位补码 | ⛔ **已回滚，别用** |
| `0007-swanlab-021-compat` | SwanLab 0.10.2 API 兼容 | ✅ 必需 |

**重新应用全部补丁**：
```powershell
git -C D:\LeRobot\lerobot checkout -- .
Get-ChildItem D:\LeRobot\patches\0*.patch | Where-Object { $_.Name -notlike '*REVERTED*' } |
  ForEach-Object { git -C D:\LeRobot\lerobot apply $_.FullName }
```

---

## 10. 录制与推理的操作细节

**录制按键**（键盘焦点必须在那个窗口上）

| 键 | 作用 |
|---|---|
| `→` | 结束本轮 / 跳过整理等待 |
| `←` | 放弃本轮重录 |
| `空格` | 暂停/继续（暂停期间不录画面、不发指令） |
| `ESC` | 停止（已录的保留，下次 `-Resume` 继续） |

**录制注意**
- `-Episodes N` 是"**本次再录 N 轮**"，不是"录到总共 N 轮"
- 数据集目录已存在时必须加 `-Resume`，否则脚本会拒绝启动
- 堆叠完成立刻按 `→`，别干等 30 秒超时

**推理注意**
- `07_run_policy.ps1` 只连从臂，**主臂不用动也不用接**
- 会自动选 `checkpoints\last`
- eval 数据集名必须以 `eval_` 开头（脚本会自动补）
- **推理效果极度依赖环境一致性**：相机位置、光照、绿块初始点位都要和录制时一致

---

## 11. 跨机器共享校准（和队友协作）

**前提**：必须是**同一台机械臂**（`homing_offset` 取决于每个舵机的舵盘安装角度）。

**正确流程**：
1. 在一台机器上完成"两臂摆相同姿态"的配对校准
2. 验证 6 个关节归一化差值 < 5
3. 把 `_tools\hf-cache\lerobot\calibration\` 下的两个 JSON 打包给其他机器
4. 对方放到同样路径（**文件名必须和对方配置的 id 一致**：`my_follower.json` / `my_leader.json`）
5. 用 `bus.write_calibration()` 写回舵机，逐字段核对

**参考**：`_tools\calibration-share-v2\`（队友发来的包，含 `README.txt` + `sync_calibration.py`，
但那个 py 用的是旧版模块路径 `lerobot.robots.so_follower`，本仓库是 `so101_follower`，**跑不了**）

**数据合并训练**：数据集里存的是归一化值，只要**行程跨度一致**就能合并
（`Homing_Offset` 在归一化公式的分子分母里互相抵消）。
