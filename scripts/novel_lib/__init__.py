"""novel-forge 内部实现包。

模块划分：
- models.py       JSON 安全读写（四步铁律：read → merge → write → verify）
- frontmatter.py  零依赖平面 k:v frontmatter 解析/回写
- project.py      项目发现（向上查找 book.json）与 init 骨架
- chapter.py      章节文件管理：new/list/stats/set-status/insert/renumber
- foreshadow.py   伏笔登记册：add/list/recover/audit 预警
- lexicon.py      三级词表加载与合并（内置默认 + 项目级覆盖）
- gate.py         质量门禁引擎：G01-G12 规则、评分、报告
- stats.py        字数统计、进度计算
- ai_provider.py  AIProvider 抽象 + NullProvider（v1 空实现）
"""

__version__ = "1.0.0"
