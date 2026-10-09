# -*- coding: utf-8 -*-
"""零依赖平面 frontmatter 解析/回写（无 PyYAML）。

支持的格式为严格平面 `key: value` 行，位于首行 `---` 与下一个 `---` 之间：

    ---
    chapter: 1
    title: 雨夜
    status: draft
    ---

    # 第1章 雨夜

    正文……

约定：
- 值为原始字符串，不做类型推断（调用方自行转换 int/float/bool）
- 复杂类型（列表）用逗号分隔字符串表示
- 解析时忽略无法匹配 `key: value` 的行；回写时按固定 key 顺序输出
"""
from __future__ import annotations

import re
from pathlib import Path

FM_SEP = "---"
_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


def parse(text: str) -> tuple[dict[str, str], str]:
    """解析全文，返回 (meta, body)。无 frontmatter 时 meta 为空 dict。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != FM_SEP:
        return {}, text
    meta: dict[str, str] = {}
    idx = 1
    while idx < len(lines):
        line = lines[idx]
        if line.strip() == FM_SEP:
            idx += 1
            break
        m = _KV_RE.match(line.strip())
        if m:
            meta[m.group(1)] = m.group(2).strip()
        idx += 1
    else:
        # 只有起始分隔符：视为无 frontmatter，原文返回
        return {}, text
    body = "\n".join(lines[idx:])
    if body.startswith("\n"):
        body = body[1:]
    return meta, body


def dump(meta: dict[str, str], body: str, key_order: list[str] | None = None) -> str:
    """把 meta 与 body 组装回全文。key_order 指定输出顺序，未列出的 key 追加在后。"""
    keys = list(key_order or []) if key_order else []
    keys += [k for k in meta if k not in keys]
    out = [FM_SEP]
    for k in keys:
        out.append(f"{k}: {meta.get(k, '')}")
    out.append(FM_SEP)
    return "\n".join(out) + "\n\n" + body


def read_file(path: str | Path) -> tuple[dict[str, str], str]:
    """读取文件并解析 frontmatter。"""
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


def write_file(path: str | Path, meta: dict[str, str], body: str,
               key_order: list[str] | None = None) -> None:
    """回写文件（覆盖）。遵循 read → 修改 → write → 回读验证铁律。"""
    p = Path(path)
    expected = dump(meta, body, key_order)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(expected)
    # 回读验证
    back_meta, back_body = read_file(p)
    # body 末尾的换行差异允许存在（dump 会在 body 前补空行）
    if {k: v for k, v in back_meta.items() if v} != {k: v for k, v in meta.items() if v}:
        raise IOError(f"frontmatter 回写验证失败 {p}")
    if back_body.rstrip("\n") != body.rstrip("\n") and back_body != body:
        raise IOError(f"正文回写验证失败 {p}")


def get_int(meta: dict[str, str], key: str, default: int = 0) -> int:
    """从 meta 中取 int，失败返回 default。"""
    try:
        return int(str(meta.get(key, default)).strip())
    except (ValueError, TypeError):
        return default
