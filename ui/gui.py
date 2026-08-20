# -*- coding: utf-8 -*-
"""狗头军师自动回复 —— 桌面可视化窗口（tkinter）。

功能：
- 单实例：重复启动时自动激活已有窗口（Windows 互斥体）
- 回复对象可选：下拉框从微信会话列表选择，切换即生效并持久化
- 启动/停止监控（后台线程轮询微信）
- 实时显示：她的消息、生成的回复、信号、日志
- 模式切换：dry（只生成）/ 自动发送 / 确认（写 pending）
- 一键「提取回复风格」：从 ChatLab 聊天数据提炼你的风格档案并即时生效
- 查看当前风格档案

打包：pyinstaller --noconfirm --onefile --windowed --name goutou-auto --collect-all wxauto4 gui.py
"""

from __future__ import annotations

import ctypes
import json
import queue
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# 冻结（EXE）模式下以 exe 所在目录为根
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import main as core  # noqa: E402

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

# ---------- 单实例互斥（Windows 命名互斥体） ----------
_MUTEX_HANDLE = None


def acquire_single_instance() -> bool:
    """抢单实例互斥体。返回 True=本实例持有（可继续）；False=已有实例，应退出。"""
    global _MUTEX_HANDLE
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    _MUTEX_HANDLE = kernel32.CreateMutexW(None, False, "GoutouAutoSingleInstance")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return False
    return True


def activate_existing_window() -> None:
    """找到已运行实例的主窗口并置前。"""
    user32 = ctypes.windll.user32
    user32.EnumWindows.restype = wintypes.BOOL

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if "狗头军师自动回复" in buf.value:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                return False
        return True

    user32.EnumWindows(callback, 0)


# windowed（无控制台）模式下异常静默，写入 crash.log 便于诊断
def _write_probe(msg: str) -> None:
    try:
        with open(ROOT / "probe.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


if getattr(sys, "frozen", False) and sys.stderr is None:
    def _excepthook(t, v, tb):
        _write_probe(f"CRASH: {t.__name__}: {v}")
        try:
            import traceback
            _write_probe(traceback.format_exc()[-2000:])
        except Exception:
            pass

    sys.excepthook = _excepthook
PROFILE_PATH = ROOT / "data" / "style_profile.json"


class GoutouApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"狗头军师自动回复 — 目标: {core.CURRENT_TARGET}")
        self.root.geometry("680x760")
        self.root.minsize(560, 620)

        self.ui_queue: queue.Queue = queue.Queue()
        self.ctrl_queue: queue.Queue = queue.Queue()  # UI → worker 控制指令
        self.running = False
        self.worker: threading.Thread | None = None
        self.mode = tk.StringVar(value="dry")

        self._build_ui()
        self._poll_ui_queue()
        # 重定向核心模块的日志到 UI 队列
        core.log = self._thread_log
        self._append_log(f"狗头军师 v2 已启动，目标: {core.CURRENT_TARGET}")

    # ---------- UI 构建 ----------
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        font = ("Microsoft YaHei UI", 10)

        # 状态栏
        status = ttk.Frame(self.root, padding=(10, 8))
        status.pack(fill="x")
        self.status_dot = tk.Label(status, text="●", fg="#9e9e9e", font=("Segoe UI", 12))
        self.status_dot.pack(side="left")
        self.status_text = tk.Label(status, text="未运行", fg="#555", font=font)
        self.status_text.pack(side="left", padx=(6, 16))
        self.mode_label = tk.Label(status, text="模式: dry（只生成不发送）", fg="#555", font=font)
        self.mode_label.pack(side="left")
        self.distance_label = tk.Label(status, text="异地: 未知", fg="#888", font=("Microsoft YaHei UI", 9))
        self.distance_label.pack(side="right")

        # 模式选择
        mode_frame = ttk.Frame(self.root, padding=(10, 0))
        mode_frame.pack(fill="x")
        for key, label in [("dry", "dry 只生成"), ("auto", "自动发送"), ("confirm", "确认后发")]:
            ttk.Radiobutton(mode_frame, text=label, value=key, variable=self.mode,
                            command=self._on_mode_change).pack(side="left", padx=(0, 12))

        # 回复对象选择
        target_frame = ttk.Frame(self.root, padding=(10, 4))
        target_frame.pack(fill="x")
        ttk.Label(target_frame, text="回复对象:", font=font).pack(side="left")
        self.target_combo = ttk.Combobox(target_frame, state="readonly", width=28, font=font)
        self.target_combo.pack(side="left", padx=(6, 6))
        self.target_combo.set(core.CURRENT_TARGET)
        self.target_combo.bind("<<ComboboxSelected>>", self._on_target_selected)
        self.btn_refresh = ttk.Button(target_frame, text="↻ 刷新列表", command=self._refresh_targets)
        self.btn_refresh.pack(side="left")

        # 待确认面板（确认后发送模式 + 花钱/见面承诺自动转入）
        pending_frame = ttk.LabelFrame(self.root, text=" 待确认回复（花钱/见面承诺须人工确认） ", padding=6)
        pending_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.pending_list = tk.Listbox(pending_frame, height=4, font=("Microsoft YaHei UI", 9),
                                       selectmode="single", activestyle="none")
        pending_scroll = ttk.Scrollbar(pending_frame, command=self.pending_list.yview)
        self.pending_list.configure(yscrollcommand=pending_scroll.set)
        self.pending_list.pack(side="left", fill="both", expand=True)
        pending_scroll.pack(side="left", fill="y")
        pending_btns = ttk.Frame(pending_frame)
        pending_btns.pack(side="left", padx=(8, 0), fill="y")
        self.btn_confirm_send = ttk.Button(pending_btns, text="✓ 确认发送", command=self._confirm_send)
        self.btn_confirm_send.pack(fill="x", pady=(0, 4))
        self.btn_ignore = ttk.Button(pending_btns, text="✗ 忽略", command=self._ignore_pending)
        self.btn_ignore.pack(fill="x", pady=(0, 4))
        self.btn_clear_pending = ttk.Button(pending_btns, text="清空", command=self._clear_pending)
        self.btn_clear_pending.pack(fill="x")

        # 消息区
        msg_frame = ttk.LabelFrame(self.root, text=" 她的消息 → 生成回复 ", padding=6)
        msg_frame.pack(fill="both", expand=True, padx=10, pady=6)
        self.msg_text = tk.Text(msg_frame, height=10, font=("Microsoft YaHei UI", 10),
                                state="disabled", wrap="word", bg="#fafafa")
        msg_scroll = ttk.Scrollbar(msg_frame, command=self.msg_text.yview)
        self.msg_text.configure(yscrollcommand=msg_scroll.set)
        self.msg_text.pack(side="left", fill="both", expand=True)
        msg_scroll.pack(side="right", fill="y")

        # 日志区
        log_frame = ttk.LabelFrame(self.root, text=" 运行日志 ", padding=6)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.log_text = tk.Text(log_frame, height=12, font=("Consolas", 9),
                                state="disabled", wrap="word", bg="#1e1e1e", fg="#d4d4d4")
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        # 按钮
        btns = ttk.Frame(self.root, padding=(10, 8))
        btns.pack(fill="x")
        self.btn_start = ttk.Button(btns, text="▶ 启动监控", command=self._start)
        self.btn_start.pack(side="left", padx=(0, 8))
        self.btn_stop = ttk.Button(btns, text="■ 停止", command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 8))
        self.btn_style = ttk.Button(btns, text="✨ 提取回复风格", command=self._extract_style)
        self.btn_style.pack(side="left", padx=(0, 8))
        self.btn_view_style = ttk.Button(btns, text="查看风格档案", command=self._view_style)
        self.btn_view_style.pack(side="left", padx=(0, 8))
        self.btn_help = ttk.Button(btns, text="❓ 使用说明", command=self._show_help)
        self.btn_help.pack(side="left", padx=(0, 8))
        self.btn_settings = ttk.Button(btns, text="⚙ 设置", command=self._open_settings)
        self.btn_settings.pack(side="left", padx=(0, 8))
        self.btn_clear = ttk.Button(btns, text="清空日志", command=self._clear_logs)
        self.btn_clear.pack(side="left")

    # ---------- 队列轮询（UI 线程） ----------
    def _poll_ui_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "msg":
                    self._append_msg(payload)
                elif kind == "status":
                    self._set_status(*payload)
                elif kind == "style_done":
                    self._append_msg(f"✅ 风格档案已更新: {payload}")
                    self._append_log(f"风格档案已更新: {payload}")
                    self.btn_style.configure(state="normal")
                    messagebox.showinfo("提取完成", f"回复风格已更新并即时生效！\n{payload}")
                elif kind == "style_fail":
                    self._append_log(f"❌ 风格提取失败: {payload}")
                    self.btn_style.configure(state="normal")
                    messagebox.showerror("提取失败", str(payload))
                elif kind == "targets":
                    self.target_combo.configure(values=payload)
                    if core.CURRENT_TARGET not in payload:
                        self.target_combo.set("")
                    else:
                        self.target_combo.set(core.CURRENT_TARGET)
                    self._append_log(f"会话列表已刷新（{len(payload)} 个），选择回复对象后即生效")
                    self.btn_refresh.configure(state="normal")
                    self._refreshing = False
                elif kind == "targets_fail":
                    self._append_log(f"❌ 读取会话列表失败: {payload}")
                    self.btn_refresh.configure(state="normal")
                    self._refreshing = False
                elif kind == "pending_sync":
                    self._refresh_pending_display(payload)
                elif kind == "distance":
                    labels = {"异地": "异地: 是", "同城": "异地: 否（同城）", "未知": "异地: 未知"}
                    self.distance_label.configure(text=labels.get(payload, f"异地: {payload}"))
                elif kind in ("test_ok", "test_fail"):
                    cb = getattr(self, "_test_cb", None)
                    if cb:
                        cb(kind, payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_ui_queue)

    # ---------- UI 更新 ----------
    def _thread_log(self, msg: str):
        """后台线程日志 → UI 队列（core.log 重定向目标）。"""
        self.ui_queue.put(("log", msg))
        if (msg.startswith("收到她的消息") or "→ 回复:" in msg
                or msg.startswith("已发送") or msg.startswith("（dry")):
            self.ui_queue.put(("msg", msg))

    def _append_log(self, line: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {line}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _append_msg(self, line: str):
        self.msg_text.configure(state="normal")
        self.msg_text.insert("end", line + "\n")
        self.msg_text.see("end")
        self.msg_text.configure(state="disabled")

    def _set_status(self, running: bool, text: str):
        self.status_dot.configure(fg="#4caf50" if running else "#9e9e9e")
        self.status_text.configure(text=text)

    def _on_mode_change(self):
        mode = self.mode.get()
        labels = {"dry": "dry（只生成不发送）", "auto": "自动发送", "confirm": "确认后发送"}
        self.mode_label.configure(text=f"模式: {labels.get(mode, mode)}")
        self._append_log(f"模式切换为: {mode}")

    # ---------- 回复对象选择 ----------
    def _refresh_targets(self):
        """从微信会话列表拉取所有会话，填充下拉框（后台线程，避免卡 UI）。"""
        if getattr(self, "_refreshing", False):
            return
        self._refreshing = True
        self.btn_refresh.configure(state="disabled")
        self._append_log("正在读取微信会话列表…")
        threading.Thread(target=self._refresh_targets_worker, daemon=True).start()

    def _refresh_targets_worker(self):
        try:
            from adapters.wechat_wxauto import WeChatAdapter
            adapter = WeChatAdapter(core.CURRENT_TARGET, log=self._thread_log)
            names = adapter.list_sessions()
            names = list(dict.fromkeys(names))  # 去重保序
            self.ui_queue.put(("targets", names))
        except Exception as e:
            self.ui_queue.put(("targets_fail", str(e)))

    def _on_target_selected(self, _event=None):
        name = self.target_combo.get()
        if not name or name == core.CURRENT_TARGET:
            return
        core.set_target(name)
        self.root.title(f"狗头军师自动回复 — 目标: {name}")
        # 提示该对象当前的风格档案状态
        import goutou.prompts as prompts
        style_note = "（有专属风格档案）" if prompts.load_style_profile(name) else "（无专属档案，用默认风格；点「提取回复风格」为该对象生成）"
        self._append_log(f"✅ 回复对象切换为: {name}{style_note}（已保存，监控运行中即刻生效）")

    def _clear_logs(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ---------- 待确认面板 ----------
    def _refresh_pending_display(self, items: list):
        """刷新待确认 Listbox。items: state.data['pending'] 列表（含多候选）。"""
        self.pending_list.delete(0, "end")
        for it in items:
            flag = "⚠需确认 " if it.get("approval") else ""
            msg = str(it.get("msg", ""))[:14]
            variants = it.get("variants") or [it.get("reply", "")]
            best = int(it.get("best") or 0)
            parts = []
            for i, v in enumerate(variants):
                if not v:
                    continue
                star = "⭐" if i == best else f"{i+1}."
                parts.append(f"{star}{v[:10]}")
            self.pending_list.insert("end", f"{flag}她: {msg} → {' | '.join(parts)}")

    def _selected_pending(self):
        sel = self.pending_list.curselection()
        if not sel:
            messagebox.showinfo("提示", "先在列表里选中一条待确认的回复")
            return None
        return sel[0], self.pending_list.get(sel[0])

    def _choose_variant_dialog(self, item: dict) -> str | None:
        """弹出候选选择窗口：3 条回复 + 系统推荐（默认选中），返回选中的回复文本。"""
        variants = item.get("variants") or [item.get("reply", "")]
        best = int(item.get("best") or 0)
        win = tk.Toplevel(self.root)
        win.title("选择要发送的回复")
        win.geometry("520x420")
        win.transient(self.root)
        font = ("Microsoft YaHei UI", 10)

        tk.Label(win, text=f"她的消息：{str(item.get('msg', ''))[:40]}",
                 font=font, wraplength=480, justify="left").pack(anchor="w", padx=14, pady=(12, 8))

        var = tk.IntVar(value=best if best < len(variants) else 0)
        for i, v in enumerate(variants):
            if not v:
                continue
            star = " ⭐系统推荐" if i == best else ""
            tk.Radiobutton(win, text=f"候选 {i + 1}{star}", variable=var, value=i,
                           font=font).pack(anchor="w", padx=14)
            tk.Label(win, text=v, font=("Microsoft YaHei UI", 10), wraplength=470,
                     justify="left", fg="#333", bg="#f5f5f5", padx=8, pady=6).pack(
                anchor="w", padx=30, pady=(0, 8), fill="x")
        tk.Label(win, text="提示：可修改后发送？暂不支持——先选一条，或点取消后忽略该条",
                 font=("Microsoft YaHei UI", 8), fg="#888").pack(anchor="w", padx=14)

        result = {"text": None}

        def ok():
            result["text"] = variants[var.get()] if var.get() < len(variants) else variants[0]
            win.destroy()

        btn_row = ttk.Frame(win)
        btn_row.pack(fill="x", padx=14, pady=12)
        ttk.Button(btn_row, text="✓ 发送这条", command=ok).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="取消", command=win.destroy).pack(side="left")
        self.root.wait_window(win)
        return result["text"]

    def _confirm_send(self):
        if not self.running:
            messagebox.showwarning("未运行", "请先「启动监控」，确认发送由监控线程执行")
            return
        sel = self._selected_pending()
        if sel is None:
            return
        index = sel[0]
        try:
            state = core.State(ROOT / CONFIG["paths"]["state_file"])
            pending = state.data.get("pending", [])
            if not (0 <= index < len(pending)):
                messagebox.showinfo("提示", "该条目已不存在（可能已被处理）")
                return
            item = pending[index]
            chosen = self._choose_variant_dialog(item)
            if chosen is None:
                return
            self.ctrl_queue.put(("send", (index, chosen)))
            self._append_log(f"已提交确认发送: {chosen[:40]}")
        except Exception as e:
            self._append_log(f"读取待确认失败: {e}")

    def _ignore_pending(self):
        sel = self._selected_pending()
        if sel is None:
            return
        self.ctrl_queue.put(("ignore", sel[0]))
        self._append_log("已提交忽略…")

    def _clear_pending(self):
        self.ctrl_queue.put(("clear_pending", None))

    # ---------- 设置 ----------
    def _open_settings(self):
        """设置窗口（可滚动）：LLM（可插拔+测试连接）/ 知识库 / 异地 / 监控，一键保存。"""
        from goutou.config import load_config, save_config

        cfg = load_config()
        win = tk.Toplevel(self.root)
        win.title("⚙ 设置")
        win.geometry("580x620")
        win.minsize(520, 420)
        win.transient(self.root)
        font = ("Microsoft YaHei UI", 10)
        small = ("Microsoft YaHei UI", 9)
        entries: dict[str, tk.Entry] = {}

        # --- 滚动容器（Canvas + 内嵌 Frame，支持鼠标滚轮） ---
        canvas = tk.Canvas(win, highlightthickness=0)
        vbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

        inner = ttk.Frame(canvas, padding=(10, 8))
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _on_inner_configure)

        def _on_canvas_configure(e):
            canvas.itemconfigure(win_id, width=e.width)

        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")

        win.bind("<MouseWheel>", _on_mousewheel)
        canvas.bind("<MouseWheel>", _on_mousewheel)
        inner.bind("<MouseWheel>", _on_mousewheel)

        def add_row(parent, label, key, default="", show=None, width=46):
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=16, font=small).pack(side="left")
            var = tk.StringVar(value=default)
            ent = ttk.Entry(row, textvariable=var, width=width, font=small, show=show)
            ent.pack(side="left", padx=(4, 0))
            entries[key] = ent
            return row

        # --- LLM 设置 ---
        llm_frame = ttk.LabelFrame(inner, text=" 大模型（LLM 可插拔：填 API 即切换） ", padding=8)
        llm_frame.pack(fill="x", pady=(0, 6))
        llm = cfg.get("llm", {})
        add_row(llm_frame, "API 地址", "base_url", str(llm.get("base_url") or ""))
        add_row(llm_frame, "API Key", "api_key", str(llm.get("api_key") or ""), show="*")
        add_row(llm_frame, "模型名", "model", str(llm.get("model") or ""))

        # 温度：滑块 + 通俗解释
        temp_row = ttk.Frame(llm_frame)
        temp_row.pack(fill="x", pady=3)
        ttk.Label(temp_row, text="温度", width=16, font=small).pack(side="left")
        temp_var = tk.DoubleVar(value=float(llm.get("temperature") or 0.85))
        temp_scale = tk.Scale(temp_row, from_=0.0, to=1.5, resolution=0.05,
                              orient="horizontal", length=220, variable=temp_var,
                              showvalue=False, command=lambda _v: temp_desc.configure(
                                  text=_temp_label(temp_var.get())))
        temp_scale.pack(side="left")
        temp_desc = ttk.Label(llm_frame, text="", font=small, foreground="#c66")
        temp_desc.pack(anchor="w", padx=(118, 0), pady=(0, 2))

        def _temp_label(v):
            if v < 0.4:
                return f"稳定（{v:.2f}）：认真保守，话少稳妥"
            if v < 0.8:
                return f"平衡（{v:.2f}）：日常推荐"
            if v < 1.1:
                return f"活泼（{v:.2f}）：俏皮放飞，推荐聊天用"
            return f"天马行空（{v:.2f}）：脑洞大，慎用"

        temp_desc.configure(text=_temp_label(temp_var.get()))

        ttk.Label(llm_frame,
                  text="温度 = 回复的「创意程度」：低→稳定认真，高→俏皮放飞。\n聊天建议 0.7~1.0；API Key 留空时用环境变量 DEEPSEEK_API_KEY。",
                  font=("Microsoft YaHei UI", 8), foreground="#888", justify="left").pack(
            anchor="w", pady=(2, 0))

        # 测试连接
        test_row = ttk.Frame(llm_frame)
        test_row.pack(fill="x", pady=(4, 0))
        test_status = ttk.Label(test_row, text="", font=small)
        test_status.pack(side="left")

        def do_test():
            base_url = entries["base_url"].get().strip()
            model = entries["model"].get().strip()
            api_key = entries["api_key"].get().strip()
            test_status.configure(text="⏳ 测试中…", foreground="#888")
            test_row.update_idletasks()

            def worker():
                try:
                    from goutou.engine import call_openai_compatible
                    from goutou.config import resolve_api_key
                    key = resolve_api_key(api_key)
                    if not key:
                        raise RuntimeError("API Key 为空（设置里填，或设环境变量）")
                    if not base_url:
                        raise RuntimeError("API 地址为空")
                    call_openai_compatible(key, [
                        {"role": "user", "content": "回复两个字：正常"},
                    ], base_url=base_url, model=model or "deepseek-chat",
                        temperature=0.1, timeout=20, max_tokens=20)
                    self.ui_queue.put(("test_ok", None))
                except Exception as e:
                    self.ui_queue.put(("test_fail", str(e)))

            threading.Thread(target=worker, daemon=True).start()

        def _on_test_result(kind, payload):
            if kind == "test_ok":
                test_status.configure(text="✅ 连接成功，模型可用", foreground="#2e7d32")
                self._append_log("✅ LLM 测试连接成功")
            else:
                test_status.configure(text=f"❌ {payload}", foreground="#c62828")
                self._append_log(f"❌ LLM 测试连接失败: {payload}")

        # 队列里处理测试结果
        self._test_cb = _on_test_result
        ttk.Button(test_row, text="测试连接", command=do_test).pack(side="left")

        # --- 知识库 ---
        kb_frame = ttk.LabelFrame(inner, text=" 知识库（可定制：换目录 = 换行业知识） ", padding=8)
        kb_frame.pack(fill="x", pady=(0, 6))
        from goutou import kb as kb_mod
        # kb 目录：默认显示空（= 使用内置知识库），用户浏览选择后才自定义
        cfg_kb_dir = str((cfg.get("kb", {}) or {}).get("dir") or "")
        add_row(kb_frame, "知识库目录", "kb_dir", cfg_kb_dir, width=38)
        ttk.Button(kb_frame, text="浏览…", width=8,
                   command=lambda: entries["kb_dir"].delete(0, "end") or
                                   entries["kb_dir"].insert(0, filedialog.askdirectory(
                                       initialdir=str(kb_mod.get_kb_dir())))).pack(
            side="left", padx=(4, 0))
        kb_count = len(kb_mod.list_kb_files())
        ttk.Label(kb_frame, text=f"当前知识库 {kb_count} 个文件；留空 = 使用内置知识库，填目录 = 换行业知识",
                  font=("Microsoft YaHei UI", 8), foreground="#888").pack(anchor="w", pady=(2, 0))

        # --- 异地城市 ---
        loc_frame = ttk.LabelFrame(inner, text=" 异地判断（填城市最准，留空则聊天推断） ", padding=8)
        loc_frame.pack(fill="x", pady=(0, 6))
        loc = cfg.get("location", {})
        add_row(loc_frame, "我的城市", "loc_me", str(loc.get("me") or ""), width=20)
        add_row(loc_frame, "TA 的城市", "loc_her", str(loc.get("her") or ""), width=20)

        # --- 监控参数 ---
        mon_frame = ttk.LabelFrame(inner, text=" 监控参数（保存后需重启监控生效） ", padding=8)
        mon_frame.pack(fill="x", pady=(0, 6))
        mon = cfg.get("monitor", {})
        add_row(mon_frame, "轮询间隔(秒)", "poll", str(mon.get("poll_interval_seconds") or 3), width=10)
        add_row(mon_frame, "冷却(秒)", "cooldown", str(mon.get("cooldown_seconds") or 45), width=10)
        add_row(mon_frame, "小时上限", "max_hour", str(mon.get("max_replies_per_hour") or 30), width=10)
        ttk.Label(mon_frame,
                  text="冷却：同一对象连续消息只回一条的时间窗；小时上限：防风控",
                  font=("Microsoft YaHei UI", 8), foreground="#888").pack(anchor="w", pady=(2, 0))

        # --- 保存（空输入框 = 保留原值，绝不覆盖已有配置） ---
        def do_save():
            try:
                cfg2 = load_config()
                llm2 = cfg2.setdefault("llm", {})

                def _set_if_filled(ent, key):
                    v = ent.get().strip()
                    if v:
                        llm2[key] = v

                _set_if_filled(entries["base_url"], "base_url")
                _set_if_filled(entries["api_key"], "api_key")
                _set_if_filled(entries["model"], "model")
                llm2["temperature"] = round(temp_var.get(), 2)
                kb_dir = entries["kb_dir"].get().strip()
                if kb_dir:
                    kb_mod.set_kb_dir(kb_dir)  # 运行时切换（引擎立即生效）
                    cfg2.setdefault("kb", {})["dir"] = kb_dir
                elif cfg2.get("kb", {}).get("dir"):
                    cfg2["kb"]["dir"] = ""  # 清空 = 回到内置知识库
                loc2 = cfg2.setdefault("location", {})
                me_v = entries["loc_me"].get().strip()
                her_v = entries["loc_her"].get().strip()
                if me_v:
                    loc2["me"] = me_v
                if her_v:
                    loc2["her"] = her_v
                mon2 = cfg2.setdefault("monitor", {})
                try:
                    mon2["poll_interval_seconds"] = int(entries["poll"].get() or 3)
                except ValueError:
                    pass
                try:
                    mon2["cooldown_seconds"] = int(entries["cooldown"].get() or 45)
                except ValueError:
                    pass
                try:
                    mon2["max_replies_per_hour"] = int(entries["max_hour"].get() or 30)
                except ValueError:
                    pass
                save_config(cfg2)
                # 同步 main 模块的 CONFIG 缓存（异地/监控参数立即被 worker 读到）
                core.CONFIG.clear()
                core.CONFIG.update(load_config())
                self._append_log("✅ 设置已保存（LLM/知识库/城市立即生效；监控参数重启监控后生效）")
                messagebox.showinfo("设置", "已保存。\n\n大模型 / 知识库 / 异地城市：立即生效\n监控参数：停止后重新「启动监控」生效")
                win.destroy()
            except Exception as e:
                messagebox.showerror("保存失败", str(e))

        btn_row = ttk.Frame(inner)
        btn_row.pack(fill="x", pady=(4, 10))
        ttk.Button(btn_row, text="保存", command=do_save).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="取消", command=win.destroy).pack(side="left")

        # 滚动区域刷新
        win.after(50, _on_inner_configure)

    # ---------- 使用说明 ----------
    def _show_help(self):
        win = tk.Toplevel(self.root)
        win.title("狗头军师 — 使用说明")
        win.geometry("640x640")
        win.transient(self.root)

        text = tk.Text(win, font=("Microsoft YaHei UI", 10), wrap="word",
                       padx=14, pady=10, bg="#fcfcfc", fg="#222")
        scroll = ttk.Scrollbar(win, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        help_text = """【狗头军师自动回复 · 使用说明】

━━━ 一、快速开始 ━━━
1. 电脑微信保持登录（程序通过模拟操作微信界面工作）
2. 选模式：dry 只生成 / 自动发送 / 确认后发
3. 点「▶ 启动监控」→ 程序开始监听目标对象的消息
4. 她发消息 → 自动生成回复 → 按模式决定是否发送
5. 首次使用建议先跑 dry 模式，看生成的话术是否对味

━━━ 二、三种模式 ━━━
• dry 只生成：收到消息只生成回复，不发送（测试用）
• 自动发送：生成后直接发到微信（花钱/见面类回复除外，自动转待确认）
• 确认后发：所有回复都写入下方「待确认」列表，点
  「✓ 确认发送」才发，「✗ 忽略」丢弃（最安全）

━━━ 三、待确认机制（花钱/见面必确认） ━━━
• 回复涉及花钱（请客/买东西/外卖/转账/红包/送礼）或
  见面承诺（我去找你/送东西/见面给）时，**任何模式都不会自动发**，
  一律转入「待确认回复」面板
• 选中条目 →「✓ 确认发送」由监控线程发出；「✗ 忽略」丢弃
• 异地状态下见面承诺尤其严格（见下文异地判断）

━━━ 四、异地判断 ━━━
• 状态栏右侧显示「异地: 是 / 否 / 未知」
• 判断依据：config.json 的 location 填两人城市最准；
  没填时从聊天记录里的城市词和「异地」字样推断
• 异地时：不自动承诺见面/送东西，涉及见面的回复必须人工确认

━━━ 三、回复对象 ━━━
• 点「↻ 刷新列表」读取微信会话，下拉选择要回复的对象
• 切换对象自动保存，重启不丢；监控运行中切换即刻生效
• 一次只回复一个对象（防误发设计）

━━━ 四、回复风格（核心功能） ━━━
• 每个对象可以有自己的专属风格档案：
  data/style_profiles/<对象名>.json
• 点「✨ 提取回复风格」：
  1) 自动在 ChatLab 里找同名会话（需要先导入该对象数据）
  2) 分析你在该会话里的说话方式（口头禅、语气、关心方式）
  3) 生成风格档案，之后回复该对象时自动使用
• 没有专属档案的对象用默认风格
• 「查看风格档案」可随时查看当前对象的风格

━━━ 五、回复的判断逻辑 ━━━
1. 触发：只处理目标对象的文本消息（含带文字的表情包）；
   纯表情/图片/语音/文件不触发
2. 信号识别：实则→说真感受；我不行了/哭了→求心疼；
   算了/不吃了→小作求留；嗯/哦→冷淡；王者/奶茶/家庭话题各有应对
3. 主基调：聊天提供情绪价值，不引导花钱——不主动提议
   请客/买东西/点外卖/转账；她撒娇要东西时用言语接住
4. 生成：最近 20 条上下文 + 信号 + 对象风格 + 异地状态
   → DeepSeek 生成 1 条回复
5. 安全：危险信号（威胁/自伤/明确拒绝）不自动发送；
   花钱/见面承诺必须人工确认

━━━ 六、回复风格（核心功能） ━━━
• 每个对象可以有自己的专属风格档案：
  data/style_profiles/<对象名>.json
• 点「✨ 提取回复风格」：
  1) 自动在 ChatLab 里找同名会话（需要先导入该对象数据）
  2) 分析你在该会话里的说话方式（口头禅、语气、关心方式）
  3) 生成风格档案，之后回复该对象时自动使用
• 没有专属档案的对象用默认风格
• 「查看风格档案」可随时查看当前对象的风格

━━━ 七、注意事项 ━━━
• 单实例：重复打开只会激活已有窗口，不会开第二个
• 程序运行期间微信主窗口会停留在目标对象的会话
  （这是「只回复她」的必要代价）
• 鼠标保护：程序操作微信时不会挪动你的鼠标（用完即还）
• 后台运行时请保持微信窗口存在（可最小化，别退出）
• 日志实时显示在下方；崩溃信息写入 crash.log

━━━ 八、风险声明 ━━━
• 本工具通过 UI 自动化模拟操作微信，不注入、不解密、
  不读取聊天数据库
• 自动回复违反微信服务条款，有封号风险；
  程序内置了冷却和频率上限（每小时≤30条），但风险仍在
• 微信升级可能导致功能失效，届时需重新适配
• 请仅用于合法合规的个人场景
"""

        text.insert("1.0", help_text)
        text.configure(state="disabled")

    # ---------- 启动/停止 ----------
    def _start(self):
        if self.running:
            return
        self.running = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._set_status(True, "运行中")
        self._append_log(f"启动监控（模式: {self.mode.get()}）…")
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()

    def _stop(self):
        self.running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._set_status(False, "已停止")
        self._append_log("已停止监控")

    def _worker(self):
        """后台监控线程：轮询微信 → 处理新消息。"""
        from adapters.wechat_wxauto import WeChatAdapter

        state = core.State(ROOT / CONFIG["paths"]["state_file"])
        try:
            adapter = WeChatAdapter(core.CURRENT_TARGET, log=self._thread_log)
            adapter.install_mouse_guard()  # 鼠标操作后光标回位（防鼠标乱跑）
        except Exception as e:
            self.ui_queue.put(("log", f"❌ 连接微信失败: {e}"))
            self.running = False
            self.root.after(0, lambda: (self.btn_start.configure(state="normal"),
                                        self.btn_stop.configure(state="disabled")))
            return

        if not core.switch_to_target(adapter):
            self.ui_queue.put(("log", "⚠ 未在会话列表找到目标，停止"))
            self.running = False
            self.root.after(0, lambda: (self.btn_start.configure(state="normal"),
                                        self.btn_stop.configure(state="disabled")))
            return

        # 首次启动：把窗口已有消息标记为已见（不触发回复旧消息）
        state.seed(adapter.get_all_messages(30))
        self.ui_queue.put(("log", f"已就绪（目标: {core.CURRENT_TARGET}，监听她的新消息）"))

        dry = self.mode.get() == "dry"
        confirm = self.mode.get() == "confirm"
        interval = CONFIG["monitor"]["poll_interval_seconds"]

        # 异地状态检测：配置城市优先；未配置 → 自动分析（规则 → LLM 语境 → 窗口消息兜底）
        try:
            from goutou.approval import (detect_distance, analyze_distance_from_chatlab,
                                         analyze_distance_with_llm)
            loc = CONFIG.get("location", {})
            me_city = loc.get("me", "")
            her_city = loc.get("her", "")
            dist = None
            if me_city or her_city:
                dist = detect_distance([], me_city=me_city, her_city=her_city)
            else:
                # 未配置：自动分析（ChatLab 数据 → 规则；未知 → LLM 语境判断）
                self.ui_queue.put(("log", "未配置城市，正在自动分析异地状态…"))
                dist = analyze_distance_from_chatlab(
                    core.CURRENT_TARGET,
                    cli=CONFIG.get("chatlab", {}).get("cli", "chatlab"),
                    session=CONFIG.get("chatlab", {}).get("session", ""),
                )
                if dist is None or dist == "未知":
                    # 用 ChatLab 样本 + LLM 语境判断
                    try:
                        from goutou.engine import _fetch_chatlab_sample
                        from goutou.config import get_llm_settings
                        sample = _fetch_chatlab_sample(
                            core.CURRENT_TARGET,
                            cli=CONFIG.get("chatlab", {}).get("cli", "chatlab"),
                            session=CONFIG.get("chatlab", {}).get("session", ""),
                        )
                        if sample:
                            llm = get_llm_settings()
                            if llm.get("api_key"):
                                dist = analyze_distance_with_llm(
                                    sample, llm["api_key"], llm["base_url"], llm["model"])
                                self.ui_queue.put(("log", f"LLM 语境分析异地状态: {dist}"))
                    except Exception as e:
                        self.ui_queue.put(("log", f"LLM 异地分析失败: {e}"))
                if dist is None:
                    dist = detect_distance(core.get_history(adapter, 40))
            self.ui_queue.put(("distance", dist))
            self.ui_queue.put(("log", f"异地状态: {dist}"
                               + ("（自动分析，可在设置里填城市更准）" if not (me_city and her_city) else "")))
        except Exception as e:
            self.ui_queue.put(("log", f"异地检测失败: {e}"))

        self.ui_queue.put(("log", f"开始轮询（每 {interval}s）"))
        self._sync_pending(state)

        last_target = core.CURRENT_TARGET
        while self.running:
            # 处理 UI 控制指令（确认发送 / 忽略 / 清空）——任何异常不得杀死 worker
            try:
                while True:
                    item = self.ctrl_queue.get_nowait()
                    cmd = item[0] if len(item) > 0 else None
                    payload = item[1] if len(item) > 1 else None
                    if cmd == "send":
                        # payload: (index, chosen_reply)
                        index, chosen = payload
                        self._do_send_pending(adapter, state, index, chosen)
                    elif cmd == "ignore":
                        self._do_ignore_pending(state, payload)
                    elif cmd == "clear_pending":
                        state.data["pending"] = []
                        state.save()
                        self.ui_queue.put(("log", "待确认列表已清空"))
                        self._sync_pending(state)
            except queue.Empty:
                pass
            except Exception as e:
                self.ui_queue.put(("log", f"⚠ 指令处理异常: {e}"))

            # 目标切换：重建连接，重置消息增量状态（避免把新对象历史消息当新消息）
            if core.CURRENT_TARGET != last_target:
                self.ui_queue.put(("log", f"检测到回复对象切换 → {core.CURRENT_TARGET}，重置连接…"))
                try:
                    adapter = WeChatAdapter(core.CURRENT_TARGET, log=self._thread_log)
                    if not core.switch_to_target(adapter):
                        self.ui_queue.put(("log", "⚠ 新目标不在会话列表，请刷新列表确认名称"))
                    last_target = core.CURRENT_TARGET
                except Exception as e:
                    self.ui_queue.put(("log", f"重建连接失败: {e}"))
            try:
                core.process_new_messages(adapter, state, dry, confirm)
            except Exception as e:
                self.ui_queue.put(("log", f"轮询异常: {e}"))
            self._sync_pending(state)
            for _ in range(int(interval / 0.2)):
                if not self.running:
                    break
                time.sleep(0.2)

    # ---------- 待确认发送（worker 线程执行） ----------
    def _sync_pending(self, state):
        """把 pending 列表同步到 UI。"""
        try:
            items = list(state.data.get("pending", []))
            self.ui_queue.put(("pending_sync", items))
        except Exception:
            pass

    def _do_send_pending(self, adapter, state, index, chosen_reply=None):
        """确认发送：从 pending 取出对应项 → 确保目标会话 → 发送（失败恢复待确认，可重发）。"""
        try:
            pending = state.data.get("pending", [])
            if not (0 <= index < len(pending)):
                self.ui_queue.put(("log", "⚠ 待确认项不存在（可能已被处理）"))
                return
            item = pending[index]
            reply = chosen_reply or str(item.get("reply", ""))
            pending.pop(index)
            state.save()

            if not core.switch_to_target(adapter):
                self.ui_queue.put(("log", "⚠ 确认发送失败：未定位到目标会话"))
                pending.insert(0, item)  # 恢复待确认
                state.save()
                return
            try:
                adapter.send(reply)
                state.note_reply()
                self.ui_queue.put(("log", f"已发送 ✓（人工确认）: {reply[:40]}"))
            except Exception as e:
                # 发送失败：恢复条目到待确认列表（可重新发送）
                pending.insert(0, item)
                state.save()
                self.ui_queue.put(("log", f"⚠ 发送失败，条目已恢复待确认（可重新发送）: {e}"))
        except Exception as e:
            self.ui_queue.put(("log", f"确认发送异常: {e}"))

    def _do_ignore_pending(self, state, index):
        try:
            pending = state.data.get("pending", [])
            if not (0 <= index < len(pending)):
                return
            item = pending.pop(index)
            state.save()
            self.ui_queue.put(("log", f"已忽略: {str(item.get('reply', ''))[:40]}"))
        except Exception as e:
            self.ui_queue.put(("log", f"忽略异常: {e}"))

    # ---------- 风格提取 ----------
    def _extract_style(self):
        target = core.CURRENT_TARGET
        if not messagebox.askyesno("提取回复风格",
                                   f"将从 ChatLab 聊天数据提取「回复 {target} 时」的风格并即时生效，\n"
                                   f"保存为该对象的专属风格档案。需要 1-2 分钟。继续吗？"):
            return
        self.btn_style.configure(state="disabled")
        threading.Thread(target=self._style_worker, args=(target,), daemon=True).start()

    def _style_worker(self, target: str):
        try:
            import style_profile
            self.ui_queue.put(("log", f"拉取「{target}」的聊天数据…（需 ChatLab 已导入该对象会话）"))
            my_msgs = style_profile.fetch_my_messages(60, target_name=target)
            if not my_msgs:
                self.ui_queue.put(("style_fail",
                                   "没有可用聊天样本。请确认：1) ChatLab 已导入该对象的会话 2) 会话名与微信备注一致"))
                return
            self.ui_queue.put(("log", f"提取到 {len(my_msgs)} 条样本，DeepSeek 分析中…"))
            profile = style_profile.extract_profile(my_msgs, model=CONFIG["llm"]["model"])
            path = style_profile.save_profile(profile, target_name=target)
            self.ui_queue.put(("style_done", f"{target} → {path}"))
        except Exception as e:
            self.ui_queue.put(("style_fail", e))

    def _view_style(self):
        import style_profile
        target = core.CURRENT_TARGET
        profile = style_profile.load_profile(target)
        if not profile:
            messagebox.showinfo("风格档案",
                                f"「{target}」还没有专属风格档案，点「提取回复风格」生成。")
            return
        path = style_profile.profile_path_for(target)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            lines = [f"对象: {target} | 生成时间: {data.get('generated_at', '?')}", ""]
            for key, label in [("tone", "整体语气"), ("humor_style", "调侃方式"),
                               ("care_style", "关心表达"), ("catchphrases", "口头禅")]:
                val = profile.get(key)
                if val:
                    lines.append(f"{label}: {val if isinstance(val, str) else '、'.join(val)}")
            features = profile.get("style_features", [])
            if features:
                lines.append("")
                lines.append("风格特征:")
                lines.extend(f"  · {f}" for f in features)
            examples = profile.get("style_examples", [])
            if examples:
                lines.append("")
                lines.append("风格示例:")
                lines.extend(f"  · {e}" for e in examples)
            messagebox.showinfo(f"「{target}」的回复风格档案", "\n".join(lines))
        except Exception as e:
            messagebox.showerror("读取失败", str(e))


def main():
    # 单实例：已有实例时激活其窗口并退出
    if not acquire_single_instance():
        activate_existing_window()
        return
    root = tk.Tk()
    app = GoutouApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
