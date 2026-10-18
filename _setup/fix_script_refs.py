"""脚本改编号后，批量修正文件里互相引用的旧编号（保留 UTF-8 BOM）。"""

import os

S = r"D:\LeRobot\scripts"

FIXES = {
    "03_calibrate.ps1": [("02_calibrate", "03_calibrate"), ("03_teleoperate", "04_teleoperate")],
    "04_teleoperate.ps1": [("03_teleoperate", "04_teleoperate"), ("04_record_dataset", "05_record_dataset")],
    "05_record_dataset.ps1": [("04_record_dataset", "05_record_dataset"), ("05_train_act", "06_train_act")],
    "06_train_act.ps1": [
        ("05_train_act", "06_train_act"),
        ("04_record_dataset", "05_record_dataset"),
        ("06_run_policy", "07_run_policy"),
    ],
    "07_run_policy.ps1": [("06_run_policy", "07_run_policy"), ("05_train_act", "06_train_act")],
}

for fn, pairs in FIXES.items():
    path = os.path.join(S, fn)
    raw = open(path, "rb").read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    total = 0
    for old, new in pairs:
        total += text.count(old)
        text = text.replace(old, new)
    with open(path, "wb") as fh:
        fh.write((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
    print(f"{fn:<26} 替换 {total:>2} 处   BOM={bom}")

# 00_env_check.py 收尾提示里的流程串
p = os.path.join(S, "00_env_check.py")
text = open(p, encoding="utf-8").read()
old = "01_find_ports -> 02_calibrate -> 03_teleoperate -> 04_record"
new = (
    "01_find_ports -> 02_setup_motors(仅散件) -> 03_calibrate -> 04_teleoperate "
    "-> 05_record_dataset -> 06_train_act -> 07_run_policy"
)
found = old in text
open(p, "w", encoding="utf-8").write(text.replace(old, new))
print(f"{'00_env_check.py':<26} 收尾提示更新={found}")
