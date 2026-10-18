"""带进度和大小的 HTTPS 下载器。

用途：DSH 沙箱会拦掉 Windows schannel，导致 curl / git 默认后端握手失败。
Python 走自带 OpenSSL，可以正常下载，因此统一用它来拉取安装包。

用法: python download.py <url> <输出文件路径>
"""

import os
import sys
import time
import urllib.request


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    url, dest = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    tmp = dest + ".part"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        started = time.time()
        last = 0.0
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                now = time.time()
                if now - last >= 2:
                    last = now
                    speed = done / max(now - started, 1e-6)
                    pct = f"{done / total * 100:5.1f}%" if total else "  ?  "
                    print(
                        f"  {pct} {human(done)}/{human(total)} @ {human(speed)}/s",
                        flush=True,
                    )

    os.replace(tmp, dest)
    print(f"DONE {dest} {human(os.path.getsize(dest))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
