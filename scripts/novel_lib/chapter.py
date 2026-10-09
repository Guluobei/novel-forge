# -*- coding: utf-8 -*-
"""章节文件管理：new / list / stats / set-status / insert / renumber。

设计要点：
- 一章一文件：chapters/ch_%04d.md（4 位补零保证字典序 == 章节序）
- 章节文件是唯一事实源：list/stats/audit 实时扫描，不维护缓存文件，杜绝索引失步
- 章节文件 = frontmatter（chapter/title/status/hook_type/words/updated_at）+ 正文（首行为 `# 第N章 标题`）
- 插章/重编号三重防护：--dry-run 预览 → trash/<时间戳> 整目录备份 → 执行后自动校验
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import frontmatter as fm
from .models import read_json, safe_write_json
from .project import CHAPTER_TITLE_RE, now_iso, touch_state

CHAPTERS_DIR = "chapters"
TRASH_DIR = "trash"
META_KEY_ORDER = ["chapter", "title", "status", "hook_type", "words", "updated_at"]
STATUS_VALUES = ["draft", "writing", "review", "done"]
SPEC_FIELDS = ["summary", "characters", "must_happen", "tension_curve", "new_hooks", "target_words"]


# ---------------------------------------------------------------- 章节 spec（章级创作锚点）

def spec_path(project: Path, no: int) -> Path:
    """章节 spec 伴生文件：chapters/ch_NNNN.spec.json。"""
    return chapters_dir(project) / f"ch_{no:04d}.spec.json"


def spec_skeleton(no: int, title: str = "") -> dict:
    """生成 spec 骨架（字段对齐 cn-novel-craft 章节规范）。"""
    return {
        "chapter": no,
        "title": title,
        "summary": "",          # 200 字内摘要：本章发生什么
        "characters": [],       # 本章出场角色名（context 装配声线卡的依据）
        "must_happen": [],      # 本章必须发生的情节点（保证剧情推进的锚）
        "tension_curve": [],    # 张力曲线 [{pos: 0-100, value: 1-10, note}]
        "new_hooks": [],        # 本章埋下的新钩子/伏笔
        "target_words": None,   # 本章目标字数（缺省用全书 words_per_chapter）
    }


def spec_get(project: Path, no: int, init_if_missing: bool = True) -> dict:
    """读取章节 spec；不存在时可选生成骨架。"""
    from .models import read_json
    p = spec_path(project, no)
    data = read_json(p, default=None)
    if isinstance(data, dict):
        return data
    if not init_if_missing:
        raise ChapterError(f"第 {no} 章尚无 spec：{p.name}")
    title = ""
    cp = chapter_path(project, no)
    if cp.exists():
        meta, _ = fm.read_file(cp)
        title = meta.get("title", "")
    return spec_skeleton(no, title)


def spec_save(project: Path, no: int, data: dict) -> dict:
    """保存章节 spec（四步安全写）。"""
    if int(data.get("chapter", no)) != no:
        raise ChapterError(f"spec.chapter({data.get('chapter')}) 与目标章号 {no} 不一致")
    from .models import safe_write_json
    safe_write_json(spec_path(project, no), data)
    return data


def spec_set(project: Path, no: int, key: str, raw_value: str) -> dict:
    """更新 spec 单字段：值可解析为 JSON 则结构化，否则按字符串处理。"""
    import json as _json
    data = spec_get(project, no)
    try:
        value = _json.loads(raw_value)
    except _json.JSONDecodeError:
        value = raw_value
    if key not in SPEC_FIELDS:
        raise ChapterError(f"非法 spec 字段 {key!r}，可选：{'/'.join(SPEC_FIELDS)}")
    data[key] = value
    return spec_save(project, no, data)


class ChapterError(RuntimeError):
    """章节操作失败。"""


# ---------------------------------------------------------------- 基础工具

def chapters_dir(project: Path) -> Path:
    return project / CHAPTERS_DIR


def chapter_path(project: Path, no: int) -> Path:
    return chapters_dir(project) / f"ch_{no:04d}.md"


def count_words(text: str) -> int:
    """字数口径：去除所有空白字符后的字符数（含标点）。"""
    return sum(1 for c in text if not c.isspace())


def split_body(body: str) -> tuple[str, str]:
    """把正文拆为 (标题行, 纯正文)。标题行形如 `# 第N章 标题`。"""
    lines = body.split("\n")
    if lines and lines[0].lstrip().startswith("#"):
        return lines[0], "\n".join(lines[1:])
    return "", body


def refresh_words(project: Path, no: int) -> int:
    """重新统计某章字数并写回 frontmatter，返回字数。"""
    path = chapter_path(project, no)
    if not path.exists():
        raise ChapterError(f"第 {no} 章文件不存在：{path.name}")
    meta, body = fm.read_file(path)
    _, pure = split_body(body)
    words = count_words(pure)
    meta["words"] = str(words)
    meta["updated_at"] = now_iso()
    _rewrite(path, meta, body)
    return words


def _rewrite(path: Path, meta: dict[str, str], body: str,
             key_order: list[str] | None = None) -> None:
    """统一入口回写章节文件（保持 key 顺序）。"""
    fm.write_file(path, meta, body, key_order=key_order or META_KEY_ORDER)



# 未开始写作的判定：正文长度低于此值视为占位（新建章默认正文约 8 字）
PLACEHOLDER_MIN_WORDS = 20
# 新建章写入的占位正文标记
PLACEHOLDER_MARK = "（正文待创作）"


def scan_chapters(project: Path) -> list[dict]:
    """实时扫描章节目录，返回按章号升序的章节信息列表。

    字数**始终实时从正文重算**（不读 frontmatter 缓存）：
    作者直接编辑正文后，所有统计即刻准确，无需额外刷新命令。
    """
    result: list[dict] = []
    cdir = chapters_dir(project)
    if not cdir.is_dir():
        return result
    for path in sorted(cdir.glob("ch_*.md")):
        try:
            meta, body = fm.read_file(path)
        except Exception:
            continue
        no = fm.get_int(meta, "chapter", 0)
        if no <= 0:
            m = re.match(r"ch_0*(\d+)", path.name)
            if not m:
                continue
            no = int(m.group(1))
        _, pure = split_body(body)
        real_words = count_words(pure)
        unwritten = _is_unwritten(pure, real_words)
        result.append({
            "no": no,
            "title": meta.get("title", ""),
            "status": meta.get("status", "draft"),
            "hook_type": meta.get("hook_type", ""),
            "words": real_words,
            "words_cached": fm.get_int(meta, "words", -1),
            "unwritten": unwritten,
            "file": path.name,
            "updated_at": meta.get("updated_at", ""),
        })
    result.sort(key=lambda c: c["no"])
    return result


def _is_unwritten(pure: str, words: int) -> bool:
    """判断章节是否尚未真正创作（新建占位 / 正文过短）。"""
    if PLACEHOLDER_MARK in pure:
        return True
    return words < PLACEHOLDER_MIN_WORDS


def max_chapter_no(project: Path) -> int:
    chapters = scan_chapters(project)
    return chapters[-1]["no"] if chapters else 0


def get_chapter(project: Path, no: int) -> dict:
    for c in scan_chapters(project):
        if c["no"] == no:
            return c
    raise ChapterError(f"第 {no} 章不存在")


# ---------------------------------------------------------------- 命令实现

def new_chapter(project: Path, number: int | None, title: str) -> dict:
    """创建新章节文件（不写正文，正文由 Claude/作者随后填入）。"""
    if number is None or number <= 0:
        number = max_chapter_no(project) + 1
    path = chapter_path(project, number)
    if path.exists():
        raise ChapterError(f"第 {number} 章已存在：{path.name}")
    meta = {
        "chapter": str(number),
        "title": title,
        "status": "draft",
        "hook_type": "",
        "words": "0",
        "updated_at": now_iso(),
    }
    body = f"# 第{number}章 {title}\n\n（正文待创作）\n"
    _rewrite(path, meta, body)
    touch_state(project)
    return {"no": number, "title": title, "file": path.name, "path": str(path)}


def list_chapters(project: Path, status: str | None = None) -> list[dict]:
    chapters = scan_chapters(project)
    if status:
        chapters = [c for c in chapters if c["status"] == status]
    return chapters


def chapter_stats(project: Path, target: str = "all") -> dict:
    """单章或全书字数统计（实时计算，并可回写失步的缓存值）。"""
    chapters = scan_chapters(project)
    if target != "all":
        no = int(target)
        chapter = next((c for c in chapters if c["no"] == no), None)
        if not chapter:
            raise ChapterError(f"第 {no} 章不存在")
        sync_cached_words(project, chapter)
        return {"no": no, "title": chapter["title"], "words": chapter["words"],
                "status": chapter["status"], "hook_type": chapter["hook_type"],
                "unwritten": chapter["unwritten"]}
    written = [c for c in chapters if not c["unwritten"]]
    total = sum(c["words"] for c in chapters)
    return {
        "total_chapters": len(chapters),
        "written_chapters": len(written),
        "unwritten_chapters": len(chapters) - len(written),
        "total_words": total,
        "avg_words": round(total / len(written), 1) if written else 0,
        "min_words": min((c["words"] for c in written), default=0),
        "max_words": max((c["words"] for c in written), default=0),
    }


def sync_cached_words(project: Path, chapter: dict) -> bool:
    """若 frontmatter 缓存字数与实际不符，回写修正。返回是否发生了修正。"""
    cached = chapter.get("words_cached", -1)
    real = chapter["words"]
    if cached == real:
        return False
    path = chapters_dir(project) / chapter["file"]
    if not path.exists():
        return False
    try:
        meta, body = fm.read_file(path)
    except Exception:
        return False
    meta["words"] = str(real)
    meta["updated_at"] = now_iso()
    _rewrite(path, meta, body)
    chapter["words_cached"] = real
    return True


def set_status(project: Path, no: int, status: str) -> dict:
    if status not in STATUS_VALUES:
        raise ChapterError(f"非法状态 {status!r}，可选：{'/'.join(STATUS_VALUES)}")
    path = chapter_path(project, no)
    if not path.exists():
        raise ChapterError(f"第 {no} 章文件不存在")
    meta, body = fm.read_file(path)
    meta["status"] = status
    meta["updated_at"] = now_iso()
    _rewrite(path, meta, body)
    touch_state(project)
    return {"no": no, "status": status}


def set_hook(project: Path, no: int, hook_type: str) -> dict:
    """登记/修改章节钩子类型（供 G06/G11 检测）。"""
    path = chapter_path(project, no)
    if not path.exists():
        raise ChapterError(f"第 {no} 章文件不存在")
    meta, body = fm.read_file(path)
    meta["hook_type"] = hook_type
    meta["updated_at"] = now_iso()
    _rewrite(path, meta, body)
    return {"no": no, "hook_type": hook_type}


# ---------------------------------------------------------------- 插章与重编号

def _backup_chapters(project: Path, tag: str) -> str:
    """把 chapters/ 整目录备份到 trash/<tag>/，返回备份路径。"""
    ts = now_iso().replace(":", "").replace("-", "").replace("T", "_").replace(" ", "_")
    dest = project / TRASH_DIR / f"{tag}_{ts}"
    shutil.copytree(chapters_dir(project), dest)
    return str(dest)


def insert_chapter(project: Path, before: int, title: str, dry_run: bool = False,
                   shift_foreshadow: bool = True) -> dict:
    """在第 before 章之前插入新章：新章占章号 before，原 before..末尾章全部 +1。

    顺序：dry-run 预览 → 备份 → 从最大章号降序搬迁（防覆盖）→ 建新章 → 伏笔联动 → 校验。
    """
    chapters = scan_chapters(project)
    if not chapters:
        raise ChapterError("章节目录为空，请先用 chapter new 创建章节")
    if before < 1 or before > chapters[-1]["no"] + 1:
        raise ChapterError(f"插入点越界：第 {before} 章之前（合法范围 1..{chapters[-1]['no'] + 1}）")

    moved = [c for c in chapters if c["no"] >= before]
    plan = {
        "action": "insert",
        "before": before,
        "new_chapter": {"no": before, "title": title},
        "moved": [{"from": c["no"], "to": c["no"] + 1, "file": c["file"]} for c in moved],
        "foreshadow_shift": {"from_chapter": before, "delta": 1} if (shift_foreshadow and moved) else None,
    }
    if dry_run:
        plan["dry_run"] = True
        return plan

    backup = _backup_chapters(project, "insert")
    # 降序搬迁，避免低号写入覆盖高号文件（正文与 spec 伴生文件同步搬迁）
    for c in sorted(moved, key=lambda x: x["no"], reverse=True):
        src = chapters_dir(project) / c["file"]
        meta, body = fm.read_file(src)
        new_no = c["no"] + 1
        meta["chapter"] = str(new_no)
        meta["updated_at"] = now_iso()
        # 若标题行存在，同步章号；无标题行则只改 frontmatter
        lines = body.split("\n")
        if lines and CHAPTER_TITLE_RE.match(lines[0]):
            m = CHAPTER_TITLE_RE.match(lines[0])
            lines[0] = f"# 第{new_no}章" + lines[0][m.end():].rstrip()
            body = "\n".join(lines)
        _rewrite(src, meta, body, key_order=META_KEY_ORDER)
        src.rename(chapter_path(project, new_no))
        # spec 伴生文件同步改名 + 章号字段更新
        old_spec = spec_path(project, c["no"])
        if old_spec.exists():
            from .models import read_json, safe_write_json
            spec = read_json(old_spec, default={})
            spec["chapter"] = new_no
            safe_write_json(old_spec, spec)
            old_spec.rename(spec_path(project, new_no))
    # 创建新章
    created = new_chapter(project, before, title)
    # 伏笔册联动
    fore_shift = None
    if shift_foreshadow:
        from .foreshadow import shift_chapters as fore_shift_chapters
        fore_shift = fore_shift_chapters(project, before, 1)
    # 收尾校验
    check = renumber(project, check_only=True)
    return {"plan": plan, "backup": backup, "created": created,
            "foreshadow_updated": fore_shift, "check": check}


def renumber(project: Path, dry_run: bool = False, check_only: bool = False) -> dict:
    """把全部章节从 1 开始连续重排；--check 只校验不修改。

    需要修复的判定：文件名/frontmatter 章号与目标序号不一致，
    或正文标题行章号与目标序号不一致。
    """
    chapters = scan_chapters(project)
    if not chapters:
        return {"action": "renumber-check", "total": 0, "ok": True, "issues": []}

    issues: list[str] = []      # 阻塞性问题（重复标题）
    advisory: list[str] = []    # 提示性问题（空章等，不阻塞）
    renum_plan = []
    for idx, c in enumerate(chapters, start=1):
        needs_fix = c["no"] != idx or c["file"] != f"ch_{idx:04d}.md"
        if not needs_fix:
            # 章号已正确时仍检查文件内部一致性（frontmatter / 标题行）
            path = chapters_dir(project) / c["file"]
            meta, body = fm.read_file(path)
            lines = body.split("\n")
            if fm.get_int(meta, "chapter", 0) != idx:
                needs_fix = True
            elif lines and CHAPTER_TITLE_RE.match(lines[0]):
                if CHAPTER_TITLE_RE.match(lines[0]).group(1) != str(idx):
                    needs_fix = True
        if needs_fix:
            renum_plan.append({"file": c["file"], "from": c["no"], "to": idx})
    # 重复标题检测
    titles = [c["title"] for c in chapters if c["title"]]
    dup = {t for t in titles if titles.count(t) > 1}
    if dup:
        issues.append(f"重复标题：{ '、'.join(sorted(dup)) }")
    # 空章检测（正文过短视为空章，提示性质）
    for c in chapters:
        if c["words"] < 10:
            advisory.append(f"第 {c['no']} 章疑似空章（frontmatter words={c['words']}）")

    if check_only:
        ok = not renum_plan and not issues
        return {"action": "renumber-check", "total": len(chapters), "ok": ok,
                "renumber_needed": renum_plan, "issues": issues, "advisory": advisory}
    if dry_run:
        return {"action": "renumber", "dry_run": True, "total": len(chapters),
                "renumber_plan": renum_plan, "issues": issues, "advisory": advisory}

    if not renum_plan:
        return {"action": "renumber", "total": len(chapters), "changed": 0, "issues": issues}

    backup = _backup_chapters(project, "renumber")
    # 先统一改名到临时名（防 A→B 时 B 已存在；正文与 spec 伴生文件同步）
    tmp_map: list[tuple[Path, Path]] = []
    for c, new_no in zip(chapters, range(1, len(chapters) + 1)):
        src = chapters_dir(project) / c["file"]
        tmp = chapters_dir(project) / f".tmp_{new_no:04d}.md"
        src.rename(tmp)
        old_spec = spec_path(project, c["no"])
        tmp_spec = None
        if old_spec.exists():
            tmp_spec = chapters_dir(project) / f".tmp_{new_no:04d}.spec.json"
            old_spec.rename(tmp_spec)
        tmp_map.append((tmp, tmp_spec, new_no))
    for tmp, tmp_spec, new_no in tmp_map:
        path = chapter_path(project, new_no)
        tmp.rename(path)
        meta, body = fm.read_file(path)
        changed = False
        if fm.get_int(meta, "chapter", 0) != new_no:
            meta["chapter"] = str(new_no)
            meta["updated_at"] = now_iso()
            changed = True
        lines = body.split("\n")
        if lines and CHAPTER_TITLE_RE.match(lines[0]):
            m = CHAPTER_TITLE_RE.match(lines[0])
            if m.group(1) != str(new_no):
                lines[0] = f"# 第{new_no}章" + lines[0][m.end():].rstrip()
                body = "\n".join(lines)
                changed = True
        if changed:
            _rewrite(path, meta, body)
        if tmp_spec is not None:
            from .models import read_json, safe_write_json
            spec_file = spec_path(project, new_no)
            tmp_spec.rename(spec_file)
            spec = read_json(spec_file, default={})
            if spec.get("chapter") != new_no:
                spec["chapter"] = new_no
                safe_write_json(spec_file, spec)
    check = renumber(project, check_only=True)
    return {"action": "renumber", "total": len(chapters), "changed": len(renum_plan),
            "backup": backup, "issues": issues, "check": check}
