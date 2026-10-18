# `_setup\` 目录说明

这里只是**安装过程**留下的脚本和日志，**跑机械臂完全不需要它们**，可以整个删掉。

保留它们的目的：环境出问题时能追溯是怎么装的、当时是什么报错。

| 文件 | 作用 |
| --- | --- |
| `get_python310.py` | 下载并解压便携版 CPython 3.10（python-build-standalone）。**重建环境用这个** |
| `cpython-3.10.22+...tar.gz` | 上面下载的原始包（39MB），可删；留着方便重装 |
| `download.py` | 通用 HTTPS 下载器（本机 curl/git 的 schannel 握手失败，只能用 Python 下载） |
| `fetch_repo.py` | 用 Python 下载并解压 GitHub 仓库 tar 包（git clone 不通时的兜底） |
| `constraints.txt` | 安装约束（opencv<5、huggingface-hub<1、**rerun-sdk<0.23**）。**重建环境用这个** |
| `add_bom.py` | 给 `.ps1`/`.ini` 加 UTF-8 BOM（PS 5.1 没有 BOM 会把中文当 ANSI 解析）。**改完脚本要重跑** |
| `set_ports.py` | 临时改/还原 `config\robot.ini` 里的串口（验证脚本用） |
| `fix_script_refs.py` | 脚本改编号后批量修正互相引用的旧编号 |
| `verify_patches.py` | 验证 checkpoint 目录联接补丁 + 摄像头参数解析 |
| `verify_activate.ps1` | 验证 `activate.ps1` 能在 Bypass 策略下正确激活环境 |
| `probe_fs.py` / `probe_patch.py` / `probe_xproc.py` | 排查"临时目录权限被拒"用的对照实验（坑 2） |
| `probe_rerun.py` | 检查 rerun 版本与 lerobot 的接口兼容性（坑 13） |
| `probe_torch_cuda.py` / `speedtest.py` / `list_torch.py` / `list_rerun.py` | 测镜像速度、确认 CUDA 版 torch / 兼容 rerun 版本的来源 |
| `extract_mm.py` / `find310.py` | 中间过程脚本（micromamba 已弃用，找 3.10 资源用） |
| `pip_install*.log` | 各次 pip 安装日志 |
| `cam_snapshots\` | `01_find_ports.ps1 -Cams -Snapshot` 存的摄像头快照 |
| `dataset_rrd\` | `08_view_dataset.ps1 -Save` 导出的 `.rrd`（用 `rerun xxx.rrd` 打开） |

## 如果要从零重建环境

```powershell
# 1) 便携 Python（会装到 D:\LeRobot\_tools\python310）
python _setup\get_python310.py

# 2) CUDA 版 torch（必须走 PyTorch 官方源，PyPI 上的是 CPU 版）
D:\LeRobot\_tools\python310\python.exe -m pip install `
  --index-url https://mirrors.ustc.edu.cn/pypi/simple `
  --extra-index-url https://download.pytorch.org/whl/cu126 `
  "torch==2.7.1+cu126" "torchvision==0.22.1+cu126"

# 3) 其余依赖（注意 --no-build-isolation，见 README 坑 3）
D:\LeRobot\_tools\python310\python.exe -m pip install `
  --index-url https://pypi.org/simple `
  --constraint _setup\constraints.txt `
  --no-build-isolation `
  -e "D:/LeRobot/lerobot[feetech]"

# 4) 【关键】补回 sitecustomize 补丁：
#    _tools\python310\Lib\site-packages\sitecustomize.py
#    它修两件事（README 坑 2、坑 14）：
#      * tempfile.mkdtemp  -> 不再用 os.mkdir(0o700) 建临时目录
#      * tarfile.TarFile.makedir -> 同上，否则解压 tar 包会 PermissionError
#    重建后必须重新放回去，否则 pip 装包 / 解压 / 建 venv 都会报权限错

# 5) 打 lerobot 的 checkpoint 补丁（符号链接 -> 目录联接，README 坑 4）
git -C D:\LeRobot\lerobot apply D:\LeRobot\patches\0001-windows-checkpoint-junction.patch

# 6) 重新加 BOM
D:\LeRobot\_tools\python310\python.exe _setup\add_bom.py

# 7) 自检
powershell -ExecutionPolicy Bypass -File D:\LeRobot\scripts\00_env_check.ps1
```
