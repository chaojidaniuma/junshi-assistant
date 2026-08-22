# -*- coding: utf-8 -*-
"""微信适配（wxauto4 UI 自动化）。从旧 adapters/wechat_wxauto.py 迁移，实现 base.ChatAdapter。"""
from __future__ import annotations

import time

from .base import ChatAdapter


class WeChatAdapter(ChatAdapter):
    def __init__(self, target_name: str, log=None):
        self.target_name = target_name
        self.log = log or (lambda msg: None)
        try:
            from wxauto4 import WeChat
            from wxauto4 import uia as uia_mod
            self._uia_mod = uia_mod
            self.wx = WeChat()
        except ImportError as e:
            raise RuntimeError(
                "未安装 wxauto4，请先: pip install git+https://github.com/zhengheng077/wxauto4.git") from e

    # ---- 会话 ----
    def current_chat_name(self) -> str:
        try:
            return str(self.wx.ChatBox.editbox.Name or "").strip()
        except Exception:
            return ""

    def list_sessions(self) -> list[str]:
        names = [s.name for s in self.wx.GetSession() if s.name]
        cur = self.current_chat_name()
        if cur and cur not in names:
            names.insert(0, cur)
        return names

    def find_session(self, name: str):
        for el in self.wx.GetSession():
            if el.name == name:
                return el
        return None

    def switch_to(self, name: str | None = None) -> bool:
        name = name or self.target_name
        if self.current_chat_name() == name:
            return True
        el = self.find_session(name)
        if el is not None:
            try:
                el.click()
                time.sleep(0.6)
                return True
            except Exception as e:
                self.log(f"切换会话失败: {e}")
                return False
        try:
            if self.wx.ChatWith(name):
                time.sleep(0.6)
                if self.current_chat_name() == name:
                    return True
                self.recover_ui()
                return self.current_chat_name() == name
        except Exception as e:
            self.log(f"搜索切换会话失败: {e}")
        return False

    def recover_ui(self) -> None:
        try:
            self._uia_mod.SendKeys("{ESC}")
            time.sleep(0.5)
        except Exception:
            pass
        try:
            self.wx.SwitchToChat()
        except Exception:
            pass
        time.sleep(0.6)

    def unread_count(self, name: str | None = None) -> int:
        el = self.find_session(name or self.target_name)
        if el is None:
            return 0
        try:
            return el.unread_count
        except Exception:
            return 0

    def get_session_info(self, name: str | None = None) -> dict:
        name = name or self.target_name
        el = self.find_session(name)
        if el is None:
            if self.current_chat_name() != name:
                return {"exists": False, "unread": 0, "last_line": ""}
            last_line = ""
            try:
                her_lines = [h["text"].strip() for h in self.get_all_messages(10)
                             if h["role"] == "her" and h["text"].strip()]
                last_line = her_lines[-1] if her_lines else ""
            except Exception:
                pass
            return {"exists": True, "unread": 0, "last_line": last_line}
        unread = 0
        try:
            unread = el.unread_count
        except Exception:
            pass
        last_line = ""
        try:
            lines = [ln for ln in str(el.content).split("\n") if ln.strip()]
            skip = {name, "已置顶"}
            for ln in reversed(lines):
                if ln not in skip and not ln.replace(":", "").replace(".", "").isdigit():
                    last_line = ln
                    break
        except Exception:
            pass
        return {"exists": True, "unread": unread, "last_line": last_line}

    # ---- 消息 ----
    def get_all_messages(self, window: int = 20) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        try:
            msgs = self.wx.GetAllMessage()
            for m in msgs[-window:]:
                if m.is_system:
                    continue
                role = "me" if m.is_self else "her"
                history.append({"role": role, "text": str(getattr(m, "content", "") or "")})
        except Exception as e:
            self.log(f"获取历史失败（降级为空历史）: {e}")
        return history

    def send(self, text: str) -> None:
        from wxauto4.utils.win32 import SetClipboardText

        chatbox = self.wx.ChatBox
        editbox = chatbox.editbox
        try:
            chatbox._show()
        except Exception:
            pass
        try:
            editbox.Click()
            editbox.SendKeys("{Ctrl}a", waitTime=0)
            editbox.SendKeys("{DELETE}")
        except Exception:
            pass

        last_err: Exception | None = None
        for attempt in range(2):
            try:
                SetClipboardText(text)
                editbox.Click()
                editbox.SendKeys("{Ctrl}v")
                time.sleep(0.4)
                try:
                    value = editbox.GetValuePattern().Value or ""
                    if not value.replace("￼", "").strip():
                        editbox.SendKeys("{Ctrl}v")
                        time.sleep(0.4)
                except Exception:
                    pass
                editbox.SendKeys("{ENTER}")
                time.sleep(0.5)
                if self._input_cleared(editbox):
                    return
                btn = chatbox.control.ButtonControl(Name="发送", timeout=2)
                if btn.Exists(2):
                    btn.Click()
                    time.sleep(0.5)
                    if self._input_cleared(editbox):
                        return
                last_err = RuntimeError("回车未发出，发送按钮点击后输入框仍有内容")
            except Exception as e:
                last_err = e
            time.sleep(1.0)
        raise RuntimeError(f"发送失败（已重试）: {last_err}")

    @staticmethod
    def _input_cleared(editbox) -> bool:
        try:
            value = editbox.getValuePattern().Value or "" if hasattr(editbox, "getValuePattern") \
                else editbox.GetValuePattern().Value or ""
            return not value.replace("￼", "").strip()
        except Exception:
            return True

    def install_mouse_guard(self) -> None:
        import ctypes
        uia_mod = self._uia_mod
        user32 = ctypes.windll.user32

        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        def _get_pos():
            p = _POINT()
            user32.GetCursorPos(ctypes.byref(p))
            return p.x, p.y

        def _guard(orig):
            def wrapper(*args, **kwargs):
                px, py = _get_pos()
                try:
                    return orig(*args, **kwargs)
                finally:
                    time.sleep(0.12)
                    user32.SetCursorPos(px, py)
            return wrapper

        for name in ("Click", "MiddleClick", "RightClick", "DoubleClick",
                     "WheelDown", "WheelUp"):
            if hasattr(uia_mod.Control, name):
                setattr(uia_mod.Control, name, _guard(getattr(uia_mod.Control, name)))
