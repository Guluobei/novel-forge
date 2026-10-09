# -*- coding: utf-8 -*-
"""生成上下文装配：一条命令组装"写本章"所需的全部资料。

解决 AI 长篇创作第一痛点（上下文丢失）：写第 N 章前，把书籍信息、
本章 spec（章级创作锚点）、出场角色声线卡、上一章结尾、待回收伏笔、
近期钩子历史一次性装配为一份 Markdown，Claude 以此为唯一生成依据。

输出原则：精简、结构化、无冗余——够写一章，不淹没上下文窗口。
"""
from __future__ import annotations

from pathlib import Path

from . import frontmatter as fm
from .chapter import chapter_path, chapters_dir, spec_get, split_body
from .foreshadow import audit as fore_audit
from .framework import load as load_framework
from .models import read_json
from .settings import scan_characters


def _tail_excerpt(project: Path, no: int, tail_chars: int) -> str:
    """取第 no 章正文结尾片段（衔接用）。"""
    cp = chapter_path(project, no)
    if not cp.exists():
        return ""
    _, body = fm.read_file(cp)
    _, pure = split_body(body)
    text = pure.strip()
    if len(text) <= tail_chars:
        return text
    return "…" + text[-tail_chars:]


def build_context(project: Path, no: int, tail_chars: int = 500) -> dict:
    """装配第 no 章的生成上下文。"""
    from .chapter import scan_chapters

    book = read_json(project / "book.json", default={})
    chapters = scan_chapters(project)
    chapter = next((c for c in chapters if c["no"] == no), None)
    if not chapter:
        raise FileNotFoundError(f"第 {no} 章不存在，请先 chapter new")

    spec = spec_get(project, no, init_if_missing=False) if spec_path_exists(project, no) else None
    prev = next((c for c in chapters if c["no"] == no - 1), None)

    # 出场角色：spec.characters 优先；未声明则取全部 active 角色
    all_chars = scan_characters(project)
    declared = list((spec or {}).get("characters") or [])
    if declared:
        cast = [c for c in all_chars if c["name"] in declared]
        missing = [n for n in declared if n not in {c["name"] for c in cast}]
    else:
        cast = [c for c in all_chars if c.get("status") == "active"]
        missing = []

    # 角色卡全文（声线卡是语气一致性的关键）
    cast_cards = []
    for c in cast:
        p = project / "settings" / "characters" / c["file"]
        if p.exists():
            _meta, body = fm.read_file(p)
            cast_cards.append({"name": c["name"], "role": c["role"], "card": body.strip()})

    # 待回收伏笔（全部 planted；到期/超期的打标记）
    aud = fore_audit(project)
    alert_map = {a["item"]["id"]: a["level"] for a in aud["alerts"]}
    fore_data = read_json(project / "foreshadow.json", default={"items": []})
    planted = []
    for it in fore_data.get("items", []):
        if it.get("status") != "planted":
            continue
        fid = str(it.get("id"))
        level = alert_map.get(fid, "planted")
        planted.append({
            "id": fid,
            "desc": it.get("desc", ""),
            "planted_chapter": it.get("planted_chapter"),
            "expected_recover_chapter": it.get("expected_recover_chapter"),
            "status": level,
        })

    # 近 3 章钩子（多样性约束：连续 3 章不可同型）
    hook_history = [{"no": c["no"], "hook": c["hook_type"]}
                    for c in chapters if c["no"] < no and c["hook_type"]][-3:]

    # 全书框架（写每章都要知道这本书在讲什么、这一卷要达成什么）
    fw = load_framework(project)
    fw_core = fw.get("core") or {}
    fw_theme = fw.get("theme") or {}
    fw_struct = fw.get("structure") or {}
    fw_cast = {c.get("name"): c for c in (fw.get("characters") or [])}
    # 定位本章所属卷
    cur_vol = None
    for v in (fw_struct.get("volumes") or []):
        rng = v.get("chapters") or ""
        if isinstance(rng, str) and "-" in rng:
            try:
                a, b = (int(x.strip()) for x in rng.split("-")[:2])
                if a <= no <= b:
                    cur_vol = v
                    break
            except (ValueError, IndexError):
                continue

    return {
        "chapter": no,
        "title": chapter["title"],
        "book": {
            "name": book.get("name", ""),
            "genre": book.get("genre", ""),
            "words_per_chapter": (book.get("target") or {}).get("words_per_chapter"),
            "total_chapters": (book.get("target") or {}).get("total_chapters"),
        },
        "framework": {
            "has_framework": bool(fw_core or fw_theme),
            "one_liner": fw_core.get("one_liner", ""),
            "protagonist": fw_core.get("protagonist", ""),
            "goal": fw_core.get("goal", ""),
            "theme_question": fw_theme.get("question", ""),
            "current_volume": ({"name": cur_vol.get("name", ""),
                                "goal": cur_vol.get("goal", ""),
                                "climax": cur_vol.get("climax", ""),
                                "theme_question": cur_vol.get("theme_question", "")}
                               if cur_vol else None),
            "cast_roles": {n: {"relation": c.get("relation", ""),
                              "theme_face": c.get("theme_face", "")}
                           for n, c in fw_cast.items()},
        },
        "spec": spec,
        "spec_exists": spec is not None,
        "previous_chapter": ({
            "no": prev["no"], "title": prev["title"], "hook_type": prev["hook_type"],
            "tail": _tail_excerpt(project, prev["no"], tail_chars),
        } if prev else None),
        "cast": cast_cards,
        "cast_missing": missing,
        "pending_foreshadow": planted,
        "hook_history": hook_history,
    }


def spec_path_exists(project: Path, no: int) -> bool:
    return (chapters_dir(project) / f"ch_{no:04d}.spec.json").is_file()


def render_context_md(data: dict) -> str:
    """把上下文渲染为可直接喂给生成流程的 Markdown。"""
    b = data.get("book") or {}
    fw = data.get("framework") or {}
    lines = [
        f"# 第 {data['chapter']} 章写作上下文",
        "",
        f"- 书名：《{b.get('name', '')}》（{b.get('genre', '')}）",
        f"- 本章标题：{data.get('title') or '（未定）'}",
        f"- 目标字数：{(data.get('spec') or {}).get('target_words') or b.get('words_per_chapter') or '未设定'}",
        "",
    ]

    # 框架锚点：这一章在整本书里的位置与意义
    lines.append("## 全书框架锚点")
    if fw.get("has_framework"):
        if fw.get("one_liner"):
            lines.append(f"- 故事内核：{fw['one_liner']}")
        if fw.get("theme_question"):
            lines.append(f"- **主题句（本卷/本章都在追问它）**：{fw['theme_question']}")
        vol = fw.get("current_volume")
        if vol:
            lines.append(f"- 所属卷：{vol.get('name', '')}")
            if vol.get("goal"):
                lines.append(f"  - 本卷目标：{vol['goal']}")
            if vol.get("climax"):
                lines.append(f"  - 卷末高潮：{vol['climax']}")
            if vol.get("theme_question"):
                lines.append(f"  - 本卷对主题的新问法：{vol['theme_question']}")
        lines.append("> 写作时确保本章既服务本卷目标，也对主题有所触碰（哪怕只是一次反问）。")
    else:
        lines.append("> ⚠️ 全书框架尚未成型。长篇不建议在框架缺失时动笔——"
                     "先用 brainstorming-workflow.md 的流程把内核/主题/分卷想清楚。")
    lines.append("")

    spec = data.get("spec")
    lines.append("## 本章 spec（创作锚点）")
    if spec and (spec.get("summary") or spec.get("must_happen")):
        lines.append(f"- 摘要：{spec.get('summary') or '（未填）'}")
        if spec.get("must_happen"):
            lines.append("- 必须发生的情节点：")
            lines += [f"  {i}. {m}" for i, m in enumerate(spec["must_happen"], 1)]
        if spec.get("tension_curve"):
            curve = " → ".join(f"{p.get('pos')}%张力{p.get('value')}({p.get('note', '')})"
                               for p in spec["tension_curve"])
            lines.append(f"- 张力曲线：{curve}")
        if spec.get("new_hooks"):
            lines.append("- 本章需埋新钩子：" + "；".join(spec["new_hooks"]))
    else:
        lines.append("> ⚠️ spec 为空：先与作者确认本章要发生什么（summary/must_happen/tension_curve），"
                     "再动笔。不要在没有 spec 的情况下凭空生成。")
    lines.append("")

    prev = data.get("previous_chapter")
    lines.append("## 上一章衔接")
    if prev:
        lines.append(f"- 第 {prev['no']} 章《{prev['title']}》钩子类型：{prev['hook_type'] or '未登记'}")
        if prev.get("tail"):
            lines.append(f"- 结尾片段（衔接口吻）：「{prev['tail']}」")
    else:
        lines.append("- 本章为全书第一章：按黄金三章法则，开篇 500 字内必须出现钩子")
    lines.append("")

    lines.append("## 出场角色与声线卡（对话必须按声线卡区分）")
    if data.get("cast"):
        for c in data["cast"]:
            lines.append(f"### {c['name']}（{c['role']}）")
            lines.append(c["card"])
            lines.append("")
    else:
        lines.append("> （无角色卡。建议先 `setting add character` 登记主要角色）")
    if data.get("cast_missing"):
        lines.append(f"> ⚠️ spec 声明的角色未登记卡：{'、'.join(data['cast_missing'])}")

    lines.append("## 待回收伏笔（可安排回收，勿新增无关支线）")
    if data.get("pending_foreshadow"):
        for f in data["pending_foreshadow"]:
            mark = "（已超期）" if f["status"] in ("overdue", "severe") else ""
            lines.append(f"- [{f['id']}] {f['desc']}：第 {f['planted_chapter']} 章埋入，"
                         f"预期第 {f['expected_recover_chapter']} 章回收{mark}")
    else:
        lines.append("- （无到期伏笔）")
    lines.append("")

    lines.append("## 近期钩子历史（连续 3 章不可同型）")
    if data.get("hook_history"):
        lines += [f"- 第 {h['no']} 章：{h['hook'] or '未登记'}" for h in data["hook_history"]]
    else:
        lines.append("- （无）")
    return "\n".join(lines) + "\n"
