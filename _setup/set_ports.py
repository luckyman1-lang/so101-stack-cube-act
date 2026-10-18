"""临时把 config\\robot.ini 里的两个串口改成指定值（保留 UTF-8 BOM），用于 -DryRun 验证。

用法: python set_ports.py COM9 COM10
     python set_ports.py --restore      # 从 robot.ini.bak 还原
"""

import os
import re
import shutil
import sys

CFG = r"D:\LeRobot\config\robot.ini"
BAK = CFG + ".bak"


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--restore":
        if not os.path.exists(BAK):
            print("没有备份文件，无法还原")
            return 1
        shutil.copy2(BAK, CFG)
        os.remove(BAK)
        print("已还原 robot.ini")
        return 0

    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    robot_port, teleop_port = sys.argv[1], sys.argv[2]
    if not os.path.exists(BAK):
        shutil.copy2(CFG, BAK)

    raw = open(CFG, "rb").read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")

    section = None
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
        elif re.match(r"^port\s*=", stripped):
            if section == "robot":
                line = f"port = {robot_port}\n"
            elif section == "teleop":
                line = f"port = {teleop_port}\n"
        out.append(line)

    with open(CFG, "wb") as fh:
        fh.write((b"\xef\xbb\xbf" if bom else b"") + "".join(out).encode("utf-8"))
    print(f"已临时设置: robot={robot_port} teleop={teleop_port}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
