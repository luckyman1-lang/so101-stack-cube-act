"""从官方仓库 TheRobotStudio/SO-ARM100 拉取 SO-101 的 URDF / MJCF / STL 资产。

为什么需要：LeRobot 仓库里不带任何 URDF/MJCF，而 placo/pinocchio 在 Windows 装不上，
所以运动学、仿真、IK 校验全部依赖这份官方模型。

用法：
    D:\\LeRobot\\_tools\\python310\\python.exe _setup\\fetch_so101_sim.py
    ... --dest D:\\LeRobot\\assets\\so101_sim     指定落地目录
    ... --dry-run                                 只列清单不下载

落地结构（必须保持，因为 MJCF 里写死了 meshdir="assets"）：
    <dest>/
        README.md  joints_properties.xml  scene.xml
        so101_new_calib.xml            <- 主轴（新校准，与 LeRobot 中点约定一致）
        so101_new_calib_camera.xml     <- 带腕部相机挂载（仿真用这个）
        so101_new_calib.urdf  so101_new_calib_camera.urdf
        assets/*.stl
"""
import argparse
import json
import os
import sys
import urllib.request

API = "https://api.github.com/repos/TheRobotStudio/SO-ARM100/contents/Simulation/SO101"
RAW = "https://raw.githubusercontent.com/TheRobotStudio/SO-ARM100/main/Simulation/SO101"

# 顶层想保留的文件（.part 是占位小文件，跳过）
WANT_TOP = [
    "README.md",
    "joints_properties.xml",
    "scene.xml",
    "so101_new_calib.xml",
    "so101_new_calib_camera.xml",
    "so101_new_calib.urdf",
    "so101_new_calib_camera.urdf",
    "so101_old_calib.xml",
    "so101_old_calib.urdf",
    "so101_leader_new_calib.urdf",
]


def http_get(url: str, binary: bool = True) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "lerobot-so101-fetch"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def list_dir(url: str):
    data = json.loads(http_get(url).decode("utf-8"))
    if isinstance(data, dict):  # 出错时 GitHub 返回 dict
        raise RuntimeError(f"GitHub API 返回错误: {data}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=r"D:\LeRobot\assets\so101_sim")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dest = os.path.abspath(args.dest)
    assets_dir = os.path.join(dest, "assets")

    print(f"[1/3] 列出官方目录 ...")
    top = list_dir(API)
    names = [e["name"] for e in top]
    print(f"      顶层 {len(names)} 项: {', '.join(names)}")
    have = {e["name"]: e["size"] for e in top}

    missing = [n for n in WANT_TOP if n not in have]
    if missing:
        print(f"      !! 官方目录里缺少: {missing}")
    top_files = [n for n in WANT_TOP if n in have]

    print(f"[2/3] 列出 assets/ ...")
    assets = list_dir(API + "/assets")
    stl = [e for e in assets if e["name"].lower().endswith(".stl")]
    print(f"      assets 共 {len(assets)} 项，其中 STL {len(stl)} 个，"
          f"合计 {sum(e['size'] for e in stl)/1e6:.1f} MB")

    jobs = [(n, f"{RAW}/{urllib.parse.quote(n)}") for n in top_files]
    jobs += [(f"assets/{e['name']}", f"{RAW}/assets/{urllib.parse.quote(e['name'])}") for e in stl]

    if args.dry_run:
        print(f"[dry-run] 将下载 {len(jobs)} 个文件 -> {dest}")
        for n, u in jobs:
            print(f"   {have.get(n, '?'):>9} B  {n}")
        return 0

    os.makedirs(assets_dir, exist_ok=True)
    print(f"[3/3] 下载 {len(jobs)} 个文件 -> {dest}")
    ok = fail = 0
    for i, (name, url) in enumerate(jobs, 1):
        out = os.path.join(dest, name.replace("/", os.sep))
        size_hint = have.get(name) or next((e["size"] for e in stl if "assets/" + e["name"] == name), 0)
        try:
            blob = http_get(url)
            if size_hint and len(blob) != size_hint:
                print(f"      [{i}/{len(jobs)}] 大小不符 {name}: {len(blob)} != {size_hint}")
            with open(out, "wb") as f:
                f.write(blob)
            print(f"      [{i}/{len(jobs)}] {len(blob)/1024:9.1f} KB  {name}")
            ok += 1
        except Exception as e:
            print(f"      [{i}/{len(jobs)}] 失败 {name}: {type(e).__name__} {e}")
            fail += 1

    print(f"\n完成: 成功 {ok} / 失败 {fail}")
    print(f"落地目录: {dest}")
    print("自检建议:")
    print(f'  & "D:\\LeRobot\\_tools\\python310\\python.exe" -c "import mujoco;'
          f"m=mujoco.MjModel.from_xml_path(r'{os.path.join(dest, 'so101_new_calib_camera.xml')}');"
          f"print('nq',m.nq,'njnt',m.njnt)\"")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
