"""一键启动/停止后端服务 (Windows)

用法:
    python scripts/run_server.py start   # 后台启动
    python scripts/run_server.py stop    # 停止
    python scripts/run_server.py status  # 状态
"""
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PID_FILE = BASE / "data" / "logs" / "server.pid"
STDOUT = BASE / "data" / "logs" / "server_stdout.log"
STDERR = BASE / "data" / "logs" / "server_stderr.log"
PORT = 8000


def _pid():
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except Exception:
            return None
    return None


def start():
    if _pid() and _is_alive(_pid()):
        print(f"已在运行 pid={_pid()}")
        return
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(PORT)],
        cwd=BASE,
        stdout=open(STDOUT, "a", encoding="utf-8"),
        stderr=open(STDERR, "a", encoding="utf-8"),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    PID_FILE.write_text(str(proc.pid))
    print(f"后端启动中 pid={proc.pid}  (日志: data/logs)")


def _is_alive(pid):
    try:
        subprocess.run(["tasklist", "/fi", f"PID eq {pid}"], capture_output=True, timeout=5)
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        return False


def stop():
    pid = _pid()
    if pid:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        try:
            PID_FILE.unlink()
        except Exception:
            pass
        print(f"已停止 pid={pid}")
    # 兜底：按端口找到监听进程并杀掉
    found = _find_by_port(PORT)
    if found:
        for p in found:
            subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)
            print(f"已按端口停止 pid={p}")
    if not pid and not found:
        print("未在运行")


def _find_by_port(port):
    out = subprocess.run(["netstat", "-ano"], capture_output=True,
                         encoding="gbk", errors="replace").stdout
    pids = set()
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            pids.add(line.rsplit(" ", 1)[-1].strip())
    result = []
    for pid in pids:
        if pid.isdigit():
            p = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True,
                               encoding="gbk", errors="replace", text=True)
            if "python" in p.stdout.lower():
                result.append(int(pid))
    return result


def status():
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    pid = _pid()
    alive = _is_alive(pid) if pid else False
    try:
        r = opener.open(f"http://127.0.0.1:{PORT}/api/v1/system/health", timeout=3)
        content = r.read().decode("utf-8")
        print(f"运行中 pid={pid} 健康检查: {content}")
    except Exception as e:
        print(f"进程 pid={pid} alive={alive} 但服务未响应: {e}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "status":
        status()