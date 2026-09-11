"""启动/停止前端开发服务器 (Windows)"""
import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend"
LOGS = Path(__file__).resolve().parent.parent / "data" / "logs"
PID_FILE = LOGS / "vite.pid"
STDOUT = LOGS / "vite_stdout.log"
STDERR = LOGS / "vite_stderr.log"


def start():
    if PID_FILE.exists():
        print("已在运行")
        return
    import os
    LOGS.mkdir(parents=True, exist_ok=True)
    npm = "npm.cmd"
    proc = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=FRONTEND,
        stdout=open(STDOUT, "a", encoding="utf-8"),
        stderr=open(STDERR, "a", encoding="utf-8"),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    PID_FILE.write_text(str(proc.pid))
    print(f"前端启动中 pid={proc.pid}  (http://127.0.0.1:5173)")


def stop():
    pid = PID_FILE.read_text().strip() if PID_FILE.exists() else None
    if pid:
        subprocess.run(["taskkill", "/F", "/PID", pid, "/T"], capture_output=True)
        PID_FILE.unlink(missing_ok=True)
    # 兜底找 node 占 5173
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if ":5173" in line and "LISTENING" in line:
            p = line.rsplit(" ", 1)[-1].strip()
            if p.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", p, "/T"], capture_output=True)
    print("前端已停止")


def status():
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    ok = any(":5173" in line and "LISTENING" in line for line in out.splitlines())
    print("前端" + ("运行中 http://127.0.0.1:5173" if ok else "未运行"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"start": start, "stop": stop, "status": status}[cmd]()