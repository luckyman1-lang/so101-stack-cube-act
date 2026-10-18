"""跨进程测试：子进程用 tempfile.mkdtemp 建的目录，父进程能不能访问/删除。"""

import os
import shutil
import subprocess
import sys
import tempfile

BASE = r"D:\LeRobot\_tools\tmp\xproc"
shutil.rmtree(BASE, ignore_errors=True)
os.makedirs(BASE, exist_ok=True)

for flags in ([], ["-S"], ["-I"]):
    label = " ".join(flags) or "(default)"
    code = (
        "import tempfile,os,sys\n"
        f"d = tempfile.mkdtemp(prefix='.tmp-', dir=r'{BASE}')\n"
        "open(os.path.join(d,'w.whl'),'w').write('x')\n"
        "print(d)\n"
    )
    r = subprocess.run([sys.executable, *flags, "-c", code], capture_output=True, text=True)
    d = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
    print(f"\n--- subprocess {label} ---")
    if not d:
        print("  subprocess failed:", r.stderr.strip()[:200])
        continue
    try:
        entries = os.listdir(d)
        print(f"  parent listdir: OK {entries}")
    except Exception as e:
        print(f"  parent listdir: FAIL {type(e).__name__} {e}")
    try:
        shutil.rmtree(d)
        print("  parent rmtree : OK")
    except Exception as e:
        print(f"  parent rmtree : FAIL {type(e).__name__} {e}")
    rc = subprocess.run(["icacls", d], capture_output=True, text=True)
    print("  icacls rc:", rc.returncode, (rc.stdout or rc.stderr).strip()[:150])
