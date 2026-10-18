"""确认 Windows 上 torch 的 CUDA 轮子要从 download.pytorch.org 取，并测下载速度。"""

import re
import time
import urllib.parse
import urllib.request

CANDIDATES = {
    "pytorch-cu126": "https://download.pytorch.org/whl/cu126/torch/",
    "pytorch-cu128": "https://download.pytorch.org/whl/cu128/torch/",
    "pypi": "https://pypi.org/simple/torch/",
}
PROBE = 15 * 1024 * 1024


def head_size(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "probe"})
    return int(urllib.request.urlopen(req, timeout=60).headers.get("Content-Length") or 0)


def speed(url, limit=PROBE):
    req = urllib.request.Request(url, headers={"User-Agent": "probe", "Range": f"bytes=0-{limit - 1}"})
    t0, got = time.time(), 0
    with urllib.request.urlopen(req, timeout=90) as r:
        while got < limit:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            got += len(chunk)
    return got, time.time() - t0


print("== PyPI 上的 torch(cp310 win) 体积，用来判断是不是 CUDA 版 ==")
for ver in ("2.14.1", "2.7.1"):
    url = f"https://pypi.org/simple/torch/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "probe"})
        html = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
        pat = re.compile(rf'href="([^"]*torch-{re.escape(ver)}-cp310-cp310-win_amd64\.whl[^"]*)"')
        m = pat.findall(html)
        if m:
            u = urllib.parse.urljoin(url, m[-1].split("#")[0])
            print(f"  torch {ver:<8} {head_size(u) / 1024**3:5.2f} GB")
        else:
            print(f"  torch {ver:<8} 没找到")
    except Exception as e:
        print(f"  torch {ver:<8} 失败 {e}")

print("\n== download.pytorch.org 上的 CUDA 轮子 ==")
for name, index in CANDIDATES.items():
    if not name.startswith("pytorch"):
        continue
    try:
        req = urllib.request.Request(index, headers={"User-Agent": "probe"})
        html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        links = re.findall(r'href="([^"]+)"', html)
        matches = [
            urllib.parse.urljoin(index, l.split("#")[0])
            for l in links
            if "cp310" in l and "win_amd64" in l
        ]
        if not matches:
            print(f"  {name}: 没有 cp310 win_amd64")
            continue
        # 取 2.7.1 优先
        pick = next((u for u in matches if "2.7.1" in u), matches[-1])
        size = head_size(pick)
        got, dt = speed(pick)
        print(f"  {name}: {pick.rsplit('/', 1)[-1]}  {size / 1024**3:.2f} GB  "
              f"速度 {got / dt / 1024 / 1024:.2f} MB/s  (整包约 {size / 1024**3 / (got / dt / 1024**3) / 60:.1f} 分钟)")
    except Exception as e:
        print(f"  {name}: FAILED {type(e).__name__} {str(e)[:90]}")
