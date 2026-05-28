#!/usr/bin/env python
# -*- coding: utf-8 -*-
'平面设计师职业生涯模拟器 - 游戏服务器 v2'

import json, os, random, traceback, uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, session

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'designer-game-fixed-key-2024')

BASE_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
PLAYERS_DIR = os.path.join(BASE_DIR, 'players')

# ============================================================
# Time / Calendar System — 真实日历 + 季节事件
# ============================================================
def get_game_date(state):
    '''Calculate real calendar date from start_date + turns (1 turn = 1 week).'''
    start = state.get('start_date')
    if not start:
        return datetime.now().strftime('%Y年%m月')
    try:
        start_dt = datetime.fromisoformat(start)
        current = start_dt + timedelta(weeks=state.get('turn_count', 0))
        return current.strftime('%Y年%m月')
    except:
        return datetime.now().strftime('%Y年%m月')

def get_season_and_events(date_str):
    '''Return (season_name, [event_hints]) for a calendar date.'''
    try:
        month = int(date_str.split('年')[1].replace('月', ''))
    except:
        month = datetime.now().month
    if month in [3, 4, 5]:
        return '春季', ['金三银四招聘旺季', '毕业季应届生涌入市场', '春季行业展会密集']
    elif month in [6, 7, 8]:
        return '夏季', ['年中总结和评审', '暑期实习生活跃', '夏季高温易疲劳']
    elif month in [9, 10, 11]:
        return '秋季', ['秋招季人才流动加剧', '各大设计周/设计展举办', '年底项目冲刺']
    else:
        return '冬季', ['年终评审和年终奖', '春节前项目收尾催稿', '年会和行业聚会密集']

SEASON_EVENT_HINTS = {
    (3,4,5): {'tag': '行业事件', 'hint': '春季招聘市场活跃，猎头和HR频繁联系'},
    (6,7,8): {'tag': '转折点', 'hint': '年中评审——是争取升职加薪的关键窗口'},
    (9,10,11): {'tag': '项目推进', 'hint': '设计周密集举办，年底项目冲刺'},
    (12,1,2): {'tag': '转折点', 'hint': '年终总结和绩效考核，春节前后节奏放缓'},
}

def get_season_llm_hint(month):
    for months, info in SEASON_EVENT_HINTS.items():
        if month in months:
            return info
    return {'tag': '日常', 'hint': ''}

# ============================================================
# Session-based State Management — 多玩家隔离
# ============================================================
def ensure_players_dir():
    if not os.path.exists(PLAYERS_DIR):
        os.makedirs(PLAYERS_DIR)

def get_session_id():
    '''Generate or retrieve persistent session ID.'''
    if 'player_id' not in session:
        session['player_id'] = uuid.uuid4().hex[:12]
        session.permanent = True
    return session['player_id']

def get_state_file():
    pid = get_session_id()
    ensure_players_dir()
    return os.path.join(PLAYERS_DIR, f'state_{pid}.json')

def load_state():
    path = get_state_file()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_state(state):
    path = get_state_file()
    ensure_players_dir()
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# ============================================================
# Config (shared — one server, one API key)
# ============================================================
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'api_base': 'https://api.openai.com/v1', 'api_key': '', 'model': 'gpt-4o-mini'}

def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ============================================================
# System Prompt
# ============================================================
SYSTEM_PROMPT = '''# 你是平面设计师模拟器的 Game Master (DM)

## 你的身份
你是本游戏的 DM，负责剧情推进、NPC 扮演、事件生成、职业属性结算。

## 核心基调
- 写实向职业生涯模拟，非爽文，非恋爱向。但**不能全程只有苦——生活有苦有甜，职业生涯也如此。**
- 女主不是天才，成长必须有代价、犹豫、自我怀疑。但同样会有突破时刻、被认可的温暖、以及"选对了"的欣慰。
- 没有天降贵人。但通过努力赢得的信任和尊重，应该在叙事中有清晰的正面反馈。
- 叙事信息有限性：只描述第一视角所见所闻，不透露 NPC 隐藏意图。
- 没有恋爱线。NPC 限于：同事、导师、竞争对手、甲方、合作者、行业前辈。

## 基调平衡（IMPORTANT）
每 3-4 回合至少有一个「正面时刻」——可以是：
- 客户的一句真心认可，让你觉得加班值得
- 同事主动帮忙，团队感温暖
- 作品被同行点赞，在社交媒体上有了小传播
- 拿到一笔意料之外的奖金
- 完成一个项目后走在街上，感觉自己在成长
- 一位前辈说了句让你受益匪浅的话

不要让女主一直处于"苦熬"状态。挫折之后要有回弹，低谷之后要有光亮。职业生涯是马拉松，不是持续的泥潭。

## 核心属性（1-10分）
审美判断力 — 视觉品味、风格把控、设计决策
执行能力   — 落地速度、改稿效率、抗压韧性
商业思维   — 定价谈判、理解客户需求、市场嗅觉
表达能力   — 提案说服、建立人脉、行业声誉
创意深度   — 概念思考、原创性、独立判断
作品集厚度 — 综合产出指标，积累优质作品

## 时间尺度（CRITICAL）
每个回合代表**约1周**的真实时间。叙事体现周度节奏——项目执行4-8周，面试1-3周。选项使用周度语言（"这周""下周"）。当前日历日期和季节会注入上下文：
- **春季（3-5月）**: 招聘旺季、毕业季、行业展会季——面试、跳槽、参展类事件增多
- **夏季（6-8月）**: 年中评审、实习季、高温疲劳——评审/晋升/倦怠事件概率↑
- **秋季（9-11月）**: 秋招季、设计周密集、年底冲刺——项目推进/行业曝光事件↑  
- **冬季（12-2月）**: 年终绩效、春节、年会——财务结算/人脉/休息事件↑

## 资源系统
精力值：0-100，每次行动消耗 5-15（加班消耗大，休息可恢复）
储蓄：每月自动发工资（行业标准根据头衔）+ 自动扣除约2500元基础生活开销。项目奖金/额外收入由LLM通过savings_change补充。
当精力<20 时女主表现出疲劳、效率下降、易出错
当储蓄不足以支撑生活时产生焦虑叙事

## 选项后果系统（CRITICAL）
每个选项必须标注「短期后果」和「属性影响」，让玩家知道选择在改变什么：

短期后果：本回合的直接结果（≤12字），如「甲方同意了方案」「熬夜赶工到凌晨」
属性影响：格式 "属性名±数字"，如 "审美+1 执行-2"
## 职业成长节奏（CRITICAL — 必须严格遵循）
- 属性增长必须缓慢写实：大部分回合变化为 0 或 ±1
- 从 5 升到 6 需要持续投入，从 8 升到 9 需要重大突破
- 作品集厚度增长尤为缓慢：每回合涨幅不超过 +1，且只有真正产出作品时才提升
- 每回合属性总变化幅度控制在 -2 ~ +2 之间（精力消耗不计入）
- 正负必须平衡：纯正面的回合极少，好的选择往往附带代价
- 过高属性（≥8）会自然遇到瓶颈期，很难继续上升

## 输出格式（严格JSON，只输出JSON，不要任何额外文字）
{
  "narrative": "用第二人称「你」叙述本回合剧情，150-300字，生动具体",
  "choices": [
    {"id": "A", "text": "选项A（≤20字）", "hint": "短期后果（≤12字）", "effect": "审美+1 执行-1"},
    {"id": "B", "text": "选项B（≤20字）", "hint": "短期后果（≤12字）", "effect": "商业+1"},
    {"id": "C", "text": "选项C（≤20字）", "hint": "短期后果（≤12字）", "effect": "表达+1 精力+15"}
  ],
  "atmosphere": "场景氛围（≤10字）",
  "attr_display": {"审美判断力": 7, "执行能力": 6, "商业思维": 5, "表达能力": 6, "创意深度": 4, "作品集厚度": 3},
  "stamina_change": -8,
  "savings_change": 0,
  "event_tag": "项目推进 / 行业事件 / 日常 / 转折点 / 倦怠预警",
  "npc_updates": [
    {"name": "陈知夏", "relation": "新的关系描述", "desc": "新的简介"}
  ],
  "company_update": {"name": "XX设计工作室", "position": "初级设计师", "action": "入职"}
}

## stamina_change / savings_change 规则
- stamina_change: 本轮精力的变化量（正=休息恢复，负=消耗），范围 -15 ~ +20
- savings_change: 储蓄的增减（正=收入进账/项目酬劳，负=消费/交租/降薪），单位：元
- 加班、改稿、提案通常消耗精力；休息、度假、完成项目获得恢复
- 完成项目、升职带来储蓄增长；被裁、日常开销带来储蓄减少

## choice.effect 规则
- effect 格式："属性简称±数字 属性简称±数字"，空格分隔
- 属性简称映射：审美=审美判断力 执行=执行能力 商业=商业思维 表达=表达能力 创意=创意深度 作品=作品集厚度 精力=精力值 储蓄=储蓄
- 必须至少包含一个属性变化
- 示例: "审美+1" / "执行-1 精力-10" / "商业+1 表达+1 精力-5"
- 涨属性的选项必须伴随代价（精力消耗、储蓄消耗、或其他属性下降）

## company_update 规则
- 游戏开场时必须初始化公司信息（action: "入职"）
- 之后仅在职业生涯发生重大变动时更新：跳槽、被辞退、升职、创业
- 无变化时 action 设为 "无变化" 或省略整个字段

## npc_updates 规则
- npc_updates 是可选的，如果没有 NPC 参与本回合剧情可以为空数组 []
- 仅在剧情中确实出现了该 NPC 时才更新其 relation 和/或 desc

CRITICAL: choices 数组必须始终包含 2-3 个有意义的选项。这是一个没有终点的职业生涯体验，属性低不代表游戏结束。'''

# ============================================================
# NPC Generation
# ============================================================
NPC_TYPES = [
    {'role': '行业前辈/导师', 'tags': ['资深设计师', '前老板', '教授', '评审']},
    {'role': '竞争对手', 'tags': ['同级别设计师', '风格鲜明', '有野心']},
    {'role': '甲方/客户', 'tags': ['品牌总监', '产品经理', '创始人']},
    {'role': '合作者/搭档', 'tags': ['文案', '插画师', '摄影师', '前端开发']},
    {'role': '行业暗流', 'tags': ['争议人物', '灰色地带', '利益链推手']},
    {'role': '职场关系', 'tags': ['直属上级', 'HR', '合伙人']},
]

NPC_NAMES = ['陈知夏', '林墨', '苏晚晴', '方屿', '周念', '何秋池', '沈予安', '姜莱', '秦舒', '温予白', '季南星', '陆屿', '白鹿', '顾念之', '柳青禾', '徐柚']

def generate_npcs():
    npcs = []
    used_names = set()
    for i, tpl in enumerate(NPC_TYPES):
        name = random.choice([n for n in NPC_NAMES if n not in used_names])
        used_names.add(name)
        npcs.append({
            'id': f'npc_{i}',
            'name': name,
            'role': tpl['role'],
            'tag': random.choice(tpl['tags']),
            'relation': '待剧情展开',
            'desc': f'{name}，{tpl["role"]}。',
            'active': True
        })
    return npcs

# ============================================================
# LLM Call
# ============================================================
def call_llm(messages, api_base, api_key, model):
    try:
        import requests
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
        payload = {
            'model': model,
            'messages': messages,
            'temperature': 0.85,
            'max_tokens': 1500,
            'response_format': {'type': 'json_object'}
        }
        resp = requests.post(f'{api_base}/chat/completions', headers=headers, json=payload, timeout=120)
        if resp.status_code != 200:
            return None, f'API错误 {resp.status_code}: {resp.text[:200]}'
        data = resp.json()
        content = data['choices'][0]['message']['content'].strip()
        # Clean markdown code blocks
        content = content.replace('```json', '').replace('```', '')
        return json.loads(content), None
    except json.JSONDecodeError as e:
        return None, f'JSON解析失败: {str(e)[:100]}'
    except Exception as e:
        return None, f'调用失败: {str(e)[:100]}'

# ============================================================
# Fallback choice generators
# ============================================================
def make_fallback_choices(turn_count, attrs):
    '''Always return valid choices, never empty.'''
    base = [
        {'id': 'A', 'text': '继续当前的工作节奏', 'hint': '稳扎稳打', 'effect': '执行+1'},
        {'id': 'B', 'text': '主动寻求新机会', 'hint': '冒险可能突破', 'effect': '商业+1 精力-8'},
        {'id': 'C', 'text': '停下来复盘和思考', 'hint': '恢复和规划', 'effect': '精力+15'},
    ]
    if turn_count % 7 == 0:
        return [
            {'id': 'A', 'text': '抓住这个转折机会', 'hint': '职业跃升', 'effect': '表达+1 精力-8'},
            {'id': 'B', 'text': '谨慎观望再做决定', 'hint': '保守安全', 'effect': '执行+2'},
            {'id': 'C', 'text': '和信任的人商量一下', 'hint': '借助他人视角', 'effect': '表达+1'},
        ]
    return base

def validate_and_fix_result(result, turn_count, attrs):
    '''Ensure the LLM result is always valid.'''
    if not isinstance(result, dict):
        result = {}
    if not result.get('narrative'):
        result['narrative'] = '日子在设计和改稿中悄然流逝。你的工作台堆满了色票和草图，窗外天色已暗。你揉了揉酸涩的眼睛，看着屏幕上的作品——还差一点，但方向是对的。下一步该怎么走？'
    if not result.get('choices') or len(result['choices']) == 0:
        result['choices'] = make_fallback_choices(turn_count, attrs)
    # Ensure each choice has required fields
    for i, ch in enumerate(result['choices']):
        if not isinstance(ch, dict):
            result['choices'][i] = {'id': chr(65+i), 'text': f'继续推进', 'hint': '下一步', 'effect': ''}
        if 'id' not in ch:
            ch['id'] = chr(65+i)
        if 'text' not in ch:
            ch['text'] = '继续推进'
        if 'hint' not in ch:
            ch['hint'] = ''
        if 'effect' not in ch:
            ch['effect'] = ''
    # Ensure 2-3 choices
    if len(result['choices']) < 2:
        result['choices'] = make_fallback_choices(turn_count, attrs)
    if len(result['choices']) > 3:
        result['choices'] = result['choices'][:3]
    if not result.get('atmosphere'):
        result['atmosphere'] = '设计工作室的日常'
    if not result.get('event_tag'):
        result['event_tag'] = '日常'
    if not result.get('attr_display'):
        result['attr_display'] = attrs
    # Ensure all 6 attributes are present
    for key in ['审美判断力', '执行能力', '商业思维', '表达能力', '创意深度', '作品集厚度']:
        if key not in result['attr_display']:
            result['attr_display'][key] = attrs.get(key, 5)
        result['attr_display'][key] = max(1, min(10, int(result['attr_display'][key])))
    # Stamina & savings
    if 'stamina_change' not in result:
        result['stamina_change'] = -5
    if 'savings_change' not in result:
        result['savings_change'] = 0
    # Ensure each choice has effect field
    for ch in result.get('choices', []):
        if 'effect' not in ch:
            ch['effect'] = ''
    return result

def apply_npc_updates(npcs, npc_updates):
    '''Apply LLM-generated NPC relationship updates to the NPC list.'''
    if not npc_updates or not isinstance(npc_updates, list):
        return npcs
    name_map = {n['name']: n for n in npcs}
    for update in npc_updates:
        if not isinstance(update, dict):
            continue
        name = update.get('name', '')
        if name in name_map:
            if 'relation' in update and update['relation']:
                name_map[name]['relation'] = update['relation']
            if 'desc' in update and update['desc']:
                name_map[name]['desc'] = update['desc']
    return npcs

def apply_choice_effects(state, choice_effect):
    '''Parse effect string like '审美+1 执行-2 精力-10' and apply to state.'''
    ATTR_MAP = {
        '审美': '审美判断力', '执行': '执行能力', '商业': '商业思维',
        '表达': '表达能力', '创意': '创意深度', '作品': '作品集厚度'
    }
    if not choice_effect or not isinstance(choice_effect, str):
        return {}
    applied = {}
    parts = choice_effect.strip().split()
    for part in parts:
        # Handle attribute changes
        for short, full in ATTR_MAP.items():
            if part.startswith(short):
                try:
                    delta_str = part.replace(short, '').replace(' ', '')
                    delta = int(delta_str)
                    current = state['attributes'].get(full, 5)
                    state['attributes'][full] = max(1, min(10, current + delta))
                    applied[full] = delta
                except (ValueError, KeyError):
                    pass
                break
        # Handle stamina change
        if part.startswith('精力'):
            try:
                delta = int(part.replace('精力', ''))
                state['stamina'] = max(0, min(100, state.get('stamina', 80) + delta))
                applied['__stamina__'] = delta
            except ValueError:
                pass
        # Handle savings change
        if part.startswith('储蓄'):
            try:
                delta = int(part.replace('储蓄', ''))
                state['savings'] = max(0, state.get('savings', 3000) + delta)
                applied['__savings__'] = delta
            except ValueError:
                pass
    return applied

def apply_company_update(state, company_update):
    '''Apply company/job changes from LLM output.'''
    if not company_update or not isinstance(company_update, dict):
        return
    action = company_update.get('action', '无变化')
    if action == '无变化' or not action:
        return

    current = state.get('company', {})
    new_company = {
        'name': company_update.get('name', current.get('name', '未知')),
        'position': company_update.get('position', current.get('position', '设计师')),
        'action': action,
        'turn': state.get('turn_count', 0)
    }

    # Record history
    history = state.get('career_history', [])
    if current and current.get('name'):
        history.append({**current, 'left_at_turn': state.get('turn_count', 0)})
    state['career_history'] = history
    state['company'] = new_company

# ============================================================
# Career Title / Stage System
# ============================================================
# (moved up for milestone reference)
TITLE_THRESHOLDS = [
    {'title': '见习设计师',     'stage': '萌芽期', 'attrs': {}},
    {'title': '初级设计师',     'stage': '成长期', 'attrs': {'审美判断力': 3, '执行能力': 3}},
    {'title': '中级设计师',     'stage': '成长期', 'attrs': {'审美判断力': 5, '执行能力': 5, '作品集厚度': 3}},
    {'title': '高级设计师',     'stage': '成熟期', 'attrs': {'审美判断力': 7, '执行能力': 6, '作品集厚度': 5, '表达能力': 5}},
    {'title': '资深设计师',     'stage': '成熟期', 'attrs': {'审美判断力': 7, '执行能力': 7, '作品集厚度': 7, '表达能力': 6, '商业思维': 5}},
    {'title': '设计总监',       'stage': '巅峰期', 'attrs': {'审美判断力': 8, '执行能力': 7, '作品集厚度': 8, '表达能力': 7, '商业思维': 7, '创意深度': 7}},
    {'title': '创意合伙人',     'stage': '巅峰期', 'attrs': {'审美判断力': 9, '执行能力': 8, '作品集厚度': 9, '表达能力': 8, '商业思维': 8, '创意深度': 8}},
    {'title': '独立设计大师',   'stage': '传奇',   'attrs': {'审美判断力': 9, '作品集厚度': 10, '表达能力': 9, '创意深度': 9}},
]

ACHIEVEMENTS = [
    {'id': 'first_project',  'name': '初出茅庐', 'desc': '完成第一个设计项目', 'icon': '🌱'},
    {'id': 'portfolio_5',    'name': '作品等身', 'desc': '作品集厚度达到 5',  'icon': '📦'},
    {'id': 'portfolio_8',    'name': '业界标杆', 'desc': '作品集厚度达到 8',  'icon': '🏆'},
    {'id': 'expression_7',   'name': '金字招牌', 'desc': '表达能力达到 7',    'icon': '🤝'},
    {'id': 'expression_9',   'name': '德高望重', 'desc': '表达能力达到 9',    'icon': '👑'},
    {'id': 'aesthetic_8',    'name': '审美大师', 'desc': '审美判断力达到 8',  'icon': '🎨'},
    {'id': 'stamina_low',    'name': '至暗时刻', 'desc': '精力值降到 10 以下','icon': '🌑'},
    {'id': 'stamina_recover','name': '涅槃重生', 'desc': '精力从低谷恢复到 70+','icon': '🔥'},
    {'id': 'npc_3_related',  'name': '社交达人', 'desc': '与 3 位 NPC 建立关系', 'icon': '💬'},
    {'id': 'turn_20',        'name': '十年磨一剑', 'desc': '职业生涯超过 20 回合', 'icon': '⏳'},
    {'id': 'turn_50',        'name': '老设计师',   'desc': '职业生涯超过 50 回合', 'icon': '📜'},
    {'id': 'all_rounder',    'name': '六边形战士', 'desc': '所有属性达到 6 以上', 'icon': '⭐'},
]

# ============================================================
# S1: Milestone System — 阶段目标
# ============================================================
MILESTONE_TEMPLATES = [
    {
        'type': 'project',
        'desc_tpl': '完成"{project}"项目',
        'deadline_turns': 6,
        'reward': '商业+2 储蓄+5000',
        'check': lambda s: s.get('current_project') and s['current_project'].get('phase') == '完成'
    },
    {
        'type': 'promotion',
        'desc_tpl': '晋升至{next_title}',
        'deadline_turns': 8,
        'reward': '表达+2 储蓄+3000',
        'check': lambda s: s.get('title', {}).get('title', '') == s.get('_milestone_target_title', ''),
    },
    {
        'type': 'financial',
        'desc_tpl': '储蓄达到{savings_target}元',
        'deadline_turns': 7,
        'reward': '商业+1 储蓄+2000',
        'check': lambda s: s.get('savings', 0) >= s.get('_milestone_target_savings', 0),
    },
    {
        'type': 'networking',
        'desc_tpl': '与一位NPC建立深度合作关系',
        'deadline_turns': 6,
        'reward': '表达+2',
        'check': lambda s: any('合作' in n.get('relation', '') or '信任' in n.get('relation', '') for n in s.get('npcs', [])),
    },
    {
        'type': 'learning',
        'desc_tpl': '将{attr_name}提升至{attr_target}',
        'deadline_turns': 5,
        'reward': '创意+1 精力+20',
        'check': lambda s: s.get('attributes', {}).get(s.get('_milestone_attr', ''), 0) >= s.get('_milestone_attr_target', 0),
    },
]

def generate_milestone(state):
    '''Generate a new milestone for the player.'''
    import random as _random
    title = state.get('title', {}).get('title', '见习设计师')
    current_idx = next((i for i, t in enumerate(TITLE_THRESHOLDS) if t['title'] == title), 0)
    next_title = TITLE_THRESHOLDS[min(current_idx + 1, len(TITLE_THRESHOLDS) - 1)]['title'] if current_idx < len(TITLE_THRESHOLDS) - 1 else None

    if next_title and current_idx < 3:
        tpl = MILESTONE_TEMPLATES[1]  # promotion
        target = next_title
        state['_milestone_target_title'] = target
        return {
            'type': 'promotion', 'description': f'晋升至{target}',
            'deadline_turn': state['turn_count'] + 8, 'progress': 0,
            'reward': tpl['reward'], 'completed': False
        }
    else:
        # Pick a random non-promotion milestone
        tpl = _random.choice([t for t in MILESTONE_TEMPLATES if t['type'] != 'promotion'])
        desc = tpl['desc_tpl']
        if tpl['type'] == 'financial':
            target_savings = state.get('savings', 3000) + _random.choice([5000, 8000, 12000])
            desc = desc.replace('{savings_target}', str(target_savings))
            state['_milestone_target_savings'] = target_savings
            state['_milestone_start_savings'] = state.get('savings', 3000)
        elif tpl['type'] == 'learning':
            attr = _random.choice(['审美判断力', '执行能力', '商业思维', '表达能力', '创意深度'])
            target = min(10, state.get('attributes', {}).get(attr, 5) + _random.choice([2, 3]))
            desc = desc.replace('{attr_name}', attr).replace('{attr_target}', str(target))
            state['_milestone_attr'] = attr
            state['_milestone_attr_target'] = target
            state['_milestone_attr_start'] = state.get('attributes', {}).get(attr, 5)
        else:
            project_name = _random.choice(['品牌VI升级', '产品发布会设计', '年度画册', '空间导视系统', 'APP界面改版'])
            desc = desc.replace('{project}', project_name)
        deadline = state['turn_count'] + tpl['deadline_turns']
        return {
            'type': tpl['type'], 'description': desc,
            'deadline_turn': deadline, 'progress': 0,
            'reward': tpl['reward'], 'completed': False
        }

def check_milestone(state):
    '''Check milestone progress (state-driven) and completion. Returns (newly_completed, reward_str).'''
    ms = state.get('milestone')
    if not ms or ms.get('completed'):
        return False, ''
    turn = state['turn_count']

    # Calculate TRUE progress based on target state, not just time
    ms_type = ms.get('type')
    attrs = state.get('attributes', {})

    if ms_type == 'promotion':
        target_title = state.get('_milestone_target_title', '')
        # Progress = how many attributes meet the title threshold
        target_threshold = next((t for t in TITLE_THRESHOLDS if t['title'] == target_title), None)
        if target_threshold:
            reqs = target_threshold['attrs']
            total_reqs = len(reqs)
            met_reqs = sum(1 for k, v in reqs.items() if attrs.get(k, 0) >= v)
            ms['progress'] = min(99, int(met_reqs / max(1, total_reqs) * 100)) if total_reqs > 0 else 50
        else:
            ms['progress'] = 50

    elif ms_type == 'financial':
        target = state.get('_milestone_target_savings', 8000)
        current = state.get('savings', 0)
        start = state.get('_milestone_start_savings', max(1, current))
        ms['progress'] = min(99, int((current - start) / max(1, target - start) * 100))

    elif ms_type == 'learning':
        attr = state.get('_milestone_attr', '')
        target = state.get('_milestone_attr_target', 8)
        current = attrs.get(attr, 5)
        start = state.get('_milestone_attr_start', max(1, current))
        ms['progress'] = min(99, int((current - start) / max(1, target - start) * 100))

    elif ms_type == 'networking':
        npcs = state.get('npcs', [])
        related = [n for n in npcs if n.get('relation', '待剧情展开') != '待剧情展开']
        target_count = 3  # "与NPC建立深度关系"
        ms['progress'] = min(99, int(len(related) / target_count * 100))

    elif ms_type == 'project':
        proj = state.get('current_project')
        if proj:
            ms['progress'] = min(99, max(proj.get('quality', 0), proj.get('client_satisfaction', 0)))
        else:
            ms['progress'] = 0

    # Check completion
    for tpl in MILESTONE_TEMPLATES:
        if tpl['type'] == ms_type and tpl.get('check'):
            if tpl['check'](state):
                ms['completed'] = True
                reward = ms.get('reward', '')
                apply_choice_effects(state, reward)
                return True, reward

    # Check if expired
    if turn >= ms['deadline_turn']:
        ms['completed'] = True
        return True, ''
    return False, ''

# ============================================================
# S2: Status Effect System — 精力状态效果
# ============================================================
def get_stamina_status(stamina):
    '''Return status effect based on current stamina.'''
    if stamina >= 80:  return '精力充沛', None
    if stamina >= 60:  return '正常', None
    if stamina >= 40:  return '疲劳', 'penalty_small'
    if stamina >= 20:  return '严重疲劳', 'choices_reduced'
    if stamina >= 10:  return '透支', 'warning'
    return '濒临崩塌', 'forced_rest'

def get_status_debuff(stamina):
    '''Return additional stamina penalty for exertion choices.'''
    if stamina < 40: return 5
    if stamina < 60: return 2
    return 0

# ============================================================
# 2. Savings Crisis System — 储蓄危机事件链
# ============================================================
def check_savings_crisis(state):
    '''Check savings level and return crisis event if applicable.'''
    savings = state.get('savings', 0)
    crisis = state.get('_savings_crisis_level', 0)
    turn = state.get('turn_count', 0)

    events = []
    if savings <= 0 and crisis < 1:
        state['_savings_crisis_level'] = 1
        events.append({
            'level': 1, 'type': 'survival',
            'message': '储蓄见底！下个月房租都成问题了。',
            'attr_penalty': {'精力值': -10}
        })
    elif savings <= -3000 and crisis < 2:
        state['_savings_crisis_level'] = 2
        events.append({
            'level': 2, 'type': 'debt',
            'message': '你已经欠了两个月的房租。房东发来了最后通牒。',
            'attr_penalty': {'审美判断力': -1, '精力值': -15}
        })
    elif savings <= -8000 and crisis < 3:
        state['_savings_crisis_level'] = 3
        events.append({
            'level': 3, 'type': 'bankruptcy',
            'message': '财务状况彻底崩溃。你需要做出艰难的决定。',
            'attr_penalty': {'精力值': -20}
        })

    # Recovery: leaving crisis
    if savings > 2000 and crisis > 0:
        state['_savings_crisis_level'] = 0
        events.append({
            'level': 0, 'type': 'recovery',
            'message': '财务状况终于开始好转，你松了一口气。',
            'attr_penalty': {}
        })

    return events[-1] if events else None

# ============================================================
# 3. Project Decision System — 项目四阶段决策
# ============================================================
PROJECT_PHASES = ['竞标', '执行', '改稿', '交付']

def advance_project_phase(state):
    '''Auto-advance project phase and generate decision prompt.'''
    proj = state.get('current_project')
    if not proj or proj.get('phase') == '完成':
        return None
    turn = state.get('turn_count', 0)
    start = proj.get('start_turn', turn)
    elapsed = turn - start
    deadline = proj.get('deadline_turns', 6)
    progress = min(1.0, elapsed / deadline)

    phase_hints = {
        '竞标': '这个项目刚出现在你的视野里。需要决定要不要接：预算多少？甲方靠谱吗？精力够不够？',
        '执行': '项目正在推进中。是保守执行还是冒险突破？要不要加班赶进度？',
        '改稿': '甲方提出了修改意见。是大改还是沟通协商？每一次改稿都在消耗精力和时间。',
        '交付': '项目接近尾声。提前交稿还是打磨到极致？客户满意度 vs 你的完美主义。',
    }

    # Auto-advance based on progress
    phases_progressed = False
    if progress >= 0.1 and proj.get('phase') == '竞标':
        proj['phase'] = '执行'; phases_progressed = True
    if progress >= 0.5 and proj.get('phase') == '执行':
        proj['phase'] = '改稿'; phases_progressed = True
    if progress >= 0.7 and proj.get('phase') == '改稿':
        proj['phase'] = '交付'; phases_progressed = True
    if progress >= 1.0 and proj.get('phase') in ('交付', '改稿'):
        proj['phase'] = '完成'; phases_progressed = True
        # Completion reward
        state['savings'] = state.get('savings', 0) + proj.get('budget', 5000)
        state['attributes']['作品集厚度'] = min(10, state.get('attributes', {}).get('作品集厚度', 1) + 1)
        state['attributes']['商业思维'] = min(10, state.get('attributes', {}).get('商业思维', 3) + 1)

    return phase_hints.get(proj.get('phase', ''), '') if phases_progressed else None

# ============================================================
# 4. Narrative Arc System — 跨回合叙事弧
# ============================================================
NARRATIVE_ARCS = [
    {
        'id': 'job_hunt', 'name': '求职之旅',
        'turns': 3, 'phases': ['听说机会','准备面试','结果抉择'],
        'trigger': lambda s: '投简历' in str(s.get('story_log', [{}])[-1:]) or '找工作' in str(s.get('story_log', [{}])[-1:]),
    },
    {
        'id': 'big_project', 'name': '大项目攻防',
        'turns': 4, 'phases': ['竞标','执行','改稿','交付'],
        'trigger': lambda s: s.get('current_project') and '竞标' in s.get('current_project',{}).get('phase',''),
    },
    {
        'id': 'burnout_recovery', 'name': '倦怠与重生',
        'turns': 3, 'phases': ['身心俱疲','重新思考','找到节奏'],
        'trigger': lambda s: s.get('stamina', 80) < 15,
    },
    {
        'id': 'industry_event', 'name': '行业盛会',
        'turns': 2, 'phases': ['收到邀请','参会抉择'],
        'trigger': lambda s: '行业事件' in str(s.get('story_log', [{}])[-1].get('event_tag','')),
    },
]

def detect_and_start_arc(state):
    '''Check if a narrative arc should begin.'''
    current_arc = state.get('_narrative_arc')
    if current_arc:
        phase_idx = current_arc.get('phase_idx', 0)
        phases = current_arc.get('phases', [])
        if phase_idx < len(phases) - 1:
            current_arc['phase_idx'] = phase_idx + 1
            current_arc['turn_in_arc'] = (current_arc.get('turn_in_arc', 0) + 1)
            return f'叙事弧「{current_arc["name"]}」第{phase_idx+2}阶段：{phases[phase_idx+1]}'
        else:
            state['_narrative_arc'] = None
            return f'叙事弧「{current_arc["name"]}」完结'

    for arc in NARRATIVE_ARCS:
        if arc['trigger'](state):
            import random as _random
            if _random.random() < 0.4:  # 40% chance to start
                state['_narrative_arc'] = {
                    'id': arc['id'], 'name': arc['name'],
                    'phases': arc['phases'], 'phase_idx': 0, 'turn_in_arc': 1
                }
                return f'叙事弧开始：「{arc["name"]}」第1阶段：{arc["phases"][0]}'
    return None

# ============================================================
# 5. Enhanced Active Actions — 主动行动策略化
# ============================================================
ENHANCED_ACTIONS = {
    'rest_short': {'name': '周末休整', 'cost': {}, 'effect': '精力+15', 'icon': '☕', 'desc': '休息两天，恢复精力'},
    'rest_long': {'name': '请假休假', 'cost': {'savings': -1000}, 'effect': '精力+35', 'icon': '🏖️', 'desc': '请假一周，深度恢复，但可能错过项目节点'},
    'train': {'name': '报班学习', 'cost': {'savings': -3000}, 'effect': '自选属性+1（持续3回合缓升）', 'icon': '📚'},
    'train_intensive': {'name': '封闭集训', 'cost': {'savings': -8000, 'stamina': -20}, 'effect': '自选属性+2（一次性）', 'icon': '🎓'},
    'jobhunt_targeted': {'name': '精准投递', 'cost': {'stamina': -15}, 'effect': '投3家公司，不同回复概率', 'icon': '🎯'},
    'portfolio': {'name': '整理作品集', 'cost': {'stamina': -5}, 'effect': '作品集+1', 'icon': '🎨'},
    'networking': {'name': '社交拓展', 'cost': {'savings': -1500, 'stamina': -8}, 'effect': '随机触发NPC接触事件', 'icon': '🤝'},
}

# ============================================================
# 6. Career Stage Challenges — 职业阶段挑战
# ============================================================
CAREER_CHALLENGES = [
    {'turn': 12, 'name': '第一次倦怠', 'message': '入行快两年了。日复一日的改稿让你开始怀疑：这就是我想要的设计师生涯吗？',
     'effect': {'精力值': -20}},
    {'turn': 24, 'name': 'AI冲击', 'message': 'AI设计工具开始席卷行业。客户开始问"你们能用AI做吗？"一些低端单子被替代了。',
     'effect': {}},
    {'turn': 36, 'name': '后浪来袭', 'message': '隔壁组新来的95后设计师，作品直接上了站酷首页。你感受到了代际压力。',
     'effect': {}},
    {'turn': 48, 'name': '天花板', 'message': '你在这个位置上已经很久了。往上走需要的不只是能力——还需要机会、运气、和站队。',
     'effect': {}},
    {'turn': 60, 'name': '中年转型', 'message': '十年设计师生涯。是继续深耕，还是转型管理？或者——创业？',
     'effect': {}},
]

def check_career_challenge(state):
    '''Check if current turn triggers a career challenge.'''
    turn = state.get('turn_count', 0)
    triggered = state.get('_challenges_triggered', [])
    for ch in CAREER_CHALLENGES:
        if turn >= ch['turn'] and ch['turn'] not in triggered:
            triggered.append(ch['turn'])
            state['_challenges_triggered'] = triggered
            # Apply effects
            for attr, delta in ch.get('effect', {}).items():
                if attr == '精力值':
                    state['stamina'] = max(0, state.get('stamina', 80) + delta)
                elif attr in state.get('attributes', {}):
                    state['attributes'][attr] = max(1, min(10, state['attributes'][attr] + delta))
            return ch
    return None

# ============================================================
# 7. Trait-Driven Option Filtering — Traits影响选项池
# ============================================================
TRAIT_PREFERRED_OPTIONS = {
    '学院派':   '你偏爱创新探索型的选择方案',
    '执行力基因': '你偏好高效直接的选择方案',
    '商业嗅觉':  '你自然倾向于考虑商业回报的选择',
    '信息敏感':  '你更容易注意到行业信息和人脉机会',
    '独狼基因':  '你偏向独立解决问题的方案，而非求助他人',
    '工艺基因':  '你对材料和落地方案有天然的偏好',
}

def get_trait_context(state):
    '''Return LLM context string based on player trait.'''
    trait = state.get('trait', {})
    trait_name = trait.get('name', '')
    if trait_name and trait_name in TRAIT_PREFERRED_OPTIONS:
        return TRAIT_PREFERRED_OPTIONS[trait_name]
    return ''

# ============================================================
# Economy — 月薪月开销（1回合=1周，约4回合结算1次月薪）
# ============================================================
MONTHLY_BASE_EXPENSE = 2500  # 基础月开销
SALARY_BY_TITLE = {
    '见习设计师': 3500, '初级设计师': 5000, '中级设计师': 8000,
    '高级设计师': 12000, '资深设计师': 18000,
    '设计总监': 25000, '创意合伙人': 35000, '独立设计大师': 50000,
}
ECONOMY_INTERVAL = 4  # 每4回合（约1个月）结算一次

def process_economy(state):
    '''Process salary + expenses every N turns. Returns event dict or None.'''
    turn = state['turn_count']
    if turn <= 0 or turn % ECONOMY_INTERVAL != 0:
        return None
    city_scale = {'上海': 1.0, '北京': 0.95, '深圳': 0.9, '杭州': 0.85, '成都': 0.7, '广州': 0.8}
    city = state.get('player', {}).get('city', '上海')
    multiplier = city_scale.get(city, 1.0)

    # Expense
    expense = int(MONTHLY_BASE_EXPENSE * multiplier)
    state['savings'] = max(0, state.get('savings', 0) - expense)

    # Salary
    title = state.get('title', {}).get('title', '见习设计师')
    salary = SALARY_BY_TITLE.get(title, 4000)
    # Adjust for company position (junior vs senior modifier)
    company = state.get('company', {})
    pos = company.get('position', '')
    if '实习' in pos or '见习' in pos:
        salary = int(salary * 0.6)
    elif '初级' in pos:
        salary = int(salary * 0.8)
    elif '高级' in pos:
        salary = int(salary * 1.2)
    elif '总监' in pos or '资深' in pos:
        salary = int(salary * 1.4)

    # Freelancers don't get fixed salary
    origin = state.get('player', {}).get('origin', '')
    if '自由' in origin:
        salary = 0  # freelancers live project-to-project

    # No salary if unemployed (no company set)
    if not company.get('name'):
        salary = 0

    state['savings'] += salary

    return { 'type': 'monthly', 'expense': expense, 'salary': salary, 'city': city, 'net': salary - expense }

# ============================================================
# I1: NPC Active Events — NPC主动事件
# ============================================================
NPC_ACTIVE_EVENTS = {
    '甲方/客户': [
        '{name} 发来消息：「上次的方案客户很满意，想继续聊二期合作」',
        '{name} 项目经理催进度——甲方下周五要看定稿',
        '{name} 的公司即将品牌升级，问了你的排期',
    ],
    '竞争对手': [
        '{name} 的作品在站酷首页推荐了，你感到一阵微妙的压力',
        '业内传闻：{name} 刚拿下了你也在争取的那个客户',
    ],
    '行业前辈/导师': [
        '{name} 邀请你参加下周的设计师私享会',
        '{name} 问起你最近的项目，表示可以帮忙引荐',
    ],
    '合作者/搭档': [
        '{name} 有个有趣的项目想法，想找你一起聊聊',
    ],
    '职场关系': [
        '{name} 在茶水间和你聊起公司的近况',
    ],
}

def generate_npc_event(state):
    '''Generate a random NPC active event every 3-4 turns. Returns event dict or None.'''
    turn = state.get('turn_count', 0)
    if turn < 3 or turn % 3 != 0:
        return None
    import random as _random
    npcs = state.get('npcs', [])
    active_npcs = [n for n in npcs if n.get('relation', '待剧情展开') != '待剧情展开' and n.get('active', True)]
    if not active_npcs:
        return None
    npc = _random.choice(active_npcs)
    role = npc.get('role', '')
    events = NPC_ACTIVE_EVENTS.get(role, ['{name} 发来了一条消息'])
    text = _random.choice(events).replace('{name}', npc['name'])
    return {'npc_name': npc['name'], 'text': text, 'turn': turn}

# ============================================================
# I2: Attribute Check — 属性检定
# ============================================================
def attribute_check(attr_value, difficulty):
    '''D10 + attr vs difficulty. Returns (success, roll_result).'''
    import random as _random
    roll = _random.randint(1, 10)
    total = roll + attr_value
    return total >= difficulty, roll, total

# ============================================================
# Attribute Check Trigger — 在关键叙事节点自动检定
# ============================================================
CHECK_TRIGGERS = {
    '竞标':    {'attr': '商业思维', 'difficulty': 12, 'success': '你的报价和方案打动了客户', 'fail': '你的方案未能突出商业价值，客户犹豫了'},
    '提案':    {'attr': '表达能力', 'difficulty': 11, 'success': '提案陈述流畅有力，客户频频点头', 'fail': '提案有些磕绊，客户的眉头皱了几次'},
    '面试':    {'attr': '表达能力', 'difficulty': 10, 'success': '面试官对你的作品集和谈吐印象深刻', 'fail': '面试表现平平，竞争太激烈了'},
    '改稿':    {'attr': '执行能力', 'difficulty': 9,  'success': '你高效完成了甲方的修改要求', 'fail': '改稿进度比预期慢，甲方开始不耐烦'},
    '创新':    {'attr': '创意深度', 'difficulty': 11, 'success': '你的创意概念让人眼前一亮', 'fail': '方案中规中矩，缺少令人惊喜的亮点'},
    '社交':    {'attr': '表达能力', 'difficulty': 10, 'success': '社交场合你谈吐得体，留下了好印象', 'fail': '你有些局促，没能在人群中脱颖而出'},
    '承受压力':{'attr': '执行能力', 'difficulty': 12, 'success': '你在高压下稳住了节奏', 'fail': '压力太大，进度和质量都受到了影响'},
    '审美决策':{'attr': '审美判断力', 'difficulty': 10, 'success': '你的审美判断精准，方案方向对了', 'fail': '设计方向有些偏差，可能需要调整'},
}

def run_attribute_checks(state, current_narrative, story_log):
    '''Run relevant attribute checks based on narrative keywords. Returns list of check results.'''
    import random as _random
    results = []
    turn = state.get('turn_count', 0)

    # Determine which checks to run
    narrative_lower = (current_narrative or '').lower()
    active_triggers = []
    for key, cfg in CHECK_TRIGGERS.items():
        if key in narrative_lower or key in (story_log[-2].get('event_tag','') if len(story_log) > 1 else ''):
            active_triggers.append((key, cfg))

    # Pick 1-2 most relevant checks (not all)
    if len(active_triggers) > 2:
        active_triggers = _random.sample(active_triggers, 2)

    for key, cfg in active_triggers:
        attr_name = cfg['attr']
        attr_value = state.get('attributes', {}).get(attr_name, 5)
        success, roll, total = attribute_check(attr_value, cfg['difficulty'])
        results.append({
            'trigger': key,
            'attr': attr_name,
            'value': attr_value,
            'roll': roll,
            'total': total,
            'difficulty': cfg['difficulty'],
            'success': success,
            'message': cfg['success'] if success else cfg['fail'],
        })

    return results

# ============================================================
# I3: Traits System — 基因式Traits
# ============================================================
ORIGIN_TRAITS = {
    '应届生':   {'name': '学院派',   'desc': '理论基础扎实，对新风格吸收快', 'attr_bonus': lambda attrs: {'创意深度': 1} if attrs.get('创意深度', 5) > 5 else {}},
    '乙方执行': {'name': '执行力基因', 'desc': '长期乙方训练出的高效执行习惯', 'effect_mod': lambda e: e + 1 if '执行' in e else e},
    '甲方品牌': {'name': '商业嗅觉',   'desc': '从品牌方视角理解设计的商业价值', 'savings_mod': 0.15},
    '媒体编辑': {'name': '信息敏感',   'desc': '对行业动态和人脉变化更敏锐', 'event_bonus': True},
    '自由职业': {'name': '独狼基因',   'desc': '靠自己成长，快但不稳定', 'stamina_penalty': 3},
    '印刷厂':   {'name': '工艺基因',   'desc': '对材料和落地有直觉理解', 'attr_bonus': lambda attrs: {'作品集厚度': 1}},
    '自定义':   {'name': '无标签',     'desc': '你的道路由自己定义', 'attr_bonus': lambda attrs: {}},
}

def calculate_title(attrs):
    '''Determine current career title based on highest threshold met.'''
    current = TITLE_THRESHOLDS[0]
    for t in TITLE_THRESHOLDS:
        meets = all(attrs.get(k, 0) >= v for k, v in t['attrs'].items())
        if meets:
            current = t
    return current

def check_achievements(state, prev_stamina=None):
    '''Check and unlock new achievements. Returns list of newly unlocked.'''
    attrs = state.get('attributes', {})
    npcs = state.get('npcs', [])
    turn = state.get('turn_count', 0)
    stamina = state.get('stamina', 80)
    unlocked = set(state.get('unlocked_achievements', []))
    new_unlocks = []

    def unlock(ach_id):
        if ach_id not in unlocked:
            unlocked.add(ach_id)
            new_unlocks.append(ach_id)

    # Attribute-based
    if attrs.get('作品集厚度', 0) >= 5: unlock('portfolio_5')
    if attrs.get('作品集厚度', 0) >= 8: unlock('portfolio_8')
    if attrs.get('表达能力', 0) >= 7: unlock('expression_7')
    if attrs.get('表达能力', 0) >= 9: unlock('expression_9')
    if attrs.get('审美判断力', 0) >= 8: unlock('aesthetic_8')

    # Stamina
    if stamina <= 10: unlock('stamina_low')
    if prev_stamina is not None and prev_stamina <= 10 and stamina >= 70:
        unlock('stamina_recover')

    # NPC relationships
    related_count = sum(1 for n in npcs if n.get('relation', '待剧情展开') != '待剧情展开')
    if related_count >= 3: unlock('npc_3_related')

    # Turn milestones
    if turn >= 20: unlock('turn_20')
    if turn >= 50: unlock('turn_50')

    # All-rounder
    all_attrs = ['审美判断力', '执行能力', '商业思维', '表达能力', '创意深度', '作品集厚度']
    if all(attrs.get(k, 0) >= 6 for k in all_attrs): unlock('all_rounder')

    # First project — check if any log entry has event_tag '项目推进'
    if any(e.get('event_tag') == '项目推进' for e in state.get('story_log', [])):
        unlock('first_project')

    return new_unlocks, unlocked
def build_messages(state, player_action=None):
    player = state.get('player', {})
    attrs = state.get('attributes', {})
    npcs = state.get('npcs', [])
    story_len = len(state.get('story_log', []))

    parts = [
        '# 游戏状态',
        f'女主: {player.get("name","?")}, {player.get("age","?")}岁, {player.get("city","上海")}',
        f'职业: {player.get("origin","?")} → 目标: {player.get("goal","?")}',
        f'当前头衔: {state.get("title",{}).get("title","见习设计师")}（{state.get("title",{}).get("stage","萌芽期")}）',
        f'资源: {player.get("resources","?")}, 节奏: {player.get("pace","标准")}',
        f'当前回合: 第{story_len+1}回合',
        '',
        f'# 当前公司: {state.get("company",{}).get("name","待定")} | 职位: {state.get("company",{}).get("position","设计师")}',
        '',
        '# 资源',
        f'  精力值: {state.get("stamina",80)}/100',
        f'  储蓄: {state.get("savings",3000)}元',
        '',
        '# 属性',
    ]
    for k, v in attrs.items():
        bar = '\u2587' * v + '\u2581' * (10 - v)
        parts.append(f'  {k}: {bar} ({v}/10)')

    parts.append('')

    # Time dimension — real calendar
    game_date = get_game_date(state)
    season, events = get_season_and_events(game_date)
    try:
        month_num = int(game_date.split('年')[1].replace('月', ''))
    except:
        month_num = datetime.now().month
    season_hint = get_season_llm_hint(month_num)
    parts.append(f'# 时间: {game_date}（{season}）')
    parts.append(f'# 季节事件倾向: {season_hint["tag"]} — {season_hint["hint"]}')
    parts.append(f'  当前季节特征: {", ".join(events[:2])}')

    parts.append('# NPC（含当前关系）')
    for n in npcs[:6]:
        parts.append(f'  {n["name"]} - {n["role"]} | 关系: {n.get("relation","待展开")} | {n.get("desc","")}')

    if state.get('current_project'):
        cp = state['current_project']
        parts.append(f'\n# 当前项目: {cp.get("name","无")} ({cp.get("phase","进行中")})')
        if cp.get('budget'):
            parts.append(f'  预算: {cp["budget"]}元 | 质量: {cp.get("quality",0)}/100 | 客户满意度: {cp.get("client_satisfaction",50)}/100')

    # S1: Milestone
    ms = state.get('milestone')
    if ms:
        parts.append(f'\n# 当前阶段目标: {ms.get("description","")}（第{ms.get("deadline_turn",0)}回合截止，进度{ms.get("progress",0)}%）')

    # S2: Stamina status
    status, _ = get_stamina_status(state.get('stamina', 80))
    parts.append(f'\n# 精力状态: {status}（{state.get("stamina",80)}/100）')

    # I3: Trait
    trait = state.get('trait', {})
    if trait:
        parts.append(f'\n# 职业特质: {trait.get("name","")} — {trait.get("desc","")}')
    trait_ctx = get_trait_context(state)
    if trait_ctx:
        parts.append(f'# 特质倾向: {trait_ctx}')

    # 4: Narrative arc
    arc = state.get('_narrative_arc')
    if arc:
        phases = arc.get('phases', [])
        idx = arc.get('phase_idx', 0)
        phase_name = phases[idx] if idx < len(phases) else '完结'
        parts.append(f'\n# 当前叙事弧: 「{arc.get("name","")}」第{idx+1}阶段：{phase_name}')

    # Savings crisis
    if state.get('_savings_crisis_level', 0) > 0:
        parts.append(f'\n# ⚠️ 财务危机等级: {state.get("_savings_crisis_level")}/3')

    parts.append('\n# 最近回合')
    for e in state.get('story_log', [])[-5:]:
        parts.append(f'  [{e.get("event_tag","")}] 玩家: {e.get("player_action","")}')
        if e.get('narrative'):
            parts.append(f'  → {e["narrative"][:120]}...')

    parts.append('\n---')
    msg = '\n'.join(parts)

    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': msg},
    ]

    if player_action:
        if is_forced_rest:
            messages.append({'role': 'user', 'content': f'玩家精力耗尽，被迫去医院/躺了几天。花费了 {hospital_fee} 元。请叙述这次健康危机的场景（150-200字），并给出 2-3 个恢复后的新选择。必须包含 choices 数组。只输出JSON。'})
        else:
            messages.append({'role': 'user', 'content': f'玩家刚才的行动: {player_action}\n\n请叙述这个选择带来的后果，并给出接下来的 2-3 个新选择。记住：每个回合代表约1周的时间。必须包含 choices 数组。只输出JSON。'})
    else:
        # Opening — customized based on origin
        origin = state.get('player', {}).get('origin', '')
        city = state.get('player', {}).get('city', '上海')
        opening_prompt = '请生成游戏开场剧情。'
        if '应届' in origin:
            opening_prompt += f'女主刚从设计专业毕业，正在{city}找工作/面试阶段，还没有正式入职。'
        elif '自由' in origin:
            opening_prompt += f'女主是自由职业设计师，正在{city}寻找第一个客户或接第一个私单。'
        elif '印刷' in origin:
            opening_prompt += f'女主在{city}一家印刷厂/材料商工作，但想转型做真正的设计。'
        elif '媒体' in origin:
            opening_prompt += f'女主在{city}做设计媒体编辑，日常写文章评设计而非亲手做设计，开始感到局限。'
        elif '乙方' in origin:
            opening_prompt += f'女主在{city}一家乙方设计公司担任执行设计师，每天面对客户的改稿要求。'
        elif '甲方' in origin:
            opening_prompt += f'女主在{city}一家公司的品牌部做内部设计师，做着千篇一律的企业物料。'
        else:
            opening_prompt += f'女主刚踏入{city}设计行业。'
        opening_prompt += '每个回合代表约1周。只输出JSON。'
        messages.append({'role': 'user', 'content': opening_prompt})

    return messages

# ============================================================
# API Routes
# ============================================================
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'GET':
        cfg = load_config()
        return jsonify({
            'api_base': cfg.get('api_base', ''),
            'api_key': '***' if cfg.get('api_key') else '',
            'model': cfg.get('model', 'gpt-4o-mini'),
            'has_key': bool(cfg.get('api_key'))
        })
    data = request.get_json(silent=True) or {}
    cfg = load_config()
    for key in ['api_base', 'model']:
        if data.get(key):
            cfg[key] = data[key]
    if data.get('api_key') and data['api_key'] != '***':
        cfg['api_key'] = data['api_key']
    save_config(cfg)
    return jsonify({'ok': True, 'has_key': bool(cfg.get('api_key'))})

@app.route('/api/new_game', methods=['POST'])
def api_new_game():
    data = request.get_json(silent=True) or {}
    cfg = load_config()
    if not cfg.get('api_key'):
        return jsonify({'error': '请先配置 API Key'}), 400

    origin_map = {
        'A': '设计专业应届生', 'B': '乙方设计公司执行设计师',
        'C': '甲方品牌部设计师', 'D': '设计媒体编辑/自媒体运营',
        'E': '自由职业/兼职设计师', 'F': '印刷厂/材料商对接人',
        'G': data.get('custom_origin', '自定义身份')
    }
    res_map = {'A': '零资源白手起家', 'B': '有行业引路人', 'C': '有基础人脉网络', 'D': '背负关系债'}
    goal_map = {
        'A': '成为顶级独立设计师', 'B': '做到创意总监/合伙人',
        'C': '创立自己的设计品牌/厂牌', 'D': '成为行业话语权拥有者',
        'E': '活着就好'
    }

    player = {
        'name': data.get('name', '林知夏'),
        'age': data.get('age', '24'),
        'city': data.get('city', '上海'),
        'origin': origin_map.get(data.get('origin', 'A'), '设计专业应届生'),
        'resources': res_map.get(data.get('resources', 'A'), '零资源白手起家'),
        'goal': goal_map.get(data.get('goal', 'A'), '成为顶级独立设计师'),
        'pace': data.get('pace', 'A')
    }

    attr_base = {
        '应届生': {'审美判断力': 5, '执行能力': 3, '商业思维': 2, '表达能力': 3, '创意深度': 5, '作品集厚度': 1},
        '乙方执行': {'审美判断力': 4, '执行能力': 5, '商业思维': 3, '表达能力': 4, '创意深度': 3, '作品集厚度': 3},
        '甲方品牌': {'审美判断力': 4, '执行能力': 4, '商业思维': 5, '表达能力': 5, '创意深度': 3, '作品集厚度': 2},
        '媒体编辑': {'审美判断力': 5, '执行能力': 3, '商业思维': 3, '表达能力': 6, '创意深度': 4, '作品集厚度': 1},
        '自由职业': {'审美判断力': 4, '执行能力': 4, '商业思维': 3, '表达能力': 4, '创意深度': 5, '作品集厚度': 2},
        '印刷厂':   {'审美判断力': 3, '执行能力': 5, '商业思维': 2, '表达能力': 3, '创意深度': 2, '作品集厚度': 0},
        '自定义':   {'审美判断力': 4, '执行能力': 4, '商业思维': 4, '表达能力': 4, '创意深度': 4, '作品集厚度': 0},
    }

    origin_key = '应届生' if '应届' in player['origin'] else \
                 '乙方执行' if '乙方' in player['origin'] else \
                 '甲方品牌' if '甲方' in player['origin'] else \
                 '媒体编辑' if '媒体' in player['origin'] else \
                 '自由职业' if '自由' in player['origin'] else \
                 '印刷厂' if '印刷' in player['origin'] else '自定义'

    attributes = attr_base.get(origin_key, attr_base['自定义']).copy()
    if '引路人' in player['resources']:
        attributes['表达能力'] = min(10, attributes['表达能力'] + 2)
    if '人脉' in player['resources']:
        attributes['表达能力'] = min(10, attributes['表达能力'] + 1)
        attributes['作品集厚度'] = min(10, attributes['作品集厚度'] + 1)

    npcs = generate_npcs()

    # Preset NPC relations based on resource choice
    if '引路人' in player['resources']:
        # Find mentor-type NPC and preset relation
        mentors = [n for n in npcs if n['role'] == '行业前辈/导师']
        target = mentors[0] if mentors else npcs[0]
        target['relation'] = '你的导师，曾带过你第一个项目'
        target['desc'] = f'{target["name"]}，行业前辈，在你入行时给予了关键指导。'
        if len(npcs) > 1:
            npcs[1]['relation'] = '通过导师认识的行业联系人'
    elif '人脉' in player['resources']:
        # 1-2 NPCs start with pre-established relations
        preset = random.sample(npcs, min(2, len(npcs)))
        relations = ['前同事，关系不错', '大学同学，偶尔联系', '合作过一次的甲方']
        for i, n in enumerate(preset):
            n['relation'] = random.choice(relations) if n['role'] != '甲方/客户' else '之前服务过的客户，比较认可你的作品'
            n['desc'] = f'{n["name"]}，{n["role"]}，通过行业网络认识。'
    elif '关系债' in player['resources']:
        # One NPC has complicated history
        target = npcs[0] if npcs else None
        if target:
            target['relation'] = '欠过人情，关系微妙'
            target['desc'] = f'{target["name"]}，曾帮过你一个大忙，但你还没还上。'

    state = {
        'phase': 'playing',
        'player': player,
        'attributes': attributes,
        'npcs': npcs,
        'story_log': [],
        'current_project': None,
        'turn_count': 0,
        'stamina': 80,
        'savings': 3000,
        'start_date': datetime.now().isoformat(),
        'created_at': datetime.now().isoformat(),
    }
    # I3: Assign trait based on origin
    trait = ORIGIN_TRAITS.get(origin_key, ORIGIN_TRAITS['自定义'])
    state['trait'] = {'name': trait['name'], 'desc': trait['desc']}
    # S1: Initialize first milestone
    state['milestone'] = None

    messages = build_messages(state)
    result, error = call_llm(messages, cfg['api_base'], cfg['api_key'], cfg['model'])
    if error:
        result = validate_and_fix_result({}, 0, attributes)
    else:
        result = validate_and_fix_result(result, 0, attributes)
    if result.get('npc_updates'):
        state['npcs'] = apply_npc_updates(state['npcs'], result['npc_updates'])
    if result.get('company_update'):
        apply_company_update(state, result['company_update'])

    state['story_log'].append({
        'turn': 1,
        'player_action': '开始游戏',
        'narrative': result['narrative'],
        'choices': result['choices'],
        'atmosphere': result.get('atmosphere', ''),
        'attr_display': result['attr_display'],
        'event_tag': result.get('event_tag', '游戏开始'),
    })
    state['attributes'] = result['attr_display']
    state['turn_count'] = 1
    state['title'] = calculate_title(state['attributes'])
    state['unlocked_achievements'] = []
    # S1: Generate first milestone
    state['milestone'] = generate_milestone(state)
    new_ach, unlocked = check_achievements(state)
    state['unlocked_achievements'] = list(unlocked)
    save_state(state)
    return jsonify({
        'ok': True,
        'state': state,
        'new_achievements': [a for a in ACHIEVEMENTS if a['id'] in new_ach]
    })

@app.route('/api/action', methods=['POST'])
def api_action():
    data = request.get_json(silent=True) or {}
    state = load_state()
    if not state:
        return jsonify({'error': '没有存档，请先开始新游戏'}), 400

    cfg = load_config()
    if not cfg.get('api_key'):
        return jsonify({'error': '请先配置 API Key'}), 400

    choice_id = data.get('choice_id', '')
    action_text = data.get('action', '')

    # Apply the chosen effect BEFORE calling LLM
    # Reset NPC interaction tracking for new turn
    state['_npc_interacted'] = {}
    chosen_effect = ''
    if choice_id and not action_text:
        last_entry = state['story_log'][-1] if state['story_log'] else None
        if last_entry and last_entry.get('choices'):
            for ch in last_entry['choices']:
                if ch['id'] == choice_id:
                    action_text = ch['text']
                    chosen_effect = ch.get('effect', '')
                    break
    if not action_text:
        action_text = '玩家做出了选择'

    # F1: Apply choice effects deterministically
    # I3: Apply trait modifier to effect
    trait = state.get('trait', {})
    origin_key = '应届生' if '应届' in state.get('player', {}).get('origin', '') else \
                 '乙方执行' if '乙方' in state.get('player', {}).get('origin', '') else \
                 '甲方品牌' if '甲方' in state.get('player', {}).get('origin', '') else \
                 '自由职业' if '自由' in state.get('player', {}).get('origin', '') else \
                 '印刷厂' if '印刷' in state.get('player', {}).get('origin', '') else '自定义'
    trait_def = ORIGIN_TRAITS.get(origin_key, ORIGIN_TRAITS['自定义'])
    # Trait stamina penalty for freelancer
    if trait_def.get('stamina_penalty'):
        state['stamina'] = max(0, state['stamina'] - trait_def.get('stamina_penalty', 0))
    applied_effects = apply_choice_effects(state, chosen_effect)

    # F-EXTRA: Forced rest when stamina depleted
    is_forced_rest = False
    if state.get('stamina', 80) <= 0:
        state['stamina'] = min(100, state['stamina'] + 30)
        hospital_fee = min(state.get('savings', 0), random.randint(1000, 3000))
        state['savings'] = max(0, state.get('savings', 3000) - hospital_fee)
        action_text = f'精力耗尽，强制休息，就医花费 {hospital_fee} 元'
        is_forced_rest = True

    messages = build_messages(state, action_text)

    # Run attribute checks and inject results
    last_narrative = state['story_log'][-1].get('narrative', '') if state['story_log'] else ''
    check_results = run_attribute_checks(state, last_narrative, state.get('story_log', []))
    if check_results:
        check_text = '\n\n[D M 属性检定结果 - 必须融入叙事]\n'
        for cr in check_results:
            check_text += f'  {cr["trigger"]}检定: {cr["attr"]}({cr["value"]}) + D10({cr["roll"]}) = {cr["total"]} vs 难度{cr["difficulty"]} → {"✅成功" if cr["success"] else "❌失败"}\n'
            check_text += f'  叙事方向: {cr["message"]}\n'
        messages.append({'role': 'user', 'content': check_text})

    result, error = call_llm(messages, cfg['api_base'], cfg['api_key'], cfg['model'])

    if error:
        result = validate_and_fix_result({}, state['turn_count'], state['attributes'])

    result = validate_and_fix_result(result, state['turn_count'], state['attributes'])
    if result.get('npc_updates'):
        state['npcs'] = apply_npc_updates(state['npcs'], result['npc_updates'])
    if result.get('company_update'):
        apply_company_update(state, result['company_update'])

    turn = state['turn_count'] + 1
    entry = {
        'turn': turn,
        'player_action': action_text,
        'narrative': result['narrative'],
        'choices': result['choices'],
        'atmosphere': result.get('atmosphere', ''),
        'attr_display': result['attr_display'],
        'event_tag': result.get('event_tag', '日常'),
    }
    state['story_log'].append(entry)
    # F1: Blend LLM attr_display as reference with deterministic effects
    llm_attrs = result.get('attr_display', state['attributes'].copy())
    for key in ['审美判断力', '执行能力', '商业思维', '表达能力', '创意深度', '作品集厚度']:
        llm_val = int(llm_attrs.get(key, state['attributes'].get(key, 5)))
        deterministic = state['attributes'].get(key, 5)
        # Blend: if LLM disagrees by >1, trust deterministic; if ±1, average
        if abs(llm_val - deterministic) <= 1:
            state['attributes'][key] = llm_val
        else:
            # LLM drifted too far, bring it back toward deterministic
            state['attributes'][key] = max(1, min(10, int((deterministic + llm_val) / 2)))
    state['stamina'] = max(0, min(100, state.get('stamina', 80) + result.get('stamina_change', -5)))
    state['savings'] = max(0, state.get('savings', 3000) + result.get('savings_change', 0))
    state['turn_count'] = turn

    # Title & achievements
    prev_stamina = state.get('_prev_stamina', state.get('stamina', 80))
    state['title'] = calculate_title(state['attributes'])
    new_ach, unlocked = check_achievements(state, prev_stamina)
    state['unlocked_achievements'] = list(unlocked)
    state['_prev_stamina'] = state['stamina']

    # 4: Narrative arc detection
    arc_msg = detect_and_start_arc(state)

    # 6: Career stage challenges
    challenge = check_career_challenge(state)

    # S3: Process weekly economy
    economy_event = process_economy(state)

    # 2: Savings crisis
    crisis_event = check_savings_crisis(state)

    # 3: Project phase advancement
    project_phase_hint = advance_project_phase(state)

    # S1: Check milestone
    milestone_done, milestone_reward = check_milestone(state)
    if milestone_done:
        new_ach, unlocked = check_achievements(state, prev_stamina)
        state['unlocked_achievements'] = list(unlocked)

    # I1: NPC active event
    npc_event = generate_npc_event(state)

    save_state(state)
    # S2: Get stamina status for response
    stamina_status, status_debuff = get_stamina_status(state['stamina'])

    return jsonify({
        'ok': True,
        'entry': entry,
        'attributes': state['attributes'],
        'stamina': state['stamina'],
        'savings': state['savings'],
        'title': state['title'],
        'npcs': state['npcs'],
        'company': state.get('company', {}),
        'career_history': state.get('career_history', []),
        'unlocked_achievements': list(unlocked),
        'new_achievements': [a for a in ACHIEVEMENTS if a['id'] in new_ach],
        'milestone': state.get('milestone'),
        'milestone_done': milestone_done,
        'milestone_reward': milestone_reward,
        'economy_event': economy_event,
        'crisis_event': crisis_event,
        'arc_msg': arc_msg,
        'project_phase_hint': project_phase_hint,
        'challenge': challenge,
        'npc_event': npc_event,
        'stamina_status': stamina_status,
        'status_debuff': status_debuff,
        'trait': state.get('trait'),
        'turn': turn
    })

@app.route('/api/state', methods=['GET'])
def api_state():
    state = load_state()
    return jsonify({'state': state})

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

@app.route('/api/export', methods=['GET'])
def api_export():
    state = load_state()
    if not state:
        return jsonify({'error': '没有存档'}), 404
    from flask import Response
    return Response(
        json.dumps(state, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=designer_save.json'}
    )

@app.route('/api/import', methods=['POST'])
def api_import():
    data = request.get_json()
    if not data or 'state' not in data:
        return jsonify({'error': '无效的存档数据'}), 400
    state = data['state']
    if not isinstance(state, dict):
        return jsonify({'error': '存档格式错误'}), 400
    save_state(state)
    return jsonify({'ok': True, 'state': state})

@app.route('/api/reset', methods=['POST'])
def api_reset():
    path = get_state_file()
    if os.path.exists(path):
        os.remove(path)
    if os.path.exists(path + '.tmp'):
        os.remove(path + '.tmp')
    return jsonify({'ok': True})

# ============================================================
# NPC Interaction System
# ============================================================
NPC_INTERACTIONS = {
    '行业前辈/导师': [
        {'id': 'ask_advice', 'text': '请教职业建议', 'effect': '表达+1', 'stamina_cost': 5},
        {'id': 'show_work', 'text': '展示作品集', 'effect': '审美+1', 'stamina_cost': 8},
        {'id': 'ask_referral', 'text': '请求内推机会', 'effect': '商业+1', 'stamina_cost': 10},
    ],
    '竞争对手': [
        {'id': 'observe', 'text': '观察对方动态', 'effect': '商业+1', 'stamina_cost': 3},
        {'id': 'compete', 'text': '主动竞争', 'effect': '执行+1 审美-1', 'stamina_cost': 12},
        {'id': 'collaborate', 'text': '寻求合作可能', 'effect': '表达+1', 'stamina_cost': 8},
    ],
    '甲方/客户': [
        {'id': 'pitch', 'text': '主动提案', 'effect': '商业+1', 'stamina_cost': 10},
        {'id': 'feedback', 'text': '收集反馈', 'effect': '审美+1', 'stamina_cost': 5},
        {'id': 'maintain', 'text': '维护关系', 'effect': '表达+1', 'stamina_cost': 6},
    ],
    '合作者/搭档': [
        {'id': 'brainstorm', 'text': '头脑风暴', 'effect': '创意+1', 'stamina_cost': 8},
        {'id': 'divide_work', 'text': '分工协作', 'effect': '执行+1', 'stamina_cost': 6},
        {'id': 'social', 'text': '社交闲聊', 'effect': '精力+10', 'stamina_cost': -10},
    ],
    '行业暗流': [
        {'id': 'gossip', 'text': '打听内幕', 'effect': '商业+1', 'stamina_cost': 5},
        {'id': 'caution', 'text': '保持距离', 'effect': '无变化', 'stamina_cost': 0},
        {'id': 'confront', 'text': '正面交锋', 'effect': '执行+1 表达-1', 'stamina_cost': 12},
    ],
    '职场关系': [
        {'id': 'chat', 'text': '日常闲聊', 'effect': '精力+5', 'stamina_cost': -5},
        {'id': 'help', 'text': '提供帮助', 'effect': '表达+1', 'stamina_cost': 8},
        {'id': 'network', 'text': '拓展人脉', 'effect': '商业+1', 'stamina_cost': 10},
    ],
}

@app.route('/api/npc/interact', methods=['POST'])
def api_npc_interact():
    state = load_state()
    if not state:
        return jsonify({'error': '没有存档'}), 404

    data = request.get_json()
    npc_id = data.get('npc_id')
    action_id = data.get('action_id')
    npcs = state.get('npcs', [])
    npc = next((n for n in npcs if n.get('id') == npc_id), None)
    if not npc:
        return jsonify({'error': 'NPC 不存在'}), 404

    # One interaction per NPC per turn
    interacted = state.get('_npc_interacted', {})
    if interacted.get(npc_id):
        return jsonify({'error': f'本回合已经和{npc["name"]}互动过了'}), 400

    role = npc.get('role', '职场关系')
    interactions = NPC_INTERACTIONS.get(role, NPC_INTERACTIONS['职场关系'])
    action = next((a for a in interactions if a['id'] == action_id), None)
    if not action:
        return jsonify({'error': '无效的互动'}), 400
    stamina = state.get('stamina', 80)
    cost = action['stamina_cost']
    if stamina < cost:
        return jsonify({'error': '精力不足'}), 400
    state['stamina'] = max(0, min(100, stamina - cost))

    # Apply effects — changes state, which influences next LLM call
    effect = action['effect']
    attrs = state.get('attributes', {})
    for short, full in [('审美', '审美判断力'), ('执行', '执行能力'), ('商业', '商业思维'),
                         ('表达', '表达能力'), ('创意', '创意深度')]:
        if f'{short}+1' in effect:
            attrs[full] = min(10, attrs.get(full, 5) + 1)
        if f'{short}-1' in effect:
            attrs[full] = max(1, attrs.get(full, 5) - 1)
    state['attributes'] = attrs

    # Update NPC relation
    if npc.get('relation') == '待剧情展开':
        npc['relation'] = '已建立联系'
    # Deepen relation slightly
    rel_bonus = {'请教':'更熟悉了', '展示':'对你的作品有了印象', '内推':'在帮你留意机会',
                 '讨论':'建立了初步信任', '提交':'对你的执行力有了认知', '争取':'认可你的商业意识',
                 '聊聊':'对你印象不错', '分享':'觉得你很有洞察力',
                 '一起':'合作默契在增长', '头脑':'创意碰撞有火花', '推荐':'商业互信+1',
                 '随意':'轻松相处', '请教工作':'对你的专业能力有认知'}
    for key, rel in rel_bonus.items():
        if key in action['text']:
            npc['relation'] = rel
            break

    # Mark interaction
    interacted[npc_id] = True
    state['_npc_interacted'] = interacted

    save_state(state)
    return jsonify({
        'ok': True,
        'npc_name': npc['name'],
        'action_text': action['text'],
        'effect': effect,
        'stamina': state['stamina'],
        'attributes': state['attributes'],
        'npcs': state['npcs'],
    })

@app.route('/api/npc/options', methods=['POST'])
def api_npc_options():
    state = load_state()
    if not state:
        return jsonify({'error': '没有存档'}), 404
    data = request.get_json()
    npc_id = data.get('npc_id')
    npcs = state.get('npcs', [])
    npc = next((n for n in npcs if n.get('id') == npc_id), None)
    if not npc:
        return jsonify({'error': 'NPC 不存在'}), 404
    role = npc.get('role', '职场关系')
    interactions = NPC_INTERACTIONS.get(role, NPC_INTERACTIONS['职场关系'])
    stamina = state.get('stamina', 80)
    options = []
    for a in interactions:
        opt = dict(a)
        opt['available'] = stamina >= a['stamina_cost']
        options.append(opt)
    return jsonify({'ok': True, 'npc': npc, 'options': options})

# ============================================================
# I4-P0: Project System
# ============================================================
@app.route('/api/project', methods=['GET'])
def api_project():
    state = load_state()
    if not state:
        return jsonify({'error': '没有存档'}), 404
    proj = state.get('current_project')
    if not proj:
        # Auto-generate a project if none exists
        import random as _random
        clients = ['森屿集团', '云帆科技', '墨白文化', '青禾品牌', '知味餐饮', '星辰互娱']
        types = ['品牌VI升级', '产品发布会设计', '年度画册', '空间导视系统', 'APP界面改版', '包装设计']
        proj = {
            'name': f'{_random.choice(clients)}-{_random.choice(types)}',
            'client': _random.choice(clients),
            'budget': _random.choice([5000, 8000, 12000, 15000, 20000]),
            'deadline_turns': _random.choice([5, 6, 7, 8]),
            'quality': max(10, state.get('attributes', {}).get('审美判断力', 5) * 10),
            'client_satisfaction': max(10, state.get('attributes', {}).get('表达能力', 5) * 10),
            'phase': '执行中',
            'start_turn': state.get('turn_count', 0)
        }
        state['current_project'] = proj
        save_state(state)
    # Auto-progress project quality based on attributes
    attrs = state.get('attributes', {})
    proj['quality'] = min(100, proj.get('quality', 0) + attrs.get('审美判断力', 5) - 3)
    proj['client_satisfaction'] = min(100, max(0, proj.get('client_satisfaction', 50) + attrs.get('表达能力', 5) - 5))
    # Check if deadline reached
    turns_left = proj.get('start_turn', 0) + proj.get('deadline_turns', 6) - state.get('turn_count', 0)
    if turns_left <= 0 and proj.get('phase') == '执行中':
        proj['phase'] = '交付'
    return jsonify({'project': proj, 'turns_left': max(0, turns_left)})

# ============================================================
# Portfolio Generator — LLM生成作品集条目
# ============================================================
@app.route('/api/portfolio/generate', methods=['POST'])
def api_portfolio_generate():
    state = load_state()
    if not state:
        return jsonify({'error': '没有存档'}), 404
    cfg = load_config()
    if not cfg.get('api_key'):
        return jsonify({'error': '请先配置 API Key'}), 400

    log = state.get('story_log', [])
    projects = log[-8:]  # Last 8 entries
    project_entries = [e for e in projects if e.get('event_tag') == '项目推进']

    if not project_entries:
        return jsonify({'entries': [], 'message': '还没有完成的项目'})

    # Build prompt with project narratives
    project_text = '\n'.join([f'项目{i+1}（第{e["turn"]}回合）: {e.get("narrative","")[:200]}' for i, e in enumerate(project_entries)])
    messages = [
        {'role': 'system', 'content': '你是设计师的作品集编辑。根据项目叙述，为每个项目生成一个简洁的作品集条目。只输出JSON。'},
        {'role': 'user', 'content': f'''根据以下项目经历，生成作品集条目。每个条目包含：name（项目名≤15字）、role（角色≤8字）、style（视觉风格≤10字）、highlight（一句话亮点≤20字）。

{project_text}

只输出JSON数组，格式：[{{"name":"","role":"","style":"","highlight":""}}, ...]'''}
    ]
    result, error = call_llm(messages, cfg['api_base'], cfg['api_key'], cfg['model'])
    if error:
        return jsonify({'entries': [], 'message': '生成失败'})

    try:
        content = result if isinstance(result, list) else json.loads(result) if isinstance(result, str) else []
        # Clean markdown
        if isinstance(content, str):
            content = content.replace('```json', '').replace('```', '').strip()
            content = json.loads(content)
        entries = content if isinstance(content, list) else []
    except:
        entries = []

    return jsonify({'entries': entries})

# ============================================================
# I4-P1: Active Actions (non-LLM turns)
# ============================================================
ACTIVE_ACTIONS = {
    'rest_short': {'name': '周末休整', 'cost': {}, 'effect': '精力+15', 'desc': '休息两天，恢复精力', 'icon': '☕'},
    'rest_long': {'name': '请假休假', 'cost': {'savings': -1000}, 'effect': '精力+35', 'desc': '请假一周，深度恢复', 'icon': '🏖️'},
    'train': {'name': '报班学习', 'cost': {'savings': -3000}, 'effect': '某属性+1', 'desc': '选择一项属性进行提升', 'icon': '📚'},
    'train_intensive': {'name': '封闭集训', 'cost': {'savings': -8000, 'stamina': -20}, 'effect': '自选属性+2', 'desc': '高强度集训', 'icon': '🎓'},
    'portfolio': {'name': '整理作品集', 'cost': {'stamina': -5}, 'effect': '作品集厚度+1', 'desc': '花时间打磨你的作品展示', 'icon': '🎨'},
    'jobhunt_targeted': {'name': '精准投递', 'cost': {'stamina': -15}, 'effect': '投3家公司', 'desc': '精挑细选目标公司投递', 'icon': '🎯'},
    'networking': {'name': '社交拓展', 'cost': {'savings': -1500, 'stamina': -8}, 'effect': '触发NPC接触', 'desc': '参加行业活动拓展人脉', 'icon': '🤝'},
}

@app.route('/api/active_action', methods=['POST'])
def api_active_action():
    data = request.get_json(silent=True) or {}
    state = load_state()
    if not state:
        return jsonify({'error': '没有存档'}), 400

    cfg = load_config()
    if not cfg.get('api_key'):
        return jsonify({'error': '请先配置 API Key'}), 400

    action_key = data.get('action', '')
    action_attr = data.get('attr', '')  # For 'train' action

    action = ACTIVE_ACTIONS.get(action_key)
    if not action:
        return jsonify({'error': '未知行动'}), 400

    # Apply costs
    if action.get('cost'):
        if 'savings' in action['cost']:
            state['savings'] = max(0, state.get('savings', 0) + action['cost']['savings'])
        if 'stamina' in action['cost']:
            state['stamina'] = max(0, min(100, state.get('stamina', 80) + action['cost']['stamina']))

    # Apply deterministic effects (these are the "skeleton", LLM narrates the "flesh")
    result_msg = ''
    action_context = ''
    if action_key == 'train' and action_attr:
        if action_attr in state.get('attributes', {}):
            state['attributes'][action_attr] = min(10, state['attributes'][action_attr] + 1)
            action_context = f'主动行动：报班学习{action_attr}，属性提升+1。'
            result_msg = f'{action_attr} +1'
    elif action_key == 'train_intensive' and action_attr:
        if action_attr in state.get('attributes', {}):
            state['attributes'][action_attr] = min(10, state['attributes'][action_attr] + 2)
            action_context = f'主动行动：参加封闭集训，高强度学习{action_attr}，属性提升+2，但极度消耗精力和金钱。'
            result_msg = f'{action_attr} +2'
    elif action_key == 'rest_short':
        state['stamina'] = min(100, state.get('stamina', 80) + 15)
        action_context = f'主动行动：周末休整，精力恢复+15。这个月节奏比较舒缓。'
        result_msg = '精力 +15'
    elif action_key == 'rest_long':
        state['stamina'] = min(100, state.get('stamina', 80) + 35)
        action_context = f'主动行动：请了一周假，深度休息，精力恢复+35。但项目进度可能受到了一些影响。'
        result_msg = '精力 +35'
    elif action_key == 'portfolio':
        state['attributes']['作品集厚度'] = min(10, state['attributes'].get('作品集厚度', 1) + 1)
        action_context = f'主动行动：花了大量时间整理和打磨作品集，作品集厚度+1。这段时间你的设计产出减少了，但作品质量在提升。'
        result_msg = '作品集厚度 +1'
    elif action_key == 'jobhunt_targeted':
        import random as _random
        companies = _random.sample(['云帆科技','墨白文化','星辰互娱','知味餐饮','森屿集团','青禾品牌'], 3)
        replies = []
        for c in companies:
            r = _random.choices([f'{c}：已收到简历', f'{c}：约了下周面试', f'{c}：暂无回复'], weights=[2, 3, 3])[0]
            replies.append(f'{c}:{r}')
        action_context = f'主动行动：精挑细选投递了3家公司简历。结果：' + '；'.join(replies) + '。'
        result_msg = '已投递3家公司'
    elif action_key == 'networking':
        npcs = state.get('npcs', [])
        if npcs:
            target = _random.choice(npcs)
            target['relation'] = '最近在行业活动上有过接触'
            target['active'] = True
            action_context = f'主动行动：参加了行业社交活动，和{target["name"]}（{target["role"]}）建立了初步联系。'
            result_msg = f'和{target["name"]}有了接触'

    # Advance turn
    turn = state['turn_count'] + 1
    state['turn_count'] = turn

    # Call LLM to narrate this active action month + generate next choices
    messages = build_messages(state, f'{action["name"]}：{action_context}')
    result, error = call_llm(messages, cfg['api_base'], cfg['api_key'], cfg['model'])
    if error:
        result = validate_and_fix_result({}, state['turn_count'], state['attributes'])
    result = validate_and_fix_result(result, state['turn_count'], state['attributes'])

    if result.get('npc_updates'):
        state['npcs'] = apply_npc_updates(state['npcs'], result['npc_updates'])
    if result.get('company_update'):
        apply_company_update(state, result['company_update'])

    entry = {
        'turn': turn,
        'player_action': action['name'],
        'narrative': result['narrative'],
        'choices': result['choices'],
        'atmosphere': result.get('atmosphere', '日常'),
        'attr_display': state['attributes'].copy(),
        'event_tag': result.get('event_tag', '日常'),
    }
    state['story_log'].append(entry)
    state['attributes'] = result.get('attr_display', state['attributes'])

    # Run all post-turn systems (same as api_action)
    arc_msg = detect_and_start_arc(state)
    challenge = check_career_challenge(state)
    economy_event = process_monthly_economy(state)
    crisis_event = check_savings_crisis(state)
    project_phase_hint = advance_project_phase(state)
    prev_stamina = state.get('_prev_stamina', state.get('stamina', 80))
    state['title'] = calculate_title(state['attributes'])
    new_ach, unlocked = check_achievements(state, prev_stamina)
    state['unlocked_achievements'] = list(unlocked)
    state['_prev_stamina'] = state['stamina']
    milestone_done, milestone_reward = check_milestone(state)
    npc_event = generate_npc_event(state)
    stamina_status, _ = get_stamina_status(state['stamina'])

    save_state(state)
    return jsonify({
        'ok': True,
        'action': action_key,
        'result': result_msg,
        'entry': entry,
        'attributes': state['attributes'],
        'stamina': state['stamina'],
        'savings': state['savings'],
        'title': state['title'],
        'npcs': state['npcs'],
        'company': state.get('company', {}),
        'career_history': state.get('career_history', []),
        'unlocked_achievements': list(unlocked),
        'new_achievements': [a for a in ACHIEVEMENTS if a['id'] in new_ach],
        'milestone': state.get('milestone'),
        'milestone_done': milestone_done,
        'milestone_reward': milestone_reward,
        'economy_event': economy_event,
        'crisis_event': crisis_event,
        'arc_msg': arc_msg,
        'project_phase_hint': project_phase_hint,
        'challenge': challenge,
        'npc_event': npc_event,
        'stamina_status': stamina_status,
        'trait': state.get('trait'),
        'turn': turn
    })

# ============================================================
# I4-P2: Multi-Save System
# ============================================================
SAVES_DIR = os.path.join(BASE_DIR, 'players')

def get_saves_dir():
    d = os.path.join(PLAYERS_DIR, get_session_id(), 'saves')
    if not os.path.exists(d):
        os.makedirs(d)
    return d

def get_save_path(slot):
    return os.path.join(get_saves_dir(), f'slot_{slot}.json')

@app.route('/api/saves', methods=['GET'])
def api_saves_list():
    get_saves_dir()
    slots = {}
    for i in range(1, 6):
        path = get_save_path(i)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                s = json.load(f)
            player = s.get('player', {})
            slots[str(i)] = {
                'name': player.get('name', '?'),
                'title': s.get('title', {}).get('title', '?'),
                'turn': s.get('turn_count', 0),
                'city': player.get('city', '?'),
                'created': s.get('created_at', '?')
            }
    return jsonify({'slots': slots})

@app.route('/api/saves/save', methods=['POST'])
def api_saves_save():
    data = request.get_json(silent=True) or {}
    slot = data.get('slot', 1)
    state = load_state()
    if not state:
        return jsonify({'error': '没有当前存档'}), 400
    get_saves_dir()
    with open(get_save_path(slot), 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return jsonify({'ok': True, 'slot': slot})

@app.route('/api/saves/load', methods=['POST'])
def api_saves_load():
    data = request.get_json(silent=True) or {}
    slot = data.get('slot', 1)
    path = get_save_path(slot)
    if not os.path.exists(path):
        return jsonify({'error': f'存档槽位 {slot} 不存在'}), 404
    with open(path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    save_state(state)
    return jsonify({'ok': True, 'state': state})

@app.route('/api/saves/delete', methods=['POST'])
def api_saves_delete():
    data = request.get_json(silent=True) or {}
    slot = data.get('slot', 1)
    path = get_save_path(slot)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({'ok': True})

if __name__ == '__main__':
    print('=' * 50)
    print('  平面设计师模拟器 - http://localhost:8765')
    print('=' * 50)
    app.run(host='0.0.0.0', port=8765, debug=False, use_reloader=False)
