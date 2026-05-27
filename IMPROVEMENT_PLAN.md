# 平面设计师模拟器 · 缺陷改进方案

> 基于 2026-05-27 全面分析，按紧迫度排序的改进方案
> 参考文档：GDD v2.0 | server.py | static/index.html

---

## 一、致命缺陷（先修，否则游戏不可玩）

---

### F1 — 属性结算断层：effect 不生效，LLM 全权控制

**根因：** `server.py` 第 590 行直接把 LLM 输出的 `attr_display` 覆盖到 `state['attributes']`，玩家的 effect 选择从未被实际解析和应用。

**修复方案：**

在 `validate_and_fix_result` 之后、写入 state 之前，新增一个 `apply_choice_effects(state, choice_effect)` 函数：

```python
def apply_choice_effects(state, choice_effect):
    """Parse effect string like '审美+1 执行-2 精力-10' and apply to state."""
    ATTR_MAP = {
        '审美': '审美判断力', '执行': '执行能力', '商业': '商业思维',
        '表达': '表达能力', '创意': '创意深度', '作品': '作品集厚度'
    }
    if not choice_effect:
        return
    parts = choice_effect.strip().split()
    for part in parts:
        for short, full in ATTR_MAP.items():
            if part.startswith(short):
                try:
                    delta = int(part.replace(short, ''))
                    current = state['attributes'].get(full, 5)
                    state['attributes'][full] = max(1, min(10, current + delta))
                except ValueError:
                    pass
                break
        if part.startswith('精力'):
            try:
                state['stamina'] = max(0, min(100, state['stamina'] + int(part.replace('精力', ''))))
            except ValueError:
                pass
        if part.startswith('储蓄'):
            try:
                state['savings'] = max(0, state['savings'] + int(part.replace('储蓄', '')))
            except ValueError:
                pass
```

**调用位置：** 在 `api_action` 中，选择 choice 后：

```python
# 玩家选择后，先应用 effect
chosen = next((c for c in last_entry['choices'] if c['id'] == choice_id), None)
if chosen:
    apply_choice_effects(state, chosen.get('effect', ''))
```

然后 LLM 的 `attr_display` 作为**参考值**而非覆盖值——只在 effect 解析后做微调（±1 范围内）。

**额外约束：** 在调用 LLM 时，从 messages 中去掉 `attr_display` 的"覆盖"语义，改为提示"你在前一回合的基础上给出属性参考值"。

---

### F2 — 前端 state 不完整：NPC / 公司 / 职业历史在行动后不更新

**根因：** `makeChoice()` 的回调中只更新了 `attributes`/`stamina`/`savings`/`title`，没有更新 `npcs`/`company`/`career_history`/`unlocked_achievements`。

**修复方案：** 后端 `/api/action` 接口的返回 JSON 中加入完整的状态快照：

```python
# server.py api_action 返回增加字段
return jsonify({
    'ok': True,
    'entry': entry,
    'attributes': state['attributes'],
    'stamina': state['stamina'],
    'savings': state['savings'],
    'title': state['title'],
    'npcs': state['npcs'],              # ← 新增
    'company': state['company'],        # ← 新增
    'career_history': state.get('career_history', []),  # ← 新增
    'unlocked_achievements': state.get('unlocked_achievements', []),  # ← 新增
    'new_achievements': [a for a in ACHIEVEMENTS if a['id'] in new_ach],
    'turn': turn
})
```

前端 `makeChoice()` 回调对应更新所有字段：

```javascript
if (d.npcs) gameState.npcs = d.npcs;
if (d.company) gameState.company = d.company;
if (d.career_history) gameState.career_history = d.career_history;
if (d.unlocked_achievements) gameState.unlocked_achievements = d.unlocked_achievements;
```

---

### F3 — 前后端成就定义重复

**根因：** `ACHIEVEMENTS` 在 `server.py:296-309` 和 `index.html:1598-1610` 各定义了一份。

**修复方案（单向数据流）：** 删除前端硬编码的成就列表。后端 `/api/state` 和 `/api/action` 已经返回了 `unlocked_achievements`。前端改从 `ACHIEVEMENTS` 的服务端状态来渲染作品集面板，同时后端新增一个 `/api/achievements` 接口返回完整的成就定义列表 + 解锁状态：

```python
@app.route('/api/achievements', methods=['GET'])
def api_achievements():
    state = load_state()
    unlocked = set(state.get('unlocked_achievements', []) if state else [])
    return jsonify({
        'achievements': [
            {**a, 'unlocked': a['id'] in unlocked}
            for a in ACHIEVEMENTS
        ]
    })
```

前端在 `init()` 时调用此接口，此后通过 `/api/action` 返回的 `new_achievements` 增量更新。

---

## 二、严重问题（不修会在 10 回合内暴露）

---

### S1 — 缺少会话级目标 → 5 回合一过失去动力

**方案：引入"阶段目标（Milestone）"系统**

核心思路：在每段职业生涯中，系统自动设定一个**当前阶段目标**（期限 5-8 回合），玩家的选择推动目标进展。

```
阶段目标类型：
├── 项目目标：完成当前项目（竞标→执行→交付→收款）
├── 晋升目标：积累到晋升下一级所需的属性
├── 财务目标：储蓄达到某个阈值
├── 学习目标：将某项属性提升 X 点
├── 社交目标：与某位 NPC 建立某种关系
└── 转折目标：换工作 / 独立接单 / 创业
```

**实现：** 在 state 中加 `milestone` 字段：

```python
'milestone': {
    'type': 'project',           # 目标类型
    'description': '完成"森屿品牌VI设计"项目',  # 一句话描述
    'deadline_turn': 10,          # 目标回合截止
    'progress': 0,                # 0-100 进度
    'reward': '商业+2 储蓄+8000'   # 完成奖励
}
```

每回合结束时 `check_milestone(state)` 评估进度。完成后弹出庆祝 UI + 设定下一个目标。

---

### S2 — 精力值无效：没有系统后果

**方案：引入"状态效果（Status Effect）"**

精力不再是纯叙事提示，而是影响**能选什么、选了什么后果不同**：

```
精力区间  状态效果                  选项限制
──────────────────────────────────────────────
80-100   精力充沛                   无限制
60-79    正常      无限制
40-59    疲劳      「执行-1」选项自动附加 "精力-5" 惩罚
20-39    严重疲劳  最大选项数降为 2（高精力选项被锁定）
10-19    透支      所有选项标红警告，叙事中出现病痛/崩溃
0-9      濒临崩塌  自动触发"强制休息"回合（跳过选择，纯叙事）
```

**实现：** 在 `build_messages` 中，根据当前精力值在 user message 中插入"当前疲劳程度："描述。在 Python 端 `validate_and_fix_result` 中，如果精力 < 20，确保至少有一个选项标注了"休息/恢复"。

> **设计笔记：** 不把精力 < x 设为 Game Over。职业生涯不会因为累就结束——但会让你做不成某些事。

---

### S3 — 储蓄没有消费出口

**方案：引入"消费事件"和"主动消费"**

两件事：

**(A) 固定开销回合：** 每 5 回合自动触发一次"结账日"——房租 + 日常开销，固定扣除储蓄（金额随城市/生活水平不同）。给玩家可预见的财务压力。

**(B) 可选的消费入口：** 在选项面板底部加一个「💰 主动行动」按钮：

```
可选主动行动（消耗 1 回合，不消耗 LLM 调用）：
├── 报培训班：储蓄 -3000，某项属性 +1
├── 买新设备：储蓄 -5000，执行能力 +2
├── 搬工作室：储蓄 -2000/回合（持续性开销），创意环境改善
└── 去旅行：储蓄 -4000，精力 +30，创意灵感 +1
```

这些可以直接由前端 + 后端逻辑处理，不需要 LLM。

---

### S4 — 成就/头衔升级无 UI 反馈

**方案：添加 Toast/Banner 通知**

在前端新增一个 `showNotification(type, message)` 函数：

```javascript
function showNotification(type, message) {
    const banner = document.createElement('div');
    banner.className = `notification notification-${type}`;  // 'achievement' | 'promotion'
    banner.innerHTML = `<span class="notif-icon">${type === 'achievement' ? '🏆' : '⬆'}</span>${message}`;
    document.body.appendChild(banner);
    setTimeout(() => {
        banner.style.animation = 'slideOut 0.4s ease forwards';
        setTimeout(() => banner.remove(), 400);
    }, 3000);
}
```

**调用点：**
- `makeChoice` 回调中 `d.new_achievements.length > 0` → 逐个弹出
- `d.title` 与前一个不同 → 弹出晋升通知
- `check_achievements` 在 `api_new_game` 的初始化回合中也可能触发（精力 ≤ 10），同样需要返回 `new_achievements`

---

## 三、需要改进（影响长期可玩性）

---

### I1 — NPC 被动更新 → 增加 NPC 主动事件

**方案：NPC Turn（每 3-5 回合触发一次）**

在 Python 端，选择时间点（每 3 回合），随机选中 1-2 个关系不为默认的 NPC，用后端逻辑（不调 LLM）生成一条"主动事件"消息：

```python
NPC_ACTIVE_EVENTS = {
    '甲方/客户': [
        '{name} 发来消息：「上次的方案客户很满意，想继续合作二期」',
        '{name} 催稿——甲方下周三要看初稿',
    ],
    '竞争对手': [
        '{name} 的作品在站酷上了首页推荐，你感到一丝压力',
        '业内传闻：{name} 刚拿下了你想争取的客户',
    ],
    '行业前辈/导师': [
        '{name} 邀请你参加下个月的行业私享会',
        '{name} 问起你最近的项目进展，表示可以帮你引荐',
    ],
    # ...
}
```

作为不调用 LLM 的**快速插入回合**，丰富叙事节奏。

---

### I2 — 属性缺乏检定机制 → 引入隐式属性检定

**方案：** 在关键场景（竞标、谈判、提案），后端做一次隐式检定：

```python
def attribute_check(attr_value, difficulty):
    """属性检定，返回成败。10面骰子 + 属性修正 vs 难度"""
    import random
    roll = random.randint(1, 10) + attr_value
    return roll >= difficulty, roll
```

然后在 User Message 中对 LLM 注入检定结果，要求叙事反映之：

```python
if attr_name == '表达能力':
    if success:
        hint = '（DM检定：这次提案成功说服了客户）'
    else:
        hint = '（DM检定：这次提案未能说服客户，产生了分歧）'
```

检定不替代 LLM 叙事，而是给 LLM 一个**叙事方向约束**。

---

### I3 — 职业起点差异化在 5 回合后消失

**方案：基因式 Traits 系统**

每种起点赋予一个**不可变的 trait**：

```python
ORIGIN_TRAITS = {
    '应届生': {
        'name': '学院派',
        'desc': '理论基础扎实，对新风格吸收快',
        'effect': '每3回合，创意属性有概率+1（知识折旧慢）'
    },
    '乙方执行': {
        'name': '执行力基因',
        'desc': '长期乙方训练出的高效执行习惯',
        'effect': '执行能力相关的选择额外+1'
    },
    '甲方品牌': {
        'name': '商业嗅觉',
        'desc': '从品牌方视角理解设计商业价值',
        'effect': '储蓄相关选择额外获得15%收益'
    },
    '自由职业': {
        'name': '独狼基因',
        'desc': '靠自己解决问题，成长快但不稳定',
        'effect': '所有属性提升幅度翻倍，但精力消耗也翻倍'
    },
    # ...
}
```

Trait 在 `apply_choice_effects` 中叠加计算。

---

### I4 — 缺少关键系统（项目/主动行动/存档管理）

这三项对应 GDD 规划的 P0/P1/P2，但当前完全缺失。

**P0 项目系统（最小可行版）：**

```python
# state 中新增
'project': {
    'name': '森屿品牌VI升级',
    'client': '森屿集团',
    'budget': 15000,
    'deadline': 8,          # 还有 8 回合到期
    'quality': 0,           # 0-100，受审美+执行影响
    'client_satisfaction': 50, # 0-100，受表达+商业影响
    'phase': '执行中'        # 竞标 → 执行中 → 交付 → 收款 → 完成
}
```

每回合，基于属性自动计算 `quality` 和 `client_satisfaction` 的变化。项目交付时结算储蓄和声望。

**P1 主动行动（不调用 LLM 的非叙事回合）：**

在选项列表下方增加一排"主动行动"按钮（每个按钮消耗 1 回合），纯前端+后端逻辑：

| 行动 | 消耗 | 效果 |
|------|------|------|
| 📚 报班学习 | 储蓄 -3000 | 自选属性 +1 |
| 💼 投简历 | 精力 -10 | 下回合 LLM 产生"面试"剧情 |
| 🎨 整理作品集 | 精力 -5 | 作品集厚度 +1 |
| 😴 休息回合 | 精力 +25 | 纯恢复，无新剧情 |

**P2 多存档：** 将 `game_state.json` 改为 `saves/` 目录 + 多文件，支持创建/切换/删除存档。

---

### I5 — 杂项缺陷：影响小的实际问题

| # | 问题 | 修复 |
|---|------|------|
| I5a | `portfolio-showcase` 渲染了不存在的属性「行业信用」 | 改为渲染「作品集厚度」或其他 6 项之一 |
| I5b | LLM 输出的 ` ```json ` 前缀没有完整清理 | 在 `call_llm` 中加 `.replace('```json', '').replace('```', '')` |
| I5c | 点击「结束游戏」无确认弹窗 | 加 `confirm('确定要结束当前游戏吗？存档将被删除。')` |
| I5d | 移动端看不到精力和储蓄 | `#mobile-attrs` 中加入精力和储蓄显示 |
| I5e | 无存档导出功能 | 后端 `/api/export` 返回完整 state JSON 下载 |
| I5f | `game_state.json` 非原子写入 | 改为先写 `game_state.json.tmp` 再 `os.replace` 原子替换 |

---

## 四、实施路线图

```
Phase 1 (必须立即修) — 预计 1-2 小时
├── F1: apply_choice_effects 函数
├── F2: 前端 state 完整性
├── F3: 成就定义去重
├── I5a-I5f: 杂项修复

Phase 2 (核心体验闭环) — 预计 3-4 小时
├── S1: 阶段目标（Milestone）系统
├── S2: 精力值 → Status Effect
├── S4: Toast 通知

Phase 3 (深度系统) — 预计 5-6 小时
├── S3: 储蓄消费出口 + 固定开销
├── I1: NPC 主动事件
├── I2: 属性检定

Phase 4 (扩展) — 预计 4-5 小时
├── I3: Traits 系统
├── I4-P0: 项目系统（最小版）
├── I4-P1: 主动行动按钮
├── I4-P2: 多存档
```

---

## 五、设计原则（约束后续开发）

1. **机制先于叙事** — 能确定性计算的就不要依赖 LLM
2. **属性变化必须可追溯** — 任何属性变动都能在日志中看到因果链
3. **精力是真实的代价** — 而不是一个只有文字意义的数字
4. **每个回合都有"意义感"** — 要么推进目标，要么产生戏剧转折，要么恢复资源
5. **不破坏"没有胜负"的基调** — 低谷不是惩罚，是体验；只是不能让玩家觉得"我什么都没做"

---

*本方案随开发推进持续修订。*
