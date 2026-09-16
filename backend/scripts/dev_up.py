"""一键本地启动前后端(无 Docker)

用法:
    python backend/scripts/dev_up.py

逻辑:
    - 后端 uvicorn 从 8000 起找空闲端口
    - 前端 vite 从 5173 起找空闲端口(代理指向选中的后端端口)
    - 端口被占用自动顺延
    - Ctrl+C 结束并退出, 一并停掉前后端
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ROOT = BASE.parent
FRONTEND = ROOT / "frontend"
LOGS = BASE / "data" / "logs"

# 本项目自己管理的端口段: 8000~8029 后端, 5173~5192 前端
BACKEND_RANGE = range(8000, 8030)
FRONTEND_RANGE = range(5173, 5193)


def _port_rx():
    import re
    pat = ":(" + "|".join(str(p) for p in BACKEND_RANGE) + ")"
    pat = "\\.*(:" + "|".join(str(p) for p in list(BACKEND_RANGE) + list(FRONTEND_RANGE)) + ")(?=:|\\s|$)"
    return re.compile(pat)


def _py_or_node_pids():
    """找出项目残留的 uvicorn/app.main 与 vite/node 进程 pid"""
    out = subprocess.run(["netstat", "-ano"], capture_output=True,
                         encoding="gbk", errors="replace").stdout
    pids = set()
    for line in out.splitlines():
        if "LISTENING" not in line:
            continue
        if not _port_rx().search(line):
            continue
        pid = line.rsplit(" ", 1)[-1].strip()
        if pid.isdigit():
            pids.add(int(pid))
    return pids


def _confirm_python_or_node(pid):
    """tasklist 确认是 python 或 node 进程, 避免误杀用户其他程序"""
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True,
                             encoding="gbk", errors="replace").stdout
        low = out.lower()
        return ("python" in low or "node" in low)
    except Exception:
        return False


def cleanup_stale():
    """启动前清理本项目残留进程 (uvicorn 后端 + vite 前端)"""
    stale = [p for p in sorted(_py_or_node_pids()) if _confirm_python_or_node(p)]
    if not stale:
        return
    print(f"正在清理残留进程 {len(stale)} 个: {stale}")
    for pid in stale:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    time.sleep(1)


def find_free_port(start, tries=50):
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", p))
                return p
            except OSError:
                continue
    raise RuntimeError(f"端口 {start}~{start + tries - 1} 全部被占用")


def start_backend(port):
    LOGS.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    out = open(LOGS / "dev_backend_stdout.log", "a", encoding="utf-8")
    err = open(LOGS / "dev_backend_stderr.log", "a", encoding="utf-8")
    backend = sys.executable
    proc = subprocess.Popen(
        [backend, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(port)],
        cwd=str(BASE),
        stdout=out, stderr=err, env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return proc


def start_frontend(port, backend_port):
    LOGS.mkdir(parents=True, exist_ok=True)
    if not (FRONTEND / "node_modules").exists():
        print("首次运行前端, 正在安装依赖 (npm install)...")
        subprocess.run(["npm.cmd", "install", "--no-audit", "--no-fund"],
                       cwd=str(FRONTEND), check=True)
    env = dict(os.environ)
    env["BACKEND_PORT"] = str(backend_port)
    out = open(LOGS / "dev_frontend_stdout.log", "a", encoding="utf-8")
    err = open(LOGS / "dev_frontend_stderr.log", "a", encoding="utf-8")
    proc = subprocess.Popen(
        ["npm.cmd", "run", "dev", "--", "--port", str(port), "--strictPort"],
        cwd=str(FRONTEND),
        stdout=out, stderr=err, env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return proc


def wait_health(port, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/system/health", timeout=2)
            if r.status == 200:
                return True
        except Exception:
            time.sleep(1)
    return False


def kill_tree(proc):
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def main():
    # 启动前先清理本项目残留的后端(uvicorn)与前端(vite/node)进程, 避免端口越滚越多
    cleanup_stale()

    backend_port = find_free_port(8000)
    # 抽出 vite 的监听端口: 也顺延寻找, 默认 5173
    frontend_port = find_free_port(5173)

    print("=============================================")
    print("deepAStock 本地开发模式 (无 Docker)")
    print("=============================================")
    print(f"[1/3] 启动后端 端口={backend_port}")
    bp = start_backend(backend_port)
    url_api = f"http://127.0.0.1:{backend_port}"
    if wait_health(backend_port):
        print(f"      后端就绪 {url_api}/docs")
    else:
        print("      警告: 后端未及时响应, 查看 data/logs/dev_backend_stderr.log")

    print(f"[2/3] 启动前端 端口={frontend_port} (代理 api -> {backend_port})")
    fp = start_frontend(frontend_port, backend_port)
    url_ui = f"http://127.0.0.1:{frontend_port}"
    print(f"      前端就绪 {url_ui}")

    print("[3/3] 已打开浏览器 (如未打开请手动访问)")
    try:
        webbrowser.open(url_ui)
    except Exception:
        pass

    print("      按 Ctrl+C 停止前后端")
    try:
        while True:
            if bp.poll() is not None or fp.poll() is not None:
                print("      后端或前端进程已退出, 请查看日志")
                break
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        kill_tree(bp)
        kill_tree(fp)
        print("已停止")


if __name__ == "__main__":
    main()