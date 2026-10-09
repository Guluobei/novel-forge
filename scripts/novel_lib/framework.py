# -*- coding: utf-8 -*-
"""全书框架管理：内核 / 主题 / 人物关系网 / 分卷结构 / 揭示表。

长篇写作的地基。框架数据存于项目根的 framework.json，
在动笔任何章节之前应先成型（见 references/brainstorming-workflow.md）。

框架由作者与 Claude 共同构思，本模块只负责：
- 结构化存储与查询（供每章 context 装配时引用）
- 完整性体检（缺哪一块一目了然）
- 与分卷/章节的衔接校验
"""
from __future__ import annotations

from pathlib import Path

from .models import read_json, safe_write_json
from .project import now_iso

FRAMEWORK_FILE = "framework.json"

# 框架各版块及其权重（用于完整度体检）
# 前六块是「一本书的地基」；后五块是「一本书能活到一百万字的骨架」。
SECTIONS = [
    ("core", "故事内核", "主角/目标/阻碍/催化剂四要素"),
    ("engine", "核心循环与驱动轮", "核心循环闭环 + 四驱动轮配比 + 延展性自检"),
    ("theme", "主题与内核矛盾", "主题句 + 正题/反题/合题"),
    ("characters", "人物关系网", "核心角色的力场与主题面"),
    ("ladder", "可攀越的世界观", "5-7 阶阶梯表：舞台/实力上限/对手/资源/秘密"),
    ("structure", "分卷结构", "三幕 + 卷划分 + 每卷本质变化"),
    ("rhythm", "节奏与情绪波", "抑扬波周期 + 难度梯度 + 爽点呼吸法则"),
    ("midgame", "中期弹药库", "中期三件套 + 认知线五真相（防空转/防人设崩）"),
    ("reveal", "信息揭示表", "重大秘密的揭示位置与铺垫"),
    ("opening", "开篇设计", "前三章任务分工（黄金三章）"),
    ("platform", "平台与门面", "目标平台定位 + 书名公式 + 简介四要素"),
]

STAGES = ["core", "engine", "theme", "characters", "ladder", "structure",
          "rhythm", "midgame", "reveal", "opening", "platform"]


class FrameworkError(RuntimeError):
    """框架操作失败。"""


def empty_framework() -> dict:
    return {
        "version": 2,
        "updated_at": now_iso(),
        "stage": "core",          # 当前构思进行到哪一阶段
        "core": {},               # 故事内核
        "engine": {},             # 核心循环 + 四驱动轮 + 延展性自检
        "theme": {},              # 主题与内核矛盾
        "characters": [],         # 人物关系网
        "ladder": {},             # 可攀越的世界观（阶梯表）
        "structure": {},          # 分卷结构
        "rhythm": {},             # 节奏与情绪波
        "midgame": {},            # 中期弹药库
        "reveal": [],             # 信息揭示表
        "opening": {},            # 开篇设计
        "platform": {},           # 平台与门面
        "rejected": [],           # 被否决的方案（避免重复提议）
    }


def load(project: Path) -> dict:
    """读取框架；不存在时返回空框架骨架（不落盘）。"""
    data = read_json(project / FRAMEWORK_FILE, default=None)
    if not isinstance(data, dict):
        return empty_framework()
    base = empty_framework()
    base.update(data)
    return base


def save(project: Path, data: dict) -> dict:
    data["updated_at"] = now_iso()
    safe_write_json(project / FRAMEWORK_FILE, data)
    return data


def exists(project: Path) -> bool:
    return (project / FRAMEWORK_FILE).is_file()


def set_stage(project: Path, stage: str) -> dict:
    """记录构思进度。"""
    if stage not in STAGES:
        raise FrameworkError(f"非法阶段 {stage!r}，可选：{'/'.join(STAGES)}")
    data = load(project)
    data["stage"] = stage
    return save(project, data)


def _shape_warnings(section: str, value) -> list[str]:
    """写入前的结构校验（非阻塞）。

    目的：抓住「把 dict 版块写成字符串」这类静默失败——写进去不报错，
    但后续体检读不到字段、告警静默失效，是长篇框架里最危险的坑。
    只对强结构约束的关键点告警，允许用户自由扩展额外字段。
    """
    out: list[str] = []
    if section == "engine":
        if not isinstance(value, dict):
            out.append("engine 应为对象（dict），含 loop 与 drive_wheels")
        else:
            loop = value.get("loop")
            if loop is not None and not isinstance(loop, dict):
                out.append("engine.loop 应为对象 {gain,end,drive,diagram}；写成字符串会让「核心循环未闭合」体检静默失效")
            elif isinstance(loop, dict):
                for k, label in (("gain", "每轮获得"), ("end", "每轮终点"), ("drive", "驱动力")):
                    if not loop.get(k):
                        out.append(f"engine.loop.{k}（{label}）为空——这是百万字尺度的关键体检项")
            wheels = value.get("drive_wheels")
            if wheels is not None and not isinstance(wheels, dict):
                out.append("engine.drive_wheels 应为对象 {power,world,conflict,payoff}")
    elif section == "ladder":
        steps = value.get("steps") if isinstance(value, dict) else None
        if isinstance(value, dict) and steps is not None and not isinstance(steps, list):
            out.append("ladder.steps 应为数组（每阶一个对象），而不是其它类型")
    elif section == "rhythm":
        if isinstance(value, dict):
            for k, label in (("wave_period", "抑扬波周期"), ("difficulty_step", "难度梯度")):
                v = value.get(k)
                if v not in (None, "") and not isinstance(v, (int, float)):
                    out.append(f"rhythm.{k}（{label}）应是数字（万字/%），写字符串会让节奏体检失效")
    elif section == "structure":
        if isinstance(value, dict):
            vols = value.get("volumes")
            if vols is not None and not isinstance(vols, list):
                out.append("structure.volumes 应为数组")
            elif isinstance(vols, list):
                for i, vol in enumerate(vols):
                    if isinstance(vol, dict) and not vol.get("chapters"):
                        out.append(f"structure.volumes[{i}] 缺少 chapters（章节范围）——一致性校验 C04 需要它")
    elif section == "characters":
        if not isinstance(value, list):
            out.append("characters 应为数组（每个角色一个对象），而不是对象包一层")
    elif section == "reveal":
        if not isinstance(value, list):
            out.append("reveal 应为数组（每条揭示一个对象），而不是对象包一层")
    return out


def set_section(project: Path, section: str, value) -> dict:
    """写入框架某版块（整块替换）。

    返回 {"saved": True, "size": n, "shape_warnings": [...]}。
    shape_warnings 非阻塞：结构可疑时仍然写入，但明确告知，避免静默失败。
    """
    valid = {s[0] for s in SECTIONS}
    if section not in valid:
        raise FrameworkError(f"非法版块 {section!r}，可选：{'/'.join(sorted(valid))}")
    shape = _shape_warnings(section, value)
    data = load(project)
    data[section] = value
    saved = save(project, data)
    result = {"saved": True, "size": len(value) if hasattr(value, "__len__") else 1}
    if shape:
        result["shape_warnings"] = shape
    return result


def add_rejected(project: Path, idea: str, reason: str = "") -> dict:
    """登记被否决的方案，避免反复提议同一个被否过的方向。"""
    data = load(project)
    data.setdefault("rejected", []).append({"idea": idea, "reason": reason, "at": now_iso()})
    return save(project, data)


def _section_status(data: dict, key: str) -> tuple[bool, str]:
    """判断某版块是否已成型，返回 (是否完整, 摘要)。"""
    v = data.get(key)
    if key == "characters":
        n = len(v) if isinstance(v, list) else 0
        return (n >= 3, f"{n} 位核心角色" + ("" if n >= 3 else "（建议 ≥3，含主角/对手/影响者）"))
    if key == "reveal":
        n = len(v) if isinstance(v, list) else 0
        return (n >= 1, f"{n} 条揭示项")
    if not v:
        return (False, "未填写")
    # dict 版块：看关键字段是否非空
    required = {
        "core": ["protagonist", "goal", "obstacle", "catalyst", "one_liner"],
        "engine": ["loop", "drive_wheels"],
        "theme": ["question", "thesis", "antithesis", "synthesis"],
        "ladder": ["steps"],
        "structure": ["acts", "volumes"],
        "rhythm": ["wave_period", "difficulty_step"],
        "midgame": ["hidden_identity", "erased_history", "unseen_faction"],
        "opening": ["ch1", "ch2", "ch3"],
        "platform": ["target"],
    }.get(key, [])
    missing = [k for k in required if not v.get(k)]
    if missing:
        return (False, f"缺少字段：{'/'.join(missing)}")
    return (True, "已完整")


def _check_longform(data: dict, project: Path) -> tuple[list[str], list[str]]:
    """百万字尺度体检：返回 (warnings 告警, hints 提示)。

    这些规则来自长篇创作方法论，用来在动笔前发现「撑不到一百万字的隐患」：
    - 核心循环的「获得」环为空 → 读者三章后觉得主角在瞎忙
    - 四驱动轮无配比 → 纯实力引擎的书 60 万字后必单调
    - 阶梯表台阶 < 5 → 撑不住 50 万字
    - 抑扬波周期过密/过疏 → 情绪失控
    - 中期三件套缺失 → 30 万字后无弹药
    """
    warnings: list[str] = []
    hints: list[str] = []
    book = read_json(project / "book.json", default={})
    target_ch = int((book.get("target") or {}).get("total_chapters") or 0)
    wpc = int((book.get("target") or {}).get("words_per_chapter") or 0)
    total_words = target_ch * wpc if (target_ch and wpc) else 0

    engine = data.get("engine") or {}
    if engine:
        loop = engine.get("loop") or {}
        if isinstance(loop, dict):
            if not loop.get("gain"):
                warnings.append("核心循环的「获得」一环为空——读者三章后会觉得主角在瞎忙，必须写清每轮循环获得什么（成长/资源/情报）")
            if not loop.get("end"):
                warnings.append("核心循环的「终点」未写明——每轮循环应导向新挑战/新敌人/新地图")
            if not loop.get("drive"):
                warnings.append("核心循环的「驱动力」未写明——复仇？守护？求知？变强？这是支撑百万字的底层情绪")
        wheels = engine.get("drive_wheels") or {}
        if isinstance(wheels, dict) and wheels:
            total = 0
            for k in ("power", "world", "conflict", "payoff"):
                try:
                    total += int(wheels.get(k) or 0)
                except (TypeError, ValueError):
                    pass
            if total == 0:
                warnings.append("四驱动轮未给出配比——建议实力/世界/矛盾/爽点四轮各给百分比（如 60/20/10/10）")
            elif total != 100:
                hints.append(f"四驱动轮配比合计 {total}（≠100），建议归一化以便看清这本书的气质偏哪一极")
            else:
                try:
                    conflict = int(wheels.get("conflict") or 0)
                except (TypeError, ValueError):
                    conflict = 0
                if conflict < 10:
                    hints.append("矛盾冲突引擎占比过低——读者可能说不出「为什么还要看下去」，建议下一卷专门补一条矛盾线")

    ladder = data.get("ladder") or {}
    steps = ladder.get("steps") if isinstance(ladder, dict) else None
    if isinstance(steps, list) and steps:
        if len(steps) < 5:
            warnings.append(f"阶梯表只有 {len(steps)} 阶——少于 5 阶撑不住 50 万字，建议补到 5-7 阶")

    rhythm = data.get("rhythm") or {}
    if rhythm:
        period = rhythm.get("wave_period")
        try:
            pw = int(period) if period is not None else 0
        except (TypeError, ValueError):
            pw = 0
        if pw:
            if pw < 8:
                warnings.append(f"抑扬波周期 {pw} 万字偏密（参考 10-20 万字一轮）——情绪没有山谷就没有山峰")
            elif pw > 25:
                hints.append(f"抑扬波周期 {pw} 万字偏疏——读者可能在中途感到「越来越平」")
        step = rhythm.get("difficulty_step")
        try:
            ds = int(step) if step is not None else 0
        except (TypeError, ValueError):
            ds = 0
        if ds and not (15 <= ds <= 35):
            hints.append(f"难度梯度 {ds}% 偏离黄金比例（参考每次 +20%~30%）")

    if total_words >= 500000:
        mid = data.get("midgame") or {}
        missing_mid = [k for k, label in [("hidden_identity", "身世伏笔"),
                                          ("erased_history", "被抹去的历史"),
                                          ("unseen_faction", "未登场的势力")]
                        if not (isinstance(mid, dict) and mid.get(k))]
        if missing_mid:
            warnings.append(f"目标 {total_words//10000} 万字的长篇缺少「中期三件套」中的：{'、'.join(missing_mid)}——这是 30 万字之后的弹药库")

    return warnings, hints


def audit(project: Path) -> dict:
    """框架完整度体检：逐版块检查，给出缺口清单与建议下一步。"""
    data = load(project)
    rows, missing = [], []
    for key, name, desc in SECTIONS:
        ok, summary = _section_status(data, key)
        rows.append({"section": key, "name": name, "filled": ok,
                     "summary": summary, "requirement": desc})
        if not ok:
            missing.append(key)

    # 一致性校验：分卷章节数是否与总目标匹配
    warnings: list[str] = []
    vols = (data.get("structure") or {}).get("volumes") or []
    if isinstance(vols, list) and vols:
        total_ch = 0
        for v in vols:
            if not isinstance(v, dict):
                warnings.append("分卷条目应为对象（含 name/chapters/goal/theme_question），当前有非对象项")
                continue
            rng = v.get("chapters") or ""
            if isinstance(rng, str) and "-" in rng:
                try:
                    a, b = rng.split("-")[:2]
                    total_ch += int(b.strip()) - int(a.strip()) + 1
                except (ValueError, IndexError):
                    warnings.append(f"卷「{v.get('name', '?')}」章节范围格式不规范（应如 1-40）")
        book = read_json(project / "book.json", default={})
        target = (book.get("target") or {}).get("total_chapters")
        if target and total_ch and abs(total_ch - int(target)) > max(10, int(target) * 0.1):
            warnings.append(f"各卷章节数合计 {total_ch} 与目标总章数 {target} 差异较大，建议核对")

    # 主题是否贯穿分卷
    if data.get("theme") and isinstance(vols, list):
        for v in vols:
            if not isinstance(v, dict):
                continue
            if not v.get("theme_question"):
                warnings.append(f"卷「{v.get('name', '?')}」未标注本卷对主题的新问法")

    # 百万字尺度体检
    lf_warn, lf_hint = _check_longform(data, project)
    warnings.extend(lf_warn)
    hints = lf_hint

    next_stage = missing[0] if missing else "done"
    return {
        "stage": data.get("stage", "core"),
        "complete": not missing,
        "sections": rows,
        "missing": missing,
        "warnings": warnings,
        "hints": hints,
        "next_action": _next_hint(next_stage),
        "rejected_count": len(data.get("rejected") or []),
    }


def _next_hint(stage: str) -> str:
    if stage == "done":
        return "框架已成型，可以开始设计开篇并进入章节创作流程"
    names = {k: n for k, n, _ in SECTIONS}
    return f"下一步：完成「{names.get(stage, stage)}」（见 references/brainstorming-workflow.md 对应阶段）"


def _row(item, *keys) -> str:
    """把一条记录渲染成 `k1 | k2 | ...`，兼容 dict 与纯字符串两种写法。

    框架的 list 版块（acts/chars/steps/reveal）允许作者写「对象」或「一句话」，
    渲染时都必须能落地，不能因为写了字符串就崩。
    """
    if isinstance(item, dict):
        return " | ".join(str(item.get(k, "") or "") for k in keys)
    return str(item or "")


def render_md(data: dict) -> str:
    """把框架渲染为人类可读 Markdown（供作者审阅整份蓝图）。"""
    lines = ["# 全书框架蓝图", ""]
    core = data.get("core") or {}
    if core:
        lines += ["## 故事内核", ""]
        if core.get("one_liner"):
            lines += [f"> {core['one_liner']}", ""]
        for k, label in [("protagonist", "主角"), ("goal", "想要什么"),
                         ("obstacle", "什么在阻止他"), ("catalyst", "为什么是现在")]:
            if core.get(k):
                lines.append(f"- **{label}**：{core[k]}")
        lines.append("")

    theme = data.get("theme") or {}
    if theme:
        lines += ["## 主题与内核矛盾", ""]
        if theme.get("question"):
            lines.append(f"- **主题句（无标准答案的问题）**：{theme['question']}")
        for k, label in [("thesis", "正题（主角起初相信）"),
                         ("antithesis", "反题（世界的答案）"),
                         ("synthesis", "合题（结尾给出的、有代价的答案）")]:
            if theme.get(k):
                lines.append(f"- **{label}**：{theme[k]}")
        lines.append("")

    engine = data.get("engine") or {}
    if engine:
        lines += ["## 核心循环与驱动轮", ""]
        loop = engine.get("loop") or {}
        if isinstance(loop, dict) and loop:
            lines += ["**核心循环**（长篇的永动机，必须闭合）", "",
                      "| 环节 | 内容 |", "|---|---|"]
            for k, label in [("gain", "每轮获得什么"), ("end", "每轮终点"),
                             ("drive", "驱动力")]:
                lines.append(f"| {label} | {loop.get(k, '')} |")
            lines.append("")
            if loop.get("diagram"):
                lines += [f"> 循环图：{loop['diagram']}", ""]
        wheels = engine.get("drive_wheels") or {}
        if isinstance(wheels, dict) and wheels:
            lines += ["**四驱动轮配比**", "",
                      "| 引擎 | 占比 | 说明 |", "|---|---|---|"]
            for k, label in [("power", "实力提升"), ("world", "世界扩展"),
                             ("conflict", "矛盾冲突"), ("payoff", "爽点释放")]:
                if wheels.get(k):
                    lines.append(f"| {label} | {wheels[k]}% | {wheels.get(k + '_note', '')} |")
            lines.append("")
        ext = engine.get("extensibility") or {}
        if isinstance(ext, dict) and ext:
            lines += ["**延展性三问自检**", ""]
            for k, label in [("tiers", "「变强」能分出几个可命名档次（<5 撑不住 50 万字）"),
                             ("stages", "每档能否对应不同舞台/敌人形态"),
                             ("beyond", "除「打赢」外第二种期待（真相/选择/代价）")]:
                if ext.get(k):
                    lines.append(f"- {label}：{ext[k]}")
            lines.append("")

    chars = data.get("characters") or []
    if chars:
        lines += ["## 人物关系网", "",
                  "| 角色 | 与主角的关系（力的方向） | 自己的目标 | 承载的主题面 | 声线锚点 |",
                  "|---|---|---|---|---|"]
        for c in chars:
            lines.append("| " + _row(c, "name", "relation", "own_goal", "theme_face", "voice") + " |")
        lines.append("")

    ladder = data.get("ladder") or {}
    steps = ladder.get("steps") if isinstance(ladder, dict) else None
    if isinstance(steps, list) and steps:
        lines += ["## 可攀越的世界观（阶梯表）", "",
                  "| 阶 | 舞台 | 主角实力上限 | 主要对手 | 核心资源 | 该阶解开的秘密 |",
                  "|---|---|---|---|---|---|"]
        for s in steps:
            lines.append("| " + _row(s, "name", "stage", "power", "enemy", "resource", "secret") + " |")
        lines.append("")

    struct = data.get("structure") or {}
    if struct:
        lines += ["## 结构蓝图", ""]
        for act in (struct.get("acts") or []):
            if isinstance(act, dict):
                lines.append(f"- **{act.get('name', '')}**：{act.get('content', '')}")
            else:
                lines.append(f"- {act}")
        vols = struct.get("volumes") or []
        if vols:
            lines += ["", "| 卷 | 章节范围 | 卷内目标 | 卷末高潮 | 主角的本质变化 | 主题新问法 |",
                      "|---|---|---|---|---|---|"]
            for v in vols:
                lines.append("| " + _row(v, "name", "chapters", "goal", "climax", "change", "theme_question") + " |")
        lines.append("")

    reveal = data.get("reveal") or []
    if reveal:
        lines += ["## 信息揭示表", "",
                  "| 秘密 | 揭示位置 | 由谁揭示 | 前置铺垫 |", "|---|---|---|---|"]
        for r in reveal:
            lines.append("| " + _row(r, "secret", "at", "by", "foreshadow") + " |")
        lines.append("")

    rhythm = data.get("rhythm") or {}
    if rhythm:
        lines += ["## 节奏与情绪波", ""]
        if rhythm.get("wave_period"):
            lines.append(f"- **抑扬波周期**：每 {rhythm['wave_period']} 万字一轮完整的抑→扬→更大的抑→更大的扬")
        if rhythm.get("difficulty_step"):
            lines.append(f"- **难度梯度**：每次提升 {rhythm['difficulty_step']}%（黄金比例 20%~30%）")
        if rhythm.get("breather_rule"):
            lines.append(f"- **呼吸章纪律**：{rhythm['breather_rule']}")
        if rhythm.get("ratio_note"):
            lines.append(f"- **节奏比例**：{rhythm['ratio_note']}")
        waves = rhythm.get("waves") or []
        if isinstance(waves, list) and waves:
            lines += ["", "| 抑扬波 | 覆盖章节 | 抑点 | 扬点 | 主要情绪 |",
                      "|---|---|---|---|---|"]
            for w in waves:
                lines.append("| " + _row(w, "name", "chapters", "low", "high", "mood") + " |")
        lines.append("")

    mid = data.get("midgame") or {}
    if mid:
        lines += ["## 中期弹药库（防空转 / 防人设崩）", ""]
        for k, label in [("hidden_identity", "开篇就埋下的身世伏笔"),
                         ("erased_history", "一段被抹去的历史"),
                         ("unseen_faction", "一个还没登场的势力阵营")]:
            if mid.get(k):
                lines.append(f"- **{label}**：{mid[k]}")
        truths = mid.get("cognitive_truths") or []
        if isinstance(truths, list) and truths:
            lines += ["", "**认知线五真相**（每跑完两轮实力循环解锁一个，用来续命 60 万字之后）", ""]
            for i, t in enumerate(truths, 1):
                lines.append(f"{i}. {t if isinstance(t, str) else t.get('truth', t)}")
        lines.append("")

    platform = data.get("platform") or {}
    if platform:
        lines += ["## 平台与门面", ""]
        if platform.get("target"):
            lines.append(f"- **目标平台**：{platform['target']}")
        if platform.get("reader_want"):
            lines.append(f"- **该平台读者第 1 章最想看到**：{platform['reader_want']}")
        if platform.get("update_plan"):
            lines.append(f"- **更新计划**：{platform['update_plan']}")
        titles = platform.get("titles") or []
        if isinstance(titles, list) and titles:
            lines.append(f"- **备选书名**：{' / '.join(str(t) for t in titles)}")
        blurbs = platform.get("blurbs") or []
        if isinstance(blurbs, list) and blurbs:
            lines += ["", "**简介版本**", ""]
            for i, b in enumerate(blurbs, 1):
                lines.append(f"{i}. {b}")
        lines.append("")

    opening = data.get("opening") or {}
    if opening:
        lines += ["## 开篇设计", ""]
        for k, label in [("ch1", "第 1 章"), ("ch2", "第 2 章"), ("ch3", "第 3 章")]:
            if opening.get(k):
                lines.append(f"- **{label}**：{opening[k]}")
        lines.append("")

    rej = data.get("rejected") or []
    if rej:
        lines += ["## 已否决的方案（不再重复提议）", ""]
        for r in rej:
            lines.append(f"- ~~{r.get('idea', '')}~~" + (f"：{r['reason']}" if r.get("reason") else ""))
    return "\n".join(lines).rstrip() + "\n"
