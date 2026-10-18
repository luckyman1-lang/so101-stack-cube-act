import subprocess

p = r"D:\LeRobot\lerobot\src\lerobot\motors\motors_bus.py"
repo = r"D:\LeRobot\lerobot"

# 1) 恢复到原始文件（两个补丁都重新打一遍，保证顺序正确）
r = subprocess.run(["git", "-C", repo, "checkout", "--", "src/lerobot/motors/motors_bus.py"],
                   capture_output=True, text=True)
print("git checkout rc =", r.returncode, r.stderr.strip()[:120])
assert r.returncode == 0

raw = open(p, "rb").read()
CRLF = b"\r\n"
nl = CRLF if CRLF in raw else b"\n"
lines = raw.split(nl)

# 2) 先打 num_retry 补丁（行号在后面，不会被第 3 步影响）
for i in (991, 1059):
    assert b"num_retry: int = 0" in lines[i - 1], i
    lines[i - 1] = lines[i - 1].replace(b"num_retry: int = 0", b"num_retry: int = 3")
for i in (1006, 1067):
    lines[i - 1] = lines[i - 1].replace(b"Defaults to `0`", b"Defaults to `3`")
print("num_retry 补丁 OK")

# 3) 再整体替换 record_ranges_of_motion 的核心段（第 747~770 行，一次替换避免行号漂移）
assert b"start_positions = self.sync_read" in lines[746], lines[746]
assert b"same_min_max = [motor for motor in motors" in lines[769], lines[769]

new_block = [
    '        # [本地改动] 只接受 12 位编码范围(0~4095)内的读数：偶发的通信错读会返回',
    '        # 超范围值（实测出现过 32918 / 33605），一旦被 min/max 记住，该关节的校准',
    '        # 跨度就会虚高，归一化后行程被压缩，遥操作时这个关节几乎不动。',
    '        start_positions = self.sync_read("Present_Position", motors, normalize=False)',
    '        mins = {}',
    '        maxes = {}',
    '        for motor, pos in start_positions.items():',
    '            if 0 <= pos <= 4095:',
    '                mins[motor] = pos',
    '                maxes[motor] = pos',
    '',
    '        user_pressed_enter = False',
    '        while not user_pressed_enter:',
    '            positions = self.sync_read("Present_Position", motors, normalize=False)',
    '            for motor in motors:',
    '                pos = positions[motor]',
    '                if 0 <= pos <= 4095:',
    '                    mins[motor] = min(pos, mins.get(motor, pos))',
    '                    maxes[motor] = max(pos, maxes.get(motor, pos))',
    '',
    '            if display_values:',
    '                print("\\n-------------------------------------------")',
    "                print(f\"{'NAME':<15} | {'MIN':>6} | {'POS':>6} | {'MAX':>6}\")",
    '                for motor in motors:',
    '                    print(f"{motor:<15} | {mins.get(motor, -1):>6} | {positions[motor]:>6} | {maxes.get(motor, -1):>6}")',
    '',
    '            if enter_pressed():',
    '                user_pressed_enter = True',
    '',
    '            if display_values and not user_pressed_enter:',
    '                # Move cursor up to overwrite the previous output',
    '                move_cursor_up(len(motors) + 3)',
    '',
    '        same_min_max = [motor for motor in motors if mins.get(motor) == maxes.get(motor)]',
]
lines[746:770] = [b.encode("utf-8") for b in new_block]
open(p, "wb").write(nl.join(lines))
print("过滤补丁 OK（第 747~770 行整体替换）")
