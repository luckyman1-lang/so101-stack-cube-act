"""把 lerobot 的 swanlab_utils 适配到 swanlab 0.10.2（写入的是 .id 而不是 .public.run_id）。"""
import io
import sys

P = r"D:\LeRobot\lerobot\src\lerobot\utils\swanlab_utils.py"

src = io.open(P, "r", encoding="utf-8", newline="").read()
NL = "\r\n" if "\r\n" in src else "\n"

old_run_id = "        run_id = self._run.public.run_id"
new_run_id = NL.join(
    [
        "        # [本地改动] swanlab 0.10.2 的 Run 没有 .public，run id 直接在 .id 上",
        "        run_id = self._run.id",
    ]
)

old_log = (
    "        logging.info("
    + NL
    + '            f"Track this run --> {colored(self._run.public.cloud.experiment_url, \'yellow\', attrs=[\'bold\'])}"'
    + NL
    + "        )"
)
new_log = NL.join(
    [
        "        # [本地改动] offline/local 模式没有 experiment_url（0.10.2 读它会抛 ValueError）",
        "        try:",
        "            run_url = self._run.url",
        "        except Exception:",
        "            run_url = str(self.log_dir)",
        '        logging.info(f"Track this run --> {colored(run_url, \'yellow\', attrs=[\'bold\'])}")',
    ]
)

if old_run_id not in src:
    print("run_id 那行没找到（可能已经改过）" if "self._run.id" in src else "run_id 那行没找到")
else:
    src = src.replace(old_run_id, new_run_id, 1)
    print("已替换 run_id")

if old_log not in src:
    print("experiment_url 那段没找到（可能已经改过）" if "run_url" in src else "experiment_url 那段没找到")
else:
    src = src.replace(old_log, new_log, 1)
    print("已替换 experiment_url")

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("写回完成")

rest = [ln for ln in src.split(NL) if ".public" in ln]
print("残留的 .public 行数:", len(rest))
for ln in rest:
    print("  ", ln.strip())
