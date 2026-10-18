p = r"D:\LeRobot\lerobot\src\lerobot\motors\motors_bus.py"
raw = open(p, "rb").read()
CRLF = b"\r\n"
nl = CRLF if CRLF in raw else b"\n"
eol = "CRLF" if nl == CRLF else "LF"
lines = raw.split(nl)
print("换行符: " + eol + "  总行数: " + str(len(lines)))

def show(i, tag):
    print("  " + tag + " " + str(i) + ": " + lines[i-1].decode("utf-8", "replace").strip()[:95])

print("")
print("替换前:")
for i, tag in ((991, "write   "), (1006, "doc     "), (1059, "sync_read"), (1067, "doc     ")):
    show(i, tag)

for i in (991, 1059):
    assert b"num_retry: int = 0" in lines[i - 1], "第 %d 行没找到预期内容" % i
    lines[i - 1] = lines[i - 1].replace(b"num_retry: int = 0", b"num_retry: int = 3")
for i in (1006, 1067):
    lines[i - 1] = lines[i - 1].replace(b"Defaults to `0`", b"Defaults to `3`")

open(p, "wb").write(nl.join(lines))
print("")
print("替换后:")
for i, tag in ((991, "write   "), (1006, "doc     "), (1059, "sync_read"), (1067, "doc     ")):
    show(i, tag)
