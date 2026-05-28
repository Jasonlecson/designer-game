# 前后端通信协议

## 概述

- **通信方式**: HTTP REST API，全部使用 JSON 格式
- **鉴权**: 使用 Flask session（浏览器 Cookie）自动维护，无需前端手动传 token
- **状态维护**: 服务端按 session 隔离玩家数据，存储在 `players/state_{player_id}.json`
- **LLM 调用**: 所有涉及叙事的接口调用 OpenAI 兼容 API，代理到外部 LLM 服务

---

## 接口列表

### 1. 获取/保存 LLM 配置

```
GET  /api/config
POST /api/config
```

**GET 响应:**
```json
{
  "api_base": "https://api.openai.com/v1",
  "api_key": "***",
  "model": "gpt-4o-mini",
  "has_key": true
}
```
- `api_key` 已配置时返回 `"***"` 脱敏，未配置时为空字符串

**POST 请求/响应:**
```json
// Request
{ "api_base": "https://...", "api_key": "sk-xxx", "model": "gpt-4o" }

// Response
{ "ok": true, "has_key": true }
```
- 若 `api_key` 值为 `"***"` 则跳过更新（前端脱敏回显）

---

### 2. 开始新游戏

```
POST /api/new_game
```

**请求:**
```json
{
  "name": "林知夏",
  "age": "24",
  "city": "上海",
  "origin": "A",
  "resources": "A",
  "goal": "A",
  "pace": "A",
  "custom_origin": ""
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 角色名 |
| `age` | string | 初始年龄 |
| `city` | string | 所在城市 |
| `origin` | string | 出身: A=设计专业应届生, B=乙方设计公司执行设计师, C=甲方品牌部设计师, D=设计媒体编辑, E=自由职业, F=印刷厂对接人, G=自定义 |
| `resources` | string | 开局资源: A=零资源, B=有引路人, C=有基础人脉, D=背负关系债 |
| `goal` | string | 职业目标: A=顶级独立设计师, B=创意总监, C=创立设计师品牌, D=行业话语权, E=活着就好 |
| `pace` | string | 节奏偏好 |
| `custom_origin` | string | 当 origin=G 时的自定义描述 |

**响应:**
```json
{
  "ok": true,
  "state": { /* 完整游戏状态，见状态结构 */ },
  "new_achievements": []
}
```

---

### 3. 回合行动

```
POST /api/action
```

**请求:**
```json
{
  "choice_id": "A",
  "action": "自由输入文本（可选，有 choice_id 时自动从选项提取）"
}
```

- `choice_id` 必须匹配上回合 `choices` 中的 `id` 字段
- 若玩家精力 ≤0 则触发强制休息，`action` 被覆盖

**响应:**
```json
{
  "ok": true,
  "entry": { /* 本回合叙事条目 */ },
  "attributes": { "审美判断力": 5, "执行能力": 3, ... },
  "stamina": 75,
  "savings": 5000,
  "game_date": "2010年07月",
  "player_age": 24,
  "title": { "title": "初级设计师", "level": 1, ... },
  "npcs": [ /* NPC 列表 */ ],
  "company": {},
  "career_history": [],
  "unlocked_achievements": [],
  "new_achievements": [],
  "milestone": { "name": "...", "target": 10, "progress": 3, "reward": "..." },
  "milestone_done": false,
  "milestone_reward": null,
  "economy_event": null,
  "crisis_event": null,
  "arc_msg": null,
  "project_phase_hint": null,
  "challenge": null,
  "npc_event": null,
  "stamina_status": "正常",
  "status_debuff": null,
  "trait": { "name": "...", "desc": "..." },
  "turn": 5
}
```

---

### 4. 主动行动（不消耗 LLM 选项的回合）

```
POST /api/active_action
```

**请求:**
```json
{
  "action": "rest_short",
  "attr": "审美判断力"
}
```

| action 值 | 说明 | 耗用 |
|-----------|------|------|
| `rest_short` | 周末休整 | 免费，精力+15 |
| `rest_long` | 请假休假 | 储蓄-1000，精力+35 |
| `train` | 报班学习 | 储蓄-3000，指定属性+1 |
| `train_intensive` | 封闭集训 | 储蓄-8000，精力-20，指定属性+2 |
| `portfolio` | 整理作品集 | 精力-5，作品集厚度+1 |
| `jobhunt_targeted` | 精准投递 | 精力-15，投3家公司 |
| `networking` | 社交拓展 | 储蓄-1500，精力-8，触发NPC接触 |

`attr` 仅在 `train` / `train_intensive` 时需要，可选值: `审美判断力` `执行能力` `商业思维` `表达能力` `创意深度`

**响应结构与 `/api/action` 基本相同**，额外包含:
```json
{
  "action": "rest_short",
  "result": "精力 +15",
  "stamina_restored": 15,
  "savings_spent": 0
}
```

---

### 5. NPC 互动

#### 5.1 获取互动选项

```
POST /api/npc/options
```

**请求:**
```json
{ "npc_id": "npc_0" }
```

**响应:**
```json
{
  "ok": true,
  "npc": { "id": "npc_0", "name": "陈知夏", "role": "行业前辈/导师", "relation": "待剧情展开", ... },
  "options": [
    { "id": "ask_advice", "text": "请教职业建议", "effect": "表达+1", "stamina_cost": 5, "available": true },
    { "id": "show_work", "text": "展示作品集", "effect": "审美+1", "stamina_cost": 8, "available": true },
    { "id": "ask_referral", "text": "请求内推机会", "effect": "商业+1", "stamina_cost": 10, "available": true }
  ]
}
```

- `available` 为 `false` 表示精力不足以支付 `stamina_cost`
- 每回合每个 NPC 只能互动一次

NPC 角色类型对应的互动:
| 角色 | 互动选项 |
|------|---------|
| 行业前辈/导师 | 请教职业建议、展示作品集、请求内推机会 |
| 竞争对手 | 观察对方动态、主动竞争、寻求合作可能 |
| 甲方/客户 | 主动提案、收集反馈、维护关系 |
| 合作者/搭档 | 头脑风暴、分工协作、社交闲聊 |
| 行业暗流 | 打听内幕、保持距离、正面交锋 |
| 职场关系 | 日常闲聊、提供帮助、拓展人脉 |

#### 5.2 执行互动

```
POST /api/npc/interact
```

**请求:**
```json
{ "npc_id": "npc_0", "action_id": "ask_advice" }
```

**响应:**
```json
{
  "ok": true,
  "npc_name": "陈知夏",
  "action_text": "请教职业建议",
  "effect": "表达+1",
  "stamina": 75,
  "attributes": { "表达能力": 6, ... },
  "npcs": [ /* 更新后的NPC列表 */ ]
}
```

---

### 6. 获取游戏状态

```
GET /api/state
```

**响应:**
```json
{ "state": { /* 完整游戏状态 */ } }
```

---

### 7. 获取成就列表

```
GET /api/achievements
```

**响应:**
```json
{
  "achievements": [
    {
      "id": "first_job",
      "name": "初入职场",
      "desc": "拿到第一份工作",
      "icon": "...",
      "unlocked": true
    }
  ]
}
```

---

### 8. 项目系统

```
GET /api/project
```

当前没有项目时自动生成一个。

**响应:**
```json
{
  "project": {
    "name": "森屿集团-品牌VI升级",
    "client": "森屿集团",
    "budget": 15000,
    "deadline_turns": 6,
    "quality": 52,
    "client_satisfaction": 45,
    "phase": "执行中",
    "start_turn": 3
  },
  "turns_left": 4
}
```

- `phase`: `执行中` → `交付`（deadline 到期自动切换）
- `turns_left` ≤ 0 表示已到交付期

---

### 9. 作品集生成

```
POST /api/portfolio/generate
```

**请求:** 无参数（从最近 8 回合提取项目经历）

**响应:**
```json
{
  "entries": [
    { "name": "森屿集团品牌升级", "role": "主设计师", "style": "极简商务风", "highlight": "全案独立完成" }
  ],
  "message": ""
}
```

---

### 10. 存档系统

#### 10.1 列出所有槽位

```
GET /api/saves
```

**响应:**
```json
{
  "slots": {
    "1": { "name": "林知夏", "title": "初级设计师", "turn": 12, "city": "上海", "created": "2025-..." },
    "2": { ... }
  }
}
```

共 5 个槽位（1-5），无存档的槽位不出现在响应中。

#### 10.2 保存

```
POST /api/saves/save
{ "slot": 1 }
→ { "ok": true, "slot": 1 }
```

#### 10.3 读取

```
POST /api/saves/load
{ "slot": 1 }
→ { "ok": true, "state": { /* 完整状态 */ } }
```

#### 10.4 删除

```
POST /api/saves/delete
{ "slot": 1 }
→ { "ok": true }
```

---

### 11. 导出/导入存档

#### 11.1 导出

```
GET /api/export
```

返回 JSON 文件下载，Content-Disposition 设为 `attachment`。

#### 11.2 导入

```
POST /api/import
{ "state": { /* 完整游戏状态 */ } }
→ { "ok": true, "state": { ... } }
```

---

### 12. 重置游戏

```
POST /api/reset
→ { "ok": true }
```

删除当前 session 的状态文件。

---

## 核心数据结构

### 游戏状态 (State)

```json
{
  "phase": "playing",
  "player": {
    "name": "林知夏",
    "age": "24",
    "city": "上海",
    "origin": "设计专业应届生",
    "resources": "零资源白手起家",
    "goal": "成为顶级独立设计师",
    "pace": "A"
  },
  "attributes": {
    "审美判断力": 5,
    "执行能力": 3,
    "商业思维": 2,
    "表达能力": 3,
    "创意深度": 5,
    "作品集厚度": 1
  },
  "attribute_xp": {
    "审美判断力": 500,
    "执行能力": 180,
    ...
  },
  "npcs": [
    {
      "id": "npc_0",
      "name": "陈知夏",
      "role": "行业前辈/导师",
      "tag": "资深设计师",
      "relation": "待剧情展开",
      "desc": "陈知夏，行业前辈/导师。",
      "active": true
    }
  ],
  "story_log": [
    {
      "turn": 1,
      "player_action": "开始游戏",
      "narrative": "你用第二人称叙述的剧情文字...",
      "choices": [
        { "id": "A", "text": "选项文字", "hint": "短期后果", "effect": "审美+1 执行-1" },
        { "id": "B", "text": "...", "hint": "...", "effect": "..." }
      ],
      "atmosphere": "场景氛围",
      "attr_display": { "审美判断力": 5, ... },
      "event_tag": "游戏开始"
    }
  ],
  "turn_count": 1,
  "stamina": 80,
  "savings": 3000,
  "title": { "title": "初级设计师", "level": 1 },
  "unlocked_achievements": [],
  "milestone": { "name": "...", "target": 10, "progress": 0, "reward": "..." },
  "trait": { "name": "学院派底子", "desc": "理论知识扎实，但缺乏实战经验..." },
  "company": { "name": "XX设计工作室", "position": "初级设计师" },
  "career_history": [],
  "current_project": { ... },
  "start_date": "2010-01-01T00:00:00",
  "created_at": "2025-01-01T12:00:00"
}
```

### 叙事条目 (StoryLog Entry)

| 字段 | 类型 | 说明 |
|------|------|------|
| `turn` | int | 回合数 |
| `player_action` | string | 玩家执行的行动 |
| `narrative` | string | LLM 生成的叙事文本（150-300字） |
| `choices` | array | 2-3 个后续选项 |
| `atmosphere` | string | 场景氛围描述 |
| `attr_display` | object | 本回合结束时各属性值 |
| `event_tag` | string | 事件标签：`项目推进` `行业事件` `日常` `转折点` `倦怠预警` |

### 选项 (Choice)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | A/B/C，用于 `choice_id` |
| `text` | string | 选项文字 |
| `hint` | string | 短期后果提示 |
| `effect` | string | 属性影响，如 `"审美+1 执行-1"` |

### NPC

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识 `npc_0` ~ `npc_5` |
| `name` | string | 中文名 |
| `role` | string | 6 种角色类型之一 |
| `tag` | string | 角色标签 |
| `relation` | string | 与玩家的关系描述 |
| `desc` | string | 简介 |
| `active` | bool | 是否活跃 |

---

## 错误响应格式

所有接口在出错时返回:
```json
{ "error": "错误描述" }
```

常见 HTTP 状态码:
- `400` — 请求参数错误 / 未配置 API Key
- `404` — 没有存档 / NPC 不存在
- `503` — LLM 调用失败

---

## 回合流程

```
前端                          后端
 |                             |
 |  GET /api/config            |
 | ←-----------------------→  |
 |                             |
 |  POST /api/new_game  ------→ 初始化状态 + LLM 生成开局叙事
 | ←-----------------------   返回完整 state
 |                             |
 |  ┌── 回合循环 ──────────    |
 |  │ POST /api/action  ------→ 处理选择 + LLM 生成叙事 + 系统结算
 |  │ ←-----------------------  返回 entry + 属性变化 + 事件
 |  │                           |
 |  │ (可选) POST /api/npc/options → 获取 NPC 互动选项
 |  │ (可选) POST /api/npc/interact → 执行 NPC 互动
 |  │ (可选) POST /api/active_action → 主动行动跳过一个回合
 |  │ (可选) GET  /api/project  → 查看项目进度
 |  └────────────────────────  |
 |                             |
 |  GET  /api/achievements     → 查看成就
 |  GET  /api/saves            → 查看存档列表
 |  POST /api/saves/save       → 存档
 |  POST /api/saves/load       → 读档
```
