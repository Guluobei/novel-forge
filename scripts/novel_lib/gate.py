# -*- coding: utf-8 -*-
"""质量门禁引擎：G01-G12 可机检量化规则、100 分制评分、报告生成。

规则级别语义：
- error：章节不通过（check 退出码 1）
- warn  ：计分扣分（每处 -2 分），--strict 时也判不通过
- info  ：仅提示，不扣分

评分：100 - error违规数*5 - warn违规数*2，下限 0。
继承 cn-novel-craft 已验证的 10 步量化门禁并工程化，全部确定性机检，无 AI 参与。
"""
from __future__ import annotations

import datetime as _dt
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter as fm
from .chapter import chapter_path, scan_chapters, split_body
from .lexicon import build_patterns, load_lexicon
from .project import HOOK_TYPES, gate_thresholds

from . import consistency as consistency_mod

LEVELS = ["error", "warn", "info"]


def _thresholds(project: Path) -> dict:
    """读取合并后的门禁阈值（默认 + 项目覆盖）。"""
    from .models import read_json as _rj
    return gate_thresholds(_rj(project / "book.json", default={}))
# 复合对话标签（安全词，不会误伤「知道/道路/小说」）
_TAG_COMPOUND = r"(?:说道|问道|答道|喊道|叫道|笑道|叹道|冷笑道|开口道|回应道|低声道|淡淡道|沉声道|朗声道|嘀咕道|嘟囔道)"
COMPOUND_TAG_RE = re.compile(_TAG_COMPOUND)
# 裸标签 = 代词主语 + （复合标签 或 单字 说/道/问/答）；「他知道」不匹配（道前有知字）
BARE_TAG_RE = re.compile(r"(?:我|你|他|她|它)(?:说道|问道|答道|喊道|叫道|笑道|叹道|说|道)")
FLAT_END_RE = re.compile(r"第\s*0*\d+\s*章\s*完|本章完|（完）|\(完\)")
EMOTION_RE = re.compile(r"感到|觉得|感觉到")


@dataclass
class Violation:
    line: int = 0
    excerpt: str = ""

    def to_dict(self) -> dict:
        return {"line": self.line, "excerpt": self.excerpt[:60]}


@dataclass
class RuleResult:
    rule_id: str
    name: str
    level: str          # error / warn / info
    passed: bool
    count: int = 0
    limit: int | float | None = None
    violations: list[Violation] = field(default_factory=list)
    message: str = ""
    units: int | None = None   # 扣分单位数（缺省：未通过时按 1 计）

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id, "name": self.name, "level": self.level,
            "passed": self.passed, "count": self.count, "limit": self.limit,
            "violations": [v.to_dict() for v in self.violations],
            "message": self.message,
        }


def _line_of(text: str, pos: int) -> int:
    """字符偏移 → 行号（1 起）。"""
    return text.count("\n", 0, pos) + 1


def _count_literal_on_lines(text: str, regex) -> tuple[int, list[Violation]]:
    hits: list[Violation] = []
    for m in regex.finditer(text):
        hits.append(Violation(line=_line_of(text, m.start()), excerpt=m.group(0)))
    return len(hits), hits


# ---------------------------------------------------------------- 规则实现

def _g01_words(pure: str, ctx: dict) -> RuleResult:
    words = sum(1 for c in pure if not c.isspace())
    limit = int(ctx["thresholds"].get("min_words", 3000))
    if ctx.get("unwritten"):
        return RuleResult(
            "G01", "字数下限", "error", True, count=words, limit=limit, units=0,
            message=f"本章尚未创作（{words} 字）：完成正文后再来质检")
    ok = words >= limit
    return RuleResult(
        "G01", "字数下限", "error", ok, count=words, limit=limit, units=1,
        message=f"实际 {words} 字，要求 ≥{limit} 字" + ("" if ok else "，字数不足需扩写（心理独白/环境渲染/动作细节/配角反应）"))


def _g02_dash(pure: str, ctx: dict) -> RuleResult:
    limit = int(ctx["thresholds"].get("max_dash", 12))
    hits, vs = _count_literal_on_lines(pure, re.compile("——"))
    ok = hits <= limit
    return RuleResult(
        "G02", "破折号密度", "error", ok, count=hits, limit=limit, violations=vs,
        units=max(1, hits - limit),
        message=f"破折号 {hits} 处，上限 {limit} 处/章；解释改冒号、转折改句号、补充改分号" if not ok else f"{hits} 处")


def _g03_ban(pure: str, ctx: dict) -> RuleResult:
    total_vs: list[Violation] = []
    for _, compiled, kind in ctx["patterns"]["ban"]:
        _, vs = _count_literal_on_lines(pure, compiled)
        total_vs.extend(vs)
    ok = not total_vs
    return RuleResult(
        "G03", "ban 词（零容忍）", "error", ok, count=len(total_vs), limit=0,
        violations=total_vs, units=len(total_vs),
        message="ban 词零容忍，全部删除或改写" if not ok else "未命中")


def _g04_warn_words(pure: str, ctx: dict) -> RuleResult:
    limit = int(ctx["thresholds"].get("max_warn", 3))
    total_vs: list[Violation] = []
    for _, compiled, _k in ctx["patterns"]["warn"]:
        _, vs = _count_literal_on_lines(pure, compiled)
        total_vs.extend(vs)
    ok = len(total_vs) <= limit
    return RuleResult(
        "G04", "warn 词", "warn", ok, count=len(total_vs), limit=limit,
        violations=total_vs, units=max(1, len(total_vs) - limit),
        message=f"warn 词 {len(total_vs)} 处，上限 {limit} 处/章" if not ok else f"{len(total_vs)} 处")


def _g05_limit(pure: str, ctx: dict) -> RuleResult:
    total_vs: list[Violation] = []
    over_items = []
    for l in ctx["patterns"]["limit"]:
        n, vs = _count_literal_on_lines(pure, l["regex"])
        if n > l["max"]:
            total_vs.extend(vs)
            over_items.append(f"{l['pattern']}×{n}>{l['max']}")
    ok = not total_vs
    return RuleResult(
        "G05", "limit 词限量", "error", ok, count=len(total_vs), limit=None,
        violations=total_vs, units=len(total_vs),
        message="超限：" + "；".join(over_items) if not ok else "全部在限额内")


def _g06_hook(pure: str, ctx: dict) -> RuleResult:
    hook = (ctx.get("hook_type") or "").strip()
    if not hook:
        return RuleResult("G06", "钩子登记", "warn", False, count=0, limit=None, units=1,
                          message="未登记钩子类型：在 frontmatter 的 hook_type 填写 "
                                  + "/".join(HOOK_TYPES))
    if hook not in HOOK_TYPES:
        return RuleResult("G06", "钩子登记", "warn", False, count=1, limit=None, units=1,
                          message=f"钩子类型 {hook!r} 不在 8 类之内：" + "/".join(HOOK_TYPES))
    return RuleResult("G06", "钩子登记", "warn", True, count=1, limit=None, message=f"已登记：{hook}")


def _g07_bare_tag(pure: str, ctx: dict) -> RuleResult:
    """裸标签率 = 代词主语标签 / (复合标签总数 + 代词单字标签)。

    口径说明：单字「说/道」仅统计代词主语（我/你/他/她/它 + 说），
    非代词主语的单字标签（如「林晚说」）不计入 total——低估而非高估，可接受。
    """
    compound_total, _ = _count_literal_on_lines(pure, COMPOUND_TAG_RE)
    bare, vs = _count_literal_on_lines(pure, BARE_TAG_RE)
    total = compound_total + bare
    max_ratio = float(ctx["thresholds"].get("bare_tag_max_ratio", 0.3))
    if total == 0:
        return RuleResult("G07", "裸对话标签", "warn", True, count=0, limit=None,
                          message="未检测到对话标签")
    ratio = bare / total
    ok = ratio <= max_ratio
    return RuleResult(
        "G07", "裸对话标签", "warn", ok, count=bare, limit=int(total * max_ratio),
        violations=vs, units=1,
        message=f"裸标签 {bare}/{total}（{ratio:.0%}），上限 {max_ratio:.0%}；把「他说」替换为动作标签" if not ok
        else f"{bare}/{total}（{ratio:.0%}）")


def _g08_chapter_end(pure: str, ctx: dict) -> RuleResult:
    if ctx.get("unwritten"):
        return RuleResult("G08", "章末收束", "error", True, count=0, limit=None, units=0,
                          message="本章尚未创作，跳过章末检查")
    lines = [l for l in pure.split("\n") if l.strip()]
    if not lines:
        return RuleResult("G08", "章末收束", "error", False, count=1, limit=None, units=1,
                          message="正文为空")
    last = lines[-1].strip()
    vs = [Violation(line=len(pure.split("\n")), excerpt=last)]
    if last.endswith("？") or last.endswith("！"):
        return RuleResult("G08", "章末收束", "error", False, count=1, limit=None, units=1,
                          violations=vs, message="章末为反问/感叹结尾，改为陈述/动作/画面收尾")
    if FLAT_END_RE.search(last) or last in ("完",):
        return RuleResult("G08", "章末收束", "error", False, count=1, limit=None, units=1,
                          violations=vs, message="章末为平收（第X章完），删除并给出钩子")
    return RuleResult("G08", "章末收束", "error", True, count=0, limit=None, message="章末合规")


def _g09_emotion(pure: str, ctx: dict) -> RuleResult:
    limit = int(ctx["thresholds"].get("max_emotion_naming", 2))
    n, vs = _count_literal_on_lines(pure, EMOTION_RE)
    ok = n <= limit
    return RuleResult(
        "G09", "情绪命名", "warn", ok, count=n, limit=limit, violations=vs,
        units=max(1, n - limit),
        message=f"「感到/觉得/感觉到」{n} 次，上限 {limit} 次/章；改写为行为外化（如「他把烟点反了两次」）" if not ok else f"{n} 次")


def _g10_rhythm(pure: str, ctx: dict) -> RuleResult:
    """句子长短交替：按 。！？切句，变异系数过低提示。"""
    sentences = [s for s in re.split(r"[。！？…]+", pure) if s.strip()]
    if len(sentences) < 10:
        return RuleResult("G10", "长短句交替", "info", True, count=len(sentences),
                          message="句子太少，跳过检查")
    lens = [sum(1 for c in s if not c.isspace()) for s in sentences]
    mean = statistics.mean(lens)
    cv = statistics.pstdev(lens) / mean if mean else 0
    ok = cv >= 0.25
    return RuleResult(
        "G10", "长短句交替", "info", ok, count=round(cv, 2), limit=0.25,
        message=f"句长变异系数 {cv:.2f}（≥0.25 为佳）：拆长句、合并短句，制造节奏起伏" if not ok
        else f"变异系数 {cv:.2f}，节奏良好")


def _g11_hook_variety(pure: str, ctx: dict) -> RuleResult:
    hook = (ctx.get("hook_type") or "").strip()
    recent = [h for h in (ctx.get("recent_hooks") or []) if h]
    if not hook or len(recent) < 2:
        return RuleResult("G11", "钩子多样性", "warn", True, count=0,
                          message="历史钩子不足 2 章，跳过")
    if hook == recent[-1] == recent[-2]:
        return RuleResult("G11", "钩子多样性", "warn", False, count=3, limit=None, units=1,
                          message=f"连续 3 章使用同一种钩子（{hook}），换用其他类型：" + "/".join(HOOK_TYPES))
    return RuleResult("G11", "钩子多样性", "warn", True, count=0, message="钩子类型有变化")


def _g12_para_repeat(pure: str, ctx: dict) -> RuleResult:
    """段首重复：连续 ≥3 段以相同 2 字开头则提示。"""
    paras = [l.strip() for l in pure.split("\n") if l.strip()]
    streak, streak_head, hits = 1, None, []
    for i, p in enumerate(paras):
        head = p[:2]
        if i > 0 and head == streak_head:
            streak += 1
            if streak >= 3:
                hits.append({"line_start": p, "head": head})
        else:
            streak, streak_head = 1, head
    ok = not hits
    return RuleResult(
        "G12", "段首重复", "info", ok, count=len(hits), limit=0,
        message=f"存在连续 {len(hits)} 组段首重复，变换段落开头方式" if not ok else "无连续重复段首")


# ---------------------------------------------------------------- 引擎

RULES = [
    ("G01", _g01_words), ("G02", _g02_dash), ("G03", _g03_ban),
    ("G04", _g04_warn_words), ("G05", _g05_limit), ("G06", _g06_hook),
    ("G07", _g07_bare_tag), ("G08", _g08_chapter_end), ("G09", _g09_emotion),
    ("G10", _g10_rhythm), ("G11", _g11_hook_variety), ("G12", _g12_para_repeat),
]


def _score_of(results: list[RuleResult]) -> int:
    """按"超出单位数"扣分：error 每单位 -5，warn 每单位 -2，下限 0。

    units 语义（各规则显式声明）：
    - G01 字数不足 = 1；G02/G04/G09 超出限额的处数；G03/G05 每处违规各 1；
    - G06/G08/G11 等布尔型违规 = 1。
    """
    penalty = 0
    for r in results:
        if r.passed:
            continue
        units = r.units if r.units is not None else 1
        if r.level == "error":
            penalty += 5 * max(1, units)
        elif r.level == "warn":
            penalty += 2 * max(1, units)
    return max(0, 100 - penalty)


def check_chapter(project: Path, no: int, strict: bool = False,
                  with_consistency: bool = False) -> dict:
    """对单章执行全部门禁规则，返回报告 dict。

    with_consistency=True 时额外做框架一致性校验（C01-C05），结果并入报告。
    """
    chapters = scan_chapters(project)
    info = next((c for c in chapters if c["no"] == no), None)
    if not info:
        raise FileNotFoundError(f"第 {no} 章不存在")
    path = chapter_path(project, no)
    meta, body = fm.read_file(path)
    _, pure = split_body(body)

    recent_hooks = [c["hook_type"] for c in chapters if c["no"] < no][-2:]
    unwritten = bool(info.get("unwritten"))
    ctx = {
        "thresholds": _thresholds(project),
        "patterns": build_patterns(load_lexicon(project)),
        "hook_type": meta.get("hook_type", ""),
        "recent_hooks": recent_hooks,
        "chapter_no": no,
        "unwritten": unwritten,
    }
    results = [fn(pure, ctx) for _, fn in RULES]
    rmap = revision_map(pure, results)
    score = _score_of(results)
    has_error = any(not r.passed and r.level == "error" for r in results)
    has_warn = any(not r.passed and r.level == "warn" for r in results)
    passed = not has_error
    strict_passed = not has_error and not has_warn
    words = sum(1 for c in pure if not c.isspace())
    verdict = ("通过" if (strict_passed if strict else passed)
               else "不通过" + ("（strict）" if strict and passed else ""))
    if unwritten:
        verdict = "尚未创作"
        score = None
    return {
        "chapter": no,
        "title": meta.get("title", ""),
        "words": words,
        "unwritten": unwritten,
        "score": score,
        "passed": passed,
        "strict_passed": strict_passed,
        "verdict": verdict,
        "errors": sum(1 for r in results if not r.passed and r.level == "error"),
        "warns": sum(1 for r in results if not r.passed and r.level == "warn"),
        "infos": sum(1 for r in results if not r.passed and r.level == "info"),
        "rules": [r.to_dict() for r in results],
        "revision_map": rmap,
        "consistency": (consistency_mod.check_consistency(project, no)
                        if with_consistency else None),
    }


def check_all(project: Path, strict: bool = False, with_consistency: bool = False) -> dict:
    """全书逐章检查，返回汇总。"""
    chapters = scan_chapters(project)
    reports = [check_chapter(project, c["no"], strict, with_consistency) for c in chapters]
    failed = [r["chapter"] for r in reports if not (r["strict_passed"] if strict else r["passed"])]
    scored = [r for r in reports if r.get("score") is not None]
    return {
        "total": len(reports),
        "passed": len(reports) - len(failed),
        "failed_chapters": failed,
        "avg_score": round(sum(r["score"] for r in scored) / len(scored), 1) if scored else 100,
        "reports": reports,
        "verdict": "全部通过" if not failed else f"{len(failed)} 章不通过：{failed}",
    }


def render_report_md(report: dict) -> str:
    """把单章检查报告渲染为 Markdown。"""
    lines = [
        f"# 第 {report['chapter']} 章门禁报告",
        "",
        f"- 标题：{report['title'] or '（无）'}",
        f"- 字数：{report['words']}",
        f"- 评分：**{report['score']} / 100**" if report.get("score") is not None else "- 评分：（尚未创作）",
        f"- 结论：**{report['verdict']}**（error {report['errors']} / warn {report['warns']} / info {report['infos']}）",
        "",
        "| 规则 | 级别 | 结果 | 计数/限额 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for r in report["rules"]:
        status = "✅" if r["passed"] else "❌"
        cnt = f"{r['count']}/{r['limit']}" if r["limit"] is not None else f"{r['count']}"
        lines.append(f"| {r['rule_id']} {r['name']} | {r['level']} | {status} | {cnt} | {r['message']} |")
    rmap = report.get("revision_map") or []
    if rmap:
        lines += ["", "## 修订优先级（AI 味热力图：从上往下改）", ""]
        lines.append("| 优先 | 段落 | 行号 | 热度 | 命中规则 | 段落摘录 | 修改指引 |")
        lines.append("|---|---|---|---|---|---|---|")
        for i, slot in enumerate(rmap, 1):
            lines.append(f"| {i} | 段{slot['para']} | L{slot['lines']} | 🔥{slot['heat']} "
                         f"| {'+'.join(slot['rules'])} | {slot['excerpt']} | {'；'.join(slot['advice'])} |")
        lines += ["", "> 行号相对正文（不含 frontmatter 与标题行）。"]
    cons = report.get("consistency")
    if cons:
        lines += ["", consistency_mod.render_consistency_md(cons).rstrip()]
    viols = [v for r in report["rules"] if not r["passed"] for v in r["violations"]]
    if viols:
        lines += ["", "## 违规明细", ""]
        for v in viols[:60]:
            lines.append(f"- L{v['line']}：{v['excerpt']}")
        if len(viols) > 60:
            lines.append(f"- ……（共 {len(viols)} 处，仅展示前 60）")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 修订导航图

def _paragraphs(pure: str) -> list[dict]:
    """把正文切为段落：[{idx, start_line, end_line, text}]（行号相对正文，1 起）。"""
    paras, cur_start, buf = [], 1, []
    line_no = 0
    for line in pure.split("\n"):
        line_no += 1
        if line.strip():
            if not buf:
                cur_start = line_no
            buf.append(line)
        elif buf:
            paras.append({"idx": len(paras) + 1, "start_line": cur_start,
                          "end_line": line_no - 1, "text": "\n".join(buf)})
            buf = []
    if buf:
        paras.append({"idx": len(paras) + 1, "start_line": cur_start,
                      "end_line": line_no, "text": "\n".join(buf)})
    return paras


_LEVEL_WEIGHT = {"error": 3, "warn": 1, "info": 0}


def revision_map(pure: str, results: list[RuleResult], top: int = 5) -> list[dict]:
    """修订导航图：按段落聚合违规热度，输出修订优先级排序。

    热度 = Σ(error×3 + warn×1)。用途：作者手工润色时先改热度最高的段落，
    把"AI 味"最重的地方优先处理掉。
    """
    paras = _paragraphs(pure)
    if not paras:
        return []
    heat: dict[int, dict] = {}
    for r in results:
        if r.passed or not r.violations:
            continue
        for v in r.violations:
            target = None
            for p in paras:
                if p["start_line"] <= v.line <= p["end_line"]:
                    target = p
                    break
            if target is None:
                continue
            slot = heat.setdefault(target["idx"], {
                "para": target["idx"], "lines": f"{target['start_line']}-{target['end_line']}",
                "excerpt": target["text"].strip().replace("\n", " ")[:50],
                "heat": 0, "rules": [], "advice": []})
            slot["heat"] += _LEVEL_WEIGHT.get(r.level, 1)
            if r.rule_id not in slot["rules"]:
                slot["rules"].append(r.rule_id)
            if r.message and r.message not in slot["advice"]:
                slot["advice"].append(r.message)
    ranked = sorted(heat.values(), key=lambda x: -x["heat"])
    for slot in ranked:
        slot["advice"] = slot["advice"][:3]
    return ranked[:top]


def save_report(project: Path, report: dict) -> dict:
    """把报告落盘到 reports/，返回 md/json 路径。"""
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    rdir = project / "reports"
    rdir.mkdir(parents=True, exist_ok=True)
    stem = f"check_ch{report['chapter']:04d}_{ts}"
    md_path = rdir / f"{stem}.md"
    json_path = rdir / f"{stem}.json"
    md_path.write_text(render_report_md(report), encoding="utf-8")
    from .models import safe_write_json
    safe_write_json(json_path, report)
    return {"md": str(md_path), "json": str(json_path)}
