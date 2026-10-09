# -*- coding: utf-8 -*-
"""项目发现与初始化。

项目根 = book.json 所在目录。所有需要项目的命令支持：
1. 显式 --project 参数；
2. 否则从当前工作目录向上逐级查找 book.json。
"""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from .models import read_json, safe_write_json

BOOK_FILE = "book.json"
STATE_FILE = "state.json"
FORESHADOW_FILE = "foreshadow.json"
# 章节标题行：兼容「# 第3章」「第 3 章」「第003章」（允许 # 前缀）
CHAPTER_TITLE_RE = re.compile(r"^\s*#*\s*第\s*0*(\d+)\s*章")

DEFAULT_THRESHOLDS = {
    "min_words": 3000,
    "max_dash": 12,
    "max_warn": 3,
    "max_emotion_naming": 2,
    "bare_tag_max_ratio": 0.3,
}

HOOK_TYPES = ["危机", "悬疑", "反转", "信息", "情感", "时间", "选择", "生存"]


class ProjectNotFound(RuntimeError):
    """从当前目录向上未找到 book.json。"""


def skill_root() -> Path:
    """技能根目录（novel_lib 的上上级）。"""
    return Path(__file__).resolve().parent.parent.parent


def assets_dir() -> Path:
    return skill_root() / "assets"


def find_project(start: str | Path | None = None) -> Path:
    """从 start（默认 cwd）向上查找 book.json，返回项目根；找不到抛异常。"""
    cur = Path(start).resolve() if start else Path.cwd()
    if cur.is_file():
        cur = cur.parent
    while True:
        if (cur / BOOK_FILE).is_file():
            return cur
        parent = cur.parent
        if parent == cur:
            raise ProjectNotFound(f"未找到 {BOOK_FILE}：请 --project 指定项目路径，或在项目目录内运行")
        cur = parent


def now_iso() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def load_book(project: Path) -> dict:
    book = read_json(project / BOOK_FILE, default=None)
    if not isinstance(book, dict):
        raise ProjectNotFound(f"{project / BOOK_FILE} 缺失或格式错误")
    return book


def gate_thresholds(book: dict) -> dict:
    """合并默认阈值与 book.json 中的覆盖项。"""
    override = (book.get("gate") or {}).get("thresholds") or {}
    out = dict(DEFAULT_THRESHOLDS)
    out.update({k: v for k, v in override.items() if v is not None})
    return out


def init(path: str | Path, name: str, genre: str = "", author: str = "",
         target_chapters: int = 300, words_per_chapter: int = 3000) -> dict:
    """初始化小说项目骨架，返回创建结果摘要。"""
    root = Path(path).expanduser().resolve()
    if (root / BOOK_FILE).exists():
        raise FileExistsError(f"项目已存在：{root / BOOK_FILE}")

    # 目录骨架
    for d in ("settings/characters", "chapters", "reports", "trash", "outline"):
        (root / d).mkdir(parents=True, exist_ok=True)

    # book.json
    book = {
        "name": name,
        "author": author,
        "genre": genre,
        "target": {"total_chapters": target_chapters, "words_per_chapter": words_per_chapter},
        "schema_version": 1,
        "gate": {"thresholds": dict(DEFAULT_THRESHOLDS), "lexicon_override": {}},
        "ai": {
            "enabled": False,
            "provider": "null",
            "base_url": "",
            "model": "",
            "api_key_env": "NOVEL_FORGE_API_KEY",
            "features": {"continue": False, "polish": False},
        },
    }
    safe_write_json(root / BOOK_FILE, book)

    # state.json
    safe_write_json(root / STATE_FILE, {
        "next_chapter_number": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })

    # 伏笔登记册
    safe_write_json(root / FORESHADOW_FILE, {"warn_after_overdue": 3, "items": []})

    # 设定模板（从 assets 复制）
    _copy_template("worldview.template.md", root / "settings" / "worldview.md", name=name)
    _copy_template("factions.template.md", root / "settings" / "factions.md", name=name)
    _copy_template("outline.template.md", root / "settings" / "outline.md", name=name)
    _copy_template("volumes.template.md", root / "outline" / "volumes.md", name=name)

    # 角色索引
    safe_write_json(root / "settings" / "characters" / "_index.json", {"characters": []})

    return {
        "project_root": str(root),
        "name": name,
        "created": [
            "book.json", "state.json", "foreshadow.json",
            "settings/worldview.md", "settings/factions.md", "settings/outline.md",
            "settings/characters/_index.json", "outline/volumes.md",
            "chapters/", "reports/", "trash/",
        ],
    }


def _copy_template(template_name: str, dest: Path, **ctx: str) -> None:
    """从 assets 复制模板并替换 {{name}} 占位符。"""
    src = assets_dir() / template_name
    if src.exists():
        text = src.read_text(encoding="utf-8")
        for k, v in ctx.items():
            text = text.replace("{{" + k + "}}", v)
        dest.write_text(text, encoding="utf-8")
    else:
        dest.write_text(f"# {{{ctx.get('name', '')}}}\n", encoding="utf-8")


def project_info(project: Path) -> dict:
    """汇总项目概览：书籍信息 + 章节统计 + 伏笔状态（字数实时重算）。"""
    from .chapter import scan_chapters  # 延迟导入避免循环依赖
    from .foreshadow import load_foreshadow

    book = load_book(project)
    chapters = scan_chapters(project)
    fore = load_foreshadow(project)
    total_words = sum(c["words"] for c in chapters)
    written = [c for c in chapters if not c.get("unwritten")]
    unwritten = [c for c in chapters if c.get("unwritten")]
    target = book.get("target") or {}
    done = [c for c in chapters if c.get("status") == "done"]
    fw_exists = (project / "framework.json").is_file()
    return {
        "project_root": str(project),
        "name": book.get("name", ""),
        "author": book.get("author", ""),
        "genre": book.get("genre", ""),
        "target": target,
        "chapters": {
            "total": len(chapters),
            "written": len(written),
            "unwritten": len(unwritten),
            "done": len(done),
            "draft": len(chapters) - len(done),
            "total_words": total_words,
            "avg_words": round(total_words / len(written), 1) if written else 0,
        },
        "framework": {"established": fw_exists},
        "foreshadow": {
            "total": len(fore.get("items", [])),
            "planted": sum(1 for i in fore.get("items", []) if i.get("status") == "planted"),
            "recovered": sum(1 for i in fore.get("items", []) if i.get("status") == "recovered"),
        },
        "ai": book.get("ai", {}),
    }


def touch_state(project: Path) -> None:
    """更新 state.json 的 updated_at 时间戳。"""
    state_path = project / STATE_FILE
    state = read_json(state_path, default={})
    state["updated_at"] = now_iso()
    try:
        safe_write_json(state_path, state)
    except Exception:
        pass  # 时间戳更新失败不阻塞主流程
