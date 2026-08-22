# -*- coding: utf-8 -*-
"""CLI 入口：python run_cli.py [--once]

复用与 Web 完全相同的 harness 栈，仅接入层不同。
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from junshi_harness.config import Config          # noqa: E402
from junshi_harness.event_bus import EventBus     # noqa: E402
from junshi_harness.item import Item              # noqa: E402
from junshi_harness.store import Store            # noqa: E402
from runtime import MonitorRuntime                # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="军师助手 v2 CLI")
    ap.add_argument("--config", default=None, help="config.json 路径")
    ap.add_argument("--interval", type=float, default=None, help="轮询秒数")
    args = ap.parse_args()

    cfg = Config(args.config)
    target = cfg.load()["target"]["name"]
    if not target:
        print("错误：config.json 未配置 target.name")
        sys.exit(1)

    bus = EventBus()
    bus.subscribe(lambda item: print(
        f"[{time.strftime('%H:%M:%S')}] {item.type}: "
        + (item.data.get("msg") or item.data.get("text") or "")))
    store = Store(cfg.db_path)

    from adapters.wechat_wxauto import WeChatAdapter
    adapter = WeChatAdapter(target_name=target,
                            log=lambda m: bus.publish(Item(type="log", data={"msg": m})))
    rt = MonitorRuntime(cfg, store, bus, adapter)
    if args.interval:
        rt.poll_interval = args.interval
    rt.start()
    print(f"监听中（目标: {target}），Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        rt.stop()


if __name__ == "__main__":
    main()
