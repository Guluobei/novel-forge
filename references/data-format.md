# 数据格式说明

## 项目结构

```
<项目根>/                     # book.json 所在目录（项目定位向上查找）
├── book.json                 # 书籍元数据 + 门禁配置 + AI 配置
├── framework.json            # 全书框架（11 版块，长篇地基）
├── state.json                # 机器状态（next_chapter_number/created_at/updated_at）
├── foreshadow.json           # 伏笔登记册
├── settings/
│   ├── worldview.md          # 世界观（模板生成，内容直接编辑）
│   ├── factions.md           # 势力
│   ├── outline.md            # 总大纲
│   └── characters/
│       ├── _index.json       # 角色索引（加速缓存，扫描为准）
│       └── char_001_林晚.md  # 角色卡（ASCII 前缀保证排序）
├── outline/volumes.md        # 卷规划
├── chapters/
│   ├── ch_0001.md            # 一章一文件（4 位补零，字典序 == 章节序）
│   └── ch_0001.spec.json     # 章节 spec 伴生文件
├── reports/                  # 门禁报告（md+json）与上下文存档
└── trash/                    # 插章/重编号的时间戳备份（不真删）
```

## book.json

```json
{
  "name": "书名", "author": "", "genre": "",
  "target": {"total_chapters": 300, "words_per_chapter": 3000},
  "schema_version": 1,
  "gate": {
    "thresholds": {
      "min_words": 3000, "max_dash": 12, "max_warn": 3,
      "max_emotion_naming": 2, "bare_tag_max_ratio": 0.3
    },
    "lexicon_override": {
      "ban": {"add": [], "remove": []},
      "warn": {"add": [], "remove": []},
      "limit": {"add": [], "remove": []}
    }
  },
  "ai": {
    "enabled": false, "provider": "null",
    "base_url": "", "model": "",
    "api_key_env": "NOVEL_FORGE_API_KEY",
    "features": {"continue": false, "polish": false}
  }
}
```

## framework.json（全书框架）

11 个版块，全部可选但建议填齐。前六块是「一本书的地基」，后五块是「能活到一百万字的骨架」。

```json
{
  "version": 2,
  "stage": "core",
  "core": {"protagonist": "", "goal": "", "obstacle": "", "catalyst": "", "one_liner": ""},
  "engine": {
    "loop": {"gain": "每轮获得什么", "end": "每轮终点", "drive": "驱动力", "diagram": "循环图"},
    "drive_wheels": {"power": 60, "world": 20, "conflict": 12, "payoff": 8},
    "extensibility": {"tiers": "6 档", "stages": "每档不同舞台", "beyond": "真相与代价"}
  },
  "theme": {"question": "", "thesis": "", "antithesis": "", "synthesis": ""},
  "characters": [{"name": "", "relation": "", "own_goal": "", "theme_face": "", "voice": ""}],
  "ladder": {"steps": [{"name": "一阶", "stage": "乡镇", "power": "引气", "enemy": "", "resource": "", "secret": ""}]},
  "structure": {
    "acts": [{"name": "第一幕", "content": ""}],
    "volumes": [{"name": "卷一", "chapters": "1-40", "goal": "", "climax": "", "change": "", "theme_question": ""}]
  },
  "rhythm": {"wave_period": 15, "difficulty_step": 25, "breather_rule": "", "ratio_note": "",
             "waves": [{"name": "", "chapters": "", "low": "", "high": "", "mood": ""}]},
  "midgame": {"hidden_identity": "", "erased_history": "", "unseen_faction": "",
              "cognitive_truths": ["真相一"]},
  "reveal": [{"secret": "", "at": "", "by": "", "foreshadow": ""}],
  "opening": {"ch1": "", "ch2": "", "ch3": ""},
  "platform": {"target": "起点", "reader_want": "", "update_plan": "", "titles": [], "blurbs": []},
  "rejected": [{"idea": "", "reason": "", "at": ""}]
}
```

**字段语义要点**：

- `engine.loop` 的 `gain` 为空是最危险的信号——读者会认为主角在瞎忙
- `engine.drive_wheels` 四项建议合计 100，用来判断这本书偏哪一极
- `ladder.steps` 建议 5-7 阶；**哪一阶缺对手/资源/秘密，哪一阶将来就会水**
- `rhythm.wave_period` 单位是万字（10-20 为佳）；`difficulty_step` 单位是百分比（20-30 为佳）
- `midgame` 是 30 万字之后的弹药库，目标 ≥50 万字时体检会检查
- `platform` 影响前三章密度，写前三章前应确定

`framework audit` 会基于以上字段给出告警与提示。详见 `references/commands.md`。

## 章节文件

frontmatter 为平面 `k: v`（自实现解析器，无 PyYAML 依赖；列表用 JSON 字符串经 CLI 写入）：

```markdown
---
chapter: 3
title: 旧宅
status: draft
hook_type: 悬疑
words: 3150
updated_at: 2026-10-08T11:32:06
---

# 第3章 旧宅

正文……
```

- status 流转：draft → writing → review → done
- 字数口径：正文去除所有空白字符后的字符数（含标点），不含 frontmatter 与标题行
- 正文标题行 `# 第N章 标题` 与 frontmatter.chapter 双写一致（renumber 自动维护）

## 章节 spec（ch_NNNN.spec.json）

```json
{
  "chapter": 3,
  "title": "旧宅",
  "summary": "200 字内摘要",
  "characters": ["林晚"],
  "must_happen": ["发现拖痕", "怀表指针异动"],
  "tension_curve": [{"pos": 0, "value": 3, "note": "开场"}, {"pos": 60, "value": 8, "note": "发现"}],
  "new_hooks": ["神秘人是谁"],
  "target_words": 3000
}
```

context 装配时：spec.characters 决定加载哪些声线卡；must_happen 是生成锚点。

## 角色卡

frontmatter：`id` / `name` / `role` / `status`（active/dead/…）/ `relations`。
正文四节：基本档案、性格与动机、**声线卡**（高频词/句式特征/比喻域——对话一致性的根基）、人物弧光。

## 伏笔登记册

```json
{
  "warn_after_overdue": 3,
  "items": [{
    "id": "F-001", "desc": "描述",
    "planted_chapter": 1, "expected_recover_chapter": 15,
    "recovered_chapter": null, "status": "planted", "priority": "main"
  }]
}
```

status：planted → recovered。audit 动态标记：最新章号 ≥ 预期回收章 → overdue；
超期超过 warn_after_overdue 章 → severe。插章/重编号时三个章号字段自动 +1（--no-shift-foreshadow 可关）。

## AI 配置（当前版本无需任何配置）

novel-forge v1 **不接任何外部大模型服务**：

- **生成**：由 WorkBuddy 对话内的模型完成（Claude 按 generation-workflow.md 的流程写作），
  无需 API Key、无需网络请求，不存在境外模型访问问题
- **检查**：全部由本地 Python 脚本确定性执行

`ai status` 显示 `provider: null / available: False` 是正常状态，不影响任何功能。

### 预留接入点（仅当未来需要「无人值守批量生成」时才使用）

1. `scripts/novel_lib/ai_provider.py` 的 `AIProvider` 抽象（is_available / continue_writing / polish）
2. 在 `get_provider` 注册表登记新 provider（如 `openai_compatible`）
3. book.json 的 ai 段填 `{"enabled": true, "provider": "openai_compatible", "base_url": "...", "model": "...", "api_key_env": "NOVEL_FORGE_API_KEY"}`

接口为 **OpenAI 兼容格式**，国产大模型均提供兼容端点，例如：

| 模型 | base_url |
|---|---|
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` |
| DeepSeek | `https://api.deepseek.com` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Kimi | `https://api.moonshot.cn/v1` |

API Key 一律走环境变量（api_key_env 指定变量名），禁止写入 book.json。

## 写入安全

所有台账 JSON（book/state/foreshadow/spec/_index）的写入走 `safe_write_json`：
写临时文件 → 原子替换 → 回读验证（内容不一致即报错）。
章节 Markdown 走 frontmatter.write_file：写入 → 回读 meta/body 校验。
