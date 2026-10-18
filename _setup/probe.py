import urllib.request, ssl, sys
urls = [
 "https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease/Miniforge3-Windows-x86_64.exe",
 "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe",
 "https://mirrors.aliyun.com/pypi/simple/",
]
for u in urls:
    try:
        req = urllib.request.Request(u, method="HEAD", headers={"User-Agent":"probe"})
        r = urllib.request.urlopen(req, timeout=25)
        print("OK  ", r.status, r.headers.get("Content-Length"), u)
    except Exception as e:
        print("FAIL", type(e).__name__, str(e)[:110], u)
