"""拍照 + 自动分析：绿块相对红块的位置是否适合录制。

必须【管理员身份】的 PowerShell 运行（Orbbec 相机需要提权）。

用法：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\check_layout.py"
    & "D:\\LeRobot\\_tools\\python310\\python.exe" "D:\\LeRobot\\_setup\\check_layout.py" 1     # 指定索引

流程（连拍模式）：
    摆好一个位置 → 按回车 → 自动拍照 + 分析 + 打印结论
    换位置 → 再按回车 → 再分析
    输入 q 退出 → 打印汇总

每张照片和一张带检测框的标注图会存到 _setup\\cam_snapshots\\

判断标准：
    1) 绿块和红块都要能被检测到（颜色够鲜明、没被遮挡）
    2) 绿块到红块的距离 >= MIN_GAP_CM（防止夹爪下探时碰到红块）
    3) 绿块不能贴画面边缘（防止机械臂够不到 / 出画）
"""

import os
import sys

import cv2
import numpy as np

INDEX = int(sys.argv[1]) if len(sys.argv) > 1 else 1
OUT_DIR = r"D:\LeRobot\_setup\cam_snapshots"

# 红块边长（cm）—— 用来把像素距离换算成厘米。按你实际的方块量一下改这里。
RED_SIZE_CM = 4.5
# 绿块到红块的最小安全距离（cm）
MIN_GAP_CM = 4.5
MAX_GAP_CM = 12.0
# 绿块离画面边缘的最小留白（像素）
EDGE_MARGIN_PX = 25

# HSV 颜色范围（OpenCV 的 H 是 0~179）
GREEN_RANGES = [((30, 35, 20), (95, 255, 255))]
RED_RANGES = [((0, 80, 50), (12, 255, 255)), ((160, 80, 50), (180, 255, 255))]


def find_blob(hsv: np.ndarray, ranges, min_area: int = 700):
    """在 HSV 图里找最大的色块，返回信息或 None。"""
    mask = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None, mask
    c = max(cnts, key=cv2.contourArea)
    area = float(cv2.contourArea(c))
    if area < min_area:
        return None, mask
    m = cv2.moments(c)
    cx = int(m["m10"] / m["m00"])
    cy = int(m["m01"] / m["m00"])
    x, y, w, h = cv2.boundingRect(c)
    return {"cx": cx, "cy": cy, "area": area, "w": w, "h": h, "box": (x, y, w, h)}, mask


def analyze(frame: np.ndarray, tag: str) -> tuple[bool, list[str]]:
    """返回 (是否合格, 报告行列表)。"""
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    red, _ = find_blob(hsv, RED_RANGES)
    green, _ = find_blob(hsv, GREEN_RANGES)

    lines: list[str] = []
    ok = True

    if red is None:
        lines.append("  ✗ 没检测到【红色方块】 —— 检查：红块是否在画面内、颜色是否被反光洗白")
        ok = False
    else:
        lines.append(
            f"  红块: 中心({red['cx']},{red['cy']})  外接框 {red['w']}x{red['h']}px  面积 {int(red['area'])}px²"
        )

    if green is None:
        lines.append("  ✗ 没检测到【绿色方块】 —— 检查：绿块是否在画面内、是否被别的东西挡住")
        ok = False
    else:
        lines.append(
            f"  绿块: 中心({green['cx']},{green['cy']})  外接框 {green['w']}x{green['h']}px  面积 {int(green['area'])}px²"
        )

    if red is not None and green is not None:
        # 用红块边长当比例尺：cm_per_px
        red_px = max(red["w"], red["h"], 1)
        cm_per_px = RED_SIZE_CM / red_px
        dist_px = float(np.hypot(green["cx"] - red["cx"], green["cy"] - red["cy"]))
        dist_cm = dist_px * cm_per_px

        lines.append(
            f"  两者距离: {dist_px:.0f}px ≈ {dist_cm:.1f}cm（按红块 {RED_SIZE_CM}cm 换算）"
        )
        if dist_cm < MIN_GAP_CM:
            lines.append(f"  ✗ 太近了！要求 ≥ {MIN_GAP_CM}cm —— 夹爪下探会碰到红块")
            ok = False
        if dist_cm > MAX_GAP_CM:
            lines.append(f"  ✗ 太远了（{dist_cm:.1f}cm > {MAX_GAP_CM}cm）—— 超出随机范围，机械臂伸展吃力")
            ok = False

        # 绿块是否在合理工作区：不能贴画面边缘
        gx, gy, gw, gh = green["box"]
        margin = min(gx, gy, w - (gx + gw), h - (gy + gh))
        if margin < EDGE_MARGIN_PX:
            lines.append(f"  ✗ 绿块太靠画面边缘（最小留白 {margin}px < {EDGE_MARGIN_PX}px）")
            ok = False
        else:
            lines.append(f"  绿块离画面边缘: {margin}px ✓")

        # 绿块应该在红块靠近相机的一侧（画面里 y 更大 = 更靠前）
        if green["cy"] <= red["cy"]:
            lines.append("  ⚠ 绿块在红块的『后方』（更远离相机）—— 机械臂要跨过红块，路径别扭")
        else:
            lines.append("  绿块在红块的『前方』✓")

        # 存标注图
        vis = frame.copy()
        cv2.rectangle(vis, (red["box"][0], red["box"][1]),
                      (red["box"][0] + red["box"][2], red["box"][1] + red["box"][3]), (0, 0, 255), 2)
        cv2.rectangle(vis, (gx, gy), (gx + gw, gy + gh), (0, 255, 0), 2)
        cv2.circle(vis, (red["cx"], red["cy"]), 4, (0, 0, 255), -1)
        cv2.circle(vis, (green["cx"], green["cy"]), 4, (0, 255, 0), -1)
        cv2.line(vis, (red["cx"], red["cy"]), (green["cx"], green["cy"]), (255, 255, 0), 1)
        cv2.putText(vis, f"{dist_cm:.1f}cm", (int((red["cx"] + green["cx"]) / 2) + 5,
                    int((red["cy"] + green["cy"]) / 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        cv2.putText(vis, "OK" if ok else "CHECK", (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 0) if ok else (0, 0, 255), 2)

    return ok, lines


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    cap = cv2.VideoCapture(INDEX, cv2.CAP_DSHOW)
    try:
        if not cap.isOpened():
            print(f"✗ 打不开索引 {INDEX}（Orbbec 需要管理员权限）")
            return 1
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        for _ in range(15):
            cap.read()          # 预热，等自动曝光稳定

        # 从已有编号之后继续
        n = 1
        while os.path.exists(os.path.join(OUT_DIR, f"check_{n:02d}.png")):
            n += 1

        print(f"相机已打开（索引 {INDEX}）。红块按 {RED_SIZE_CM}cm 估算，要求间距 ≥ {MIN_GAP_CM}cm。")
        print("摆好一个位置 → 回车 → 自动分析；输入 q 退出。")
        print()

        results = []
        while True:
            try:
                cmd = input(f"[第 {n} 个位置] 摆好后按回车分析，输入 q 退出: ").strip()
            except EOFError:
                break
            if cmd.lower() in ("q", "quit", "exit"):
                break

            for _ in range(8):
                cap.read()
            ok, frame = cap.read()
            if not ok or frame is None:
                print("  ✗ 读帧失败，再试一次")
                continue

            print()
            good, lines = analyze(frame, f"#{n}")
            for line in lines:
                print(line)
            print(f"  → {'✅ 这个位置可以' if good else '❌ 这个位置需要调整'}")
            print()

            cv2.imwrite(os.path.join(OUT_DIR, f"check_{n:02d}.png"), frame)
            if not good:
                # 检测失败时也存一张原图，方便排查到底是拍错了对象还是颜色不对
                cv2.imwrite(os.path.join(OUT_DIR, f"fail_{n:02d}.png"), frame)
                print(f"  （原图已存 fail_{n:02d}.png 便于诊断）")
            results.append((n, good))
            n += 1

        print("=" * 60)
        if results:
            good_n = sum(1 for _, g in results if g)
            print(f"共测了 {len(results)} 个位置，其中 {good_n} 个合格")
            for i, g in results:
                print(f"  位置 {i}: {'✅ 合格' if g else '❌ 需要调整'}")
            if good_n == len(results):
                print()
                print("所有位置都合格 → 可以开始录制了：")
                print("  powershell -ExecutionPolicy Bypass -File D:\\LeRobot\\scripts\\05_record_dataset.ps1 -Episodes 100 -NoRerun")
        else:
            print("没有测任何位置")
        print("=" * 60)
        return 0
    finally:
        cap.release()


if __name__ == "__main__":
    sys.exit(main())
