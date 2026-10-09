# -*- coding: utf-8 -*-
"""写作进度可视化：零依赖的终端图表。

设计约束：
- 不引入任何外部绘图库（matplotlib 等），纯文本字符渲染；
- 图表默认宽度 48 列，可在窄终端安全显示；
- 颜色交给调用方决定（本模块只返回纯文本 / 结构化数据）。

提供三类图：
1. bar_progress        单条进度条（全书 / 单卷完成度）
2. bar_series          横向条形序列（近 N 天日产出）
3. bucket_distribution 分布直方图（章节字数分布）
"""
from __future__ import annotations

from pathlib import Path

from .chapter import scan_chapters
from .framework import load as load_framework
from .models import read_json

FULL = "█"
HALF = "▌"
EMPTY = "░"
DEFAULT_WIDTH = 48


def bar_progress(done: float, total: float, width: int = DEFAULT_WIDTH,
                 label: str = "", label_pad: int = 0) -> str:
    """单条进度条。done/total 可为 0，返回纯文本（不含颜色）。"""
    total = total or 0
    ratio = 0.0 if total <= 0 else max(0.0, min(1.0, done / total))
    filled = ratio * width
    full_n = int(filled)
    has_half = (filled - full_n) >= 0.5
    bar = FULL * full_n + (HALF if has_half else "") + EMPTY * (width - full_n - (1 if has_half else 0))
    pct = f"{ratio * 100:5.1f}%"
    if label:
        # 中文按 2 列宽估算，保证多行标签左对齐
        pad = max(0, label_pad - _disp_width(label))
        return f"{label}{' ' * pad} {bar} {pct}"
    return f"{bar} {pct}"


def _disp_width(s: str) -> int:
    """估算显示宽度：CJK 记 2 列。"""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in s)


def bar_series(series: list[dict], key: str = "words", label_key: str = "date",
               width: int = DEFAULT_WIDTH) -> list[str]:
    """横向条形序列：系列第一项映射到满宽，其余按比例。
    返回逐行文本列表（含标签与数值）。"""
    if not series:
        return []
    peak = max((int(s.get(key) or 0) for s in series), default=0) or 1
    out: list[str] = []
    for s in series:
        v = int(s.get(key) or 0)
        n = int(round(v / peak * width))
        bar = FULL * n if v > 0 else ""
        label = str(s.get(label_key, ""))[-5:]  # MM-DD
        out.append(f"{label} |{bar:<{width}}| {v}")
    return out


def bucket_distribution(values: list[int], width: int = DEFAULT_WIDTH,
                        bins: int = 5) -> list[str]:
    """数值分布直方图（等宽分箱）。"""
    vals = [v for v in values if v is not None]
    if not vals:
        return ["（暂无数据）"]
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return [f"{lo:>6} |{FULL * width}| {len(vals)} 章"]
    step = (hi - lo) / bins
    counts = [0] * bins
    for v in vals:
        idx = min(bins - 1, int((v - lo) / step))
        counts[idx] += 1
    peak = max(counts) or 1
    out: list[str] = []
    for i, c in enumerate(counts):
        a = int(lo + step * i)
        b = int(lo + step * (i + 1))
        n = int(round(c / peak * width))
        out.append(f"{a:>5}-{b:<5} |{FULL * n:<{width}}| {c} 章")
    return out


def volume_progress(project: Path) -> list[dict]:
    """按框架登记的卷，计算每卷完成度（按章号区间与已写章数）。"""
    fw = load_framework(project)
    volumes = ((fw.get("structure") or {}).get("volumes") or [])
    if not volumes:
        return []
    chapters = scan_chapters(project)
    written = {c["no"] for c in chapters if not c.get("unwritten")}
    out: list[dict] = []
    for v in volumes:
        rng = str(v.get("chapters") or "")
        try:
            a, b = (int(x.strip()) for x in rng.split("-")[:2])
        except (ValueError, IndexError):
            continue
        span = max(1, b - a + 1)
        done = sum(1 for n in range(a, b + 1) if n in written)
        out.append({
            "name": v.get("name") or rng,
            "range": rng, "start": a, "end": b,
            "planned": span, "written": done,
            "pct": round(done / span * 100, 1),
            "goal": v.get("goal") or "",
        })
    return out


def chapter_word_series(project: Path) -> list[dict]:
    """逐章字数序列（跳过未创作章）。"""
    return [{"no": c["no"], "words": c["words"], "title": c.get("title") or ""}
            for c in scan_chapters(project) if not c.get("unwritten")]


def build_dashboard(project: Path, days: int = 7) -> dict:
    """汇总看板数据（供 render_dashboard 渲染，也可 JSON 输出）。"""
    from .stats import overall_stats, progress, daily_words
    stats = overall_stats(project)
    prog = progress(project)
    dash: dict = {
        "progress": prog,
        "stats": {
            "total_chapters": stats["total_chapters"],
            "total_words": stats["total_words"],
            "avg_words": stats["avg_words"],
            "by_status": stats["by_status"],
        },
        "volumes": volume_progress(project),
        "daily": daily_words(project, days)["series"] if days else [],
        "distribution": [c["words"] for c in chapter_word_series(project)],
    }
    book = read_json(project / "book.json", default={})
    dash["book"] = {"name": book.get("name", ""), "genre": (book.get("meta") or {}).get("genre", "")}
    return dash


def render_dashboard(dash: dict, width: int = DEFAULT_WIDTH, show_daily: bool = True,
                     show_volumes: bool = True, show_dist: bool = True) -> str:
    """把看板渲染为终端友好文本。"""
    book = dash.get("book") or {}
    prog = dash.get("progress") or {}
    cur = prog.get("current") or {}
    tgt = prog.get("target") or {}
    lines: list[str] = []
    title = book.get("name") or "未命名"
    if book.get("genre"):
        title += f"（{book['genre']}）"
    lines.append("═" * width)
    lines.append(f"  {title}  写作进度看板")
    lines.append("═" * width)
    lines.append("")

    # 全书章节进度
    total_ch = tgt.get("total_chapters") or 0
    if total_ch:
        lines.append(bar_progress(cur.get("chapters", 0), total_ch, width,
                                  label=f"章节 {cur.get('chapters', 0)}/{total_ch}", label_pad=16))
        total_w = total_ch * (tgt.get("words_per_chapter") or 0)
        if total_w:
            lines.append(bar_progress(cur.get("words", 0), total_w, width,
                                      label=f"字数 {cur.get('words', 0)}/{total_w}", label_pad=16))
    else:
        lines.append(f"章节 {cur.get('chapters', 0)} 章 / 字数 {cur.get('words', 0)}")
    st = dash.get("stats") or {}
    lines.append(f"  平均每章 {st.get('avg_words', 0)} 字")
    by = st.get("by_status") or {}
    if by:
        lines.append("  状态：" + "  ".join(f"{k}×{v}" for k, v in sorted(by.items())))
    lines.append("")

    # 分卷进度
    if show_volumes and dash.get("volumes"):
        lines.append("── 分卷进度 ──")
        for v in dash["volumes"]:
            lines.append(bar_progress(v["written"], v["planned"], width,
                                      label=v["name"][:8], label_pad=16))
            if v.get("goal"):
                lines.append(f"        目标：{v['goal']}")
        lines.append("")

    # 日产出
    if show_daily and dash.get("daily"):
        lines.append(f"── 近 {len(dash['daily'])} 天日产出（字）──")
        for row in bar_series(dash["daily"]):
            lines.append("  " + row)
        lines.append("")

    # 章节字数分布
    if show_dist and dash.get("distribution"):
        lines.append("── 单章字数分布 ──")
        for row in bucket_distribution(dash["distribution"]):
            lines.append("  " + row)
        lines.append("")

    return "\n".join(lines)
