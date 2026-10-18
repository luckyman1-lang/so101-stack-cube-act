"""给 .ps1 / .ini 加 UTF-8 BOM。

原因：Windows PowerShell 5.1（powershell.exe）在没有 BOM 时按系统 ANSI 代码页
解析脚本文件，脚本里的中文会被解析成乱码，进而破坏字符串引号、报
"Unexpected token" / "The string is missing the terminator"。
加上 UTF-8 BOM 后，PS 5.1 和 PS 7 都能正确识别 UTF-8。

幂等：已有 BOM 的文件跳过。
"""

import os
import sys

ROOT = r"D:\LeRobot"
TARGETS = [
    os.path.join(ROOT, "scripts"),
    os.path.join(ROOT, "config"),
    ROOT,
]

changed = []
skipped = []

for base in TARGETS:
    for dirpath, _dirs, files in os.walk(base):
        # 只处理 scripts / config / 根目录的顶层脚本
        if base == ROOT and dirpath != ROOT:
            continue
        for fn in files:
            if not fn.lower().endswith((".ps1", ".ini")):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, "rb") as fh:
                raw = fh.read()
            if raw.startswith(b"\xef\xbb\xbf"):
                skipped.append(path)
                continue
            # 确认是合法 UTF-8，避免把别的编码文件强行加 BOM
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as e:
                print(f"跳过（不是 UTF-8）: {path} -> {e}")
                continue
            with open(path, "wb") as fh:
                fh.write(b"\xef\xbb\xbf" + text.encode("utf-8"))
            changed.append(path)

print(f"已加 BOM: {len(changed)} 个")
for p in changed:
    print("  +", os.path.relpath(p, ROOT))
print(f"已有 BOM 跳过: {len(skipped)} 个")
sys.exit(0)
