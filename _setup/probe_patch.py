import os
import subprocess
import sys
import tempfile

print("== 1) 当前进程补丁状态 ==")
print("  os.mkdir patched     :", getattr(os, "_dsh_mkdir_patched", False))
print("  tempfile.mkdtemp     :", getattr(tempfile, "_dsh_mkdtemp_patched", False))

print("\n== 2) 子进程是否也打上补丁 ==")
env = dict(os.environ)
env["PYTHONPATH"] = r"D:\LeRobot\_tools\tmp\fake_overlay"
code = (
    "import os,tempfile,sys;"
    "print('sub dirs:', [p for p in sys.path if 'site-packages' in p][:1]);"
    "print('sub patched:', getattr(os,'_dsh_mkdir_patched',False), getattr(tempfile,'_dsh_mkdtemp_patched',False))"
)
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
print("  ", (r.stdout or "").strip().replace("\n", "\n   "))
if r.stderr.strip():
    print("   stderr:", r.stderr.strip()[:300])

print("\n== 3) 复现 setuptools 的 TemporaryDirectory(prefix='.tmp-') ==")
base = r"D:\LeRobot\_tools\tmp\inner_test"
os.makedirs(base, exist_ok=True)
try:
    with tempfile.TemporaryDirectory(prefix=".tmp-", dir=base) as td:
        print("   created:", td)
        with open(os.path.join(td, "wheel.whl"), "w") as fh:
            fh.write("x")
        print("   写入成功")
    print("   cleanup 成功")
except Exception as e:
    print("   FAILED:", type(e).__name__, e)

print("\n== 4) 直接检查新建目录的可访问性 ==")
p = tempfile.mkdtemp(prefix=".tmp-", dir=base)
print("   dir:", p)
print("   listdir ok:", os.listdir(p) == [])
r = subprocess.run(["icacls", p], capture_output=True, text=True)
print("   icacls rc:", r.returncode, (r.stdout or r.stderr).strip()[:200])
