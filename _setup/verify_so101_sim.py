"""校验 SO-101 官方仿真资产是否完整、能否被 MuJoCo 加载。

不需要 mujoco 就能跑（纯 XML 解析）；装了 mujoco 会额外做一次真实加载。

用法：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" _setup\\verify_so101_sim.py
    ... --dest D:\\LeRobot\\assets\\so101_sim
"""
import argparse
import glob
import os
import sys
import xml.etree.ElementTree as ET

try:  # Windows 控制台默认 GBK，中文会乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

LEROBOT_JOINTS = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=r"D:\LeRobot\assets\so101_sim")
    args = ap.parse_args()
    D = os.path.abspath(args.dest)
    if not os.path.isdir(D):
        print(f"[x] 目录不存在: {D}")
        return 1

    print(f"== 目录: {D}")
    stl = sorted(glob.glob(os.path.join(D, "assets", "*.stl")))
    tot = sum(os.path.getsize(p) for p in stl)
    print(f"   STL {len(stl)} 个，共 {tot/1e6:.1f} MB")

    fail = 0
    for xml in ["so101_new_calib.xml", "so101_new_calib_camera.xml", "scene.xml"]:
        p = os.path.join(D, xml)
        print(f"\n== {xml}")
        if not os.path.exists(p):
            print("   [x] 缺失")
            fail += 1
            continue
        try:
            root = ET.parse(p).getroot()
        except Exception as e:
            print(f"   [x] XML 解析失败: {e}")
            fail += 1
            continue

        comp = root.findall("compiler")
        for c in comp:
            print(f"   compiler: {c.attrib}")
        for inc in root.findall("include"):
            print(f"   include : {inc.attrib}")

        # <default> 里也有 <joint>，那些没有 name，要滤掉
        joints = [j for j in root.findall(".//joint") if j.get("name")]
        names = [j.get("name") for j in joints]
        print(f"   关节 {len(joints)} 个: {names}")
        for j in joints:
            print(f"      {j.get('name'):<16} type={str(j.get('type')):<6} range={j.get('range')}")

        missing = [n for n in LEROBOT_JOINTS if n not in names]
        if missing:
            print(f"   [!] 缺少 LeRobot 关节名: {missing}")
        else:
            print("   [ok] 6 个关节名与 LeRobot 完全一致")

        for s in root.findall(".//site"):
            print(f"   site    : {s.get('name'):<16} pos={s.get('pos')}")

        acts = root.findall("./actuator/*")
        if acts:
            print(f"   执行器 {len(acts)} 个: {[(a.get('name'), a.get('ctrlrange')) for a in acts]}")

        meshes = root.findall(".//mesh")
        miss_mesh = []
        for m in meshes:
            f = m.get("file")
            if f and not os.path.exists(os.path.join(D, "assets", f)):
                miss_mesh.append(f)
        if miss_mesh:
            print(f"   [x] 缺网格: {miss_mesh}")
            fail += 1
        else:
            print(f"   [ok] 引用的 {len(meshes)} 个网格文件都在")

    # 可选：mujoco 真实加载
    print("\n== MuJoCo 加载测试")
    try:
        import mujoco
    except ImportError:
        print("   (mujoco 未安装，跳过 —— 安装后再跑本脚本可验证真实加载)")
    else:
        for xml in ["so101_new_calib.xml", "so101_new_calib_camera.xml", "scene.xml"]:
            p = os.path.join(D, xml)
            try:
                m = mujoco.MjModel.from_xml_path(p)
                print(f"   [ok] {xml}: nq={m.nq} nv={m.nv} njnt={m.njnt} "
                      f"nbody={m.nbody} ngeom={m.ngeom} nu={m.nu}")
            except Exception as e:
                print(f"   [x] {xml}: {type(e).__name__}: {e}")
                fail += 1

    print(f"\n结论: {'全部通过' if fail == 0 else f'{fail} 项异常'}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
