# 命令详解

唯一入口：`python3 ~/.codebuddy/skills/novel-forge/scripts/novel.py <命令>`。
全局参数 `--project <路径>` 与 `--json` 可放在主命令或子命令后任意位置。

约定：默认人类可读输出；`--json` 输出 `{"ok": true/false, "data": {...}}` 或
`{"ok": false, "error": {"code": "...", "message": "..."}}` 信封。
退出码：0 成功 / 1 门禁不通过 / 2 参数或业务错误 / 3 未找到项目。

## init

```
init <path> --name 书名 [--genre 题材] [--author 作者]
     [--target-chapters 300] [--words-per-chapter 3000]
```

创建项目骨架（目录、book.json、state.json、foreshadow.json、设定模板）。
路径已存在 book.json 时报错退出。

## info

项目概览：书籍信息、章节统计（总数/完成/字数）、伏笔状态、AI 配置。

## framework（全书框架 · 长篇地基）

| 命令 | 说明 |
|---|---|
| `framework show` | 展示完整框架蓝图（Markdown 渲染，供作者审阅） |
| `framework audit` | 完整度体检：逐版块检查 + 缺口清单 + 下一步建议 + **百万字尺度告警** |
| `framework stage [阶段]` | 记录/查看构思进度 |
| `framework set <版块> --value '<JSON>'` | 写入框架版块（整块替换），返回 `shape_warnings` 做结构校验 |
| `framework set <版块> --file spec.json` | 从 JSON 文件导入整块 |
| `framework reject --idea "..." --reason "..."` | 登记被否决方案（避免重复提议） |
| `framework path` | 打印 framework.json 路径与是否存在 |

构思阶段顺序（`framework stage` 取值为下表的 key）：

`core → engine → theme → characters → ladder → structure → rhythm → midgame → reveal → opening → platform`

十一个版块的结构：

| 版块 | 结构 |
|---|---|
| **core** | `{protagonist, goal, obstacle, catalyst, one_liner}` |
| **engine** | `{loop: {gain, end, drive, diagram}, drive_wheels: {power, world, conflict, payoff}, extensibility: {tiers, stages, beyond}}` |
| **theme** | `{question, thesis, antithesis, synthesis}` |
| **characters** | `[{name, relation, own_goal, theme_face, voice}]`（建议 ≥3 位） |
| **ladder** | `{steps: [{name, stage, power, enemy, resource, secret}]}`（5-7 阶） |
| **structure** | `{acts: [{name, content}], volumes: [{name, chapters, goal, climax, change, theme_question}]}` |
| **rhythm** | `{wave_period, difficulty_step, breather_rule, ratio_note, waves: [{name, chapters, low, high, mood}]}` |
| **midgame** | `{hidden_identity, erased_history, unseen_faction, cognitive_truths: [...]}` |
| **reveal** | `[{secret, at, by, foreshadow}]` |
| **opening** | `{ch1, ch2, ch3}` |
| **platform** | `{target, reader_want, update_plan, titles: [...], blurbs: [...]}` |

体检规则：

- **基础完整度**：characters ≥3 位；structure 各卷章节数合计与目标总章数偏差 >10% 告警；
  每卷必须标注 theme_question（主题贯穿检查）
- **百万字尺度告警**（`_check_longform`）：
  - 核心循环的「获得」/「终点」/「驱动力」任一为空 → 告警
  - 四驱动轮配比合计 ≠100 → 提示；矛盾引擎 <10% → 提示
  - 阶梯表不足 5 阶 → 告警
  - 抑扬波周期 <8 万字 → 告警；>25 万字 → 提示
  - 难度梯度偏离 15%~35% → 提示
  - 目标 ≥50 万字但缺「中期三件套」→ 告警

**结构校验（`shape_warnings`，非阻塞）**：`framework set` 写入前会检查关键结构，
结构可疑时**仍然写入**，但在返回值里给出 `shape_warnings`，防止「静默失败」：

| 触发条件 | 告警 |
|---|---|
| `engine.loop` 写成字符串（应为对象） | 会让「核心循环未闭合」体检静默失效 |
| `engine.loop` 缺 gain/end/drive | 逐项点名缺失的环 |
| `ladder.steps` 非数组 | 阶梯表无法参与体检 |
| `rhythm.wave_period`/`difficulty_step` 写成字符串 | 节奏体检失效 |
| `structure.volumes[i]` 缺 chapters | 一致性校验 C04 需要它 |
| `characters`/`reveal` 写成对象（应为数组） | 版块会被判为空 |

> 判据：结构校验只覆盖「会让后续体检静默失效」的关键点，允许自由扩展额外字段。

## context

```
context <章号> [--tail 500] [--save]
```

装配本章生成上下文并输出 Markdown：**全书框架锚点**（内核/主题句/所属卷目标与卷末高潮）、
本章 spec、上一章结尾片段（--tail 控制字数）、出场角色声线卡全文、全部 planted 伏笔（超期打标）、
近 3 章钩子历史。`--save` 同时写入 `reports/context_chNNNN.md`。
生成任何正文之前必须先跑本命令。**框架未成型时会给出醒目警告。**

## setting

| 命令 | 说明 |
|---|---|
| `setting add character --name 林晚 [--role 主角]` | 登记角色卡（模板生成，id 自动分配，重名拒绝） |
| `setting list [--type character]` | 列出角色卡与设定文件 |
| `setting get character 林晚` | 查看角色卡全文（meta + body） |
| `setting update character 林晚 --set status=dead [--set role=主角]` | 更新 frontmatter 字段，可多次 --set |
| `setting search 关键词` | settings/ 全目录全文搜索（文件+行号+摘录） |

角色卡的正文（性格/声线卡/弧光/情节记录）直接编辑 Markdown 文件维护。

## chapter

| 命令 | 说明 |
|---|---|
| `chapter new [--number N] --title 章名` | 创建章节文件（缺省章号 = 最新章+1） |
| `chapter list [--status draft]` | 列出章节（实时扫描，无缓存） |
| `chapter stats [N或all]` | 字数统计（单章或全书；总是重算真实字数并回写 frontmatter） |
| `chapter set-status N --status draft/writing/review/done` | 更新章节状态 |
| `chapter set-hook N --hook 危机` | 登记钩子类型（8 类：危机/悬疑/反转/信息/情感/时间/选择/生存） |
| `chapter spec N [--init] [--file spec.json] [--set K=V]` | 章节 spec 查看/初始化/导入/单字段更新 |
| `chapter insert --before N --title 章名 [--dry-run] [--no-shift-foreshadow]` | 在第 N 章前插章并重编号 |
| `chapter renumber [--dry-run] [--check]` | 全书章号连续重排 / 只校验 |

spec 字段（`chapters/ch_NNNN.spec.json` 伴生文件）：
`summary`（200 字摘要）、`characters`（出场角色名数组）、`must_happen`（必须发生的情节点）、
`tension_curve`（[{pos, value, note}]）、`new_hooks`（本章新钩子）、`target_words`（本章目标字数）。
--set 的值可解析为 JSON 则结构化存储，否则按字符串。

插章流程：`--dry-run` 预览（搬迁清单 + 伏笔联动）→ 向作者确认 → 去掉 --dry-run 执行。
执行时自动：chapters/ 整目录备份到 trash/<时间戳>/ → 降序搬迁正文与 spec 伴生文件 →
更新标题行与 frontmatter → 伏笔册章号联动 +1 → 自动 renumber --check 收尾。

## foreshadow

| 命令 | 说明 |
|---|---|
| `foreshadow add --desc "描述" --planted-chapter X --expected-recover Y [--priority main]` | 登记伏笔（id 自动 F-NNN） |
| `foreshadow list [--status planted/recovered/overdue/severe]` | 列出（overdue/severe 为动态计算） |
| `foreshadow recover F-001 --chapter N` | 标记回收 |
| `foreshadow audit` | 预警检查：到期未回收 overdue；超期超过 warn_after_overdue（默认 3）章升级 severe |

## check / report

| 命令 | 说明 |
|---|---|
| `check [N或all] [--strict]` | 质量门禁（默认 error 级不通过才失败；--strict 时 warn 也失败） |
| `check [N或all] --consistency` | 门禁之外追加**框架一致性校验**（C01-C05） |
| `check --rules` | 查看合并后生效的阈值与三级词表 |
| `report [N或all] [--strict] [--consistency]` | 执行门禁并把报告落盘 reports/（md + json） |

报告含：评分（100 - error单位×5 - warn单位×2）、逐规则明细（行号+摘录+指引）、
修订优先级表（段落热度 = Σ(error×3 + warn×1)，按热度降序，先改最上面）。
行号相对正文（不含 frontmatter 与标题行）。

**框架一致性校验 C01-C05**（`--consistency`，不阻塞，仅 warn/info 提示）：
C01 卷目标呼应（本章是否命中本卷 goal 关键词）、C02 角色动机锚定（出场角色是否都有框架 own_goal）、
C03 卷内伏笔进度（本卷应回收的伏笔是否到期未收）、C04 卷章节范围（是否已抵近卷末）、
C05 主题触碰（是否回应了 theme.question）。用于长篇"写着写着跑偏"的早期预警。

## stats / progress / dashboard

| 命令 | 说明 |
|---|---|
| `stats [--daily 7]` | 全书统计（总章/总字/均值/极值/状态分布；--daily 近 N 天日产出） |
| `progress` | 对照 book.json target 的章节数与字数完成度百分比 |
| `dashboard [--days 7] [--width 48] [--no-daily] [--no-volumes] [--no-dist] [--md]` | 进度可视化看板 |

`dashboard` 输出零依赖终端图表（纯字符渲染，不引外部绘图库）：

- **全书进度条**：章节数与字数对目标的完成度（含半格精度）；
- **分卷进度条**：按 framework 登记的卷区间计算每卷已写章数/计划章数，附卷目标；
- **日产出条形序列**：近 N 天每日字数（峰值映射满宽）；
- **单章字数分布直方图**：等宽 5 箱，快速识别是否有章明显偏短/偏长。

选项：`--days 0` 关闭日产出；`--width` 调图宽（窄终端可设 32）；`--md` 用代码块包裹便于存档；
`--json` 输出结构化看板数据（含 progress/stats/volumes/daily/distribution）供二次加工。
未创作章节不计入分布与字数。

## ai

| 命令 | 说明 |
|---|---|
| `ai status` | AI 配置状态。v1 为纯工具版：provider=null 恒不可用；续写/润色由对话内 Claude 按生成工作流完成 |
| `ai test` | 探测调用（v1 返回未启用提示与接入指引） |

## health（全书体检 · 跨章趋势）

```
health [--json]
```

单看每一章都挑不出毛病，但把它们排在一起看，趋势可能是危险的。本命令做四项**跨章节**检查：

| ID | 名称 | 级别 | 检查内容 |
|---|---|---|---|
| W01 | 爽点密度与呼吸章 | warn | 连续 ≥6 章都是强钩子（危机/反转/生存）→ 缺呼吸章，读者会「追不动」 |
| W02 | 钩子类型多样性 | warn | 单一钩子类型占比 >60% → 预期疲劳，建议换型 |
| W03 | 空转风险 | info | 已写 ≥10 章但 >50% 没有登记 spec 的 must_happen/summary → 无法判断是否在推进主线 |
| W04 | 字数离群 | info | 出现字数不足均值 45% 的章 → 疑似凑数/拼接 |

输出为 Markdown 表格。有 warn 级问题（W01/W02）时退出码为 1。
建议**每写完一卷或每隔 10 章**跑一次。
