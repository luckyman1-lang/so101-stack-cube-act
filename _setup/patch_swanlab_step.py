"""训练收尾的两个修复：
1) swanlab 0.10.2 要求 step 是 int，lerobot 传的是字符串 "000100" -> 自动转 int
"""
import io
import re

P = r"D:\LeRobot\lerobot\src\lerobot\utils\swanlab_utils.py"

src = io.open(P, "r", encoding="utf-8", newline="").read()
NL = "\r\n" if "\r\n" in src else "\n"

old = (
    "        step_id = checkpoint_dir.name"
    + NL
    + '        artifact_name = f"{self._group}-{step_id}"'
)
new = (
    "        # [本地改动] swanlab 0.10.2 要求 step 是 int；checkpoint 目录名是 '000100' 这种字符串"
    + NL
    + "        step_id = checkpoint_dir.name"
    + NL
    + "        try:"
    + NL
    + "            step_int = int(step_id)"
    + NL
    + "        except (TypeError, ValueError):"
    + NL
    + "            step_int = 0"
    + NL
    + '        artifact_name = f"{self._group}-{step_id}"'
)

if old not in src:
    print("没找到 step_id 那段（可能已改）")
else:
    src = src.replace(old, new, 1)
    print("已插入 step_int 转换")

old2 = '        self._swanlab.log({f"model_checkpoint": self._swanlab.Text(model_path)}, step=step_id)'
new2 = '        self._swanlab.log({f"model_checkpoint": self._swanlab.Text(model_path)}, step=step_int)'

if old2 not in src:
    print("没找到 log(...step=step_id) 那行（可能已改）")
else:
    src = src.replace(old2, new2, 1)
    print("已把 step=step_id 改为 step=step_int")

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("写回完成")

for i, ln in enumerate(src.split(NL), 1):
    if "step_int" in ln or "step=step_id" in ln:
        print("  行%d: %s" % (i, ln.strip()))
