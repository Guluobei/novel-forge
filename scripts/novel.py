#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""novel-forge：网络小说确定性创作管理工具链（唯一 CLI 入口）。

用法：
    python3 novel.py init <path> --name 书名
    python3 novel.py chapter new --title 雨夜        # 在项目目录内运行
    python3 novel.py check 3 --json                  # 第 3 章质量门禁
    python3 novel.py --help

约定：
- 项目定位：--project 指定，或从当前目录向上查找 book.json
- 输出：默认人类可读；--json 输出 {"ok":true,"data":...} 信封
- 退出码：0 成功 / 1 门禁不通过 / 2 参数或业务错误 / 3 未找到项目
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from novel_lib import (  # noqa: E402
    ai_provider,
    chapter as chapter_mod,
    consistency as consistency_mod,
    context as context_mod,
    foreshadow as foreshadow_mod,
    framework as framework_mod,
    gate as gate_mod,
    lexicon as lexicon_mod,
    project as project_mod,
    settings as settings_mod,
    stats as stats_mod,
    visualize as viz_mod,
    wholebook as wholebook_mod,
)
from novel_lib.chapter import ChapterError  # noqa: E402
from novel_lib.consistency import ConsistencyError  # noqa: E402
from novel_lib.foreshadow import ForeshadowError  # noqa: E402
from novel_lib.framework import FrameworkError  # noqa: E402
from novel_lib.lexicon import LexiconError  # noqa: E402
from novel_lib.models import JsonIOError  # noqa: E402
from novel_lib.project import ProjectNotFound  # noqa: E402
from novel_lib.settings import SettingError  # noqa: E402

EXIT_OK, EXIT_GATE, EXIT_ARGS, EXIT_NO_PROJECT = 0, 1, 2, 3

_exit_code_holder = {"code": EXIT_OK}


# ---------------------------------------------------------------- 输出渲染

def emit(args, data) -> None:
    """统一输出：--json 信封 or 人类可读。"""
    if getattr(args, "json", False):
        print(json.dumps({"ok": _exit_code_holder["code"] != EXIT_GATE or data.get("passed", True),
                          "data": data}, ensure_ascii=False, indent=2))
    else:
        text = render(data)
        if text:
            print(text)


def render(data) -> str:
    """dict → 人类可读文本（键值 + 表格的朴素渲染）。"""
    if data is None:
        return ""
    if not isinstance(data, dict):
        return str(data)
    lines: list[str] = []
    tables = []
    simple: dict = {}
    for k, v in data.items():
        if k == "reports" and isinstance(v, list) and v and isinstance(v[0], dict):
            continue  # check all 的逐章明细在 JSON 里看
        if isinstance(v, list) and v and isinstance(v[0], dict):
            tables.append((k, v))
        elif isinstance(v, dict):
            sub = render(v)
            lines.append(f"{k}:")
            lines.extend("  " + l for l in sub.split("\n"))
        else:
            simple[k] = v
    if simple:
        w = max((len(str(k)) for k in simple), default=0)
        for k, v in simple.items():
            lines.append(f"{str(k):<{w}}  {v}")
    for key, rows in tables:
        lines.append(f"\n[{key}]")
        headers = list(rows[0].keys())
        widths = [len(h) for h in headers]
        for r in rows:
            for i, h in enumerate(headers):
                widths[i] = min(60, max(widths[i], len(str(r.get(h, "")))))
        lines.append("  ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
        lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
        for r in rows:
            lines.append("  ".join(str(r.get(h, "")).ljust(widths[i])[:60] for i, h in enumerate(headers)))
    return "\n".join(lines)


def render_check(report: dict) -> str:
    """单章门禁报告的紧凑人类可读渲染。"""
    score_txt = f"{report['score']}/100" if report.get("score") is not None else "—"
    lines = [
        f"第 {report['chapter']} 章《{report['title']}》 门禁报告",
        f"字数 {report['words']}  评分 {score_txt}  结论 {report['verdict']}"
        f"（error {report['errors']} / warn {report['warns']} / info {report['infos']}）",
        "",
    ]
    rmap = report.get("revision_map") or []
    if rmap:
        lines.append("── 修订优先级（先改热力最高段）──")
        for i, slot in enumerate(rmap, 1):
            lines.append(f"{i}. 🔥{slot['heat']} 段{slot['para']}(L{slot['lines']}) "
                         f"[{'+'.join(slot['rules'])}] {slot['excerpt']}")
            for a in slot["advice"][:2]:
                lines.append(f"   ↳ {a}")
        lines.append("")
    lines.append("── 规则明细 ──")
    for r in report["rules"]:
        mark = "✅" if r["passed"] else "❌"
        lim = f"/{r['limit']}" if r["limit"] is not None else ""
        lines.append(f"{mark} {r['rule_id']} {r['name']:<10} [{r['level']}] "
                     f"{r['count']}{lim}  {r['message']}")
        for v in r["violations"][:8]:
            lines.append(f"     L{v['line']}  {v['excerpt']}")
    cons = report.get("consistency")
    if cons:
        lines += ["", consistency_mod.render_consistency_md(cons).rstrip()]
    return "\n".join(lines)


# ---------------------------------------------------------------- 参数解析

def build_parser() -> argparse.ArgumentParser:
    # 公共参数：主命令与所有子命令位置均可使用（--json / --project 放哪层都行）
    # default 用 SUPPRESS：用户未显式提供时不覆盖上层已解析的值（getattr 兜底取值）
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=argparse.SUPPRESS,
                        help="项目根目录（缺省则从当前目录向上查找 book.json）")
    common.add_argument("--json", default=argparse.SUPPRESS, action="store_true",
                        help="以 JSON 信封输出")

    p = argparse.ArgumentParser(prog="novel.py",
                                parents=[common],
                                description="novel-forge 网络小说创作管理工具链")
    sub = p.add_subparsers(dest="command", required=True)

    # init（不需要项目定位）
    sp = sub.add_parser("init", parents=[common], help="初始化小说项目")
    sp.add_argument("path", help="项目路径（不存在则创建）")
    sp.add_argument("--name", required=True, help="书名")
    sp.add_argument("--genre", default="", help="题材")
    sp.add_argument("--author", default="", help="作者")
    sp.add_argument("--target-chapters", type=int, default=300, help="目标总章数")
    sp.add_argument("--words-per-chapter", type=int, default=3000, help="目标每章字数")
    sp.set_defaults(func=cmd_init)

    _project_cmd(sub.add_parser("info", parents=[common], help="项目概览"), cmd_info)

    # framework（全书框架 / 构思协作）
    sp = sub.add_parser("framework", parents=[common], help="全书框架：内核/主题/人物网/分卷/揭示表")
    fwsub = sp.add_subparsers(dest="sub", required=True)
    f = fwsub.add_parser("show", parents=[common], help="展示完整框架蓝图")
    f.set_defaults(func=cmd_framework_show)
    f = fwsub.add_parser("audit", parents=[common], help="框架完整度体检")
    f.set_defaults(func=cmd_framework_audit)
    f = fwsub.add_parser("stage", parents=[common], help="记录/查看构思进度")
    f.add_argument("name", nargs="?", default=None,
                   choices=framework_mod.STAGES, help="要设置的阶段（缺省只看）")
    f.set_defaults(func=cmd_framework_stage)
    f = fwsub.add_parser("set", parents=[common], help="写入框架版块（值为 JSON 或文本）")
    f.add_argument("section", choices=[s[0] for s in framework_mod.SECTIONS])
    f.add_argument("--file", default=None, help="从 JSON 文件读入整块内容")
    f.add_argument("--value", default=None, help="直接提供 JSON 或字符串值")
    f.set_defaults(func=cmd_framework_set)
    f = fwsub.add_parser("reject", parents=[common], help="登记被否决的方案（避免重复提议）")
    f.add_argument("--idea", required=True)
    f.add_argument("--reason", default="")
    f.set_defaults(func=cmd_framework_reject)
    f = fwsub.add_parser("path", parents=[common], help="打印框架文件路径")
    f.set_defaults(func=cmd_framework_path)

    # setting
    sp = sub.add_parser("setting", parents=[common], help="设定管理（角色卡等）")
    ssub = sp.add_subparsers(dest="sub", required=True)
    s = ssub.add_parser("add", parents=[common], help="登记角色卡"); s.add_argument("type_", choices=["character"], help="类型")
    s.add_argument("--name", required=True); s.add_argument("--role", default="配角")
    s.set_defaults(func=cmd_setting_add)
    s = ssub.add_parser("list", parents=[common], help="列出设定"); s.add_argument("--type", default=None)
    s.set_defaults(func=cmd_setting_list)
    s = ssub.add_parser("get", parents=[common], help="查看角色卡"); s.add_argument("type_", choices=["character"])
    s.add_argument("name"); s.set_defaults(func=cmd_setting_get)
    s = ssub.add_parser("update", parents=[common], help="更新角色卡字段")
    s.add_argument("type_", choices=["character"]); s.add_argument("name")
    s.add_argument("--set", action="append", required=True, metavar="K=V", help="可多次")
    s.set_defaults(func=cmd_setting_update)
    s = ssub.add_parser("search", parents=[common], help="设定全文搜索"); s.add_argument("keyword")
    s.set_defaults(func=cmd_setting_search)

    # chapter
    sp = sub.add_parser("chapter", parents=[common], help="章节管理")
    csub = sp.add_subparsers(dest="sub", required=True)
    c = csub.add_parser("new", parents=[common], help="创建新章")
    c.add_argument("--number", type=int, default=None, help="章号（缺省为最新章+1）")
    c.add_argument("--title", required=True)
    c.set_defaults(func=cmd_chapter_new)
    c = csub.add_parser("list", parents=[common], help="列出章节"); c.add_argument("--status", default=None)
    c.set_defaults(func=cmd_chapter_list)
    c = csub.add_parser("stats", parents=[common], help="字数统计")
    c.add_argument("target", nargs="?", default="all", help="章号或 all")
    c.set_defaults(func=cmd_chapter_stats)
    c = csub.add_parser("set-status", parents=[common], help="更新章节状态")
    c.add_argument("no", type=int); c.add_argument("--status", required=True)
    c.set_defaults(func=cmd_chapter_set_status)
    c = csub.add_parser("set-hook", parents=[common], help="登记章节钩子类型")
    c.add_argument("no", type=int); c.add_argument("--hook", required=True)
    c.set_defaults(func=cmd_chapter_set_hook)
    c = csub.add_parser("insert", parents=[common], help="在第 N 章前插入新章（自动重编号）")
    c.add_argument("--before", type=int, required=True)
    c.add_argument("--title", required=True)
    c.add_argument("--dry-run", action="store_true", help="只预览不执行")
    c.add_argument("--no-shift-foreshadow", action="store_true", help="伏笔册章号不联动")
    c.set_defaults(func=cmd_chapter_insert)
    c = csub.add_parser("renumber", parents=[common], help="全书章号连续重排")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--check", action="store_true", help="只校验不修改")
    c.set_defaults(func=cmd_chapter_renumber)
    c = csub.add_parser("spec", help="章节 spec：查看/写入章级创作锚点")
    c.add_argument("no", type=int)
    c.add_argument("--init", action="store_true", help="生成骨架 spec 文件")
    c.add_argument("--file", default=None, help="从 JSON 文件导入整份 spec")
    c.add_argument("--set", action="append", default=None, metavar="K=V",
                   help="更新单字段（V 为 JSON 或字符串），可多次")
    c.set_defaults(func=cmd_chapter_spec)

    # foreshadow
    sp = sub.add_parser("foreshadow", parents=[common], help="伏笔登记册")
    fsub = sp.add_subparsers(dest="sub", required=True)
    f = fsub.add_parser("add", parents=[common], help="登记伏笔")
    f.add_argument("--desc", required=True)
    f.add_argument("--planted-chapter", type=int, required=True)
    f.add_argument("--expected-recover", type=int, required=True)
    f.add_argument("--priority", default="main", choices=foreshadow_mod.PRIORITIES)
    f.set_defaults(func=cmd_foreshadow_add)
    f = fsub.add_parser("list", parents=[common], help="列出伏笔")
    f.add_argument("--status", default=None,
                   help="planted/recovered/overdue/severe")
    f.set_defaults(func=cmd_foreshadow_list)
    f = fsub.add_parser("recover", parents=[common], help="标记回收")
    f.add_argument("id"); f.add_argument("--chapter", type=int, required=True)
    f.set_defaults(func=cmd_foreshadow_recover)
    f = fsub.add_parser("audit", parents=[common], help="伏笔预警检查")
    f.set_defaults(func=cmd_foreshadow_audit)

    # gate
    sp = sub.add_parser("check", parents=[common], help="质量门禁检查")
    sp.add_argument("target", nargs="?", default="all", help="章号或 all")
    sp.add_argument("--strict", action="store_true", help="warn 也判不通过")
    sp.add_argument("--rules", action="store_true", help="显示合并后生效的规则与词表")
    sp.add_argument("--consistency", action="store_true",
                    help="额外做框架一致性校验（C01-C05：卷目标/角色动机/伏笔进度/卷范围/主题）")
    sp.set_defaults(func=cmd_check)
    sp = sub.add_parser("report", parents=[common], help="执行门禁并落盘报告到 reports/")
    sp.add_argument("target", nargs="?", default="all")
    sp.add_argument("--strict", action="store_true")
    sp.add_argument("--consistency", action="store_true", help="同时做框架一致性校验")
    sp.set_defaults(func=cmd_report)

    # context（生成上下文装配）
    sp = sub.add_parser("context", parents=[common], help="装配本章生成上下文（spec/声线卡/前章衔接/伏笔）")
    sp.add_argument("no", type=int, help="章号")
    sp.add_argument("--tail", type=int, default=500, metavar="N", help="上一章结尾截取字数")
    sp.add_argument("--save", action="store_true", help="同时落盘到 reports/context_chNNNN.md")
    sp.set_defaults(func=cmd_context)

    # stats
    sp = sub.add_parser("stats", parents=[common], help="全书统计")
    sp.add_argument("--daily", type=int, default=0, metavar="N", help="近 N 天日产出")
    sp.set_defaults(func=cmd_stats)
    _project_cmd(sub.add_parser("progress", parents=[common], help="写作进度"), cmd_progress)

    # dashboard（进度可视化）
    sp = sub.add_parser("dashboard", parents=[common],
                        help="进度看板：全书/分卷进度条 + 日产出 + 字数分布")
    sp.add_argument("--days", type=int, default=7, metavar="N", help="日产出回看天数（0 关闭）")
    sp.add_argument("--width", type=int, default=48, metavar="W", help="图表宽度（列）")
    sp.add_argument("--no-daily", action="store_true", help="隐藏日产出")
    sp.add_argument("--no-volumes", action="store_true", help="隐藏分卷进度")
    sp.add_argument("--no-dist", action="store_true", help="隐藏字数分布")
    sp.add_argument("--md", action="store_true", help="以 Markdown 代码块输出（便于存档）")
    sp.set_defaults(func=cmd_dashboard)

    # health（全书体检：跨章趋势）
    _project_cmd(sub.add_parser("health", parents=[common],
                                help="全书体检：爽点密度/钩子多样性/空转风险/字数离群"),
                 cmd_health)

    # ai
    sp = sub.add_parser("ai", parents=[common], help="AI 能力状态（v1 预留）")
    asub = sp.add_subparsers(dest="sub", required=True)
    a = asub.add_parser("status", parents=[common]); a.set_defaults(func=cmd_ai_status)
    a = asub.add_parser("test", parents=[common]); a.set_defaults(func=cmd_ai_test)

    return p


def _project_cmd(sp, func):
    sp.set_defaults(func=func)


def _project(args) -> Path:
    return project_mod.find_project(getattr(args, "project", None))


# ---------------------------------------------------------------- 命令实现

def cmd_init(args):
    data = project_mod.init(args.path, args.name, args.genre, args.author,
                            args.target_chapters, args.words_per_chapter)
    return {**data, "hint": f"cd {data['project_root']} 后即可使用其余命令"}


def cmd_info(args):
    return project_mod.project_info(_project(args))


# ---------------------------------------------------------------- framework

def cmd_framework_show(args):
    proj = _project(args)
    data = framework_mod.load(proj)
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False, indent=2))
    else:
        print(framework_mod.render_md(data))
    return None


def cmd_framework_audit(args):
    proj = _project(args)
    if not framework_mod.exists(proj):
        return {"exists": False,
                "message": "尚未建立框架。请按 references/brainstorming-workflow.md 的阶段 1 开始构思。",
                "next_action": "与作者确认故事内核（阶段 1）"}
    return {"exists": True, **framework_mod.audit(proj)}


def cmd_framework_stage(args):
    proj = _project(args)
    if args.name:
        data = framework_mod.set_stage(proj, args.name)
        return {"stage": data["stage"], "saved": True}
    return {"stage": framework_mod.load(proj).get("stage", "core")}


def cmd_framework_set(args):
    proj = _project(args)
    if args.file:
        value = json.loads(Path(args.file).read_text(encoding="utf-8"))
    elif args.value is not None:
        try:
            value = json.loads(args.value)
        except json.JSONDecodeError:
            value = args.value
    else:
        raise ValueError("需要 --file 或 --value 之一")
    res = framework_mod.set_section(proj, args.section, value)
    return {"section": args.section, **res}


def cmd_framework_reject(args):
    data = framework_mod.add_rejected(_project(args), args.idea, args.reason)
    return {"rejected_count": len(data.get("rejected") or []), "saved": True}


def cmd_framework_path(args):
    proj = _project(args)
    return {"path": str(proj / framework_mod.FRAMEWORK_FILE),
            "exists": framework_mod.exists(proj)}


def cmd_setting_add(args):
    return settings_mod.add_character(_project(args), args.name, args.role)


def cmd_setting_list(args):
    return settings_mod.list_settings(_project(args), args.type)


def cmd_setting_get(args):
    return settings_mod.get_character(_project(args), args.name)


def cmd_setting_update(args):
    sets = []
    for kv in args.set:
        if "=" not in kv:
            raise ValueError(f"--set 需要 K=V 形式，收到 {kv!r}")
        k, v = kv.split("=", 1)
        sets.append((k.strip(), v.strip()))
    return settings_mod.update_character(_project(args), args.name, sets)


def cmd_setting_search(args):
    hits = settings_mod.search_settings(_project(args), args.keyword)
    return {"keyword": args.keyword, "hits": hits, "total": len(hits)}


def cmd_chapter_new(args):
    return chapter_mod.new_chapter(_project(args), args.number, args.title)


def cmd_chapter_list(args):
    chapters = chapter_mod.list_chapters(_project(args), args.status)
    return {"status_filter": args.status, "total": len(chapters), "chapters": chapters}


def cmd_chapter_stats(args):
    return chapter_mod.chapter_stats(_project(args), args.target)


def cmd_chapter_set_status(args):
    return chapter_mod.set_status(_project(args), args.no, args.status)


def cmd_chapter_set_hook(args):
    return chapter_mod.set_hook(_project(args), args.no, args.hook)


def cmd_chapter_insert(args):
    return chapter_mod.insert_chapter(
        _project(args), args.before, args.title,
        dry_run=args.dry_run, shift_foreshadow=not args.no_shift_foreshadow)


def cmd_chapter_renumber(args):
    return chapter_mod.renumber(_project(args), dry_run=args.dry_run, check_only=args.check)


def cmd_chapter_spec(args):
    proj = _project(args)
    if args.file:
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
        return {"saved": True, "spec": chapter_mod.spec_save(proj, args.no, data)}
    if args.set:
        out = None
        for kv in args.set:
            if "=" not in kv:
                raise ValueError(f"--set 需要 K=V 形式，收到 {kv!r}")
            k, v = kv.split("=", 1)
            out = chapter_mod.spec_set(proj, args.no, k.strip(), v.strip())
        return {"saved": True, "spec": out}
    spec = chapter_mod.spec_get(proj, args.no)
    if args.init:
        chapter_mod.spec_save(proj, args.no, spec)
        return {"initialized": True, "spec_file": str(chapter_mod.spec_path(proj, args.no)),
                "spec": spec}
    return {"spec_file": str(chapter_mod.spec_path(proj, args.no)),
            "exists": chapter_mod.spec_path_exists(proj, args.no), "spec": spec}


def cmd_context(args):
    proj = _project(args)
    data = context_mod.build_context(proj, args.no, args.tail)
    if args.save:
        rdir = proj / "reports"
        rdir.mkdir(parents=True, exist_ok=True)
        out = rdir / f"context_ch{args.no:04d}.md"
        out.write_text(context_mod.render_context_md(data), encoding="utf-8")
        data["saved_to"] = str(out)
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False, indent=2))
    else:
        print(context_mod.render_context_md(data))
        if args.save:
            print(f"\n（已保存：{data['saved_to']}）")
    return None


def cmd_foreshadow_add(args):
    return foreshadow_mod.add(_project(args), args.desc,
                             args.planted_chapter, args.expected_recover, args.priority)


def cmd_foreshadow_list(args):
    items = foreshadow_mod.list_items(_project(args), args.status)
    return {"status_filter": args.status, "total": len(items), "items": items}


def cmd_foreshadow_recover(args):
    return foreshadow_mod.recover(_project(args), args.id, args.chapter)


def cmd_foreshadow_audit(args):
    a = foreshadow_mod.audit(_project(args))
    if a["alerts"]:
        a["summary"] = [x["message"] for x in a["alerts"]]
    return a


def _parse_sets(kv_list):
    out = []
    for kv in kv_list:
        if "=" not in kv:
            raise ValueError(f"K=V 形式非法：{kv!r}")
        k, v = kv.split("=", 1)
        out.append((k.strip(), v.strip()))
    return out


def cmd_check(args):
    proj = _project(args)
    if args.rules:
        return {
            "thresholds": gate_mod.gate_thresholds_from_project(proj),
            "hook_types": project_mod.HOOK_TYPES,
            "lexicon": lexicon_mod.load_lexicon(proj),
        }
    if args.target == "all":
        result = gate_mod.check_all(proj, args.strict, args.consistency)
        passed = not result["failed_chapters"]
        if not getattr(args, "json", False):
            lines = [f"全书检查：共 {result['total']} 章，通过 {result['passed']} 章，"
                     f"平均分 {result['avg_score']}", result["verdict"]]
            print("\n".join(lines))
            for r in result["reports"]:
                if r.get("unwritten"):
                    print(f"⏳ 第{r['chapter']:>4}章    —  尚未创作  {r['title']}")
                else:
                    mark = "✅" if (r["strict_passed"] if args.strict else r["passed"]) else "❌"
                    print(f"{mark} 第{r['chapter']:>4}章  {r['score']:>3}分  "
                          f"e{r['errors']}/w{r['warns']}/i{r['infos']}  {r['title']}")
        else:
            print(json.dumps({"ok": passed, "data": result}, ensure_ascii=False, indent=2))
        _exit_code_holder["code"] = EXIT_OK if passed else EXIT_GATE
        return None
    no = int(args.target)
    report = gate_mod.check_chapter(proj, no, args.strict, args.consistency)
    passed = report["strict_passed"] if args.strict else report["passed"]
    if not getattr(args, "json", False):
        print(render_check(report))
    else:
        print(json.dumps({"ok": passed, "data": report}, ensure_ascii=False, indent=2))
    _exit_code_holder["code"] = EXIT_OK if passed else EXIT_GATE
    return None


def cmd_report(args):
    proj = _project(args)
    if args.target == "all":
        result = gate_mod.check_all(proj, args.strict, args.consistency)
        saved = [gate_mod.save_report(proj, r) for r in result["reports"]]
        passed = not result["failed_chapters"]
        data = {**result, "saved": saved, "report_dir": str(proj / "reports")}
    else:
        no = int(args.target)
        report = gate_mod.check_chapter(proj, no, args.strict, args.consistency)
        saved = gate_mod.save_report(proj, report)
        passed = report["strict_passed"] if args.strict else report["passed"]
        data = {"chapter_report": report, "saved": saved}
    if not getattr(args, "json", False):
        print(render(data))
    else:
        print(json.dumps({"ok": passed, "data": data}, ensure_ascii=False, indent=2))
    _exit_code_holder["code"] = EXIT_OK if passed else EXIT_GATE
    return None


def cmd_stats(args):
    proj = _project(args)
    data = stats_mod.overall_stats(proj)
    if args.daily:
        data["daily"] = stats_mod.daily_words(proj, args.daily)
    return data


def cmd_progress(args):
    return stats_mod.progress(_project(args))


def cmd_dashboard(args):
    proj = _project(args)
    dash = viz_mod.build_dashboard(proj, args.days)
    if getattr(args, "json", False):
        print(json.dumps({"ok": True, "data": dash}, ensure_ascii=False, indent=2))
        return None
    text = viz_mod.render_dashboard(
        dash, width=args.width,
        show_daily=not args.no_daily,
        show_volumes=not args.no_volumes,
        show_dist=not args.no_dist,
    )
    if args.md:
        print("```\n" + text + "\n```")
    else:
        print(text)
    return None


def cmd_health(args):
    proj = _project(args)
    data = wholebook_mod.whole_book_check(proj)
    if getattr(args, "json", False):
        print(json.dumps({"ok": data["passed"], "data": data}, ensure_ascii=False, indent=2))
        return None
    print(wholebook_mod.render_whole_book_md(data))
    if not data["passed"]:
        _exit_code_holder["code"] = EXIT_GATE
    return None


def cmd_ai_status(args):
    return ai_provider.ai_status(_project(args))


def cmd_ai_test(args):
    st = ai_provider.ai_status(_project(args))
    try:
        ai_provider.get_provider(_project(args)).polish("测试", "测试")
        st["test"] = "调用成功"
    except ai_provider.AINotEnabled as e:
        st["test"] = f"未通过：{e}"
    return st


# ---------------------------------------------------------------- 主流程

def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        data = args.func(args)
        if data is not None:
            emit(args, data)
        return _exit_code_holder["code"]
    except ProjectNotFound as e:
        _fail(args, "PROJECT_NOT_FOUND", str(e), EXIT_NO_PROJECT)
    except (ChapterError, SettingError, ForeshadowError, FrameworkError, ConsistencyError,
            LexiconError, JsonIOError, FileNotFoundError, FileExistsError,
            NotADirectoryError) as e:
        _fail(args, type(e).__name__, str(e), EXIT_ARGS)
    except (ValueError, KeyError) as e:
        _fail(args, type(e).__name__, str(e), EXIT_ARGS)


def _fail(args, code: str, message: str, exit_code: int) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"ok": False, "error": {"code": code, "message": message}},
                         ensure_ascii=False, indent=2))
    else:
        print(f"[{code}] {message}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
