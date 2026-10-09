# -*- coding: utf-8 -*-
"""框架一致性校验：检查章节是否真正服务于全书框架与卷目标。

长篇最危险的失败模式不是文笔差，而是**写着写着跑偏了**：
- 章节内容游离于本卷目标之外（自己在写另一个故事）
- 出场角色没有框架登记的动机（在替作者推进剧情）
- 本卷该回收的伏笔迟迟不动
- 卷章节数已超范围（结构失控）

本模块把这些"跑偏信号"变成可机检的提示，分 C01-C05 五项。
注意：一致性校验是基于**文本与框架数据的对照**，含启发式判断，
输出为 warn/info 级提示（不阻塞），供作者与 Claude 复核。
"""
from __future__ import annotations

from pathlib import Path

from . import frontmatter as fm
from .chapter import chapter_path, scan_chapters, split_body
from .framework import load as load_framework
from .foreshadow import load_foreshadow

CONSISTENCY_RULES = [
    ("C01", "卷目标呼应", "warn"),
    ("C02", "角色动机锚定", "warn"),
    ("C03", "卷内伏笔进度", "info"),
    ("C04", "卷章节范围", "info"),
    ("C05", "主题触碰", "info"),
]


class ConsistencyError(RuntimeError):
    """一致性校验参数错误。"""


def _find_volume(fw: dict, no: int) -> dict | None:
    """定位章号所属卷。"""
    for v in ((fw.get("structure") or {}).get("volumes") or []):
        if not isinstance(v, dict):
            continue
        rng = v.get("chapters") or ""
        if isinstance(rng, str) and "-" in rng:
            try:
                a, b = (int(x.strip()) for x in rng.split("-")[:2])
                if a <= no <= b:
                    return v
            except (ValueError, IndexError):
                continue
    return None


def _keyword_hit(text: str, keywords: list[str]) -> list[str]:
    return [k for k in keywords if k and k in text]


def _split_names(value) -> list[str]:
    """把角色字段（列表 / 「甲、乙、丙」字符串）统一成名字列表。"""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out.extend(_split_names(v))
        return [x for x in out if x]
    import re as _re
    parts = _re.split(r"[、,，/；;|\s]+", str(value))
    return [p.strip() for p in parts if p.strip()]


def check_consistency(project: Path, no: int) -> dict:
    """对第 no 章做框架一致性校验，返回 C01-C05 结果。"""
    fw = load_framework(project)
    if not (fw.get("core") or fw.get("theme") or fw.get("structure")):
        return {
            "chapter": no,
            "checked": False,
            "message": "全书框架尚未建立，跳过一致性校验（建议先用 framework 命令落地框架）",
            "items": [],
            "warns": 0,
        }

    chapters = scan_chapters(project)
    info = next((c for c in chapters if c["no"] == no), None)
    if not info:
        raise ConsistencyError(f"第 {no} 章不存在")
    cp = chapter_path(project, no)
    meta, body = fm.read_file(cp)
    _, pure = split_body(body)

    vol = _find_volume(fw, no)
    core = fw.get("core") or {}
    theme = fw.get("theme") or {}
    cast = {c.get("name"): c for c in (fw.get("characters") or []) if isinstance(c, dict)}
    items: list[dict] = []

    # ---- C01 卷目标呼应：卷目标关键词是否在本章出现 ----
    if vol and vol.get("goal"):
        # 从卷目标中提取 2 字以上的中文词组作为检查词
        goal_kws = _extract_keywords(vol["goal"])
        hits = _keyword_hit(pure, goal_kws)
        ok = bool(hits)
        items.append({
            "rule_id": "C01", "name": "卷目标呼应", "level": "warn", "passed": ok,
            "message": (f"本章呼应了本卷目标（命中：{'、'.join(hits)}）" if ok else
                        f"未检测到与卷目标「{vol['goal']}」相关的内容。"
                        f"若本章是过渡章可忽略；否则确认是否偏离本卷主线"),
            "hints": goal_kws,
        })
    else:
        items.append({"rule_id": "C01", "name": "卷目标呼应", "level": "warn", "passed": True,
                      "message": "本卷未登记卷内目标，无法校验（建议补充 structure.volumes[].goal）"})

    # ---- C02 角色动机锚定：出场角色是否都有框架登记的动机 ----
    declared = _split_names(meta.get("characters"))
    if not declared:
        # 从 spec 读取
        spec_file = project / "chapters" / f"ch_{no:04d}.spec.json"
        if spec_file.is_file():
            from .models import read_json
            declared = _split_names((read_json(spec_file, default={}) or {}).get("characters"))
    # 未声明出场角色时，尝试从正文中匹配框架角色名
    if not declared:
        declared = [name for name in cast if name and name in pure]
    unanchored = [n for n in declared if n in cast and not (cast[n].get("own_goal"))]
    unknown = [n for n in declared if n not in cast]
    if unanchored:
        msg = f"角色 {'、'.join(unanchored)} 在框架中未登记「自己的目标」，易沦为工具人"
        ok = False
    elif unknown and cast:
        msg = f"角色 {'、'.join(unknown)} 未在框架人物网登记（建议补充，否则动机无锚点）"
        ok = False
    else:
        msg = f"出场角色均有框架动机锚点（{'、'.join(declared)}）" if declared else "未识别到出场角色"
        ok = True
    items.append({"rule_id": "C02", "name": "角色动机锚定", "level": "warn",
                  "passed": ok, "message": msg})

    # ---- C03 卷内伏笔进度：本卷应回收的伏笔是否已回收 ----
    if vol:
        vol_range = vol.get("chapters") or ""
        try:
            vstart, vend = (int(x.strip()) for x in str(vol_range).split("-")[:2])
        except (ValueError, IndexError):
            vstart = vend = None
        if vstart:
            fore = load_foreshadow(project)
            due = [i for i in fore["items"]
                   if i.get("status") == "planted"
                   and isinstance(i.get("expected_recover_chapter"), int)
                   and vstart <= i["expected_recover_chapter"] <= vend
                   and no >= i["expected_recover_chapter"]]
            ok = not due
            msg = (f"本卷（{vstart}-{vend}）无到期未回收伏笔" if ok else
                   f"本卷内有 {len(due)} 条伏笔已到期未回收：" +
                   "；".join(f"{i['id']}（预期第 {i['expected_recover_chapter']} 章）" for i in due))
            items.append({"rule_id": "C03", "name": "卷内伏笔进度", "level": "info",
                          "passed": ok, "message": msg})

    # ---- C04 卷章节范围：当前章号是否已抵近/超出本卷预定范围 ----
    if vol:
        try:
            _, vend = (int(x.strip()) for x in str(vol.get("chapters", "")).split("-")[:2])
            # 落在卷内但已到卷末，或卷内其他章已远超（用于跨卷提醒）
            over = no >= vend
            items.append({
                "rule_id": "C04", "name": "卷章节范围", "level": "info", "passed": not over,
                "message": (f"第 {no} 章已抵近/超出本卷预定范围（{vol.get('chapters')}）末尾，"
                            f"注意本卷该收束了（是节奏放慢还是结构失控？）" if over else
                            f"在本卷预定范围（{vol.get('chapters')}）内")
            })
        except (ValueError, IndexError):
            items.append({"rule_id": "C04", "name": "卷章节范围", "level": "info", "passed": True,
                          "message": "本卷章节范围格式无法解析，跳过校验"})
    else:
        items.append({"rule_id": "C04", "name": "卷章节范围", "level": "info", "passed": True,
                      "message": f"第 {no} 章不在任何已登记的卷范围内（跨卷或新卷待登记）"})

    # ---- C05 主题触碰：本章是否对主题有所回应 ----
    if theme.get("question"):
        theme_kws = _extract_keywords(theme["question"])
        hits = _keyword_hit(pure, theme_kws)
        ok = bool(hits)
        items.append({
            "rule_id": "C05", "name": "主题触碰", "level": "info", "passed": ok,
            "message": (f"本章触碰了主题（命中：{'、'.join(hits)}）" if ok else
                        f"未检测到对主题「{theme['question']}」的回应。"
                        f"长篇靠主题撑着，建议本章埋一处相关的思考或反问")
        })

    warns = sum(1 for i in items if not i["passed"] and i["level"] == "warn")
    return {
        "chapter": no,
        "checked": True,
        "volume": vol.get("name") if vol else None,
        "items": items,
        "warns": warns,
        "passed": warns == 0,
    }


def _extract_keywords(text: str, min_len: int = 2) -> list[str]:
    """从目标/主题句中提取 2 字以上的中文词组（按标点切分去杂）。"""
    import re as _re
    parts = _re.split(r"[，。、；：！？（）()\[\]\"'“”‘’\s]+", text)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) >= min_len and not _re.fullmatch(r"[a-zA-Z0-9\-_]+", p):
            out.append(p)
    return out[:8]


def render_consistency_md(result: dict) -> str:
    """渲染一致性校验结果。"""
    if not result.get("checked"):
        return f"## 框架一致性校验\n\n> {result.get('message', '')}\n"
    lines = ["## 框架一致性校验", ""]
    if result.get("volume"):
        lines.append(f"- 所属卷：{result['volume']}")
    lines.append("")
    lines.append("| 项 | 检查 | 级别 | 结果 | 说明 |")
    lines.append("|---|---|---|---|---|")
    for i in result["items"]:
        mark = "✅" if i["passed"] else "❌"
        lines.append(f"| {i['rule_id']} | {i['name']} | {i['level']} | {mark} | {i['message']} |")
    return "\n".join(lines) + "\n"
