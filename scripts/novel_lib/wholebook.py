# -*- coding: utf-8 -*-
"""全书体检（跨章节趋势检查）：空转 / 水 / 人设崩 的早期预警。

G01-G12 管「这一章的句子好不好」，C01-C05 管「这一章该不该存在」，
本模块管「**这本书有没有在悄悄地坏掉**」——单看每一章都挑不出毛病，
但把它们排在一起看，趋势是危险的。

四项跨章检查（W01-W04，全为 info/warn 提示，不阻塞）：

- **W01 爽点密度过高**：连续 N 章都有强钩子/高潮 → 缺呼吸章，读者会「追不动」
- **W02 钩子退化**：全书钩子类型过度集中（多样性不足）
- **W03 空转风险**：长区间内没有任何「卷目标推进」迹象（章节 spec 的 must_happen 长期不更新）
- **W04 更新断层**：章节字数分布出现极端离群（个别章过短，疑似凑数/断更拼接）

这些规则基于**节奏与趋势**而非单点，判定含启发式，输出供作者复核。
"""
from __future__ import annotations

from pathlib import Path

from .chapter import scan_chapters
from .framework import load as load_framework
from .models import read_json
from .project import now_iso

CHECKS = [
    ("W01", "爽点密度与呼吸章", "warn"),
    ("W02", "钩子类型多样性", "warn"),
    ("W03", "空转风险", "info"),
    ("W04", "字数离群", "info"),
]

# 连续多少章都有强钩子视为「过山车没刹车」
DENSE_STREAK = 6
# 一个「呼吸章」应显式登记，或用非强钩子类型
STRONG_HOOKS = {"危机", "反转", "生存"}


class WholeBookError(RuntimeError):
    """全书体检参数错误。"""


def _range_check(chapters: list[dict], start: int, end: int) -> list[dict]:
    return [c for c in chapters if start <= c["no"] <= end]


def _w01_payoff_density(chapters: list[dict]) -> dict:
    """连续强钩子无间断 → 建议插入呼吸章。"""
    streak, worst_start = 0, None
    best = 0
    for i, c in enumerate(chapters):
        if c.get("hook_type") in STRONG_HOOKS:
            streak += 1
            if streak > best:
                best, worst_start = streak, c["no"] - streak + 1
        else:
            streak = 0
    ok = best < DENSE_STREAK
    msg = (f"未发现连续 {DENSE_STREAK} 章以上的强钩子密集区（最长连续 {best} 章）" if ok else
           f"第 {worst_start}-{worst_start + best - 1} 章连续 {best} 章都是强钩子（危机/反转/生存），"
           f"缺少呼吸章——爽点给得越密读者跑得越快，建议插入 2-3 章日常/信息整理/配角视角")
    return {"rule_id": "W01", "name": "爽点密度与呼吸章", "level": "warn",
            "passed": ok, "message": msg, "detail": {"streak": best, "start": worst_start}}


def _w02_hook_variety(chapters: list[dict]) -> dict:
    """全书钩子类型分布是否过度集中。"""
    hooks = [c.get("hook_type") or "" for c in chapters if c.get("hook_type")]
    if len(hooks) < 5:
        return {"rule_id": "W02", "name": "钩子类型多样性", "level": "warn", "passed": True,
                "message": f"已登记钩子的章节不足 5 章（{len(hooks)}），暂不评估多样性"}
    dist: dict[str, int] = {}
    for h in hooks:
        dist[h] = dist.get(h, 0) + 1
    top_type, top_n = max(dist.items(), key=lambda kv: kv[1])
    ratio = top_n / len(hooks)
    ok = ratio <= 0.6
    msg = (f"钩子分布健康（{len(dist)} 种，最高占比 {top_type} {ratio:.0%}）" if ok else
           f"钩子类型过度集中：{top_type} 占 {ratio:.0%}（{top_n}/{len(hooks)}）。"
           f"同类钩子反复使用会让读者产生预期疲劳，建议换钩子类型")
    return {"rule_id": "W02", "name": "钩子类型多样性", "level": "warn",
            "passed": ok, "message": msg, "detail": dist}


def _w03_spin(project: Path, chapters: list[dict]) -> dict:
    """空转风险：已写 N 章但没有任何章节 spec 登记「必须发生的推进」。"""
    written = [c for c in chapters if not c.get("unwritten")]
    if len(written) < 10:
        return {"rule_id": "W03", "name": "空转风险", "level": "info", "passed": True,
                "message": f"已写正文不足 10 章（{len(written)}），暂不评估空转风险"}
    no_spec = []
    for c in written:
        sp = project / "chapters" / f"ch_{c['no']:04d}.spec.json"
        spec = read_json(sp, default={}) or {}
        if not (spec.get("must_happen") or spec.get("summary")):
            no_spec.append(c["no"])
    ratio = len(no_spec) / len(written)
    ok = ratio <= 0.5
    msg = (f"大部分章节登记了推进目标（{len(written) - len(no_spec)}/{len(written)}）" if ok else
           f"{len(no_spec)}/{len(written)} 章没有登记 must_happen/summary——"
           f"无法判断这些章是否在推进主线。长篇空转（主角忙碌但不推进）是最隐蔽的死法，"
           f"建议补齐 spec 或用 chapter spec N --set 补登记")
    return {"rule_id": "W03", "name": "空转风险", "level": "info",
            "passed": ok, "message": msg, "detail": {"without_spec": no_spec[:20]}}


def _w04_word_outliers(chapters: list[dict]) -> dict:
    """字数离群：出现远低于均值/目标的章（疑似凑数或断更拼接）。"""
    written = [c for c in chapters if not c.get("unwritten") and c["words"] > 0]
    if len(written) < 5:
        return {"rule_id": "W04", "name": "字数离群", "level": "info", "passed": True,
                "message": "已写章节不足 5 章，暂不评估字数分布"}
    avg = sum(c["words"] for c in written) / len(written)
    outliers = [c for c in written if c["words"] < avg * 0.45]
    ok = not outliers
    msg = (f"字数分布正常（均值 {avg:.0f}，无极端离群）" if ok else
           f"第 {'、'.join(str(c['no']) for c in outliers)} 章字数远低于均值 {avg:.0f}"
           f"（不足 45%），疑似凑数或拼接。注意：水不是字数少，是没有新信息的重复")
    return {"rule_id": "W04", "name": "字数离群", "level": "info",
            "passed": ok, "message": msg, "detail": {"avg": round(avg, 1)}}


def whole_book_check(project: Path) -> dict:
    """全书体检：W01-W04 跨章趋势检查 + 框架健康度摘要。"""
    chapters = scan_chapters(project)
    items = [
        _w01_payoff_density(chapters),
        _w02_hook_variety(chapters),
        _w03_spin(project, chapters),
        _w04_word_outliers(chapters),
    ]

    labels = {"W01": "爽点密度与呼吸章", "W02": "钩子类型多样性",
              "W03": "空转风险", "W04": "字数离群"}
    for i in items:
        i["name"] = labels.get(i["rule_id"], i["name"])

    written = [c for c in chapters if not c.get("unwritten")]
    fw = load_framework(project)
    warns = sum(1 for i in items if not i["passed"] and i["level"] == "warn")
    return {
        "checked_at": now_iso(),
        "total_chapters": len(chapters),
        "written_chapters": len(written),
        "written_words": sum(c["words"] for c in written),
        "framework_complete": bool(fw.get("core") and fw.get("structure")),
        "items": items,
        "warns": warns,
        "passed": warns == 0,
    }


def render_whole_book_md(result: dict) -> str:
    """渲染全书体检结果。"""
    lines = ["## 全书体检（跨章趋势）", ""]
    lines.append(f"- 总章数：{result['total_chapters']}（已写 {result['written_chapters']}）"
                 f"｜累计 {result['written_words']} 字")
    lines.append(f"- 框架状态：{'已成型' if result['framework_complete'] else '未成型（建议先补框架）'}")
    lines.append("")
    lines.append("| 项 | 检查 | 级别 | 结果 | 说明 |")
    lines.append("|---|---|---|---|---|")
    for i in result["items"]:
        mark = "✅" if i["passed"] else "❌"
        lines.append(f"| {i['rule_id']} | {i['name']} | {i['level']} | {mark} | {i['message']} |")
    return "\n".join(lines) + "\n"
