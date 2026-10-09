# -*- coding: utf-8 -*-
"""伏笔登记册：登记 / 追踪 / 回收 / 预警。

登记规则（继承 cn-novel-craft 伏笔登记册）：
- 每埋一个伏笔必须登记：描述 + 埋入章 + 预期回收章
- 当前最新章号 >= 预期回收章 且未回收 → 预警 overdue
- 超期超过 warn_after_overdue 章 → 升级 severe
- 插章/重编号时章号自动联动（由 chapter.insert_chapter 调用 shift_chapters）
"""
from __future__ import annotations

from pathlib import Path

from .models import read_json, safe_write_json
from .project import FORESHADOW_FILE

PRIORITIES = ["main", "sub", "minor"]


class ForeshadowError(RuntimeError):
    """伏笔操作失败。"""


def load_foreshadow(project: Path) -> dict:
    data = read_json(project / FORESHADOW_FILE, default=None)
    if not isinstance(data, dict):
        raise ForeshadowError(f"{project / FORESHADOW_FILE} 缺失或格式错误")
    data.setdefault("warn_after_overdue", 3)
    data.setdefault("items", [])
    return data


def _save(project: Path, data: dict) -> None:
    safe_write_json(project / FORESHADOW_FILE, data)


def _next_id(items: list[dict]) -> str:
    nums = []
    for it in items:
        fid = str(it.get("id", ""))
        if fid.startswith("F-"):
            try:
                nums.append(int(fid[2:]))
            except ValueError:
                pass
    return f"F-{max(nums, default=0) + 1:03d}"


def add(project: Path, desc: str, planted_chapter: int, expected_recover: int,
        priority: str = "main") -> dict:
    """登记一条伏笔。"""
    if priority not in PRIORITIES:
        raise ForeshadowError(f"非法优先级 {priority!r}，可选：{'/'.join(PRIORITIES)}")
    if expected_recover < planted_chapter:
        raise ForeshadowError("预期回收章不能早于埋入章")
    data = load_foreshadow(project)
    item = {
        "id": _next_id(data["items"]),
        "desc": desc,
        "planted_chapter": planted_chapter,
        "expected_recover_chapter": expected_recover,
        "recovered_chapter": None,
        "status": "planted",
        "priority": priority,
    }
    data["items"].append(item)
    _save(project, data)
    return item


def list_items(project: Path, status: str | None = None) -> list[dict]:
    """列出伏笔；status 可选 planted/recovered/overdue/severe（overdue/severe 动态计算）。"""
    data = load_foreshadow(project)
    if status in (None, "planted", "recovered"):
        return [i for i in data["items"] if not status or i.get("status") == status]
    audited = audit(project)
    if status == "overdue":
        return [a["item"] for a in audited["alerts"] if a["level"] in ("overdue", "severe")]
    if status == "severe":
        return [a["item"] for a in audited["alerts"] if a["level"] == "severe"]
    raise ForeshadowError(f"非法过滤条件 {status!r}")


def recover(project: Path, fid: str, chapter: int) -> dict:
    """标记伏笔已回收。"""
    data = load_foreshadow(project)
    for it in data["items"]:
        if str(it.get("id")) == fid:
            it["status"] = "recovered"
            it["recovered_chapter"] = chapter
            _save(project, data)
            return it
    raise ForeshadowError(f"伏笔 {fid} 不存在")


def current_chapter_no(project: Path) -> int:
    """当前最新章号（以章节目录为准；无章节视为第 0 章）。"""
    from .chapter import max_chapter_no
    return max_chapter_no(project)


def audit(project: Path) -> dict:
    """伏笔预警检查：到期未回收 → overdue；超期超过阈值 → severe。"""
    data = load_foreshadow(project)
    warn_after = int(data.get("warn_after_overdue", 3))
    cur = current_chapter_no(project)
    alerts: list[dict] = []
    for it in data["items"]:
        if it.get("status") != "planted":
            continue
        expected = it.get("expected_recover_chapter")
        if expected is None:
            continue
        if cur >= expected:
            overdue_by = cur - expected
            level = "severe" if overdue_by > warn_after else "overdue"
            alerts.append({
                "level": level,
                "overdue_by": overdue_by,
                "item": it,
                "message": (f"伏笔 {it['id']}（第 {it['planted_chapter']} 章埋入）"
                            f"预期第 {expected} 章回收，当前已写到第 {cur} 章，"
                            f"超期 {overdue_by} 章"
                            + ("，严重超期！" if level == "severe" else "，请安排回收")),
            })
    return {
        "current_chapter": cur,
        "warn_after_overdue": warn_after,
        "total_planted": sum(1 for i in data["items"] if i.get("status") == "planted"),
        "total_recovered": sum(1 for i in data["items"] if i.get("status") == "recovered"),
        "alerts": alerts,
        "ok": not alerts,
    }


def shift_chapters(project: Path, from_chapter: int, delta: int) -> dict:
    """插章/删章联动：所有 >= from_chapter 的章号字段统一 +delta。"""
    data = load_foreshadow(project)
    changed = 0
    for it in data["items"]:
        for key in ("planted_chapter", "expected_recover_chapter", "recovered_chapter"):
            v = it.get(key)
            if isinstance(v, int) and v >= from_chapter:
                it[key] = v + delta
                changed += 1
    _save(project, data)
    return {"from_chapter": from_chapter, "delta": delta, "fields_changed": changed}
