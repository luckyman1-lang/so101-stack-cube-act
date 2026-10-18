"""训练进度监控：解析 training 日志，显示步数 / loss / 速度 / 预计剩余时间。

用法：
    python _setup/watch_train.py                 # 看一次
    python _setup/watch_train.py --loop          # 每 20 秒刷新
    python _setup/watch_train.py --plot          # 顺便存一张 loss 曲线图
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

LOG = Path(r"D:\LeRobot\outputs\train_50k.log")
OUT_PNG = Path(r"D:\LeRobot\outputs\loss_curve.png")

STEP_RE = re.compile(
    r"INFO (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?step:(\d+[KM]?).*?ep:(\d+).*?loss:([\d.]+)\s+grdn:([\d.]+)"
)
# updt_s 在行尾常被折行成 "0.1" + "86"，所以第二段数字是可选的
UPDT_RE = re.compile(r"step:\d+[KM]?.*?updt_s:([\d.]+)(?:\s+(\d+))?\s+data_s:([\d.]+)")


def _num(s: str) -> int:
    """lerobot 用 K/M 缩写显示步数：6K -> 6000, 45K -> 45000。"""
    s = s.strip()
    if s.endswith("K"):
        return int(float(s[:-1]) * 1000)
    if s.endswith("M"):
        return int(float(s[:-1]) * 1_000_000)
    return int(s)
CKPT_RE = re.compile(r"Checkpoint policy after step (\d+)")
START_RE = re.compile(r"开始时间: ([\d-]+ [\d:]+)")


def _read_log_bytes(log_path: Path) -> bytes:
    """日志正在被训练的 Tee-Object 写入，用共享读模式打开，避免被锁。"""
    with open(log_path, "rb") as f:
        return f.read()


def _decode(raw: bytes) -> str:
    """Tee-Object 在 PowerShell 5.1 下默认写 UTF-16 LE，也可能被改成 UTF-8，两种都要认。"""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig")
    # 没有 BOM：看看是否大量 \x00 交替（UTF-16 LE 无 BOM 的典型特征）
    sample = raw[:400]
    if sample and sample.count(b"\x00") > len(sample) * 0.25:
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def parse(log_path: Path):
    if not log_path.exists():
        return None
    try:
        text = _decode(_read_log_bytes(log_path))
    except OSError:
        return None
    # PowerShell 的 Tee-Object 会按窗口宽度硬折行，把 step 记录拆成两行，
    # 所以先把换行压平再匹配（正则本身不会因此误匹配）。
    flat = " ".join(text.split())
    steps = []
    for m in STEP_RE.finditer(flat):
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            ts = None
        steps.append(
            dict(
                step=_num(m.group(2)),
                ep=int(m.group(3)),
                loss=float(m.group(4)),
                grdn=float(m.group(5)),
                ts=ts,
                updt=0.0,
                data=0.0,
            )
        )
    ckpts = [int(m.group(1)) for m in CKPT_RE.finditer(flat)]
    # 每步真实耗时（updt_s + data_s），用来算速度最可靠，不受休眠/缩写影响
    per_step_ms = []
    for m in UPDT_RE.finditer(flat):
        updt = float(m.group(1) + (m.group(2) or ""))
        data = float(m.group(3))
        per_step_ms.append(updt + data)
    start = None
    m = START_RE.search(flat)
    if m:
        try:
            start = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    total = 0
    m = re.search(r"步数\s*:\s*(\d+)", flat)
    if m:
        total = int(m.group(1))
    return dict(steps=steps, ckpts=ckpts, start=start, total=total, per_step=per_step_ms)


def report(data, show_plot: bool = False):
    steps = data["steps"]
    total = data["total"] or 50000
    if not steps:
        print("日志里还没有 step 记录（训练可能刚开始，或已结束）")
        return

    last = steps[-1]
    first = steps[0]
    n = len(steps)

    # 速度：优先用每步实测耗时（updt_s + data_s）的中位数，
    # 这样能自动剔除「电脑休眠 / IO 卡住」造成的异常值。
    rate = 0.0
    ps = [x for x in data.get("per_step", []) if 0 < x < 10]
    if ps:
        ps.sort()
        mid = ps[len(ps) // 2]
        rate = 1 / mid if mid > 0 else 0
    if rate <= 0:
        recent = steps[-25:]
        per_step = []
        for a, b in zip(recent, recent[1:]):
            if a.get("ts") and b.get("ts"):
                dt = (b["ts"] - a["ts"]).total_seconds()
                ds = b["step"] - a["step"]
                if 0 < dt < 10 and ds > 0:
                    per_step.append(dt / ds)
        if per_step:
            per_step.sort()
            rate = 1 / per_step[len(per_step) // 2] if per_step[len(per_step) // 2] > 0 else 0

    if rate > 0:
        eta_s = (total - last["step"]) / rate
        eta = str(timedelta(seconds=int(eta_s)))
        speed_line = f"  速度    {1 / rate:.2f} 秒/步   （{rate:.2f} 步/秒）"
    else:
        eta = "?"
        speed_line = "  速度    计算中..."

    pct = last["step"] / total * 100
    bar_len = 40
    filled = int(bar_len * last["step"] / total)

    print("=" * 68)
    print("  ACT 训练进度")
    print("=" * 68)
    print(f"  步数    {last['step']:>6} / {total}   ({pct:.1f}%)")
    print(f"  进度    [{'#' * filled}{'.' * (bar_len - filled)}]")
    print(f"  当前    loss={last['loss']:.3f}   grdn={last['grdn']:.1f}   ep={last['ep']}")
    print(f"  首步    loss={first['loss']:.3f} (step {first['step']})")
    print(speed_line)
    print(f"  已跑    {elapsed_fmt(data)}")
    print(f"  预计剩余 {eta}   （约 {rate:.2f} 步/秒）")
    if data["ckpts"]:
        print(f"  已存检查点 {data['ckpts']}")
    print("=" * 68)

    # loss 趋势：最近 5 条
    if n >= 2:
        recent = steps[-6:]
        print("\n  最近 loss:")
        for s in recent:
            print(f"    step {s['step']:>6}   loss {s['loss']:>7.3f}   grdn {s['grdn']:>7.1f}")

    if show_plot:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            xs = [s["step"] for s in steps]
            ys = [s["loss"] for s in steps]
            plt.figure(figsize=(10, 4))
            plt.plot(xs, ys, linewidth=1.5)
            plt.xlabel("step")
            plt.ylabel("loss")
            plt.title("ACT training loss")
            plt.grid(alpha=0.3)
            OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
            plt.tight_layout()
            plt.savefig(OUT_PNG, dpi=110)
            print(f"\n  曲线图已保存: {OUT_PNG}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n  （画图失败：{type(exc).__name__}: {exc}）")


def elapsed_fmt(data):
    """没有"开始时间"时，用首条 step 记录的时间戳反推已跑时长。"""
    ref = data.get("start")
    if ref is None and data.get("steps"):
        ref = data["steps"][0].get("ts")
    if ref is None:
        return "?"
    el = (datetime.now() - ref).total_seconds()
    if el < 0:
        return "?"
    return str(timedelta(seconds=int(el)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="每 20 秒刷新")
    ap.add_argument("--plot", action="store_true", help="保存 loss 曲线图")
    ap.add_argument("--log", default=str(LOG))
    args = ap.parse_args()

    log_path = Path(args.log)
    while True:
        data = parse(log_path)
        if data is None:
            print(f"找不到日志: {log_path}")
            return
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}]")
        report(data, show_plot=args.plot)
        if not args.loop:
            return
        time.sleep(20)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
