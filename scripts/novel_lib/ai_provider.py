# -*- coding: utf-8 -*-
"""AI 能力预留：Provider 抽象 + NullProvider 空实现。

v1 为纯工具版：仅注册 NullProvider，is_available() 恒 False。
未来接入 OpenAI 兼容 API 时，新增一个 Provider 实现文件并在
get_provider 的注册表中登记即可；book.json 的 ai 段与现有命令零改动。

book.json 的 ai 段约定（init 时已生成）：
    "ai": {
        "enabled": false,
        "provider": "null",
        "base_url": "",
        "model": "",
        "api_key_env": "NOVEL_FORGE_API_KEY",
        "features": {"continue": false, "polish": false}
    }
"""
from __future__ import annotations

from typing import Protocol

from .models import read_json
from .project import ProjectNotFound


class AINotEnabled(RuntimeError):
    """AI 功能未启用。"""


class AIProvider(Protocol):
    """AI 能力接口约定。"""

    name: str

    def is_available(self) -> bool: ...

    def continue_writing(self, context: str, instruction: str) -> str: ...

    def polish(self, text: str, instruction: str) -> str: ...


class NullProvider:
    """空实现：任何调用都给出明确指引，绝不静默失败。"""

    name = "null"

    def is_available(self) -> bool:
        return False

    def continue_writing(self, context: str, instruction: str) -> str:
        raise AINotEnabled(_hint("续写"))

    def polish(self, text: str, instruction: str) -> str:
        raise AINotEnabled(_hint("润色"))


def _hint(feature: str) -> str:
    return (f"AI {feature}功能未启用：novel-forge v1 为纯工具版，所有检查与管理功能"
            f"不依赖 AI。接入方法见技能目录 references/data-format.md 的「AI 配置」一节。")


def get_provider(project) -> AIProvider:
    """根据 book.json 的 ai.provider 返回 Provider 实例。

    v1 注册表只有 "null"；未来在此登记新 provider。
    """
    ai_cfg = read_json(project / "book.json", default={}).get("ai") or {}
    name = str(ai_cfg.get("provider") or "null")
    registry = {"null": NullProvider}
    cls = registry.get(name)
    if cls is None:
        raise ProjectNotFound(f"未知 AI provider：{name!r}（可用：{'/'.join(registry)}）")
    return cls()  # type: ignore[return-value]


def ai_status(project) -> dict:
    """报告 AI 配置状态。"""
    cfg = read_json(project / "book.json", default={}).get("ai") or {}
    provider = get_provider(project)
    return {
        "enabled": bool(cfg.get("enabled")),
        "provider": provider.name,
        "available": provider.is_available(),
        "model": cfg.get("model", ""),
        "base_url": cfg.get("base_url", ""),
        "api_key_env": cfg.get("api_key_env", "NOVEL_FORGE_API_KEY"),
        "features": cfg.get("features") or {"continue": False, "polish": False},
        "note": "v1 纯工具版：AI 功能预留接口，尚未实现。"
                "续写/润色请直接在对话中让 Claude 完成（Claude 本身即创作引擎）。",
    }
