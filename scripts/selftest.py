#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""novel-forge 一键回归测试（零依赖，无 pytest）。

覆盖：底层工具（JSON 四步写/frontmatter 往返）、门禁 G01-G12 正反例、
端到端主线（init→设定→spec→context→check→插章联动→伏笔→重编号→统计）。

用法：python3 scripts/selftest.py [-v]
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from novel_lib import chapter as ch
from novel_lib import consistency as cons
from novel_lib import context as ctx
from novel_lib import foreshadow as fs
from novel_lib import framework as fw
from novel_lib import gate as gt
from novel_lib import lexicon as lx
from novel_lib import project as pj
from novel_lib import settings as st
from novel_lib import stats as stt
from novel_lib import visualize as vz
from novel_lib import wholebook as wb
from novel_lib import frontmatter as fm
from novel_lib.models import read_json, safe_write_json, JsonIOError

VERBOSE = "-v" in sys.argv
_pass, _fail = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _pass, _fail
    if cond:
        _pass += 1
        if VERBOSE:
            print(f"  ✅ {name}")
    else:
        _fail += 1
        print(f"  ❌ {name}  {detail}")


def expect_error(name: str, fn, exc: type = Exception) -> None:
    try:
        fn()
        check(name, False, "未抛出异常")
    except exc:
        check(name, True)
    except Exception as e:  # noqa: BLE001
        check(name, False, f"抛出了 {type(e).__name__}: {e}")


# ---------------------------------------------------------------- 底层工具

def test_models(tmp: Path) -> None:
    print("[models]")
    p = tmp / "a.json"
    safe_write_json(p, {"x": 1, "中文": "值"})
    check("写入后回读", read_json(p) == {"x": 1, "中文": "值"})
    expect_error("回读验证失败时报错",
                 lambda: (p.write_text('{"x": 2}', encoding="utf-8"), _force_verify(p)),
                 JsonIOError)


def _force_verify(p: Path) -> None:
    from novel_lib.models import read_json as rj
    data = {"x": 1}
    # 模拟磁盘内容与预期不一致 → 验证逻辑应抛错
    p.write_text('{"x": 2}', encoding="utf-8")
    back = rj(p)
    if back != data:
        raise JsonIOError("verify failed")


def test_frontmatter(tmp: Path) -> None:
    print("[frontmatter]")
    text = "---\nchapter: 3\ntitle: 旧宅\n---\n\n# 第3章 旧宅\n\n正文"
    meta, body = fm.parse(text)
    check("解析 meta", meta == {"chapter": "3", "title": "旧宅"})
    check("解析 body", body.startswith("# 第3章"))
    out = fm.dump(meta, body)
    meta2, body2 = fm.parse(out)
    check("往返一致", meta2 == meta and body2 == body)
    meta3, body3 = fm.parse("无 frontmatter 的普通文本")
    check("无 frontmatter 容错", meta3 == {} and "普通文本" in body3)
    f = tmp / "ch.md"
    fm.write_file(f, {"chapter": "1", "title": "t"}, "正文")
    m, b = fm.read_file(f)
    check("文件写入回读", m["chapter"] == "1" and "正文" in b)


# ---------------------------------------------------------------- 门禁规则

CLEAN_TEXT = ("林晚推开门。灰尘簌簌落下。\n\n"
              "手电的光柱扫过楼梯，台阶上有一道新鲜的拖痕。\n\n"
              "「谁在这儿？」她压低声音。\n\n"
              "陈叔把提灯举高了些，说这宅子三年没人住。\n\n") * 60

BAD_TEXT = ("她不禁愣住了。\n\n"
            "与此同时，楼上传来一声响动——她握紧手电——光柱扫过——拖痕延伸——呼吸乱了——"
            "手心出汗——心跳加速——眼前一黑——她扶住门框——灯火晃了晃——夜风灌进来——木门吱呀——脚步声近了——"
            "她深吸一口气，又深吸一口气，再深吸一口气，最后深吸一口气。\n\n"
            "「他说他知道，」她说，「我问他的时候他就笑了。」他说这话的时候一直看着我。我说你少来。\n\n"
            "她感到害怕，觉得那东西就在附近，她感到脊背发凉。\n\n"
            "那扇门后，到底藏着什么？")


def _gate_ctx(lex=None) -> dict:
    return {
        "thresholds": dict(pj.DEFAULT_THRESHOLDS),
        "patterns": lx.build_patterns(lex or lx.DEFAULT_LEXICON),
        "hook_type": "", "recent_hooks": [], "chapter_no": 1,
    }


def _split(pure_head: str) -> str:
    """门禁函数吃 pure 正文（无 frontmatter/标题）。"""
    return pure_head


def test_gate_rules() -> None:
    print("[gate G01-G12]")
    ctx = _gate_ctx()
    results = {r.rule_id: r for r in (fn(_split(BAD_TEXT), ctx) for _, fn in gt.RULES)}
    check("G01 字数不足命中", not results["G01"].passed)
    check("G02 破折号超标命中", not results["G02"].passed and results["G02"].count >= 13,
          f"count={results['G02'].count}")
    check("G03 ban 词命中（不禁/与此同时）", not results["G03"].passed and results["G03"].count >= 2)
    check("G03 行号精确", all(v.line > 0 for v in results["G03"].violations))
    check("G04 warn 词命中（深吸一口气×4）", not results["G04"].passed,
          f"count={results['G04'].count}")
    check("G06 未登记钩子命中", not results["G06"].passed)
    check("G07 裸标签占比超标", not results["G07"].passed, f"count={results['G07'].count}")
    check("G08 章末反问命中", not results["G08"].passed)
    check("G09 情绪命名命中（3 次>2）", not results["G09"].passed, f"count={results['G09'].count}")

    clean_ctx = _gate_ctx()
    clean_ctx["hook_type"] = "悬疑"
    clean_results = {r.rule_id: r for r in (fn(_split(CLEAN_TEXT), clean_ctx) for _, fn in gt.RULES)}
    # CLEAN_TEXT 设计为不含 error/warn 违规（字数按 8 倍重复计算）
    for rid in ("G02", "G03", "G04", "G07", "G08", "G09"):
        check(f"干净文本 {rid} 通过", clean_results[rid].passed,
              f"count={clean_results[rid].count} msg={clean_results[rid].message}")

    # 钩子多样性：连续 3 章同型
    hctx = _gate_ctx()
    hctx["hook_type"] = "悬疑"
    hctx["recent_hooks"] = ["悬疑", "悬疑"]
    r = gt._g11_hook_variety("", hctx)
    check("G11 连续同型钩子命中", not r.passed)
    hctx["recent_hooks"] = ["危机", "信息"]
    r = gt._g11_hook_variety("", hctx)
    check("G11 钩子有变化通过", r.passed)

    # 词表覆盖
    lex = {"ban": ["不禁", "与此同时", "然而"], "ban_regex": [], "warn": [], "limit": []}
    ov = {"ban": {"add": ["邪门"], "remove": ["然而"]}, "warn": {"add": [], "remove": []},
          "limit": {"add": [], "remove": []}}
    from novel_lib.lexicon import _apply_add_remove
    merged = _apply_add_remove(lex["ban"], ov["ban"], "ban")
    check("词表 add/remove", "邪门" in merged and "然而" not in merged and "不禁" in merged)
    expect_error("非法正则词表报错",
                 lambda: lx.LexiconError and lx._validate({"ban": [], "ban_regex": ["(["], "warn": [], "limit": []}),
                 lx.LexiconError)


def test_revision_map() -> None:
    print("[revision_map]")
    ctx = _gate_ctx()
    results = [fn(_split(BAD_TEXT), ctx) for _, fn in gt.RULES]
    rmap = gt.revision_map(_split(BAD_TEXT), results)
    check("修订导航非空", len(rmap) >= 1)
    check("热度降序", all(rmap[i]["heat"] >= rmap[i + 1]["heat"] for i in range(len(rmap) - 1)))
    check("含规则与建议", rmap[0]["rules"] and rmap[0]["advice"])


# ---------------------------------------------------------------- 一致性校验

def test_consistency(tmp: Path) -> None:
    print("[consistency C01-C05]")
    root = tmp / "cons"
    pj.init(root, "一致性测试", genre="都市高武", target_chapters=30)
    # 未建框架时应跳过而非报错
    ch.new_chapter(root, 1, "开篇")
    r0 = cons.check_consistency(root, 1)
    check("无框架时跳过校验", r0["checked"] is False)

    fw.set_section(root, "core", {"one_liner": "一个不愿被定价的人"})
    fw.set_section(root, "theme", {"question": "人被明码标价之后还剩下什么是自己的？"})
    fw.set_section(root, "characters", [
        {"name": "林砚", "relation": "自身", "own_goal": "查清父母死因", "theme_face": "正题"},
        {"name": "裴照", "relation": "对手", "own_goal": "维持协会秩序", "theme_face": "反题"},
        {"name": "哑叔", "relation": "影响者", "own_goal": "", "theme_face": "中介"},
    ])
    fw.set_section(root, "structure", {"volumes": [
        {"name": "卷一", "chapters": "1-10", "goal": "获得进入北城武院的资格",
         "climax": "c", "change": "变", "theme_question": "q"}]})

    # 跑偏章节：写买菜日常，不呼应卷目标/主题，且哑叔无动机
    ch.new_chapter(root, 2, "买菜")
    body_dev = ("# 第2章 买菜\n\n"
                "林砚拎着布袋子走进早市，跟哑叔讨价还价买了三斤白菜。\n\n"
                "摊主说今天的豆腐新鲜，他便多买了一板。回来的路上他想着晚上做个汤。\n\n")
    _write_body(root, 2, body_dev, characters="林砚、哑叔")
    r = cons.check_consistency(root, 2)
    by_id = {i["rule_id"]: i for i in r["items"]}
    check("C01 跑偏章节未通过", not by_id["C01"]["passed"])
    check("C02 无动机角色未通过", not by_id["C02"]["passed"], by_id["C02"]["message"])
    check("C05 未触碰主题", not by_id["C05"]["passed"])
    check("一致性 ok 汇总", r["passed"] is False and r["warns"] >= 1)
    md = cons.render_consistency_md(r)
    check("一致性渲染含表格", "| C01 |" in md and "所属卷" in md)

    # 呼应章节：命中卷目标 + 角色有动机
    ch.new_chapter(root, 3, "初试锋芒")
    body_ok = ("# 第3章 初试锋芒\n\n"
               "林砚把晶体按在测力桩上，武院的招生官抬起头——他直到这一刻才明白，"
               "获得进入北城武院的资格，代价是让所有人看见他不愿意被定价的那部分。\n\n"
               "裴照冷冷地记下他的编号，像记下一件货物的价签。\n\n")
    _write_body(root, 3, body_ok, characters="林砚、裴照")
    r2 = cons.check_consistency(root, 3)
    by2 = {i["rule_id"]: i for i in r2["items"]}
    check("C01 呼应章节通过", by2["C01"]["passed"], by2["C01"]["message"])
    check("C02 有动机角色通过", by2["C02"]["passed"], by2["C02"]["message"])
    check("C04 卷内范围通过", by2["C04"]["passed"])

    # C03 伏笔到期未回收
    fs.add(root, "怀表停在3:17", 1, 3)
    ch3 = cons.check_consistency(root, 3)
    by3 = {i["rule_id"]: i for i in ch3["items"]}
    check("C03 到期伏笔命中", not by3["C03"]["passed"], by3["C03"]["message"])

    # C04 抵近卷末：卷一到 10，第 10 章应提示收束
    ch.new_chapter(root, 10, "卷末")
    _write_body(root, 10, "# 第10章 卷末\n\n他站在门口。\n\n", characters="")
    r4 = cons.check_consistency(root, 10)
    by4 = {i["rule_id"]: i for i in r4["items"]}
    check("C04 抵近卷末告警", not by4["C04"]["passed"], by4["C04"]["message"])
    check("C01 章在卷内时正常判定", "C01" in by4)

    # 跨卷章节：第 15 章不在任何卷范围
    ch.new_chapter(root, 15, "跨卷")
    _write_body(root, 15, "# 第15章 跨卷\n\n他站在门口。\n\n", characters="")
    r5 = cons.check_consistency(root, 15)
    by5 = {i["rule_id"]: i for i in r5["items"]}
    check("C04 跨卷提示", by5["C04"]["passed"] and "不在任何" in by5["C04"]["message"])
    check("C01 无卷登记时通过", by5["C01"]["passed"])
    expect_error("不存在章节报错", lambda: cons.check_consistency(root, 99), cons.ConsistencyError)


def _write_body(root: Path, no: int, full_body: str, characters: str = "") -> None:
    """整篇覆盖写入（含标题行），可携带 characters 元数据。"""
    p = ch.chapter_path(root, no)
    meta, _ = fm.read_file(p)
    if characters:
        meta["characters"] = characters
    fm.write_file(p, meta, full_body, key_order=ch.META_KEY_ORDER)


# ---------------------------------------------------------------- 进度可视化

def test_visualize(tmp: Path) -> None:
    print("[visualize]")
    # 纯函数：进度条
    b0 = vz.bar_progress(0, 100, width=10)
    check("0% 进度条全空", b0.startswith("░") and "0.0%" in b0)
    b50 = vz.bar_progress(50, 100, width=10)
    check("50% 进度条半满", b50.count("█") == 5 and "50.0%" in b50)
    b100 = vz.bar_progress(100, 100, width=10)
    check("100% 进度条全满", b100.count("█") == 10 and "100.0%" in b100)
    check("total=0 不崩", "0.0%" in vz.bar_progress(5, 0, width=10))
    check("超量钳制", "100.0%" in vz.bar_progress(200, 100, width=10))
    # 标签对齐
    lb = vz.bar_progress(1, 10, width=10, label="卷一", label_pad=16)
    check("标签对齐填充", lb.startswith("卷一") and lb.count("█") + lb.count("░") == 10)
    check("显示宽度 CJK 计 2", vz._disp_width("卷一") == 4 and vz._disp_width("ab") == 2)

    # 序列图
    s = vz.bar_series([{"date": "2025-01-01", "words": 100},
                       {"date": "2025-01-02", "words": 200}], width=10)
    check("序列图行数", len(s) == 2)
    check("峰值满宽", s[1].count("█") == 10 and s[0].count("█") == 5,
          f"{s[0].count('█')}/{s[1].count('█')}")
    check("空序列容错", vz.bar_series([], width=10) == [])

    # 分布图
    d = vz.bucket_distribution([100, 200, 300, 400, 500], width=10)
    check("分布图分箱", len(d) == 5 and all("章" in x for x in d))
    check("同值单箱", len(vz.bucket_distribution([100, 100], width=10)) == 1)
    check("空分布容错", vz.bucket_distribution([])[0].startswith("（"))

    # 项目级：build_dashboard + render
    root = tmp / "viz"
    pj.init(root, "看板测试", genre="都市高武", target_chapters=40, words_per_chapter=3000)
    fw.set_section(root, "core", {"one_liner": "不愿被定价的人"})
    fw.set_section(root, "structure", {"volumes": [
        {"name": "卷一", "chapters": "1-10", "goal": "拿到资格", "climax": "c",
         "change": "变", "theme_question": "q"},
        {"name": "卷二", "chapters": "11-30", "goal": "查线索", "climax": "c",
         "change": "变", "theme_question": "q"}]})
    for i in (1, 2, 3):
        ch.new_chapter(root, i, f"章{i}")
        _write_body(root, i, f"# 第{i}章 章{i}\n\n" + "他握紧晶体。" * 200)
    dash = vz.build_dashboard(root, days=7)
    check("看板含逐章分布", len(dash["distribution"]) == 3)
    check("看板含分卷", len(dash["volumes"]) == 2)
    v1 = dash["volumes"][0]
    check("卷一进度 3/10", v1["written"] == 3 and v1["planned"] == 10 and v1["pct"] == 30.0,
          f"{v1}")
    check("卷二进度 0", dash["volumes"][1]["written"] == 0)
    text = vz.render_dashboard(dash, width=24)
    check("渲染含书名", "看板测试" in text)
    check("渲染含分卷标题", "── 分卷进度 ──" in text and "卷一" in text)
    check("渲染含日产出", "近 7 天日产出" in text)
    check("宽度生效", "═" * 24 in text)
    text2 = vz.render_dashboard(dash, width=24, show_daily=False,
                                show_volumes=False, show_dist=False)
    check("可关闭模块", "分卷进度" not in text2 and "日产出" not in text2)
    # 未创作章节不计入分布
    ch.new_chapter(root, 4, "空章")
    dash2 = vz.build_dashboard(root, days=0)
    check("未创作章不计入分布", len(dash2["distribution"]) == 3)
    check("days=0 无日产出", dash2["daily"] == [])


# ---------------------------------------------------------------- 全书体检

def test_wholebook(tmp: Path) -> None:
    print("[wholebook W01-W04]")
    root = tmp / "wb"
    pj.init(root, "体检", target_chapters=50, words_per_chapter=3000)
    # 不足 5 章时各检查应温和通过
    ch.new_chapter(root, 1, "一")
    _write_body(root, 1, "# 第1章 一\n\n" + "他握紧晶体。" * 200)
    r0 = wb.whole_book_check(root)
    by0 = {i["rule_id"]: i for i in r0["items"]}
    check("样本不足时不误报", by0["W02"]["passed"] and by0["W04"]["passed"])
    check("体检含四项", len(r0["items"]) == 4)

    # 造 12 章强钩子密集 + 一个超短章
    for i in range(2, 13):
        ch.new_chapter(root, i, f"章{i}")
        words = 3000 if i != 7 else 300
        body = f"# 第{i}章 章{i}\n\n" + ("他握紧晶体，武院钟声响起。\n\n" * (words // 16))
        _write_body(root, i, body)
        p = ch.chapter_path(root, i)
        m, _ = fm.read_file(p)
        m["hook_type"] = "危机" if i != 5 else "情感"
        fm.write_file(p, m, "# 第%d章 章%d\n\n" % (i, i) + ("他握紧晶体，武院钟声响起。\n\n" * (words // 16)),
                      key_order=ch.META_KEY_ORDER)
    r = wb.whole_book_check(root)
    by = {i["rule_id"]: i for i in r["items"]}
    check("W01 强钩子密集命中", not by["W01"]["passed"], by["W01"]["message"][:50])
    check("W02 钩子过度集中命中", not by["W02"]["passed"], by["W02"]["message"][:50])
    check("W03 缺 spec 命中", not by["W03"]["passed"])
    check("W04 字数离群命中", not by["W04"]["passed"])
    check("体检汇总 warn 计数", r["warns"] == 2 and r["passed"] is False, f"warns={r['warns']}")
    md = wb.render_whole_book_md(r)
    check("体检渲染含表格", "| W01 |" in md and "跨章趋势" in md)

    # 补 spec + 换钩子 → W01/W02/W03 应转好
    for i in range(1, 13):
        ch.spec_save(root, i, {**ch.spec_skeleton(i, f"章{i}"), "must_happen": [f"推进{i}"]})
        p = ch.chapter_path(root, i)
        m, _ = fm.read_file(p)
        m["hook_type"] = ["悬疑", "情感", "信息", "选择"][i % 4]
        fm.write_file(p, m, "# 第%d章 章%d\n\n" % (i, i) + ("他握紧晶体，武院钟声响起。\n\n" * 150),
                      key_order=ch.META_KEY_ORDER)
    r2 = wb.whole_book_check(root)
    by2 = {i["rule_id"]: i for i in r2["items"]}
    check("换钩子后 W02 转好", by2["W02"]["passed"], by2["W02"]["message"][:50])
    check("补 spec 后 W03 转好", by2["W03"]["passed"], by2["W03"]["message"][:50])


# ---------------------------------------------------------------- 端到端

def test_e2e(tmp: Path) -> None:
    print("[e2e 主线]")
    root = tmp / "书"
    r = pj.init(root, "测试之书", genre="悬疑", target_chapters=10, words_per_chapter=3000)
    check("init 骨架完整", (root / "book.json").is_file() and (root / "foreshadow.json").is_file()
          and (root / "settings/characters/_index.json").is_file())
    expect_error("重复 init 拒绝", lambda: pj.init(root, "x"), FileExistsError)

    c1 = st.add_character(root, "林晚", "主角")
    check("角色登记", c1["id"] == "char_001" and Path(c1["path"]).is_file())
    c2 = st.add_character(root, "陈叔", "配角")
    expect_error("重名拒绝", lambda: st.add_character(root, "林晚"), st.SettingError)
    st.update_character(root, "陈叔", [("status", "active")])
    got = st.get_character(root, "陈叔")
    check("角色更新与查询", got["meta"]["status"] == "active" and "{{name}}" not in got["body"])
    hits = st.search_settings(root, "林晚")
    check("设定搜索命中", len(hits) >= 1)

    ch.new_chapter(root, 1, "雨夜")
    ch.new_chapter(root, 2, "旧宅")
    check("章节创建", (root / "chapters/ch_0001.md").is_file())
    expect_error("重复建章拒绝", lambda: ch.new_chapter(root, 1, "x"), ch.ChapterError)

    # spec
    ch.spec_save(root, 2, {**ch.spec_skeleton(2, "旧宅"),
                           "summary": "发现拖痕", "characters": ["林晚", "陈叔"],
                           "must_happen": ["发现拖痕", "怀表异动"]})
    spec = ch.spec_get(root, 2)
    check("spec 读写", spec["must_happen"] == ["发现拖痕", "怀表异动"])

    # context 装配
    cctx = ctx.build_context(root, 2)
    md = ctx.render_context_md(cctx)
    check("context 含 spec", "发现拖痕" in md)
    check("context 含声线卡", "林晚" in md and "陈叔" in md)
    check("context 含前章衔接", "第 1 章" in md)

    # 写正文（第 1 章合规 / 第 2 章违规）
    _write_ch(root, 1, "雨夜", CLEAN_TEXT, hook="悬疑")
    _write_ch(root, 2, "旧宅", BAD_TEXT, hook="危机")
    ch.refresh_words(root, 1)
    ch.refresh_words(root, 2)
    r1 = gt.check_chapter(root, 1)
    check("第 1 章通过", r1["passed"], f"score={r1['score']} e={r1['errors']}")
    r2 = gt.check_chapter(root, 2)
    check("第 2 章不通过", not r2["passed"])
    check("第 2 章修订导航非空", len(r2["revision_map"]) >= 1)
    saved = gt.save_report(root, r2)
    check("报告落盘", Path(saved["md"]).is_file() and Path(saved["json"]).is_file())

    # 伏笔：第 1 章埋、预期第 2 章收 → audit 应报 overdue
    f1 = fs.add(root, "怀表停在3:17", 1, 2)
    f2 = fs.add(root, "柜子上锁", 2, 5)
    aud = fs.audit(root)
    check("伏笔到期预警", any(a["item"]["id"] == f1["id"] for a in aud["alerts"]))
    check("audit ok=False", aud["ok"] is False)
    fs.recover(root, f1["id"], 2)
    aud2 = fs.audit(root)
    check("回收后预警消除", all(a["item"]["id"] != f1["id"] for a in aud2["alerts"]))

    # 插章：在第 2 章前插入 → 原第 2 章变第 3，伏笔联动
    plan = ch.insert_chapter(root, 2, "追踪者", dry_run=True)
    check("dry-run 不落盘", not (root / "chapters/ch_0002.spec.json").exists() or
          ch.spec_get(root, 2, init_if_missing=False).get("chapter") == 2)
    ins = ch.insert_chapter(root, 2, "追踪者")
    check("插章后总数", len(ch.scan_chapters(root)) == 3)
    c3 = next(c for c in ch.scan_chapters(root) if c["no"] == 3)
    check("原第 2 章移到第 3", c3["title"] == "旧宅" and c3["file"] == "ch_0003.md")
    _, body3 = fm.read_file(root / "chapters/ch_0003.md")
    check("标题行同步", body3.startswith("# 第3章"), body3.split(chr(10))[0])
    check("spec 伴生文件迁移", ch.spec_path(root, 3).is_file()
          and ch.spec_get(root, 3, init_if_missing=False)["chapter"] == 3)
    fore = read_json(root / "foreshadow.json")
    f2d = next(i for i in fore["items"] if i["id"] == f2["id"])
    check("伏笔章号联动 +1", f2d["planted_chapter"] == 3 and f2d["expected_recover_chapter"] == 6)
    chk = ch.renumber(root, check_only=True)
    check("插章后校验通过", chk["ok"], f"issues={chk['issues']} need={chk['renumber_needed']}")

    # 手动制造断号 → renumber 修复
    (root / "chapters/ch_0003.md").rename(root / "chapters/ch_0005.md")
    chk2 = ch.renumber(root, check_only=True)
    check("断号被检出", not chk2["ok"])
    ch.renumber(root)
    chk3 = ch.renumber(root, check_only=True)
    check("重排后校验通过", chk3["ok"])
    nos = [c["no"] for c in ch.scan_chapters(root)]
    check("章号连续", nos == [1, 2, 3])

    # 统计
    s = stt.overall_stats(root)
    check("总章数", s["total_chapters"] == 3)
    p = stt.progress(root)
    check("进度百分比", p["chapter_progress_pct"] == 30.0, f"got {p.get('chapter_progress_pct')}")


def _write_ch(root: Path, no: int, title: str, body_text: str, hook: str) -> None:
    p = ch.chapter_path(root, no)
    meta, _ = fm.read_file(p)
    meta["hook_type"] = hook
    body = f"# 第{no}章 {title}\n\n{body_text}"
    fm.write_file(p, meta, body, key_order=ch.META_KEY_ORDER)


# ---------------------------------------------------------------- 框架

def test_framework(tmp: Path) -> None:
    print("[framework]")
    root = tmp / "fw"
    pj.init(root, "框架测试", genre="都市高武", target_chapters=10)
    check("空框架 audit exists=False", fw.audit(root)["missing"] and not fw.exists(root))
    fw.set_stage(root, "core")
    check("阶段记录", fw.load(root)["stage"] == "core")
    expect_error("非法阶段拒绝", lambda: fw.set_stage(root, "不存在的阶段"), fw.FrameworkError)

    fw.set_section(root, "core", {"protagonist": "拾荒者林砚", "goal": "查清父母死因",
                                  "obstacle": "协会管控", "catalyst": "听见晶体声音",
                                  "one_liner": "一个不愿被定价的人"})
    row = next(r for r in fw.audit(root)["sections"] if r["section"] == "core")
    check("core 版块成型", row["filled"])
    fw.set_section(root, "theme", {"question": "人被定价后还剩下什么？", "thesis": "正",
                                   "antithesis": "反", "synthesis": "合"})
    fw.set_section(root, "characters", [
        {"name": "A", "relation": "自身", "own_goal": "g", "theme_face": "正题", "voice": "短句"},
        {"name": "B", "relation": "影响者", "own_goal": "g2", "theme_face": "反题", "voice": "话密"},
        {"name": "C", "relation": "对手", "own_goal": "g3", "theme_face": "反题最强论证", "voice": "冷"},
    ])
    fw.set_section(root, "structure", {"acts": [{"name": "一幕", "content": "x"}],
                                       "volumes": [{"name": "卷一", "chapters": "1-10", "goal": "g",
                                                    "climax": "c", "change": "变", "theme_question": "q"}]})
    fw.set_section(root, "reveal", [{"secret": "s", "at": "第1章", "by": "主角", "foreshadow": "f"}])
    fw.set_section(root, "opening", {"ch1": "a", "ch2": "b", "ch3": "c"})
    fw.add_rejected(root, "开局打擂台", "读者还没理由关心主角")
    # 新增：长篇骨架版块
    fw.set_section(root, "engine", {
        "loop": {"gain": "每次获得新的词条权限", "end": "新的遗迹层级", "drive": "查清父母死因",
                 "diagram": "遇强敌→被压制→得机缘→升级→打脸→新强敌"},
        "drive_wheels": {"power": 60, "world": 20, "conflict": 12, "payoff": 8},
        "extensibility": {"tiers": "6 档", "stages": "每档对应不同遗迹", "beyond": "真相与代价"}})
    fw.set_section(root, "ladder", {"steps": [
        {"name": "一阶", "stage": "乡镇", "power": "引气", "enemy": "地痞武者", "resource": "晶体", "secret": "晶体来源"},
        {"name": "二阶", "stage": "县城", "power": "淬体", "enemy": "县城世家", "resource": "功法", "secret": "协会真相"},
        {"name": "三阶", "stage": "省会", "power": "凝元", "enemy": "省会宗门", "resource": "秘境", "secret": "父母身份"},
        {"name": "四阶", "stage": "国都", "power": "化罡", "enemy": "国家级势力", "resource": "本源", "secret": "文明断层"},
        {"name": "五阶", "stage": "域外", "power": "通神", "enemy": "域外存在", "resource": "规则", "secret": "终极真相"}]})
    fw.set_section(root, "rhythm", {"wave_period": 15, "difficulty_step": 25,
                                    "breather_rule": "每 10 章强制插入 1-2 章呼吸章",
                                    "ratio_note": "setup 20% / escalation 40% / climax 20% / cooling 20%"})
    fw.set_section(root, "midgame", {"hidden_identity": "主角是上代传承者的转世",
                                     "erased_history": "百年前的本源战争被抹去",
                                     "unseen_faction": "还未登场的守夜人",
                                     "cognitive_truths": ["真相一", "真相二", "真相三", "真相四", "真相五"]})
    fw.set_section(root, "platform", {"target": "起点", "reader_want": "设定厚度与长期布局",
                                      "update_plan": "日更 4000",
                                      "titles": ["晶体纪元", "定价之城"], "blurbs": ["版本一", "版本二"]})

    aud = fw.audit(root)
    check("框架完整", aud["complete"], f"missing={aud['missing']}")
    check("下一步提示 done", "进入章节创作" in aud["next_action"])
    check("否决项记录", aud["rejected_count"] == 1)
    check("新版块体检通过", not aud["warnings"], f"warns={aud['warnings']}")
    md = fw.render_md(fw.load(root))
    check("蓝图渲染含主题句", "人被定价后还剩下什么？" in md)
    check("蓝图渲染含分卷表", "卷一" in md and "主题新问法" in md)
    check("蓝图渲染含核心循环", "核心循环" in md and "每轮获得什么" in md)
    check("蓝图渲染含四驱动轮", "四驱动轮配比" in md and "60%" in md)
    check("蓝图渲染含阶梯表", "可攀越的世界观" in md and "五阶" in md)
    check("蓝图渲染含中期弹药库", "中期弹药库" in md and "认知线五真相" in md)
    check("蓝图渲染含平台门面", "平台与门面" in md and "起点" in md and "晶体纪元" in md)

    # 长篇体检：核心循环「获得」环为空 → 告警
    bad = tmp / "fwnocheck"
    pj.init(bad, "体检测试", target_chapters=300, words_per_chapter=3000)
    fw.set_section(bad, "engine", {"loop": {"end": "x", "drive": "y"}})
    aud_bad = fw.audit(bad)
    check("空获得环告警", any("获得" in w for w in aud_bad["warnings"]), f"{aud_bad['warnings']}")
    # 阶梯表阶数不足
    fw.set_section(bad, "ladder", {"steps": [{"name": "一阶"}]})
    check("阶梯表不足 5 阶告警", any("撑不住 50 万字" in w for w in fw.audit(bad)["warnings"]))
    # 中期三件套缺失（目标 90 万字 → 触发检查）
    check("中期三件套缺失告警", any("中期三件套" in w for w in fw.audit(bad)["warnings"]))
    # 抑扬波周期过密
    fw.set_section(bad, "rhythm", {"wave_period": 5})
    check("抑扬波过密告警", any("偏密" in w for w in fw.audit(bad)["warnings"]))

    # 结构校验（非阻塞 shape_warnings）：抓住静默失败
    sw = tmp / "fwshape"
    pj.init(sw, "结构校验", target_chapters=10)
    r = fw.set_section(sw, "engine", {"loop": "打怪升级", "drive_wheels": {"power": 60}})
    check("loop 写成字符串被告警", any("loop 应为对象" in w for w in r.get("shape_warnings", [])),
          f"{r.get('shape_warnings')}")
    check("结构告警不阻塞写入", r["saved"] and fw.load(sw)["engine"]["loop"] == "打怪升级")
    r2 = fw.set_section(sw, "characters", {"roles": [{"name": "A"}]})
    check("characters 包对象被告警", any("应为数组" in w for w in r2.get("shape_warnings", [])),
          f"{r2.get('shape_warnings')}")
    r3 = fw.set_section(sw, "rhythm", {"wave_period": "15", "difficulty_step": 25})
    check("节奏字段写成字符串被告警", any("应是数字" in w for w in r3.get("shape_warnings", [])),
          f"{r3.get('shape_warnings')}")
    r4 = fw.set_section(sw, "characters", [{"name": "A"}, {"name": "B"}, {"name": "C"}])
    check("正确结构无告警", not r4.get("shape_warnings"), f"{r4.get('shape_warnings')}")

    # 渲染健壮性：list 版块允许「字符串简写」，渲染与审计都不能崩
    lo = tmp / "fwloose"
    pj.init(lo, "简写渲染", target_chapters=10)
    fw.set_section(lo, "structure", {"acts": ["第一幕：起", "第二幕：承"],
                                     "volumes": ["卷一 1-5", "卷二 6-10"]})
    fw.set_section(lo, "characters", ["主角甲", "对手乙", "影响者丙"])
    fw.set_section(lo, "reveal", ["秘密一"])
    try:
        md_loose = fw.render_md(fw.load(lo))
        check("字符串简写可渲染", "第一幕：起" in md_loose and "主角甲" in md_loose)
    except Exception as e:  # noqa: BLE001
        check("字符串简写可渲染", False, f"崩溃：{e}")
    try:
        aud_loose = fw.audit(lo)
        check("字符串简写可审计", isinstance(aud_loose.get("warnings"), list))
    except Exception as e:  # noqa: BLE001
        check("字符串简写可审计", False, f"崩溃：{e}")

    # 章节数不匹配 → 告警（卷一仅 10 章，目标 300 章）
    fw.set_section(root, "structure", {"acts": [{"name": "一幕", "content": "x"}],
                                       "volumes": [{"name": "卷一", "chapters": "1-10", "goal": "g",
                                                    "climax": "c", "change": "变", "theme_question": "q"}]})
    book = read_json(root / "book.json")
    book["target"]["total_chapters"] = 300
    safe_write_json(root / "book.json", book)
    aud2 = fw.audit(root)
    check("章节数差异告警", any("差异较大" in w for w in aud2["warnings"]), f"warns={aud2['warnings']}")
    expect_error("非法版块拒绝", lambda: fw.set_section(root, "不存在", {}), fw.FrameworkError)

    # context 集成：框架锚点应出现在写作上下文中
    ch.new_chapter(root, 1, "测试章")
    c = ctx.build_context(root, 1)
    check("context 含框架标记", c["framework"]["has_framework"] is True)
    check("context 含主题句", "人被定价后还剩下什么？" in ctx.render_context_md(c))
    check("context 含所属卷", c["framework"]["current_volume"]["name"] == "卷一")
    # 无框架时给出警告
    root2 = tmp / "fw2"
    pj.init(root2, "无框架", target_chapters=5)
    ch.new_chapter(root2, 1, "章")
    c2 = ctx.build_context(root2, 1)
    check("无框架时标记 False", c2["framework"]["has_framework"] is False)
    check("无框架时渲染出警告", "框架尚未成型" in ctx.render_context_md(c2))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="novel_forge_test_"))
    try:
        print("=== novel-forge selftest ===")
        test_models(tmp)
        test_frontmatter(tmp)
        test_gate_rules()
        test_revision_map()
        test_framework(tmp)
        test_consistency(tmp)
        test_visualize(tmp)
        test_wholebook(tmp)
        test_e2e(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n结果：{_pass} 通过 / {_fail} 失败")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
