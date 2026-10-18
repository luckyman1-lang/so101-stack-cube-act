"""M1 感知原型：深度平面拟合 + 桌面凸起检测 + 3D 定位。

设计要点（都是被实测数据逼出来的）：
  1. 不用 HSV 定位物体。HSV 的边界会因抗锯齿/阴影/溢色膨胀（实测 30mm 的
     方块被量成 36.3mm，多出 21%），质心也会被带偏。
     -> 改用【深度】找物体：先 RANSAC 拟合桌面主平面，再找高出桌面的连通块。
        深度边界是物理边界，不受颜色影响。
  2. 颜色只用来分类红/绿，不用来定位。
  3. 深度只取顶面中心 ROI 的【中位数】，并用 MAD 判据挡掉非平面（结构光边缘
     有 mixed-pixel 飞点，整片 mask 的 std 会到 25mm，中心 ROI 只有 3~4mm）。
  4. HW 对齐后深度帧在彩色相机坐标系 -> 反投影用 rgb_intrinsic，不是
     depth_intrinsic（后者是 640x400 的原始标定，配错会整体偏）。

用法：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" _setup\\analyze_snapshot.py
    ... --tag green          只看某次快照
    ... --rgb X --depth Y    指定文件（无 meta 时用内置内参）
"""
import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "cam_snapshots")

# probe 快照没有 meta，用 cam_probe 实测到的真值
FALLBACK_META = {
    "rgb_intrinsic": {"fx": 516.821, "fy": 517.180, "cx": 321.623, "cy": 238.932,
                      "width": 640, "height": 480},
    "depth_scale": 1.0,
}

# AGENTS.md §7.5：阈值宁宽勿窄（只用于分类颜色，不用于定位）
HSV_RED_1 = ((0, 80, 50), (12, 255, 255))
HSV_RED_2 = ((160, 80, 50), (180, 255, 255))
HSV_GREEN = ((30, 35, 20), (95, 255, 255))

# 桌面之上的凸起判据。
# 4mm 太松：纸面起伏、结构光噪声、近处盲区都会越线（实测冒出 11 个假物体）。
# 方块高 30mm，阈值放到 8mm 仍然稳稳能分出来。
MIN_OBJ_HEIGHT_MM = 8.0
MAX_OBJ_HEIGHT_MM = 80.0
MIN_OBJ_AREA_PX = 200
MAX_OBJ_AREA_PX = 12000      # 再大就不是方块了（纸箱那种）
MIN_OBJ_DEPTH_MM = 180.0     # 工作区下限，排除相机近处盲区
MAX_OBJ_DEPTH_MM = 600.0     # 工作区上限，排除背景


# ---------------------------------------------------------------- 数据加载
def load_snapshot(tag=None, rgb_path=None, depth_path=None):
    if rgb_path and depth_path:
        bgr = cv2.imread(rgb_path)
        depth = np.load(depth_path)
        meta = FALLBACK_META
        print(f"手动指定: {rgb_path}")
        return bgr, depth, meta, os.path.splitext(rgb_path)[0]

    # 找最新 snap_*_rgb.png（不依赖 meta 存在 —— meta 可能写失败）
    pats = sorted(glob.glob(os.path.join(SNAP, "snap_*_rgb.png")), key=os.path.getmtime)
    if tag:
        pats = [p for p in pats if f"snap_{tag}_" in os.path.basename(p)]
    if pats:
        rp = pats[-1]
        base = rp[: -len("_rgb.png")]
        bgr = cv2.imread(rp)
        depth = np.load(base + "_depth.npy")
        meta = FALLBACK_META
        mp = base + "_meta.json"
        if os.path.exists(mp):
            try:
                with open(mp, encoding="utf-8") as f:
                    meta = json.load(f)
                print(f"快照: {os.path.basename(base)}  (带 meta)")
            except Exception as e:
                print(f"快照: {os.path.basename(base)}  (meta 损坏，改用内置内参: "
                      f"{type(e).__name__})")
        else:
            print(f"快照: {os.path.basename(base)}  (无 meta，用内置内参)")
        return bgr, depth, meta, base

    # 回退到 probe_*
    p_rgb = os.path.join(SNAP, "probe_rgb.png")
    p_dep = os.path.join(SNAP, "probe_depth.npy")
    if os.path.exists(p_rgb) and os.path.exists(p_dep):
        print("快照: probe_* (无 meta，用内置内参)")
        return cv2.imread(p_rgb), np.load(p_dep), FALLBACK_META, os.path.join(SNAP, "probe")
    return None, None, None, None


# ---------------------------------------------------------------- 几何
def backproject_grid(depth_mm, K):
    h, w = depth_mm.shape
    u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    z = depth_mm.astype(np.float32) / 1000.0
    x = (u - K["cx"]) * z / K["fx"]
    y = (v - K["cy"]) * z / K["fy"]
    return np.stack([x, y, z], axis=-1), z


def fit_plane_ransac(pts, valid, iters=300, thresh=0.005, seed=0):
    """返回 (normal, d, inlier_mask_full)；平面方程 n·p + d = 0。"""
    P = pts[valid]
    if P.shape[0] < 100:
        return None
    rng = np.random.default_rng(seed)
    # 子采样做 RANSAC，提升速度
    sub_n = min(6000, P.shape[0])
    idx_sub = rng.choice(P.shape[0], sub_n, replace=False)
    S = P[idx_sub]
    best = None
    for _ in range(iters):
        i = rng.choice(sub_n, 3, replace=False)
        p1, p2, p3 = S[i]
        nv = np.cross(p2 - p1, p3 - p1)
        norm = float(np.linalg.norm(nv))
        if norm < 1e-9:
            continue
        nv /= norm
        d = -float(nv @ p1)
        cnt = int((np.abs(S @ nv + d) < thresh).sum())
        if best is None or cnt > best[0]:
            best = (cnt, nv.copy(), d)
    if best is None:
        return None
    _, nv, d = best
    # 用全量精化：把 inlier 拿来做最小二乘
    dist_all = np.abs(P @ nv + d)
    inl = dist_all < thresh
    if inl.sum() > 50:
        Q = P[inl]
        c = Q.mean(axis=0)
        u, s, vt = np.linalg.svd(Q - c, full_matrices=False)
        nv = vt[-1]
        d = -float(nv @ c)
    dist_full = pts @ nv + d
    # 法向统一指回相机（z 为负方向），这样"桌面上方"= 正高度
    if nv[2] > 0:
        nv, d = -nv, -d
        dist_full = -dist_full
    return nv, d, np.abs(dist_full) < thresh


def classify_color(bgr, mask):
    """在 mask 内判红/绿/未知，靠像素占比。"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    red = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in (HSV_RED_1, HSV_RED_2):
        red |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
    green = cv2.inRange(hsv, np.array(HSV_GREEN[0], np.uint8), np.array(HSV_GREEN[1], np.uint8))
    n = max(int((mask > 0).sum()), 1)
    r = float((red[mask > 0] > 0).sum()) / n
    g = float((green[mask > 0] > 0).sum()) / n
    if r > 0.25 and r >= g:
        return "RED", r, g
    if g > 0.25:
        return "GREEN", r, g
    return "?", r, g


def top_face(depth_mm, height_mm, comp_mask, frac=0.55, top_drop_mm=6.0):
    """取【顶面】的 bbox 和深度统计。

    两个坑都要防：
    1. 不能拿整个凸起的 bbox 量尺寸 —— 凸起含四个侧壁（高度 0→30mm），
       整个 bbox 会被侧壁撑大（30mm 的方块被量成 65mm）。
    2. 也不能用相对阈值 (0.75*h_top) 切顶面 —— 相机斜视 63° 时，同一个
       水平顶面各点到相机距离不同，p10~p90 之间本来就有 20mm 跨度，
       相对阈值会把一侧边缘削掉（实测顶面被切成 80x39，长宽比 2.05）。
       用【绝对落差】h_top - 6mm 才稳。
    """
    sel = comp_mask > 0
    hvals = height_mm[sel]
    if hvals.size < 20:
        return None
    h_top = float(np.percentile(hvals, 85))
    top = sel & (height_mm > h_top - top_drop_mm)
    ys, xs = np.nonzero(top)
    if xs.size < 30:  # 顶面太小，退回整个凸起
        ys, xs = np.nonzero(sel)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    w, h = x1 - x0 + 1, y1 - y0 + 1

    # 顶面内的深度取样区（再收一层，避开轮廓边缘的 mixed pixel）
    cw, ch = max(1, int(w * frac)), max(1, int(h * frac))
    cx0 = x0 + (w - cw) // 2
    cy0 = y0 + (h - ch) // 2
    roi = depth_mm[cy0:cy0 + ch, cx0:cx0 + cw]
    vals = roi[roi > 0]
    if vals.size < 10:
        return None
    med = float(np.median(vals))
    # 质心用顶面 mask 求矩，比 bbox 中心稳（bbox 会被单侧缺口带偏）
    mm_ = cv2.moments((top.astype(np.uint8)) * 255)
    if mm_["m00"] > 0:
        cu, cvv = mm_["m10"] / mm_["m00"], mm_["m01"] / mm_["m00"]
    else:
        cu, cvv = x0 + w / 2.0, y0 + h / 2.0
    return {
        "n": int(vals.size),
        "median": med,
        "mad": float(np.median(np.abs(vals - med))),
        "p10": float(np.percentile(vals, 10)),
        "p90": float(np.percentile(vals, 90)),
        "bbox": (x0, y0, w, h),
        "roi": (int(cx0), int(cy0), int(cw), int(ch)),
        "top_h_mm": h_top,
        "n_top_px": int(xs.size),
        "centroid": (float(cu), float(cvv)),
        "top_mask": top,
        "comp_bbox": None,  # 由调用方填整个凸起的 bbox，便于对比
    }


def planar_bbox_mm(pts, mask, nv):
    """把顶面点云投影到桌面平面，在【平面内】量尺寸。

    为什么要这么做：相机与桌面法向夹角 63° 时，30mm 见方的顶面在图像上被
    压缩成 76x36px，用 w*Z/fx 反推会得到 43.8x20.7mm（长宽比 2.11 而非 1.0）。
    投影到桌面平面后量出来的是真实边长，与视角无关。
    """
    P = pts[mask]
    if P is None or P.shape[0] < 30:
        return None
    n = nv / np.linalg.norm(nv)
    ref = np.array([1.0, 0.0, 0.0])
    if abs(float(n @ ref)) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])
    u = np.cross(n, ref)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    pu = P @ u
    pv = P @ v
    # 先用 MAD 把飞点剔掉，否则 2%/98% 分位会被个别坏点拉爆
    # （实测未剔除时同一块 30mm 的方块量出 310mm）
    keep = np.ones(pu.shape[0], dtype=bool)
    for arr in (pu, pv):
        med = float(np.median(arr))
        mad = float(np.median(np.abs(arr - med)))
        keep &= np.abs(arr - med) <= max(6.0 * mad, 0.015)
    pu, pv = pu[keep], pv[keep]
    if pu.size < 20:
        return None
    du = (np.percentile(pu, 98) - np.percentile(pu, 2)) * 1000.0
    dv = (np.percentile(pv, 98) - np.percentile(pv, 2)) * 1000.0
    return float(du), float(dv), int(keep.sum()), int(keep.size)


def hsv_stats(bgr, mask):
    """mask 内像素的 HSV 中位数。用于判断物体和桌面颜色是否可分。"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    px = hsv[mask > 0]
    if px.shape[0] < 10:
        return None
    return {"h": float(np.median(px[:, 0])), "s": float(np.median(px[:, 1])),
            "v": float(np.median(px[:, 2]))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="")
    ap.add_argument("--rgb", default="")
    ap.add_argument("--depth", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    bgr, depth, meta, base = load_snapshot(args.tag, args.rgb, args.depth)
    if bgr is None:
        print("[x] 找不到快照。先跑 snap_rgbd.py 或 cam_probe.py")
        return 1

    K = meta["rgb_intrinsic"]
    scale = float(meta.get("depth_scale", 1.0))
    print(f"RGB={bgr.shape[:2]}  depth={depth.shape}  scale={scale}")
    print(f"内参 fx={K['fx']:.2f} fy={K['fy']:.2f} cx={K['cx']:.2f} cy={K['cy']:.2f}")

    if depth.shape[:2] != bgr.shape[:2]:
        depth = cv2.resize(depth, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_NEAREST)
        print("  (深度已 resize 到 RGB 尺寸)")

    depth_mm = depth.astype(np.float32) * scale
    pts, z = backproject_grid(depth_mm, K)

    # 只在工作区内拟合桌面。范围放到 100~800 会把背景墙/纸箱一起卷进来，
    # 拟合出贯穿全图的斜面，然后满屏都是"物体"。
    valid = (depth_mm > MIN_OBJ_DEPTH_MM) & (depth_mm < MAX_OBJ_DEPTH_MM)
    print(f"用于拟合的点: {int(valid.sum())} / {valid.size} "
          f"({valid.sum() / valid.size * 100:.1f}%)  "
          f"范围 {MIN_OBJ_DEPTH_MM:.0f}~{MAX_OBJ_DEPTH_MM:.0f}mm")

    fit = fit_plane_ransac(pts, valid)
    if fit is None:
        print("[x] 桌面平面拟合失败")
        return 2
    nv, dpar, inlier = fit
    inl_valid = int((inlier & valid).sum())
    print(f"桌面平面: n=({nv[0]:+.3f},{nv[1]:+.3f},{nv[2]:+.3f}) d={dpar:+.4f}  "
          f"inlier={inl_valid} ({inl_valid / max(int(valid.sum()), 1) * 100:.1f}%)")
    tilt = np.degrees(np.arccos(min(1.0, abs(float(nv @ np.array([0, 0, -1]))))))
    print(f"  平面与相机光轴夹角 {tilt:.1f}deg  (0=正对, 越大越斜)")

    # 桌面之上的高度图
    height = (pts @ nv + dpar)  # 米，正值=桌面上方
    height_mm = height * 1000.0
    obj_mask = ((height_mm > MIN_OBJ_HEIGHT_MM) & (height_mm < MAX_OBJ_HEIGHT_MM)
                & valid).astype(np.uint8) * 255
    obj_mask = cv2.morphologyEx(obj_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    obj_mask = cv2.morphologyEx(obj_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    ncc, labels, stats, cents = cv2.connectedComponentsWithStats(obj_mask, connectivity=8)
    cands = []
    for i in range(1, ncc):
        x, y, w, h, area = stats[i]
        if area < MIN_OBJ_AREA_PX or area > MAX_OBJ_AREA_PX:
            continue
        comp = (labels == i).astype(np.uint8) * 255
        tf = top_face(depth_mm, height_mm, comp)
        if tf is None:
            continue
        tf["comp_bbox"] = (int(x), int(y), int(w), int(h))
        cls, r_ratio, g_ratio = classify_color(bgr, comp)
        cands.append({
            "id": i, "bbox": (int(x), int(y), int(w), int(h)), "area": int(area),
            "tf": tf, "cls": cls, "red": r_ratio, "green": g_ratio,
        })
    cands.sort(key=lambda c: c["tf"]["median"])

    desk_hsv = hsv_stats(bgr, (inlier & valid).astype(np.uint8) * 255)
    if desk_hsv:
        print()
        print(f"桌面 HSV 中位数: H={desk_hsv['h']:.0f} S={desk_hsv['s']:.0f} "
              f"V={desk_hsv['v']:.0f}")

    print()
    print(f"== 桌面上的候选物体: {len(cands)} 个")
    vis = bgr.copy()
    # 把桌面平面 inlier 画成淡色，方便看拟合效果
    vis[inlier] = (vis[inlier] * 0.55 + np.array([0, 90, 0]) * 0.45).astype(np.uint8)

    results = []
    for c in cands:
        tf = c["tf"]
        x, y, w, h = tf["bbox"]  # 顶面 bbox，不是整个凸起（凸起含侧壁会撑大）
        cu, cvv = tf["centroid"]
        Z = tf["median"]
        P = np.array([(cu - K["cx"]) * Z / 1000.0 / K["fx"],
                      (cvv - K["cy"]) * Z / 1000.0 / K["fy"],
                      Z / 1000.0])
        # 真实物理边界来自深度（不是 HSV），所以尺寸可信
        side_x = w * Z / K["fx"]
        side_y = h * Z / K["fy"]
        print()
        print(f"  #{c['id']} 类别={c['cls']} (red={c['red']:.2f} green={c['green']:.2f})")
        print(f"      顶面 bbox={tf['bbox']} 像素={tf['n_top_px']} "
              f"(整个凸起 bbox={tf['comp_bbox']} 面积={c['area']}px)")
        print(f"      长宽比={w / max(h, 1):.2f}")
        print(f"      顶面深度 p50={Z:.0f}mm  MAD={tf['mad']:.1f}mm "
              f"(p10={tf['p10']:.0f} p90={tf['p90']:.0f})")
        print(f"      高出桌面 {tf['top_h_mm']:.1f}mm")
        print(f"      物理尺寸(图像反推) {side_x:.1f} x {side_y:.1f} mm")
        pu_sz = planar_bbox_mm(pts, tf["top_mask"], nv)
        if pu_sz:
            print(f"      物理尺寸(平面内)   {pu_sz[0]:.1f} x {pu_sz[1]:.1f} mm  "
                  f"(有效点 {pu_sz[2]}/{pu_sz[3]})  <- 不受视角影响")
        else:
            print("      物理尺寸(平面内)   点数太少，测不准")
        print(f"      3D(相机系) = ({P[0]:+.4f}, {P[1]:+.4f}, {P[2]:+.4f}) m")
        # 点云中位数：直接在 3D 里求中心，不经过"图像质心 + 深度反投影"。
        # 斜视时图像质心会被顶面投影的梯形带偏，点云法更稳。
        cent3d = np.median(pts[tf["top_mask"]], axis=0)
        err_mm = float(np.linalg.norm(cent3d - P)) * 1000.0
        print(f"      3D(点云中位) = ({cent3d[0]:+.4f}, {cent3d[1]:+.4f}, "
              f"{cent3d[2]:+.4f}) m   两种方法差 {err_mm:.1f}mm")
        o_hsv = hsv_stats(bgr, (tf["top_mask"]).astype(np.uint8) * 255)
        if o_hsv and desk_hsv:
            dh = min(abs(o_hsv["h"] - desk_hsv["h"]), 180 - abs(o_hsv["h"] - desk_hsv["h"]))
            print(f"      顶面 HSV: H={o_hsv['h']:.0f} S={o_hsv['s']:.0f} V={o_hsv['v']:.0f}"
                  f"   与桌面色相差 {dh:.0f}°")
            if dh < 12:
                print("      [!] 和桌面同色系 —— 颜色不可靠，必须靠高度/深度区分")
        if tf["mad"] > 8:
            print("      [!] 顶面 MAD 偏大，可能顶面不平或混入了别的表面")

        color = {"RED": (0, 0, 255), "GREEN": (0, 255, 0), "?": (255, 255, 0)}[c["cls"]]
        bx, by, bw, bh = tf["comp_bbox"]
        cv2.rectangle(vis, (bx, by), (bx + bw, by + bh), (90, 90, 90), 1)  # 凸起轮廓
        cv2.rectangle(vis, (x, y), (x + w, y + h), color, 2)               # 顶面
        rx, ry, rw, rh = tf["roi"]
        cv2.rectangle(vis, (rx, ry), (rx + rw, ry + rh), (0, 165, 255), 1)  # 取样区
        cv2.putText(vis, f"{c['cls']} z={Z:.0f} s={side_x:.0f}x{side_y:.0f}",
                    (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)
        results.append(c)

    # ArUco（仅用于标定，不参与定位）
    print()
    print("== ArUco（仅标定用）")
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    for dict_name in ("DICT_6X6_50", "DICT_4X4_50", "DICT_5X5_50"):
        dd = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))
        det = cv2.aruco.ArucoDetector(dd, cv2.aruco.DetectorParameters())
        corners, ids, _ = det.detectMarkers(gray)
        n = 0 if ids is None else len(ids)
        if n:
            print(f"   {dict_name}: {n} 个, ids={sorted(int(v) for v in ids.flatten())}")
            cv2.aruco.drawDetectedMarkers(vis, corners, ids)
            break
    else:
        print("   未检出")

    out = args.out or (base + "_analyze.png")
    cv2.imwrite(out, vis)
    print()
    print(f"标注图: {out}")
    print(f"绿色=拟合到的桌面, 彩色框=物体, 橙框=顶面取样区")
    return 0


if __name__ == "__main__":
    sys.exit(main())
