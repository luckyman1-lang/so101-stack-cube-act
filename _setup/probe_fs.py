"""探测沙箱下各类文件操作是否可用（诊断 pip 失败的原因）。"""

import os
import shutil
import stat
import tempfile

BASE = r"D:\LeRobot\_tools\tmp"
os.makedirs(BASE, exist_ok=True)


def show_acl(path):
    try:
        st = os.stat(path)
        print(f"    mode={stat.filemode(st.st_mode)}")
    except Exception as e:
        print("    stat failed:", e)


def check(label, fn):
    try:
        fn()
        print(f"OK    {label}")
        return True
    except Exception as e:
        print(f"FAIL  {label}: {type(e).__name__} {e}")
        return False


print("== create subdir ==")
sub = os.path.join(BASE, "probe_sub")
check("makedirs", lambda: os.makedirs(sub, exist_ok=True))
show_acl(sub)

print("== write file (w) ==")
f1 = os.path.join(sub, "a.txt")
check("open(w)", lambda: open(f1, "w").write("hello"))

print("== write file (O_CREAT|O_EXCL) ==")
f2 = os.path.join(sub, "b.txt")


def excl():
    fd = os.open(f2, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(fd, b"x")
    os.close(fd)


check("os.open O_EXCL", excl)

print("== listdir ==")
check("listdir(sub)", lambda: print("    entries:", os.listdir(sub)))

print("== rename ==")
check("rename", lambda: os.replace(f2, os.path.join(sub, "c.txt")))

print("== unlink ==")
check("unlink a.txt", lambda: os.remove(f1))

print("== rmtree ==")
check("rmtree(sub)", lambda: shutil.rmtree(sub))

print("== tempfile.mkdtemp in BASE ==")
check("mkdtemp", lambda: print("    made:", tempfile.mkdtemp(dir=BASE)))

print("== default temp dir ==")
print("    tempfile.gettempdir() =", tempfile.gettempdir())
check("mkdtemp(default)", lambda: print("    made:", tempfile.mkdtemp()))
