import tarfile, os, shutil
src = r"D:\LeRobot\_setup\micromamba.tar.bz2"
out = r"D:\LeRobot\_setup\mm"
os.makedirs(out, exist_ok=True)
with tarfile.open(src, "r:bz2") as t:
    names = t.getnames()
    t.extractall(out)
print("members:", names)
exe = os.path.join(out, "Library", "bin", "micromamba.exe")
dst = r"D:\LeRobot\_tools\micromamba.exe"
os.makedirs(os.path.dirname(dst), exist_ok=True)
shutil.copy2(exe, dst)
print("installed:", dst, os.path.getsize(dst), "bytes")
