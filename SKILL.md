---
name: novel-forge
description: 网络小说确定性创作管理工具链，采用「AI 生成 80 分草稿 + 作者润色」协作模式。当用户创建或管理小说项目（世界观、角色卡、章节、伏笔追踪）、构思百万字长篇框架（故事内核/核心循环/四驱动轮/主题/人物网/阶梯表/分卷结构/节奏抑扬波/中期弹药库/信息揭示表/黄金三章/平台定位）、要求写新章节或生成章节草稿、查询字数与写作进度（进度看板/日产出/字数分布）、执行质量门禁（ban/warn/limit 词表、破折号、对话标签、钩子、章末、情绪命名检测）、框架一致性校验（卷目标呼应/角色动机/伏笔进度/主题触碰）、全书体检（爽点密度/钩子多样性/空转风险/字数离群）、插入章节重编号、需要章节修订导航（AI 味热力图）时使用。零 API 依赖，规则检查由本地脚本确定性执行。
display_name: 网文创作工坊
version: 1.3.0
---

# novel-forge：网文创作管理工具链

**核心模式**：与作者一起想清楚框架 → Claude 生成 80 分草稿（结构到位、语言留白）→ 跑门禁出修订导航 → 作者润色语气词句 → 机检收尾。

**长篇的第一原则：框架先于章节。** 百万字长篇靠的是内核与主题撑着，不是靠一章一章往下写凑出来的。

**长篇的第二原则：短篇靠点子，长篇靠机制。** 凡是三十万字开始「空转」的书，问题不在文笔，在**核心循环**没建起来。框架必须先回答「这套机制怎么能反复跑几百次还不腻」。

## 快速开始

脚本路径（唯一 CLI 入口）：

```bash
python3 ~/.codebuddy/skills/novel-forge/scripts/novel.py <命令>
```

- 项目定位：`--project <路径>` 显式指定，或从当前目录向上查找 `book.json`
- 加 `--json` 得结构化输出（放子命令前后均可）；退出码：0 成功 / 1 门禁不通过 / 2 参数错误 / 3 未找到项目
- 完整参数见 `references/commands.md`

## 铁律（违反即返工）

1. **框架未成型不动笔**：`framework audit` 未通过前，不写任何正文。缺框架时写的章节是无效功
2. **核心循环未闭合不动笔**：循环的「获得」环为空的书，读者三章后就会觉得主角在瞎忙
3. **构思不是代做决定**：作者说"随便/你定"时，给 2-3 个差异方案 + 各自会写出什么样的书，让作者选
4. **一次只推进一个阶段**：构思阶段逐个推进，每步经作者确认
5. **不能抄近路**：目标必须可验证、反派必须是主题最强论证者、配角的"力"必须有方向、金手指必须有代价
6. **一次只写一章**：spec 未确认不动笔；交付前必跑 check；作者已润色的段落不二次改写

## 构思协作（新书第一步，也是最重要的一步）

**触发场景**：作者说"我想写一本 XX 题材的小说""帮我构思一本小说""框架还不行""书名还没想好"。

流程（详见 `references/brainstorming-workflow.md`，方法论详见 `references/long-form-craft.md`）：

1. 先判断作者起点（题材 / 画面 / 人物 / 主题），据此选择进入的阶段
2. 依次推进八个阶段，每阶段产出后用提问确认，绝不连跳：
   - **阶段 0 定平台** —— 番茄/起点决定前三章的密度，写前三章前必须定
   - **阶段 1 故事内核** —— 主角/目标/阻碍/催化剂 + **延展性三问**（这题能撑一百万吗）
   - **阶段 1.5 核心循环与驱动轮** —— 循环三问（获得/终点/驱动力）+ 四轮配比（★最硬的一块）
   - **阶段 2 主题与内核矛盾** —— 无标准答案的问题 + 正题/反题/合题；冲突要到"正义与正义的碰撞"
   - **阶段 3 人物关系网** —— 每位核心角色是"力"不是标签；九线自查；金手指三条限制两个副作用
   - **阶段 4 分卷结构** —— 三幕 + 5-8 卷 + **阶梯表（5-7 阶）** + **抑扬波（每 10-20 万字）** + **中期弹药库**
   - **阶段 5 信息揭示表** —— 每个秘密至少 3 处前置铺垫；代价早于真相
   - **阶段 6 开篇设计** —— 黄金三章硬清单，最后才做
   - **阶段 7 门面** —— 书名公式 / 简介四要素 / 5 书名 + 3 版简介
3. 每完成一块，用 `framework set <版块> --value '<JSON>'` 落盘，`framework audit` 查看缺口与**百万字尺度告警**
   - `set` 会返回 `shape_warnings`：结构写错（如把 `engine.loop` 写成字符串）时不阻塞写入，但明确告警，
     避免「写进去没报错、体检静默失效」——**看到 shape_warnings 必须按提示改成正确结构再落盘**
4. 作者否掉的方案用 `framework reject` 登记，避免反复提同一个被否过的方向
5. 全部完成后 `framework audit` 显示 complete 且无告警，才进入章节创作

**主动风险提示（必须做）**：作者的设定若会导致后期难以为继（金手指无代价、目标不可验证、
反派动机单薄、阶梯表不足 5 阶、核心循环「获得」环为空、缺中期三件套、分卷章节数严重不匹配），
必须当场说明理由并给修正方向。

## 创作循环（框架成型后，写一章的标准流程）

依次执行，顺序不可乱：

1. `chapter new --title 章名` —— 建章（已建则跳过）
2. `chapter spec N --init` → 填写 summary/must_happen/tension_curve/characters → **向作者确认后才动笔**
3. `context N` —— 装配上下文（**全书框架锚点**、spec、上一章结尾、声线卡、伏笔、钩子历史），作为唯一生成依据
4. 生成正文写入章节文件，更新 frontmatter 的 `hook_type`；遵守 `references/generation-workflow.md` 的准则
5. `check N` —— 跑门禁；长篇建议加 `--consistency` 一并查是否偏离卷目标/主题
6. 把报告的「修订优先级」表交给作者：哪几段 AI 味最重、怎么改。**不替作者润色语言**
7. 作者改完后复跑 `check N` → `chapter set-status N --status done` → 新伏笔用 `foreshadow add` 登记
8. 每写完一卷或每隔 10 章：跑 `health` 查趋势（爽点是否过密、钩子是否退化、有没有空转），跑 `dashboard` 看节奏

> **呼吸章纪律**：如果连续 10 章每章都有大爽点，强制插入 2-3 章呼吸章（日常/信息整理/配角视角/伏笔回收）。
> 爽点给得越密，读者跑得越快。

## 命令速查

| 作者意图 | 命令 |
|---|---|
| 开新书 | `init <路径> --name 书名 --genre 题材` |
| 看项目全貌 | `info` |
| **构思框架/看蓝图** | `framework show` / `framework audit`（缺哪块一目了然 + 百万字尺度告警）/ `framework stage <阶段>` |
| **写入框架版块** | `framework set core\|engine\|theme\|characters\|ladder\|structure\|rhythm\|midgame\|reveal\|opening\|platform --value '<JSON>'` |
| **登记被否方案** | `framework reject --idea "..." --reason "..."` |
| 登记角色 | `setting add character --name 角色名 --role 主角` |
| 填角色声线卡 | 直接编辑 `settings/characters/char_*.md`（声线卡是语气一致的根基） |
| 查设定/搜关键词 | `setting list` / `setting get character 名` / `setting search 词` |
| 写新章 | `chapter new --title 章名` → 走创作循环 |
| 定本章大纲 | `chapter spec N --set 'summary=...' --set 'must_happen=["A","B"]'` |
| 装配写作上下文 | `context N [--save]`（含全书框架锚点） |
| 交稿前质检 | `check N`（或 `check all`）；`--strict` 时 warn 也判不过 |
| **查是否写跑偏** | `check N --consistency`（C01-C05：卷目标/角色动机/伏笔进度/卷范围/主题） |
| 看 AI 味重灾区 | `check N` 报告的修订优先级表（按段落热度排序） |
| 生成质检报告存档 | `report N`（落盘 reports/） |
| 查生效规则与词表 | `check --rules` |
| 登记伏笔 | `foreshadow add --desc "..." --planted-chapter X --expected-recover Y` |
| 伏笔预警 | `foreshadow audit`（overdue/severe 分级） |
| 标记伏笔回收 | `foreshadow recover ID --chapter N` |
| 章前插章 | `chapter insert --before N --title 章名 --dry-run` → 确认后去掉 --dry-run（章号/伏笔/spec 自动联动） |
| 章号校验/重排 | `chapter renumber --check` / `chapter renumber` |
| 改章节状态/钩子 | `chapter set-status N --status done` / `chapter set-hook N --hook 悬疑` |
| 字数与进度 | `chapter stats N` / `stats [--daily 7]` / `progress` |
| **看进度看板** | `dashboard [--days 7] [--md]`（全书/分卷进度条 + 日产出 + 字数分布，纯文本图表） |
| **全书体检** | `health`（W01-W04：爽点密度/钩子多样性/空转风险/字数离群） |
| AI 能力状态 | `ai status`（v1 不接外部模型：草稿由对话内模型生成，检查由本地脚本完成，无需任何 API Key） |

## 项目结构（init 生成）

```
<项目根>/
├── book.json          # 元数据 + 门禁阈值/词表覆盖 + AI 配置段
├── framework.json     # 全书框架 ★长篇地基（11 版块：内核/循环/主题/人物/阶梯/结构/节奏/中期/揭示/开篇/平台）
├── foreshadow.json    # 伏笔登记册
├── settings/          # worldview/factions/outline 模板 + characters/ 角色卡
├── chapters/          # ch_NNNN.md 一章一文件 + ch_NNNN.spec.json 章级锚点
├── outline/volumes.md # 卷规划
├── reports/           # 门禁报告与上下文存档
└── trash/             # 插章/重编号的自动备份
```

框架的 11 个版块（`framework set <版块> --value '<JSON>'`）：

| 版块 | 内容 |
|---|---|
| `core` | 主角 / 目标 / 阻碍 / 催化剂 / 一句话 |
| `engine` | 核心循环（loop）+ 四驱动轮配比（drive_wheels）+ 延展性三问 |
| `theme` | 主题句 / 正题 / 反题 / 合题 |
| `characters` | 人物网：关系 / 自己的目标 / 主题面 / 声线 |
| `ladder` | 阶梯表：5-7 阶 ×（舞台/实力上限/对手/资源/秘密） |
| `structure` | 三幕 + 5-8 卷（含卷目标/高潮/本质变化/主题新问法） |
| `rhythm` | 抑扬波周期 + 难度梯度 + 呼吸章纪律 + 爽点节奏 |
| `midgame` | 中期三件套（身世/历史/势力）+ 认知线五真相 |
| `reveal` | 信息揭示表：秘密 / 位置 / 揭示者 / 铺垫 |
| `opening` | 黄金三章分工 |
| `platform` | 目标平台 / 读者期待 / 更新计划 / 书名 / 简介 |

章节文件 = frontmatter（chapter/title/status/hook_type/words）+ 正文（首行 `# 第N章 标题`）。字数口径：去空白字符数。

## 硬性规则

1. **框架先于章节**：`framework audit` 未通过前不写正文；写完后如需调整框架，回到对应阶段修订而非硬写
2. **章节文件的增删改走命令**：创建/改状态/插章/重编号必须用 CLI，保证一致性；只有正文与角色卡内容可直接编辑
3. **JSON 台账不手工编辑**：book.json/framework.json/foreshadow.json/state.json 的修改走脚本（内置四步写入校验）
4. **插章先 dry-run**：`chapter insert --dry-run` 预览计划，向作者确认后执行（执行时自动 trash 备份）
5. **生成前先 context**：任何章节生成必须先跑 `context N`，禁止凭记忆写正文

## 资源索引

- `references/brainstorming-workflow.md`：**新书第一步必读**——八阶段构思流程（含平台定位与核心循环）、每阶段的产出要求与判据、协作规范
- `references/long-form-craft.md`：**长篇骨架方法论**——核心循环 / 四驱动轮 / 延展性 / 阶梯表 / 抑扬波 / 呼吸法则 / 中期三种死法 / 九线设定 / 金手指
- `references/platform-guide.md`：**平台与运营**——番茄起点差异 / 书名简介公式 / 黄金三章 / 章末钩子 / 更新纪律 / 数据心态 / 卡文急救包 / 全稿自查清单
- `references/generation-workflow.md`：**写任何章节前必读**——80 分标准、生成准则（去 AI 味写作规则）、修订循环、交互铁律
- `references/commands.md`：全部子命令参数详解
- `references/gate-rules.md`：G01-G12 规则依据、C01-C05 一致性校验、W01-W04 全书体检、误报处理、词表覆盖方法
- `references/data-format.md`：数据结构字段说明、AI 配置接入方式
