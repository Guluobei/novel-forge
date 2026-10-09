# -*- coding: utf-8 -*-
"""三级词表（ban / warn / limit）加载与合并。

合并顺序：assets/lexicon.default.json（内置默认）
       → book.json 的 gate.lexicon_override（项目级 add/remove 覆盖）
       → 最终生效词表。

override 结构示例（book.json 内）：
    "lexicon_override": {
        "ban":  {"add": ["瞳孔骤缩"], "remove": ["然而"]},
        "warn": {"add": ["闻言"], "remove": []},
        "limit": {"add": [{"pattern": "皎洁", "max": 1}], "remove": []}
    }
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from .models import read_json
from .project import assets_dir, load_book

DEFAULT_LEXICON = {
    "ban": [
        "不禁", "与此同时", "内心深处", "缓缓说道", "命运的齿轮", "宿命感",
        "忍不住", "下意识地", "不由自主地", "众所周知", "不言而喻", "无声地",
    ],
    "ban_regex": [
        r"一股.{0,6}涌上心头",
        r"空气[中里]弥漫着",
    ],
    "warn": [
        "深吸一口气", "时间来到了", "另一边", "仿佛", "似乎", "片刻后", "闻言",
    ],
    "limit": [
        {"pattern": "嘴角勾起", "max": 2},
        {"pattern": "眸中闪过", "max": 2},
        {"pattern": "眼底闪过", "max": 2},
        {"pattern": "心跳加速", "max": 2},
        {"pattern": "咬了咬牙", "max": 2},
    ],
}


class LexiconError(RuntimeError):
    """词表配置错误。"""


def load_lexicon(project: Path) -> dict:
    """加载并合并词表，返回 {ban, ban_regex, warn, limit}。"""
    # 内置默认：assets 优先，代码内兜底
    lex: dict = copy.deepcopy(DEFAULT_LEXICON)
    asset_file = assets_dir() / "lexicon.default.json"
    if asset_file.is_file():
        try:
            lex_data = read_json(asset_file, default=None)
            if isinstance(lex_data, dict):
                for key in ("ban", "ban_regex", "warn"):
                    if isinstance(lex_data.get(key), list):
                        lex[key] = list(lex_data[key])
                if isinstance(lex_data.get("limit"), list):
                    lex["limit"] = list(lex_data["limit"])
        except Exception:
            pass  # 资产损坏时回退内置

    # 项目级覆盖
    book = load_book(project)
    override = (book.get("gate") or {}).get("lexicon_override") or {}
    for key in ("ban", "warn", "ban_regex"):
        ov = override.get(key)
        if not isinstance(ov, dict):
            continue
        lex[key] = _apply_add_remove(lex[key], ov, key)
    ov_limit = override.get("limit")
    if isinstance(ov_limit, dict):
        removes = set(ov_limit.get("remove") or [])
        adds = [x for x in (ov_limit.get("add") or []) if _valid_limit(x)]
        lex["limit"] = [l for l in lex["limit"] if l.get("pattern") not in removes] + adds
    _validate(lex)
    return lex


def _apply_add_remove(current: list, ov: dict, key: str) -> list:
    out = list(current)
    for w in (ov.get("add") or []):
        if isinstance(w, str) and w and w not in out:
            out.append(w)
    removes = set(ov.get("remove") or [])
    out = [w for w in out if w not in removes]
    return out


def _valid_limit(x) -> bool:
    return isinstance(x, dict) and isinstance(x.get("pattern"), str) and x["pattern"]


def _validate(lex: dict) -> None:
    """验证正则可编译、limit 条目合法。"""
    for key in ("ban_regex",):
        for pat in lex.get(key, []):
            try:
                re.compile(pat)
            except re.error as e:
                raise LexiconError(f"词表 {key} 正则非法 {pat!r}: {e}") from e
    for l in lex.get("limit", []):
        if not _valid_limit(l):
            raise LexiconError(f"limit 条目非法：{l!r}（需要 pattern/max）")
        try:
            int(l.get("max", 0))
        except (TypeError, ValueError):
            raise LexiconError(f"limit 条目 max 非整数：{l!r}")


def build_patterns(lex: dict) -> dict:
    """把词表编译为 {level: [(pattern_or_str, compiled_regex, kind), ...]}。

    kind: "literal" 或 "regex"。
    """
    out = {"ban": [], "warn": []}
    for w in lex.get("ban", []):
        out["ban"].append((w, re.compile(re.escape(w)), "literal"))
    for pat in lex.get("ban_regex", []):
        out["ban"].append((pat, re.compile(pat), "regex"))
    for w in lex.get("warn", []):
        out["warn"].append((w, re.compile(re.escape(w)), "literal"))
    limits = []
    for l in lex.get("limit", []):
        compiled = re.compile(l["pattern"])
        limits.append({"pattern": l["pattern"], "regex": compiled, "max": int(l.get("max", 1))})
    out["limit"] = limits
    return out
