# -*- coding: utf-8 -*-
"""狗头助手 · Windows 桌面入口。

打包后双击即可运行：
- 首次启动自动在 exe 同级生成 config.json（内嵌示例模板）
- 数据落在 exe 同级 data/ logs/，卸载即删无残留
- 自动以独立窗口（Edge/Chrome app 模式）打开界面
- 已有实例在运行时直接唤起界面，不会重复启动
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "狗头助手"
PORT_RANGE = range(8766, 8781)
START_TIMEOUT = 25  # 秒，等待服务就绪


def base_dir() -> Path:
    """数据目录：打包后取 exe 所在目录；源码运行为本文件目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def res_dir() -> Path:
    """只读资源目录：打包后在 _MEIPASS 解压目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", base_dir()))
    return base_dir()


def probe_alive(port: int) -> bool:
    """该端口是否已有狗头助手实例。"""
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/status", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def pick_port() -> int | None:
    for p in PORT_RANGE:
        if probe_alive(p):
            return p          # 已有实例 → 直接复用
        try:
            with socket.socket() as s:
                s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
    return None


def bootstrap_config() -> None:
    cfg = base_dir() / "config.json"
    if cfg.exists():
        return
    src = res_dir() / "config.example.json"
    try:
        if src.exists():
            shutil.copy(src, cfg)
            return
        raise FileNotFoundError(src)
    except Exception:
        # 兜底：内置最小可用模板
        cfg.write_text(json.dumps({
            "target": {"name": "", "profile": []},
            "llm": {"model": "deepseek-chat",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": ""},
        }, ensure_ascii=False, indent=2), encoding="utf-8")


def open_window(url: str) -> None:
    """优先 Edge/Chrome app 模式（独立无边框窗口），退回默认浏览器。"""
    cands = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    ]
    for exe in cands:
        if os.path.exists(exe):
            try:
                subprocess.Popen([exe, f"--app={url}",
                                  f"--window-size=1200,840"],
                                 close_fds=True)
                return
            except Exception:
                pass
    webbrowser.open(url)


def wait_ready(port: int) -> bool:
    deadline = time.time() + START_TIMEOUT
    while time.time() < deadline:
        if probe_alive(port):
            return True
        time.sleep(0.4)
    return False


def main() -> None:
    # --windowed 打包后 stdout/stderr 为 None，uvicorn 日志初始化会崩
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    port = pick_port()
    if port is None:
        return  # 无可用端口
    url = f"http://127.0.0.1:{port}"

    existing = probe_alive(port)
    if not existing:
        bootstrap_config()
        sys.path.insert(0, str(res_dir()))
        from interfaces.web.app import create_app
        app = create_app()

        import uvicorn
        config = uvicorn.Config(app, host="127.0.0.1", port=port,
                                log_level="warning")
        server = uvicorn.Server(config)

        def launch():
            time.sleep(1.2)           # 等服务起来再开窗
            open_window(url)
        threading.Thread(target=launch, daemon=True).start()
        server.run()
    else:
        open_window(url)


if __name__ == "__main__":
    main()
