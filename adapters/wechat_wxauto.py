# -*- coding: utf-8 -*-
"""微信平台适配层（wxauto4，UI 自动化，非 hook 非注入）。

架构定位：所有与微信客户端交互的能力收敛在此模块，
上层（main/gui）只依赖本模块的稳定接口 —— 替换成其他平台
（企业微信、Telegram、QQ…）时只需实现同样的接口。

接口：WeChatAdapter（连接/会话/切换/读消息/历史/发送）
"""

from __future__ import annotations

import time
from typing import Any


class WeChatAdapter:
    """wxauto4 封装：连接、会话定位、消息读取、发送。"""

    def __init__(self, target_name: str, log=None):
        self.target_name = target_name
        self.log = log or (lambda msg: None)
        try:
            from wxauto4 import WeChat
            from wxauto4 import uia as uia_mod
            self._uia_mod = uia_mod
            self.wx = WeChat()
        except ImportError as e:
            raise RuntimeError("未安装 wxauto4，请先: pip install git+https://github.com/zhengheng077/wxauto4.git") from e

    # ---- 会话 ----
    def list_sessions(self) -> list[str]:
        """当前可见会话名列表。"""
        return [s.name for s in self.wx.GetSession() if s.name]

    def find_session(self, name: str):
        """按名字找会话元素。"""
        for el in self.wx.GetSession():
            if el.name == name:
                return el
        return None

    def switch_to(self, name: str | None = None) -> bool:
        """点击会话（切回目标）。name 缺省用当前目标。"""
        name = name or self.target_name
        el = self.find_session(name)
        if el is None:
            return False
        try:
            el.click()
            time.sleep(0.6)
            return True
        except Exception as e:
            self.log(f"切换会话失败: {e}")
            return False

    def unread_count(self, name: str | None = None) -> int:
        el = self.find_session(name or self.target_name)
        if el is None:
            return 0
        try:
            return el.unread_count
        except Exception:
            return 0

    def session_last_line(self, name: str | None = None) -> str:
        """会话在列表里显示的最后一条（可能是 [动画表情] 占位符）。"""
        el = self.find_session(name or self.target_name)
        if el is None:
            return ""
        try:
            lines = [ln for ln in str(el.content).split("\n") if ln.strip()]
            skip = {self.target_name, "已置顶"}
            for ln in reversed(lines):
                if ln not in skip and not ln.replace(":", "").replace(".", "").isdigit():
                    return ln
        except Exception:
            pass
        return ""

    # ---- 消息 ----
    def get_new_messages(self) -> list[Any]:
        """当前会话的新消息（增量）。"""
        return self.wx.GetNewMessage()

    def get_all_messages(self, window: int = 20) -> list[dict[str, str]]:
        """当前会话最近消息 → [{'role': 'me'|'her', 'text': str}]。"""
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
        """发送到当前会话。

        自定义发送流程（微信 4.1 发送按钮在输入框为空时不存在，
        wxauto4 缓存的按钮控件会失效）：
        1. 聚焦输入框 + 剪贴板粘贴
        2. 按 Enter（微信默认回车发送）
        3. 输入框未清空（用户设置了 Ctrl+Enter）→ 现查发送按钮点击
        4. 仍失败 → 重试 1 次，再失败抛异常（上层恢复待确认）
        """
        from wxauto4.utils.win32 import SetClipboardText

        chatbox = self.wx.ChatBox
        editbox = chatbox.editbox
        # 微信窗口置前
        try:
            chatbox._show()
        except Exception:
            pass
        # 清空输入框残留
        try:
            editbox.Click()
            editbox.SendKeys("{Ctrl}a", waitTime=0)
            editbox.SendKeys("{DELETE}")
        except Exception:
            pass

        last_err: Exception | None = None
        for attempt in range(2):
            try:
                # 粘贴
                SetClipboardText(text)
                editbox.Click()
                editbox.SendKeys("{Ctrl}v")
                time.sleep(0.4)
                # 校验输入框有内容（粘贴成功）
                try:
                    value = editbox.GetValuePattern().Value or ""
                    if not value.replace("￼", "").strip():
                        editbox.SendKeys("{Ctrl}v")
                        time.sleep(0.4)
                except Exception:
                    pass
                # 方式一：Enter 发送（微信默认）
                editbox.SendKeys("{ENTER}")
                time.sleep(0.5)
                if self._input_cleared(editbox):
                    return
                # 方式二：现查发送按钮（输入框有内容后按钮才存在）
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
        """输入框已清空 = 消息已发出。"""
        try:
            value = editbox.GetValuePattern().Value or ""
            return not value.replace("￼", "").strip()
        except Exception:
            return True  # 读取失败视为已发送（避免误报）

    # ---- 鼠标保护 ----
    def install_mouse_guard(self) -> None:
        """给 wxauto4 鼠标操作加「用完还回」（防鼠标乱跑）。"""
        import ctypes
        uia_mod = self._uia_mod
        user32 = ctypes.windll.user32

        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        def _get_pos():
            p = _POINT()
            user32.GetCursorPos(ctypes.byref(p))
            return p.x, p.y

        def _set_pos(x, y):
            user32.SetCursorPos(x, y)

        def _guard(orig):
            def wrapper(*args, **kwargs):
                px, py = _get_pos()
                try:
                    return orig(*args, **kwargs)
                finally:
                    time.sleep(0.12)
                    _set_pos(px, py)
            return wrapper

        for name in ("Click", "MiddleClick", "RightClick", "DoubleClick", "WheelDown", "WheelUp"):
            if hasattr(uia_mod.Control, name):
                setattr(uia_mod.Control, name, _guard(getattr(uia_mod.Control, name)))
        for name in ("Click", "MiddleClick", "RightClick", "DoubleClick", "MoveTo"):
            if hasattr(uia_mod, name):
                setattr(uia_mod, name, _guard(getattr(uia_mod, name)))
