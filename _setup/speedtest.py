"""测几个 PyPI 镜像下载 torch 大包的实际速度（只取前 20MB 计时）。"""

import re
import time
import urllib.parse
import urllib.request

INDEXES = {
    "aliyun": "https://mirrors.aliyun.com/pypi/simple/torch/",
    "tsinghua": "https://pypi.tuna.tsinghua.edu.cn/simple/torch/",
    "ustc": "https://mirrors.ustc.edu.cn/pypi/simple/torch/",
    "pypi": "https://pypi.org/simple/torch/",
}
PAT = re.compile(r'href="([^"]*torch-[^"]*cp310-cp310-win_amd64\.whl[^"]*)"')
PROBE = 20 * 1024 * 1024


def fetch(url, limit, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": "probe", "Range": f"bytes=0-{limit - 1}"})
    t0 = time.time()
    got = 0
    with urllib.request.urlopen(req, timeout=timeout) as r:
        while got < limit:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            got += len(chunk)
        dt = time.time() - t0
    return got, dt


for name, index in INDEXES.items():
    try:
        req = urllib.request.Request(index, headers={"User-Agent": "probe"})
        html = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
        links = PAT.findall(html)
        if not links:
            print(f"{name:<9} index has no cp310 win_amd64 torch wheel")
            continue
        url = urllib.parse.urljoin(index, links[-1].split("#")[0])
        got, dt = fetch(url, PROBE)
        speed = got / dt / 1024 / 1024
        print(f"{name:<9} {got / 1024 / 1024:5.1f}MB / {dt:4.1f}s = {speed:6.2f} MB/s   {url.rsplit('/', 1)[-1][:58]}")
    except Exception as e:
        print(f"{name:<9} FAILED: {type(e).__name__} {str(e)[:80]}")
