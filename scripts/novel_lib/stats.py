# -*- coding: utf-8 -*-
"""全书统计与进度追踪。"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .chapter import scan_chapters
from .models import read_json


def overall_stats(project: Path) -> dict:
    """全书统计：总章数 / 总字数 / 平均字数 / 最长最短章 / 最近更新。"""
    chapters = scan_chapters(project)
    total = sum(c["words"] for c in chapters)
    by_status: dict[str, int] = {}
    for c in chapters:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1
    shortest = min(chapters, key=lambda c: c["words"], default=None)
    longest = max(chapters, key=lambda c: c["words"], default=None)
    return {
        "total_chapters": len(chapters),
        "total_words": total,
        "avg_words": round(total / len(chapters), 1) if chapters else 0,
        "by_status": by_status,
        "shortest": {"no": shortest["no"], "words": shortest["words"]} if shortest else None,
        "longest": {"no": longest["no"], "words": longest["words"]} if longest else None,
        "latest_updated": max((c["updated_at"] for c in chapters), default=""),
    }


def progress(project: Path) -> dict:
    """写作进度：对照 book.json 的 target（总章数 / 每章字数）。"""
    book = read_json(project / "book.json", default={})
    target = book.get("target") or {}
    total_ch = int(target.get("total_chapters") or 0)
    wpc = int(target.get("words_per_chapter") or 0)
    chapters = scan_chapters(project)
    total_words = sum(c["words"] for c in chapters)
    done_words = sum(c["words"] for c in chapters if c["status"] == "done")
    out = {
        "target": {"total_chapters": total_ch, "words_per_chapter": wpc},
        "current": {"chapters": len(chapters), "words": total_words,
                    "done_chapters": sum(1 for c in chapters if c["status"] == "done"),
                    "done_words": done_words},
    }
    if total_ch > 0:
        out["chapter_progress_pct"] = round(len(chapters) / total_ch * 100, 1)
    if total_ch > 0 and wpc > 0:
        out["word_progress_pct"] = round(total_words / (total_ch * wpc) * 100, 1)
    return out


def daily_words(project: Path, days: int = 7) -> dict:
    """近 N 天日产出（依据章节 frontmatter updated_at 与 words 估算）。"""
    chapters = scan_chapters(project)
    buckets: dict[str, int] = {}
    today = _dt.date.today()
    for c in chapters:
        ts = c.get("updated_at") or ""
        try:
            d = _dt.date.fromisoformat(ts.split("T")[0])
        except (ValueError, IndexError):
            continue
        if (today - d).days > days:
            continue
        key = d.isoformat()
        buckets[key] = buckets.get(key, 0) + c["words"]
    series = []
    for i in range(days - 1, -1, -1):
        d = (today - _dt.timedelta(days=i)).isoformat()
        series.append({"date": d, "words": buckets.get(d, 0)})
    return {"days": days, "series": series}
