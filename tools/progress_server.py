"""SO-101 项目进度看板 · 本地协作服务（零依赖，只要 Python 标准库）

为什么自己搭：项目机器没有稳定的外网，也没有腾讯文档/飞书的登录态，
但两个人在同一局域网里。这个服务让队友用浏览器打开就能看进度、改状态，
2 秒轮询自动同步。

用法：
    & "D:\\LeRobot\\_tools\\python310\\python.exe" tools\\progress_server.py
    ... --port 8770          指定端口
    ... --host 0.0.0.0       默认就监听所有网卡（局域网可访问）

数据存 docs/progress.json，写入用「原子替换」，不会写一半损坏。
并发用 version 乐观锁：谁先提交谁生效，后提交的会收到 409 然后自动刷新。

路由：
    /            看板页面
    /api/state   GET 读 / POST 写
    /plan        项目计划书（Markdown 原文）
"""
import argparse
import json
import os
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_PATH = os.path.join(ROOT, "docs", "progress.json")
BOARD_PATH = os.path.join(HERE, "board.html")
PLAN_PATH = os.path.join(ROOT, "docs", "PLAN_generalized_stacking.md")

LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def load_state() -> dict:
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(obj: dict) -> None:
    """原子写：先写 .tmp 再 os.replace。避免中途崩溃把数据写坏。"""
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_PATH)


def lan_ip() -> str:
    """拿到本机在局域网里的地址（UDP connect 不发包，只做路由选择）。"""
    for target in (("8.8.8.8", 80), ("114.114.114.114", 53)):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(target)
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        finally:
            s.close()
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


class Handler(BaseHTTPRequestHandler):
    server_version = "SO101Board/1.0"
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _file(self, path: str, ctype: str) -> None:
        try:
            with open(path, "rb") as f:
                self._send(200, f.read(), ctype)
        except FileNotFoundError:
            self._json(404, {"error": "not found", "path": path})

    def do_GET(self) -> None:
        route = self.path.split("?")[0]
        if route in ("/", "/index.html"):
            self._file(BOARD_PATH, "text/html; charset=utf-8")
        elif route == "/api/state":
            try:
                with LOCK:
                    self._json(200, load_state())
            except Exception as e:
                self._json(500, {"error": f"{type(e).__name__}: {e}"})
        elif route == "/plan":
            self._file(PLAN_PATH, "text/markdown; charset=utf-8")
        elif route == "/plan.html":
            self._file(PLAN_PATH, "text/plain; charset=utf-8")
        else:
            self._json(404, {"error": "not found", "path": route})

    def do_POST(self) -> None:
        route = self.path.split("?")[0]
        if route != "/api/state":
            self._json(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            incoming = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception as e:
            self._json(400, {"error": f"bad json: {e}"})
            return

        with LOCK:
            try:
                cur = load_state()
            except Exception as e:
                self._json(500, {"error": f"read state failed: {e}"})
                return
            if incoming.get("version") != cur.get("version"):
                # 有人先改了，把最新状态回给他，前端会自动刷新
                self._json(409, {"error": "version_conflict", "state": cur})
                return
            incoming["version"] = int(cur.get("version", 0)) + 1
            incoming["updated"] = now_iso()
            try:
                save_state(incoming)
            except Exception as e:
                self._json(500, {"error": f"write failed: {e}"})
                return

        self._json(200, incoming)

    def log_message(self, fmt, *args) -> None:
        pass  # 静音，别刷屏

    def handle_one_request(self) -> None:
        """客户端（浏览器轮询/提前关连接）会触发 ConnectionResetError，
        socketserver 默认会打一整段 traceback 刷屏。这里吃掉。"""
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--open-browser", action="store_true",
                    help="启动后自动打开本机浏览器")
    args = ap.parse_args()

    for p, what in ((STATE_PATH, "进度数据"), (BOARD_PATH, "看板页面")):
        if not os.path.exists(p):
            print(f"[x] 缺少{what}: {p}")
            return 1

    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        print(f"[x] 端口 {args.port} 起不来: {e}")
        print(f"    换个端口试试: --port {args.port + 1}")
        return 2

    ip = lan_ip()
    print("=" * 62)
    print(" SO-101 项目进度看板")
    print("=" * 62)
    print(f" 本机打开   : http://127.0.0.1:{args.port}")
    print(f" 发给队友   : http://{ip}:{args.port}")
    print(f" 计划书     : http://{ip}:{args.port}/plan")
    print(f" 数据文件   : {STATE_PATH}")
    print("=" * 62)
    print(" 首次使用若队友打不开，Windows 防火墙需放行该端口：")
    print(f"   netsh advfirewall firewall add rule name=\"SO101Board\" "
          f"dir=in action=allow protocol=TCP localport={args.port}")
    print(" Ctrl+C 停止")
    if args.open_browser:
        try:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{args.port}")
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
