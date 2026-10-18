"""下载并解压 python-build-standalone 的便携版 CPython 3.10（无需安装器/conda）。

背景：DSH 沙箱下 Windows schannel 不可用，conda / micromamba / curl 的 TLS 全部失败。
Python 自带 OpenSSL 可正常联网，因此用 Python 自身来取便携版解释器。

用法: python get_python310.py
产物: D:\\LeRobot\\_tools\\python310\\python.exe
"""

import json
import os
import re
import shutil
import sys
import tarfile
import time
import urllib.request

API = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
SETUP = r"D:\LeRobot\_setup"
TOOLS = r"D:\LeRobot\_tools"
DEST = os.path.join(TOOLS, "python310")


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


TAG = "20261009"  # 最后一个仍带 Windows 3.10 构建的 release（3.10 已 EOL）
PAT = re.compile(r"cpython-3\.10\.\d+\+.*x86_64-pc-windows-msvc.*install_only\.tar\.gz$")


def assets_of(tag: str) -> list[str]:
    url = API if tag == "latest" else f"{API.rsplit('/releases', 1)[0]}/releases/tags/{tag}"
    data = json.loads(get(url))
    return [a["browser_download_url"] for a in data["assets"]]


def pick_asset(tag: str) -> str:
    cands = [u for u in assets_of(tag) if PAT.search(u)]
    if not cands and tag != "latest":
        print(f"tag {tag} has no 3.10 windows asset, scanning releases...")
        rels = json.loads(get(f"{API.rsplit('/releases', 1)[0]}/releases?per_page=15"))
        for r in rels:
            hit = [a["browser_download_url"] for a in r["assets"] if PAT.search(a["name"])]
            if hit:
                print("fallback release tag:", r["tag_name"])
                cands = hit
                break
    if not cands:
        raise SystemExit("no matching 3.10 asset found")
    url = cands[0]
    print("asset:", url.rsplit("/", 1)[-1])
    return url


def fetch(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last, t0 = 0, 0.0, time.time()
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if time.time() - last >= 3:
                    last = time.time()
                    print(f"  {done / total * 100:5.1f}% {human(done)}/{human(total)}", flush=True)
    os.replace(tmp, dest)
    print("downloaded:", dest, human(os.path.getsize(dest)))


def main() -> int:
    url = pick_asset(TAG)
    archive = os.path.join(SETUP, url.rsplit("/", 1)[-1])
    if not os.path.exists(archive):
        fetch(url, archive)
    else:
        print("archive cached:", archive)

    if os.path.isdir(DEST):
        shutil.rmtree(DEST)
    staging = os.path.join(SETUP, "_py_stage")
    if os.path.isdir(staging):
        shutil.rmtree(staging)
    os.makedirs(staging, exist_ok=True)
    print("extracting...")
    with tarfile.open(archive, "r:gz") as t:
        t.extractall(staging)
    # tarball 顶层是 python/，把它搬到 DEST
    inner = os.path.join(staging, "python")
    src = inner if os.path.isdir(inner) else staging
    shutil.move(src, DEST)
    shutil.rmtree(staging, ignore_errors=True)

    exe = os.path.join(DEST, "python.exe")
    print("OK:", exe, "exists:", os.path.exists(exe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
