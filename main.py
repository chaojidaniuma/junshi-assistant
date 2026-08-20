# -*- coding: utf-8 -*-
"""狗头军师微信自动回复（wxauto4 主窗口轮询版，适配微信 4.1.x）。

链路：轮询主窗口新消息 → 确认消息来自「她」→ 狗头军师引擎生成 → 发回她的会话。

## 防误发设计（微信 4.1 不暴露会话标题控件，用行为锚定）：
- 她的会话 unread > 0 → 她发消息且主窗口不在她 → 点击她的会话再处理
- unread == 0 但 GetNewMessage 有新消息 → 只有「最新一条 friend 消息」与她
  会话在列表里显示的最后一条一致时才处理（说明主窗口就在她的会话）
- 其余情况一律跳过（宁漏勿错，绝不向群/他人误发）

用法：python main.py            # 全自动（生成并发送）
      python main.py --dry      # 只生成不发送
      python main.py --confirm  # 生成后写 pending 文件，不自动发送
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 冻结（EXE）模式下以 exe 所在目录为根（onefile 的 __file__ 指向临时解压目录）
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from goutou.engine import generate_variants, load_api_key  # noqa: E402
from goutou.approval import detect_distance  # noqa: E402
from goutou.config import load_config  # noqa: E402

CONFIG = load_config()
# 当前回复对象（可在 GUI 中动态切换；默认取 config）
CURRENT_TARGET: str = CONFIG["target"]["name"]


def set_target(name: str) -> None:
    """切换回复对象：更新内存 + 写回 config.json（持久化）。"""
    global CURRENT_TARGET
    CURRENT_TARGET = name
    try:
        CONFIG["target"]["name"] = name
        cfg_path = ROOT / "config.json"
        cfg_path.write_text(json.dumps(CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        log(f"写入 config.json 失败: {e}")


class State:
    """处理状态持久化（data/state.json）。

    去重机制：内容指纹（processed_fps）——不依赖 wxauto4 的 runtime id
    （切换窗口/重绘会变），重启后仍有效。
    """

    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {
            "processed_fps": [], "last_reply_ts": 0.0, "reply_hour": {},
            "pending": [], "seeded": False,
        }
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        self.data.setdefault("processed_fps", [])
        self.data.setdefault("pending", [])
        self.data.setdefault("reply_hour", {})
        self.data.setdefault("seeded", False)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ---- 内容指纹去重 ----
    @staticmethod
    def fingerprint(text: str) -> str:
        import hashlib
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def seen(self, fp: str) -> bool:
        return fp in self.data["processed_fps"]

    def mark_seen(self, fp: str) -> None:
        self.data["processed_fps"].append(fp)
        self.data["processed_fps"] = self.data["processed_fps"][-400:]
        self.save()

    def seed(self, history: list[dict[str, str]]) -> None:
        """首次启动：把当前窗口已有消息全部标记为已见（不触发回复）。"""
        if self.data.get("seeded"):
            return
        for item in history:
            text = str(item.get("text", "") or "").strip()
            if text:
                fp = self.fingerprint(text)
                if not self.seen(fp):
                    self.data["processed_fps"].append(fp)
        self.data["processed_fps"] = self.data["processed_fps"][-400:]
        self.data["seeded"] = True
        self.save()

    # ---- 旧接口兼容（runtime id） ----
    def is_processed(self, msg_id) -> bool:
        return msg_id in self.data.get("processed_ids", [])

    def mark_processed(self, msg_id) -> None:
        self.data.setdefault("processed_ids", []).append(msg_id)
        self.data["processed_ids"] = self.data["processed_ids"][-2000:]
        self.save()

    def can_reply(self) -> tuple[bool, str]:
        now = time.time()
        if now - self.data.get("last_reply_ts", 0) < CONFIG["monitor"]["min_interval_between_replies_seconds"]:
            return False, "回复间隔太短"
        hour = datetime.now().strftime("%Y-%m-%d %H")
        if self.data["reply_hour"].get(hour, 0) >= CONFIG["monitor"]["max_replies_per_hour"]:
            return False, "达到小时回复上限"
        return True, ""

    def note_reply(self) -> None:
        hour = datetime.now().strftime("%Y-%m-%d %H")
        self.data["reply_hour"][hour] = self.data["reply_hour"].get(hour, 0) + 1
        self.data["last_reply_ts"] = time.time()
        self.save()


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    log_dir = ROOT / CONFIG["paths"]["log_dir"]
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_dir / "run.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def find_target_session(adapter):
    """在会话列表找目标对象的会话元素（兼容旧调用：传 wxauto4 实例时自动包装）。"""
    return adapter.find_session(CURRENT_TARGET)


def switch_to_target(adapter) -> bool:
    """点击目标会话（切回）。返回是否成功。"""
    return adapter.switch_to(CURRENT_TARGET)


def get_history(adapter, window: int) -> list[dict[str, str]]:
    """从主窗口拉最近历史。"""
    return adapter.get_all_messages(window)


def extract_her_last_line(adapter) -> str:
    """目标会话在列表里显示的最后一条消息文本（可能含 [动画表情] 占位符）。"""
    return adapter.session_last_line(CURRENT_TARGET)


def candidate_messages(msgs):
    """提取可处理的 friend 消息：文本消息 + 带真实文字的表情/图片消息。

    排除：占位符（[动画表情]/[图片]/[表情]…）、纯「图片」字样、语音/文件/视频。
    """
    from wxauto4.msgs.friend import FriendTextMessage, FriendImageMessage, FriendOtherMessage

    out = []
    for m in msgs:
        if not m.is_friend or m.is_system:
            continue
        if not isinstance(m, (FriendTextMessage, FriendImageMessage, FriendOtherMessage)):
            continue
        content = str(getattr(m, "content", "") or "").strip()
        if not content:
            continue
        if content.startswith("[") and content.endswith("]"):
            continue  # [动画表情] 等占位符，无文字可识别
        if content == "图片":
            continue  # 纯图片消息
        out.append(m)
    return out


def is_anchored(latest_content: str, her_last_line: str) -> bool:
    """列表最后一条与最新消息互相包含即为锚定（当前会话是她）。"""
    if not her_last_line or not latest_content:
        return False
    return latest_content in her_last_line or her_last_line in latest_content


# 切回防抖：5 秒内最多自动切回一次（避免未读误判死循环/反复点击）
_last_switch_ts: list[float] = [0.0]


def is_emoticon_only(text: str) -> bool:
    """判断是否为纯表情/图片消息（无实际可回复语义）。

    跳过：图片、[动画表情]、[表情]、动画表情 [宕机]、动画表情（空降1）等；
    保留：带真实文字的（如「我不行了」表情包文字、正常聊天）。
    """
    t = (text or "").strip()
    if not t or t == "图片":
        return True
    if t.startswith("[") and t.endswith("]"):
        return True
    if "动画表情" in t or "表情" in t[:4]:
        # 只有表情名（短文本）→ 纯表情；带附加长文字（>12字）→ 保留
        return len(t) <= 12
    return False


def process_new_messages(adapter, state: State, dry: bool, confirm: bool) -> None:
    # --- 1) 未读处理（防抖：仅当目标有未读且 5 秒内未切过才点击） ---
    now = time.time()
    if adapter.unread_count(CURRENT_TARGET) > 0 and now - _last_switch_ts[0] > 5:
        log("检测到未读，切回目标会话")
        if switch_to_target(adapter):
            _last_switch_ts[0] = time.time()
        time.sleep(0.6)
        # 若点击后未读仍在，补点一次（部分场景第一次点击只激活窗口）
        if adapter.unread_count(CURRENT_TARGET) > 0 and now - _last_switch_ts[0] > 1:
            switch_to_target(adapter)
            time.sleep(0.5)

    # --- 2) 全量读当前会话最近消息（不依赖 GetNewMessage 的数量变化检测） ---
    history = get_history(adapter, CONFIG["monitor"]["history_window"])
    if not history:
        return

    # --- 3) 提取她的新文本消息（过滤纯表情；内容指纹去重） ---
    new_msgs: list[dict[str, str]] = []
    for item in history:
        if item.get("role") != "her":
            continue
        text = str(item.get("text", "") or "").strip()
        if is_emoticon_only(text):
            continue
        fp = State.fingerprint(text)
        if state.seen(fp):
            continue
        new_msgs.append(item)
        state.mark_seen(fp)
    if not new_msgs:
        return

    # --- 4) 锚定确认：最新一条她消息应与列表最后一条吻合（防误发到群/他人） ---
    her_last_line = extract_her_last_line(adapter)
    latest_content = new_msgs[-1]["text"]
    if not is_anchored(latest_content, her_last_line):
        # 锚定不符：可能是表情包文本差异（列表截断）导致；用未读状态 + 切回内容确认兜底
        log(f"锚定不符（{latest_content[:16]!r} vs {her_last_line[:16]!r}），切回目标会话内容确认")
        if not switch_to_target(adapter):
            log("⚠ 切回失败，跳过本轮")
            return
        _last_switch_ts[0] = time.time()
        time.sleep(0.4)
        re_history = get_history(adapter, CONFIG["monitor"]["history_window"])
        re_texts = {str(i.get("text", "")).strip() for i in re_history}
        # 放宽匹配：新消息文本与重读窗口文本互相包含（表情文本差异容忍）
        if not any(
            i["text"] in re_texts
            or any(t and (i["text"] in t or t in i["text"]) for t in re_texts)
            for i in new_msgs
        ):
            # 最后兜底：她的未读 > 0 说明她刚发过消息，切回后窗口就是她的
            if adapter.unread_count(CURRENT_TARGET) <= 0:
                log("⚠ 内容确认不匹配（当前会话不是目标），跳过")
                return
        log("内容确认匹配，继续处理")

    # --- 5) 逐条处理（冷却/生成/发送） ---
    # 异地状态（每次生成前检测，含配置地点 + 聊天记录推断）
    distance = detect_distance(
        get_history(adapter, CONFIG["monitor"]["history_window"]),
        me_city=CONFIG.get("location", {}).get("me", ""),
        her_city=CONFIG.get("location", {}).get("her", ""),
    )

    for msg in new_msgs:
        try:
            content = msg["text"]
            log(f"收到她的消息: {content[:60]}")

            ok, reason = state.can_reply()
            if not ok:
                log(f"跳过（{reason}）: {content[:30]}")
                continue

            history = get_history(adapter, CONFIG["monitor"]["history_window"])
            try:
                api_key = load_api_key()
                # 多候选生成：3 条 + 系统判最优（自动发送用最优那条）
                result = generate_variants(api_key, history, content,
                                           n=3, target_name=CURRENT_TARGET,
                                           distance=distance)
            except Exception as e:
                log(f"生成回复失败: {e}")
                continue

            variants = result["variants"]
            best = result["best"]
            reply = variants[best] if variants else ""
            # 空回复保护：LLM 返回空/清洗后为空 → 不发送不写 pending
            if not reply:
                log("⚠ 生成回复为空，跳过（该消息已标记已见，不会重复触发）")
                continue
            needs_approval = result["needs_approval"][best] if best < len(result["needs_approval"]) else False
            preview = " | ".join(f"{i+1}.{v[:12]}" for i, v in enumerate(variants) if v)
            log(f"信号 {result['signals'] or '无'} → 候选: {preview}（系统推荐第 {best+1} 条）"
                + (" ⚠ 涉及花钱/见面承诺" if needs_approval else ""))

            # 需确认的回复：一律转 pending（三种模式都遵守，花钱/见面必须经同意）
            if needs_approval:
                state.data["pending"].append({
                    "ts": time.time(),
                    "msg": content,
                    "reply": reply,
                    "variants": variants,
                    "best": best,
                    "signals": result["signals"],
                    "approval": True,
                })
                state.save()
                log("⚠ 涉及花钱/见面承诺，已转入待确认（未发送）")
                continue

            if dry:
                log("（dry 模式）未发送")
                continue
            if confirm:
                state.data["pending"].append({
                    "ts": time.time(),
                    "msg": content,
                    "reply": reply,
                    "variants": variants,
                    "best": best,
                    "signals": result["signals"],
                })
                state.save()
                log("（确认模式）3 条候选已写入 pending，未发送")
                continue

            try:
                resp = adapter.send(reply)
                state.note_reply()
                log(f"已发送 ✓（系统推荐第 {best + 1} 条）: {reply[:40]}（{resp}）")
            except Exception as e:
                # 自动发送失败 → 转 pending（人工重发，不丢消息）
                state.data["pending"].append({
                    "ts": time.time(),
                    "msg": content,
                    "reply": reply,
                    "variants": variants,
                    "best": best,
                    "signals": result["signals"],
                })
                state.save()
                log(f"⚠ 发送失败，已转入待确认（可手动重发）: {e}")
        except Exception as e:
            log(f"处理消息异常: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="狗头军师微信自动回复（CLI）")
    parser.add_argument("--dry", action="store_true", help="只生成不发送")
    parser.add_argument("--confirm", action="store_true", help="生成后写 pending，不自动发送")
    args = parser.parse_args()

    dry = args.dry
    confirm = args.confirm or CONFIG["monitor"]["confirm_before_send"]
    state = State(ROOT / CONFIG["paths"]["state_file"])

    from adapters.wechat_wxauto import WeChatAdapter
    log(f"连接微信…（目标: {CURRENT_TARGET}）")
    adapter = WeChatAdapter(CURRENT_TARGET, log=log)
    adapter.install_mouse_guard()

    # 启动时切到目标会话（保证初始状态锚定）
    if not switch_to_target(adapter):
        log("⚠ 未能在会话列表找到目标，请确认备注名后重试")
        sys.exit(1)

    interval = CONFIG["monitor"]["poll_interval_seconds"]
    log(f"开始轮询（每 {interval}s，Ctrl+C 退出）")
    try:
        while True:
            process_new_messages(adapter, state, dry, confirm)
            time.sleep(interval)
    except KeyboardInterrupt:
        log("已退出")
    finally:
        state.save()


if __name__ == "__main__":
    main()
