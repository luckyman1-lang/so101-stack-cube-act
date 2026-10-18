"""列出 USTC 镜像上 torch / torchvision 的 cp310 win_amd64 版本和体积。"""

import re
import urllib.parse
import urllib.request

BASE = "https://mirrors.ustc.edu.cn/pypi/simple/{pkg}/"


def list_wheels(pkg, want):
    url = BASE.format(pkg=pkg)
    req = urllib.request.Request(url, headers={"User-Agent": "probe"})
    html = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
    # PEP 503 索引里 data-requires-python / 文件名；体积要 HEAD 才拿得到
    names = re.findall(r'href="([^"]+)"', html)
    out = {}
    for href in names:
        full = urllib.parse.urljoin(url, href.split("#")[0])
        fn = full.rsplit("/", 1)[-1]
        if not fn.endswith(".whl"):
            continue
        if "cp310" not in fn or "win_amd64" not in fn:
            continue
        m = re.match(rf"{re.escape(pkg)}-(.+?)-cp310", fn)
        if not m:
            continue
        out[m.group(1)] = full
    return {v: u for v, u in out.items() if v in want}


def size_of(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "probe"})
    r = urllib.request.urlopen(req, timeout=45)
    return int(r.headers.get("Content-Length") or 0)


for pkg, want in (
    ("torch", {"2.7.1", "2.8.0", "2.9.1", "2.6.0"}),
    ("torchvision", {"0.22.1", "0.23.0", "0.24.1", "0.21.0"}),
):
    print(f"== {pkg} ==")
    for ver, url in sorted(list_wheels(pkg, want).items()):
        try:
            gb = size_of(url) / 1024**3
            print(f"  {ver:<10} {gb:5.2f} GB   {url.rsplit('/', 1)[-1]}")
        except Exception as e:
            print(f"  {ver:<10} HEAD failed: {e}")
