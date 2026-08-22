# -*- coding: utf-8 -*-
"""LLMProvider 抽象：chat / structured_output。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], temperature: float = 0.85,
             max_tokens: int = 300, timeout: int = 30) -> str:
        """单轮补全，返回文本。"""


class ProviderRegistry:
    """按名字注册/获取 provider（多模型 fallback 预留）。"""

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> LLMProvider | None:
        return self._providers.get(name)

    def primary(self) -> LLMProvider:
        if not self._providers:
            raise RuntimeError("未注册任何 LLM Provider")
        return next(iter(self._providers.values()))
