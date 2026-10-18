"""用 Python 下载并解压 GitHub 仓库的 tar 包（沙箱/网络下 git clone 不稳时的兜底）。

相比 git clone 的好处：不经过 git 的过滤器（本机 git 的 sh 过滤器在沙箱里会崩）、
不走 schannel、断线重试也简单。

用法: python fetch_repo.py <owner/repo> <branch> <目标目录>
例:   python fetch_repo.py Seeed-Projects/Seeed_RoboController factory D:\\x\\Seeed_RoboController
"""

import io
import os
import shutil
import sys
import tarfile
import urllib.request
import uuid


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    owner_repo, branch, dest = sys.argv[1], sys.argv[2], sys.argv[3]

    url = f"https://codeload.github.com/{owner_repo}/tar.gz/refs/heads/{branch}"
    print(f"下载 {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = resp.read()
    print(f"  收到 {human(len(data))}")

    # 每次都用全新的临时目录名：之前失败留下的目录可能带"受保护权限"而删不掉，
    # 复用它会直接 PermissionError。
    stage = f"{dest}__stage_{uuid.uuid4().hex[:8]}"
    os.makedirs(stage)
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            tar.extractall(stage)

        entries = os.listdir(stage)
        if len(entries) != 1:
            raise SystemExit(f"压缩包结构异常，顶层有 {len(entries)} 项: {entries}")

        if os.path.exists(dest):
            shutil.rmtree(dest, ignore_errors=True)
        if os.path.exists(dest):
            raise SystemExit(
                f"目标目录已存在且删不掉（很可能是之前失败留下的权限坏目录）：\n  {dest}\n"
                "请在你自己的资源管理器/终端里把它删掉，再重新运行。"
            )

        shutil.move(os.path.join(stage, entries[0]), dest)
        print(f"  解压到 {dest}")
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if os.path.exists(stage):
            print(f"  （注意：临时目录没删掉，可在资源管理器里手动删除：{stage}）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
