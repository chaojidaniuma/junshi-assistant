# -*- coding: utf-8 -*-
"""军师助手 云端 API 入口：python -m cloud.run 或 uvicorn cloud.app:app --port 9000"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 仓库根


def main():
    import uvicorn
    uvicorn.run("cloud.app:app", host="127.0.0.1", port=9000,
                log_level="warning")


if __name__ == "__main__":
    main()
