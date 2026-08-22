# -*- coding: utf-8 -*-
"""统一错误类型与重试策略。"""


class JunshiError(Exception):
    """基础异常。"""

    retryable = False


class ProviderError(JunshiError):
    """LLM 调用失败（网络/HTTP/解析）。"""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status
        # 网络类错误可重试；4xx（除 429）不重试
        self.retryable = status is None or status == 429 or status >= 500


class AdapterError(JunshiError):
    """平台适配层错误（微信 UI 自动化失败等）。"""


class ApprovalRequired(JunshiError):
    """Turn 需要人工审批（内部控制流）。"""
