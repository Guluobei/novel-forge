# -*- coding: utf-8 -*-
"""JSON 安全读写与合并工具。

遵守文件写入铁律：read → 内存合并 → write（原子替换）→ read 回读验证。
所有台账类 JSON（book.json / state.json / foreshadow.json）的写入必须走本模块。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonIOError(RuntimeError):
    """JSON 读写失败（含回读验证失败）。"""


def read_json(path: str | Path, default: Any = None) -> Any:
    """读取 JSON 文件；文件不存在时返回 default。"""
    p = Path(path)
    if not p.exists():
        return default
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise JsonIOError(f"读取 JSON 失败 {p}: {e}") from e


def safe_write_json(path: str | Path, data: Any) -> None:
    """原子写 JSON 并回读验证。

    步骤：写入同目录临时文件 → os.replace 原子替换 → 重新读取并比对。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp", prefix=".novel_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, p)
    except OSError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise JsonIOError(f"写入 JSON 失败 {p}: {e}") from e
    # 回读验证
    back = read_json(p)
    if back != data:
        raise JsonIOError(f"JSON 回读验证失败 {p}（写入与读回内容不一致）")



