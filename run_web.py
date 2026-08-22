# -*- coding: utf-8 -*-
"""Web 入口：python run_web.py → http://127.0.0.1:8766"""
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    import uvicorn
    from interfaces.web.app import create_app

    app = create_app()
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:8766")).start()
    print("军师助手 v2 (junshi-harness) → http://127.0.0.1:8766")
    uvicorn.run(app, host="127.0.0.1", port=8766, log_level="warning")


if __name__ == "__main__":
    main()
