"""LLM 工厂（BACKEND.md 第 2 章 / 16.7）。

DeepSeek 走 OpenAI 兼容层：ChatOpenAI(base_url="https://api.deepseek.com")。
DeepSeek 没有独立 LangChain 包，兼容层最省事。
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import settings

logger = logging.getLogger("tpa.agent.llm")

LLM_TIMEOUT_SECONDS = 60.0


def _assert_supports_tools(model: str) -> None:
    """deepseek-reasoner 不支持 function calling，而本项目核心就是工具调用。"""
    if "reasoner" in (model or "").lower():
        raise RuntimeError(
            "TPA_LLM_MODEL 不可使用 deepseek-reasoner（不支持 function calling），"
            "请改为 deepseek-chat。"
        )


class LLMFactory:
    """统一出口，方便换模型 / 换服务商。"""

    @staticmethod
    def create(*, streaming: bool = True, temperature: float | None = None) -> Any:
        from langchain_openai import ChatOpenAI

        _assert_supports_tools(settings.llm_model)
        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=(
                settings.llm_temperature if temperature is None else temperature
            ),
            streaming=streaming,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=0,  # 重试由我们自己控制（16.9）
        )

    @staticmethod
    def create_for_title() -> Any:
        """会话标题生成：一次小调用，temperature=0。"""
        return LLMFactory.create(streaming=False, temperature=0.0)
