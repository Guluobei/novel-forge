# novel-forge · 网文创作工坊

一个面向**百万字长篇网络小说**创作的确定性工具链，采用 **「AI 生成 80 分草稿 + 作者润色」** 协作模式。

> **核心理念**：不是让 AI 一键生成整本小说，而是让 AI 帮你把**结构到位、语言留白**的草稿搭出来，由你来注入语气、词句与灵魂。

---

## 为什么需要它

AI 直接写网文最大的问题是「AI 味太浓」——辞藻华丽却空洞，结构松散难支撑长篇。novel-forge 的思路相反：

- **框架先于章节**：百万字长篇靠内核与主题撑着，不是靠一章一章凑出来的
- **短篇靠点子，长篇靠机制**：三十万字开始「空转」的书，问题不在文笔，在**核心循环**没建起来
- **确定性检查交给脚本**：字数、词表、钩子、一致性这些能用规则判断的，全部本地确定性执行，零 API 依赖

**长篇的第一原则：框架先于章节。**

---

## 核心能力

### 1. 长篇框架构思（11 版块）

先想清楚「这本书能不能撑到 100 万字」，再动笔：

| 版块 | 内容 |
|---|---|
| core | 故事内核（主角/目标/阻碍/催化剂） |
| engine | **核心循环与四驱动轮**（获得/终点/驱动力 + 实力/世界/矛盾/爽点配比） |
| theme | 主题与内核矛盾（主题句 + 正反合） |
| characters | 人物关系网（力场与主题面） |
| ladder | **可攀越的世界观阶梯表**（5-7 阶 × 舞台/实力上限/对手/资源/秘密） |
| structure | 分卷结构（三幕 + 卷划分 + 每卷本质变化） |
| rhythm | 节奏与情绪波（抑扬波周期 + 难度梯度 + 呼吸法则） |
| midgame | **中期弹药库**（中期三件套 + 认知线五真相，防空转/防人设崩） |
| reveal | 信息揭示表 |
| opening | 开篇设计（黄金三章） |
| platform | 平台与门面（番茄/起点定位 + 书名公式 + 简介四要素） |

### 2. 质量门禁 G01–G12

每章交付前自动检查：字数下限、破折号密度、ban/warn/limit 三级词表、钩子登记、裸对话标签、章末收束、情绪命名、长短句交替、钩子多样性、段首重复。

### 3. 框架一致性校验 C01–C05

跨章校验：卷目标呼应、角色动机锚定、卷内伏笔进度、卷章节范围、主题触碰。

### 4. 全书体检（跨章趋势）W01–W04

- **W01** 爽点密度与呼吸章（连 6 章强钩子会告警）
- **W02** 钩子类型多样性（单类型 >60% 告警）
- **W03** 空转风险（大量章节无目标推进）
- **W04** 字数离群（远低于均值的章节）

### 5. 进度可视化

`dashboard` 命令输出章节/字数进度条、分卷进度、近 7 天日产出。

---

## 设计架构：三层分离

| 层 | 职责 | 实现 |
|---|---|---|
| **确定性层** | 规则检查、统计、校验 | Python 脚本 |
| **创作层** | 结构生成 + 作者润色 | AI 生成草稿 / 人来润色 |
| **调度层** | 决定跑什么命令 | 主流程编排 |

**零依赖**：不需要 PyYAML、绘图库、pytest。只用 Python 标准库。

---

## 安装

把 `novel-forge/` 整个目录放到 skills 目录下：

```bash
# 例如 WorkBuddy / Claude Code 的 skills 目录
cp -r novel-forge ~/.codebuddy/skills/
```

要求：Python 3.11+（仅标准库）。

---

## 快速开始

唯一 CLI 入口是 `scripts/novel.py`：

```bash
# 1. 初始化项目
python3 scripts/novel.py init ./我的小说 --name "书名" --genre 都市高武 --target-chapters 360

# 2. 构思框架（逐个版块落盘）
python3 scripts/novel.py framework set engine --project ./我的小说 --value '{"loop":{...},"drive_wheels":{...}}'

# 3. 体检框架完整度
python3 scripts/novel.py framework audit --project ./我的小说

# 4. 查看蓝图
python3 scripts/novel.py framework show --project ./我的小说

# 5. 写章节 → 跑门禁
python3 scripts/novel.py check --project ./我的小说 --consistency

# 6. 全书体检
python3 scripts/novel.py health --project ./我的小说

# 7. 进度看板
python3 scripts/novel.py dashboard --project ./我的小说
```

**退出码**：0 成功 / 1 门禁不通过 / 2 参数错误 / 3 未找到项目。

完整命令参考见 [`references/commands.md`](references/commands.md)。

---

## 目录结构

```
novel-forge/
├── SKILL.md                      # Skill 主入口（渐进式披露）
├── assets/                       # 项目初始化模板
├── references/                   # 详细资料
│   ├── brainstorming-workflow.md # 八阶段构思工作流
│   ├── long-form-craft.md        # 长篇骨架方法论
│   ├── platform-guide.md         # 平台定位与运营
│   ├── commands.md               # 命令速查
│   ├── gate-rules.md             # 门禁与体检规则
│   └── data-format.md            # 数据格式规范
└── scripts/
    ├── novel.py                  # CLI 入口
    ├── selftest.py               # 自测（142 项）
    └── novel_lib/                # 核心模块
```

---

## 方法论来源

框架方法论综合自公开的网文创作经验（核心循环、四驱动轮、阶梯表、呼吸法则、中期三件套、黄金三章、平台差异等），并与一线创作实践对齐。

---

## 测试

```bash
python3 scripts/selftest.py
```

**142 项全部通过**，覆盖 models / frontmatter / gate G01-G12 / framework / consistency C01-C05 / visualize / wholebook W01-W04 / e2e 主线。

---

## License

MIT
