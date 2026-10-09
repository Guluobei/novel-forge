# -*- coding: utf-8 -*-
"""设定管理：角色卡的登记 / 查询 / 更新 / 全文搜索。

角色卡 = settings/characters/char_NNN_名字.md（ASCII 前缀保证排序）。
文件 = frontmatter（id/name/role/status/relations）+ Markdown 正文（由模板生成骨架，
内容可由 Claude 直接编辑）。世界观 / 势力 / 大纲为 settings/ 下的单文件 Markdown，
Claude 直接创作编辑，不经本模块（setting list 会列出它们供定位）。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import frontmatter as fm
from .models import read_json, safe_write_json
from .project import assets_dir

CHAR_DIR = "settings/characters"
CHAR_INDEX = "settings/characters/_index.json"
SINGLETON_SETTINGS = ["worldview.md", "factions.md", "outline.md"]
META_KEY_ORDER = ["id", "name", "role", "status", "relations"]


class SettingError(RuntimeError):
    """设定操作失败。"""


def _char_dir(project: Path) -> Path:
    d = project / CHAR_DIR
    if not d.is_dir():
        raise SettingError("项目缺少 settings/characters/，请确认项目完整性")
    return d


def _sanitize(name: str) -> str:
    """文件名安全化：去除路径分隔符与空白。"""
    return re.sub(r"[/\\:*?\"<>|\s]+", "_", name.strip())


def _char_dir_char_files(d: Path) -> list[Path]:
    return [p for p in d.glob("char_*.md")]


def add_character(project: Path, name: str, role: str = "配角") -> dict:
    """登记角色卡：复制模板 + 分配 id + 更新索引。"""
    if not name.strip():
        raise SettingError("角色名不能为空")
    existing = find_by_name(project, name)
    if existing:
        raise SettingError(f"角色 {name!r} 已存在：{existing['file']}")
    d = _char_dir(project)
    nums = []
    for p in _char_dir_char_files(d):
        m = re.match(r"char_(\d+)_", p.name)
        if m:
            nums.append(int(m.group(1)))
    seq = max(nums, default=0) + 1
    fid = f"char_{seq:03d}"
    fname = f"{fid}_{_sanitize(name)}.md"
    dest = d / fname
    tpl = assets_dir() / "character.template.md"
    text = tpl.read_text(encoding="utf-8") if tpl.exists() else "## 基本档案\n"
    # 替换模板占位符（模板正文不含 frontmatter，meta 由本函数写入）
    text = text.replace("{{name}}", name.strip()).replace("{{role}}", role)
    meta = {"id": fid, "name": name.strip(), "role": role, "status": "active", "relations": ""}
    body = text
    fm.write_file(dest, meta, body, key_order=META_KEY_ORDER)
    _upsert_index(project, fid, name, role, fname)
    return {"id": fid, "name": name.strip(), "role": role, "file": fname, "path": str(dest)}


def _upsert_index(project: Path, fid: str, name: str, role: str, fname: str,
                  remove: bool = False) -> None:
    idx_path = project / CHAR_INDEX
    idx = read_json(idx_path, default={"characters": []})
    idx.setdefault("characters", [])
    idx["characters"] = [c for c in idx["characters"] if c.get("id") != fid]
    if not remove:
        idx["characters"].append({"id": fid, "name": name, "role": role, "file": fname})
    safe_write_json(idx_path, idx)


def scan_characters(project: Path) -> list[dict]:
    """实时扫描角色目录（_index.json 仅作加速缓存，扫描为准）。"""
    d = _char_dir(project)
    out: list[dict] = []
    for p in sorted(_char_dir_char_files(d)):
        try:
            meta, _ = fm.read_file(p)
        except Exception:
            continue
        out.append({
            "id": meta.get("id", p.name),
            "name": meta.get("name", ""),
            "role": meta.get("role", ""),
            "status": meta.get("status", ""),
            "relations": meta.get("relations", ""),
            "file": p.name,
        })
    return out


def find_by_name(project: Path, name: str) -> dict | None:
    for c in scan_characters(project):
        if c["name"] == name or c["file"] == name:
            return c
    return None


def list_settings(project: Path, type_: str | None = None) -> dict:
    """列出设定：characters（角色卡）+ singletons（世界观/势力/大纲等单文件）。"""
    chars = scan_characters(project)
    singletons = []
    sdir = project / "settings"
    for fname in SINGLETON_SETTINGS:
        p = sdir / fname
        singletons.append({"file": fname, "exists": p.is_file(),
                           "size": p.stat().st_size if p.is_file() else 0})
    out: dict = {"characters": chars, "singletons": singletons}
    if type_ == "character":
        return {"characters": chars}
    if type_ in ("worldview", "factions", "outline"):
        return {"singletons": [s for s in singletons if s["file"].startswith(type_)]}
    return out


def get_character(project: Path, name: str) -> dict:
    c = find_by_name(project, name)
    if not c:
        raise SettingError(f"角色 {name!r} 不存在")
    path = _char_dir(project) / c["file"]
    meta, body = fm.read_file(path)
    return {"file": c["file"], "path": str(path), "meta": meta, "body": body}


def update_character(project: Path, name: str, sets: list[tuple[str, str]]) -> dict:
    """更新角色卡 frontmatter 字段，如 status=dead / role=主角。"""
    c = find_by_name(project, name)
    if not c:
        raise SettingError(f"角色 {name!r} 不存在")
    path = _char_dir(project) / c["file"]
    meta, body = fm.read_file(path)
    for k, v in sets:
        meta[k] = v
    fm.write_file(path, meta, body, key_order=META_KEY_ORDER)
    if any(k in ("name", "role") for k, _ in sets):
        _upsert_index(project, meta.get("id", c["id"]), meta.get("name", c["name"]),
                      meta.get("role", c["role"]), c["file"])
    return {"file": c["file"], "updated": {k: v for k, v in sets}}


def search_settings(project: Path, keyword: str) -> list[dict]:
    """在 settings/ 全目录（含角色卡与世界观等）做全文搜索，返回命中文件与行摘录。"""
    kw = keyword.strip()
    if not kw:
        raise SettingError("搜索关键词不能为空")
    hits: list[dict] = []
    sdir = project / "settings"
    for p in sorted(sdir.rglob("*.md")):
        try:
            lines = p.read_text(encoding="utf-8").split("\n")
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if kw in line:
                rel = str(p.relative_to(project))
                hits.append({"file": rel, "line": i, "excerpt": line.strip()[:80]})
    return hits
