#!/usr/bin/env python
# -*- coding: utf-8 -*-
'平面设计师职业生涯模拟器 - 游戏服务器 v2'

import json, os, random, traceback, uuid, threading
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

# Per-player thread lock — prevents concurrent write conflicts
_player_locks = {}
_npc_interacted = {}       # {session_id: {npc_id: True}} — per-turn NPC interaction tracking (NOT persisted)
_npc_event_log = {}        # {session_id: [(npc_name, action_text)]} — recent NPC interactions for LLM context
_npc_spotlight = {}        # {session_id: {npc_name: remaining_turns}} — elevated visibility window after interaction
_npc_pending_events = {}   # {session_id: {npc_id: event_text}} — AI-initiated NPC events awaiting player response

def get_player_lock():
    pid = get_session_id()
    if pid not in _player_locks:
        _player_locks[pid] = threading.Lock()
    return _player_locks[pid]

def get_npc_interactions():
    pid = get_session_id()
    if pid not in _npc_interacted:
        _npc_interacted[pid] = {}
    return _npc_interacted[pid]

def flush_npc_event_log():
    pid = get_session_id()
    events = _npc_event_log.pop(pid, [])
    return events

def push_npc_event(npc_name, action_text):
    pid = get_session_id()
    if pid not in _npc_event_log:
        _npc_event_log[pid] = []
    _npc_event_log[pid].append((npc_name, action_text))
    # Grant spotlight
    set_npc_spotlight(npc_name)

def set_npc_spotlight(npc_name, turns=4):
    pid = get_session_id()
    if pid not in _npc_spotlight:
        _npc_spotlight[pid] = {}
    _npc_spotlight[pid][npc_name] = max(_npc_spotlight[pid].get(npc_name, 0), turns)

def tick_npc_spotlight():
    '''Decrement spotlight counters. Returns list of (name, remaining_turns) still in spotlight.'''
    pid = get_session_id()
    if pid not in _npc_spotlight:
        return []
    active = []
    expired = []
    for name, turns in list(_npc_spotlight[pid].items()):
        if turns <= 1:
            expired.append(name)
        else:
            _npc_spotlight[pid][name] = turns - 1
            active.append((name, turns - 1))
    for name in expired:
        del _npc_spotlight[pid][name]
    return active

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
SYSTEM_PROMPT = '''# 平面设计师模拟器 · Game Master

## 铁律
你的回复必须是纯JSON对象 ({...})，禁止任何额外文字、注释、Markdown标记。

## 身份与基调
你是DM，负责叙事/NPC/事件/属性。写实向、非爽文、无恋爱线。女主非天才，成长需代价。每3-4回合至少一次正面时刻（客户认可/同事帮忙/作品被赞/小奖金/成长感）。挫折后有回弹，低谷后有光亮。

## 属性 (1-20级XP累积制)
审美判断力/执行能力/商业思维/表达能力/创意深度/作品集厚度
等级由后端公式自动计算，你只输出趋势方向(up/down/flat)。

## 时间·资源
每回合≈1周。精力0-100，加班消耗，休息恢复。储蓄=工资+奖金-2500月支出。精力<20疲劳叙事，储蓄不足焦虑叙事。

## choice.effects (结构化数组)
格式: [{"attr":"审美判断力","delta":1,"text":"审美+1"}, {"attr":"stamina","delta":-8,"text":"精力-8"}]
attr必须是全称(审美判断力/执行能力/商业思维/表达能力/创意深度/作品集厚度)，stamina/savings用于精力储蓄。
+1=50XP，涨属性必须伴随代价。大部分回合trend为flat，高等级(≥15)极少up。作品集仅实际产出时up。

## 输出格式
{
  "narrative": "第二人称叙事150-300字",
  "choices": [
    {"id":"A","text":"≤20字","hint":"≤12字","effects":[{"attr":"审美判断力","delta":1,"text":"审美+1"},{"attr":"stamina","delta":-8,"text":"精力-8"}]},
    {"id":"B","text":"≤20字","hint":"≤12字","effects":[{"attr":"商业思维","delta":1,"text":"商业+1"}]},
    {"id":"C","text":"≤20字","hint":"≤12字","effects":[{"attr":"表达","delta":1,"text":"表达+1"},{"attr":"stamina","delta":15,"text":"精力+15"}]}
  ],
  "atmosphere": "≤10字",
  "attr_trend": {"审美判断力":"up","执行能力":"flat","商业思维":"up","表达能力":"flat","创意深度":"flat","作品集厚度":"up"},
  "stamina_change": -8, "savings_change": 0,
  "event_tag": "项目推进/行业事件/日常/转折点/倦怠预警",
  "npc_updates": [{"name":"陈知夏","relation":"新关系","desc":"新简介"}],
  "company_update": {"name":"XX工作室","position":"初级设计师","action":"入职"}
}

## 规则速查
- stamina_change: -15~+20, savings_change单位元
- attr_trend: 每个属性 up/down/flat，后端转XP
- company_update: 仅重大变动时更新，否则省略
- npc_updates: 可选，仅涉及NPC时更新
- choices: 必须2-3个有意义选项。无终点游戏，属性低不代表结束
- 每周1回合，季节影响事件倾向'''

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
def call_llm_stream(messages, api_base, api_key, model):
    '''Call LLM with streaming, yields text chunks.'''
    import requests
    try:
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
        payload = {
            'model': model,
            'messages': messages,
            'temperature': 0.85,
            'max_tokens': 1500,
            'stream': True
        }
        resp = requests.post(f'{api_base}/chat/completions', headers=headers, json=payload, timeout=120, stream=True)
        if resp.status_code >= 400:
            payload.pop('response_format', None)
            resp = requests.post(f'{api_base}/chat/completions', headers=headers, json=payload, timeout=120, stream=True)
        if resp.status_code != 200:
            yield None, f'API Error {resp.status_code}'
            return
        full_content = ''
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data_str = line[6:]
                if data_str.strip() == '[DONE]':
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get('choices', [{}])[0].get('delta', {})
                    content = delta.get('content', '')
                    if content:
                        full_content += content
                        yield content, None
                except json.JSONDecodeError:
                    continue
        # Clean markdown
        full_content = full_content.replace('```json', '').replace('```', '').strip()
        yield json.loads(full_content), None
    except json.JSONDecodeError as e:
        yield None, f'JSON parse: {str(e)[:100]}'
    except Exception as e:
        yield None, f'Call failed: {str(e)[:100]}'

def call_llm(messages, api_base, api_key, model):
    try:
        import requests
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
        payload = {
            'model': model,
            'messages': messages,
            'temperature': 0.85,
            'max_tokens': 3000,
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

def _legacy_effect_to_structured(effect_str):
    '''Convert legacy "审美+1 执行-2" to structured [{"attr":..., "delta":..., "text":...}].'''
    SHORT_FULL = {
        '审美': '审美判断力', '执行': '执行能力', '商业': '商业思维',
        '表达': '表达能力', '创意': '创意深度', '作品': '作品集厚度'
    }
    result = []
    parts = effect_str.strip().split()
    for part in parts:
        for short, full in SHORT_FULL.items():
            if part.startswith(short):
                try:
                    delta = int(part[len(short):])
                    result.append({'attr': full, 'delta': delta, 'text': part})
                except (ValueError, IndexError):
                    pass
    return result

# ============================================================
# Fallback choice generators
# ============================================================
def make_fallback_choices(turn_count, attrs):
    '''Always return valid choices, never empty.'''
    base = [
        {'id': 'A', 'text': '继续当前的工作节奏', 'hint': '稳扎稳打', 'effects': [{'attr': '执行能力', 'delta': 1, 'text': '执行+1'}]},
        {'id': 'B', 'text': '主动寻求新机会', 'hint': '冒险可能突破', 'effects': [{'attr': '商业思维', 'delta': 1, 'text': '商业+1'}, {'attr': 'stamina', 'delta': -8, 'text': '精力-8'}]},
        {'id': 'C', 'text': '停下来复盘和思考', 'hint': '恢复和规划', 'effects': [{'attr': 'stamina', 'delta': 15, 'text': '精力+15'}]},
    ]
    if turn_count % 7 == 0:
        return [
            {'id': 'A', 'text': '抓住这个转折机会', 'hint': '职业跃升', 'effects': [{'attr': '表达能力', 'delta': 1, 'text': '表达+1'}, {'attr': 'stamina', 'delta': -8, 'text': '精力-8'}]},
            {'id': 'B', 'text': '谨慎观望再做决定', 'hint': '保守安全', 'effects': [{'attr': '执行能力', 'delta': 2, 'text': '执行+2'}]},
            {'id': 'C', 'text': '和信任的人商量一下', 'hint': '借助他人视角', 'effects': [{'attr': '表达能力', 'delta': 1, 'text': '表达+1'}]},
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
            result['choices'][i] = {'id': chr(65+i), 'text': '继续推进', 'hint': '下一步', 'effects': []}
        if 'id' not in ch:
            ch['id'] = chr(65+i)
        if 'text' not in ch:
            ch['text'] = '继续推进'
        if 'hint' not in ch:
            ch['hint'] = ''
        # Normalize effects: always use 'effects' array format
        if 'effects' not in ch:
            ch['effects'] = []
    # Ensure 2-3 choices
    if len(result['choices']) < 2:
        result['choices'] = make_fallback_choices(turn_count, attrs)
    if len(result['choices']) > 3:
        result['choices'] = result['choices'][:3]
    # Normalize all choices to effects[] format (convert legacy 'effect' strings)
    for ch in result.get('choices', []):
        if 'effect' in ch and isinstance(ch['effect'], str) and ch['effect'].strip():
            converted = _legacy_effect_to_structured(ch['effect'])
            if converted:
                ch['effects'] = converted
            # Keep ch['effect'] for frontend display
        if 'effects' not in ch or not isinstance(ch['effects'], list):
            ch['effects'] = []
    if not result.get('atmosphere'):
        result['atmosphere'] = '设计工作室的日常'
    if not result.get('event_tag'):
        result['event_tag'] = '日常'
    if not result.get('attr_trend'):
        result['attr_trend'] = {}
    # Enforce: max 2 "up" trends per turn, rest → "flat"
    up_count = 0
    for key in ['审美判断力', '执行能力', '商业思维', '表达能力', '创意深度', '作品集厚度']:
        if key not in result['attr_trend']:
            result['attr_trend'][key] = 'flat'
        elif result['attr_trend'][key] == 'up':
            up_count += 1
            if up_count > 2:
                result['attr_trend'][key] = 'flat'
    # Stamina & savings
    if 'stamina_change' not in result:
        result['stamina_change'] = -5
    if 'savings_change' not in result:
        result['savings_change'] = 0
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
ATTR_CAP = 15  # Max attribute value (was 10)

# ============================================================
# XP-based attribute system (20-point scale)
# ============================================================
XP_PER_LEVEL_BASE = 20  # Level = floor(sqrt(xp / 20)), max level 20

def xp_to_level(xp):
    '''Convert accumulated XP to level (1-20). XP can be negative.'''
    if xp <= 0:
        return 1
    level = int((xp / XP_PER_LEVEL_BASE) ** 0.5)
    return max(1, min(20, level))

def level_to_xp_target(level):
    '''XP needed to reach this level from 0.'''
    return level * level * XP_PER_LEVEL_BASE

def xp_for_level_up(current_level):
    '''XP needed to go from current_level to current_level+1.'''
    return level_to_xp_target(current_level + 1) - level_to_xp_target(current_level)

def apply_trend_to_xp(state, attr_trends):
    '''Apply LLM trend directions (up/down/flat) as XP changes.
    Returns dict of {attr: xp_delta} for notification.'''
    GOAL_BOOST = {
        '成为顶级独立设计师': {'审美判断力': 10, '创意深度': 10},
        '做到创意总监/合伙人': {'商业思维': 10, '表达能力': 10},
        '创立自己的设计品牌/厂牌': {'商业思维': 10, '创意深度': 10},
        '成为行业话语权拥有者': {'表达能力': 10, '创意深度': 10},
        '活着就好': {'执行能力': 10},
    }
    goal = state.get('player', {}).get('goal', '')
    boosts = GOAL_BOOST.get(goal, {})
    deltas = {}
    for attr, trend in (attr_trends or {}).items():
        if trend == 'up':
            delta = random.randint(15, 35)
        elif trend == 'down':
            delta = -random.randint(15, 35)
        else:
            delta = 0
        # Goal bonus
        if delta > 0 and attr in boosts:
            delta += boosts[attr]
        if delta != 0:
            xp = state.get('attribute_xp', {})
            xp[attr] = xp.get(attr, 0) + delta
            state['attribute_xp'] = xp
            deltas[attr] = delta
    return deltas

def xp_to_attrs(state):
    '''Derive attribute levels from XP.'''
    xp_dict = state.get('attribute_xp', {})
    attrs = {}
    ALL_ATTRS = ['审美判断力', '执行能力', '商业思维', '表达能力', '创意深度', '作品集厚度']
    for attr in ALL_ATTRS:
        attrs[attr] = xp_to_level(xp_dict.get(attr, 0))
    return attrs

def apply_effect_xp(state, choice_effect):
    '''Apply choice effect — supports both string format and structured list.
    String: "审美+1 精力-8" / Structured: [{"attr":"审美","delta":1},...]
    Returns {attr: level_change} for notification.'''
    level_changes = {}

    # Parse string format into structured list
    if isinstance(choice_effect, str) and choice_effect.strip():
        SHORT_MAP = {
            '审美': '审美判断力', '执行': '执行能力', '商业': '商业思维',
            '表达': '表达能力', '创意': '创意深度', '作品': '作品集厚度'
        }
        effects_list = []
        parts = choice_effect.strip().split()
        for part in parts:
            for short, full in SHORT_MAP.items():
                if part.startswith(short):
                    try:
                        delta = int(part[len(short):])
                        effects_list.append({'attr': full, 'delta': delta, 'text': part})
                    except (ValueError, IndexError):
                        pass
                    break
            # Handle stamina/savings in string format
            if part.startswith('精力'):
                try:
                    delta = int(part[2:])
                    effects_list.append({'attr': 'stamina', 'delta': delta})
                except (ValueError, IndexError):
                    pass
            elif part.startswith('储蓄'):
                try:
                    delta = int(part[2:])
                    effects_list.append({'attr': 'savings', 'delta': delta})
                except (ValueError, IndexError):
                    pass
    elif isinstance(choice_effect, list):
        effects_list = choice_effect
    else:
        return level_changes

    XP_PER_EFFECT_POINT = 50
    xp = state.get('attribute_xp', {})

    for ef in effects_list:
        if not isinstance(ef, dict):
            continue
        attr = ef.get('attr', '')
        delta = ef.get('delta', 0)
        if not attr or not delta:
            continue
        if attr == 'stamina':
            state['stamina'] = max(0, min(100, state.get('stamina', 80) + delta))
        elif attr == 'savings':
            state['savings'] = max(0, state.get('savings', 3000) + delta)
        else:
            xp_delta = XP_PER_EFFECT_POINT * delta
            old_level = xp_to_level(xp.get(attr, 0))
            xp[attr] = xp.get(attr, 0) + xp_delta
            new_level = xp_to_level(xp[attr])
            if new_level != old_level:
                level_changes[attr] = new_level - old_level

    state['attribute_xp'] = xp
    return level_changes

# ============================================================
TITLE_THRESHOLDS = [
    {'title': '见习设计师',     'stage': '萌芽期', 'attrs': {}},
    {'title': '初级设计师',     'stage': '成长期', 'attrs': {'审美判断力': 5, '执行能力': 5}},
    {'title': '中级设计师',     'stage': '成长期', 'attrs': {'审美判断力': 8, '执行能力': 8, '作品集厚度': 6}},
    {'title': '高级设计师',     'stage': '成熟期', 'attrs': {'审美判断力': 11, '执行能力': 10, '作品集厚度': 8, '表达能力': 8}},
    {'title': '资深设计师',     'stage': '成熟期', 'attrs': {'审美判断力': 13, '执行能力': 12, '作品集厚度': 11, '表达能力': 10, '商业思维': 9}},
    {'title': '设计总监',       'stage': '巅峰期', 'attrs': {'审美判断力': 15, '执行能力': 13, '作品集厚度': 13, '表达能力': 12, '商业思维': 12, '创意深度': 12}},
    {'title': '创意合伙人',     'stage': '巅峰期', 'attrs': {'审美判断力': 17, '执行能力': 15, '作品集厚度': 16, '表达能力': 15, '商业思维': 15, '创意深度': 15}},
    {'title': '独立设计大师',   'stage': '传奇',   'attrs': {'审美判断力': 18, '作品集厚度': 18, '表达能力': 16, '创意深度': 16}},
]

ACHIEVEMENTS = [
    {'id': 'first_project',  'name': '初出茅庐', 'desc': '完成第一个设计项目', 'icon': '🌱'},
    {'id': 'portfolio_10',   'name': '作品等身', 'desc': '作品集厚度达到 10', 'icon': '📦'},
    {'id': 'portfolio_15',   'name': '业界标杆', 'desc': '作品集厚度达到 15', 'icon': '🏆'},
    {'id': 'expression_12',  'name': '金字招牌', 'desc': '表达能力达到 12',   'icon': '🤝'},
    {'id': 'expression_16',  'name': '德高望重', 'desc': '表达能力达到 16',   'icon': '👑'},
    {'id': 'aesthetic_14',   'name': '审美大师', 'desc': '审美判断力达到 14', 'icon': '🎨'},
    {'id': 'stamina_low',    'name': '至暗时刻', 'desc': '精力值降到 10 以下','icon': '🌑'},
    {'id': 'stamina_recover','name': '涅槃重生', 'desc': '精力从低谷恢复到 70+','icon': '🔥'},
    {'id': 'npc_3_related',  'name': '社交达人', 'desc': '与 3 位 NPC 建立关系', 'icon': '💬'},
    {'id': 'turn_20',        'name': '十年磨一剑', 'desc': '职业生涯超过 20 回合', 'icon': '⏳'},
    {'id': 'turn_50',        'name': '老设计师',   'desc': '职业生涯超过 50 回合', 'icon': '📜'},
    {'id': 'all_rounder',    'name': '六边形战士', 'desc': '全属性 ≥ 8', 'icon': '⭐'},
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
            target = min(ATTR_CAP, state.get('attributes', {}).get(attr, 5) + _random.choice([2, 3]))
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
                apply_effect_xp(state, reward)
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
        # Completion reward — add XP (not direct level)
        state['savings'] = state.get('savings', 0) + proj.get('budget', 5000)
        xp = state.get('attribute_xp', {})
        xp['作品集厚度'] = xp.get('作品集厚度', 0) + 200
        xp['商业思维'] = xp.get('商业思维', 0) + 200
        state['attribute_xp'] = xp
        state['attributes'] = xp_to_attrs(state)
        # Record to portfolio + cooldown
        add_portfolio_entry(state, proj)
        state['_project_cooldown'] = random.randint(4, 8)
        state.pop('current_project', None)

    if phases_progressed:
        state['_project_phase_changed'] = proj.get('phase', '')
    return phase_hints.get(proj.get('phase', ''), '') if phases_progressed else None

def add_portfolio_entry(state, proj):
    '''Record a completed project into the portfolio list.'''
    if 'portfolio' not in state:
        state['portfolio'] = []
    turn = state.get('turn_count', 0)
    # Extract last narrative line that mentions this project
    last_entry = state['story_log'][-1] if state['story_log'] else {}
    summary = ''
    if last_entry.get('event_tag') == '项目推进':
        summary = (last_entry.get('narrative', '') or '')[:100]
    entry = {
        'name': proj.get('name', '设计项目'),
        'time': get_game_date(state),
        'turn': turn,
        'client': proj.get('client', ''),
        'budget': proj.get('budget', 0),
        'quality': proj.get('quality', 50),
        'summary': summary,
    }
    state['portfolio'].append(entry)

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
                else:
                    xp = state.get('attribute_xp', {})
                    xp[attr] = xp.get(attr, 0) + 50 * delta
                    state['attribute_xp'] = xp
            state['attributes'] = xp_to_attrs(state)
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

# ============================================================
# I5: Specialization System — 专精方向
# ============================================================
SPECIALIZATIONS = {
    'brand':        {'id': 'brand',  'name': '品牌设计', 'icon': '🏷', 'desc': '企业VI、包装、品牌全案', 'bonus_attr': '商业思维', 'bonus_amount': 2},
    'ui_ux':        {'id': 'ui_ux',  'name': 'UI/UX 设计', 'icon': '📱', 'desc': '界面设计、交互逻辑、产品体验', 'bonus_attr': '执行能力', 'bonus_amount': 2},
    'illustration': {'id': 'illustration', 'name': '商业插画', 'icon': '🖌', 'desc': '商业插画、角色设计、视觉表达', 'bonus_attr': '创意深度', 'bonus_amount': 2},
    'motion':       {'id': 'motion', 'name': '动态设计', 'icon': '🎬', 'desc': '动画短片、动态品牌、视效制作', 'bonus_attr': '审美判断力', 'bonus_amount': 2},
    'print':        {'id': 'print',  'name': '印刷与物料', 'icon': '📄', 'desc': '书籍装帧、印刷工艺、空间导视', 'bonus_attr': '作品集厚度', 'bonus_amount': 2},
}

SPEC_PROJECTS = {
    'brand':        ['品牌VI升级', '包装设计', '品牌战略手册', '联名产品设计'],
    'ui_ux':        ['APP界面改版', '官网重构', '后台管理系统', '小程序设计'],
    'illustration': ['商业插画系列', '角色IP设计', '社媒视觉营销', '绘本创作'],
    'motion':       ['品牌宣传片', '产品动效演示', '社交媒体短视频', '开场动画'],
    'print':        ['年度画册', '空间导视系统', '书籍装帧', '展览物料'],
}

# ============================================================
# I5-A: Specialization Events — 专精随机事件 (每12-15回合)
# ============================================================
SPEC_EVENTS = {
    'brand': [
        '收到品牌设计行业大会的邀请函',
        '一个知名消费品牌正在寻找新的视觉合作伙伴',
        '你的品牌提案被同行转发到设计论坛引起讨论',
        '参加了品牌策略workshop，对商业设计的结合有了新理解',
    ],
    'ui_ux': [
        '收到了Figma社区年度活动的邀请',
        '一个风口上的互联网产品在寻找UI设计师',
        '你在设计论坛发的交互原型被官方推荐了',
        '面试时被问到AI是否会替代UI设计，这让你思考了很久',
    ],
    'illustration': [
        '一个独立出版品牌想和你合作一本绘本',
        '你的插画作品被某品牌看到想购买授权',
        '参加插画师社群线下活动认识了不少志同道合的人',
        '收到一个游戏项目的美术外包邀约',
    ],
    'motion': [
        '一个音乐人想为他的新专辑找你做视觉设计',
        '某广告公司外包了一个品牌宣传片的动效制作',
        '参加了Motion Design大会看到行业前沿视觉表达',
        '一个展会主办方找你做开幕动画',
    ],
    'print': [
        '独立书店想让你为年度书目做装帧设计',
        '某个展览的空间导视系统项目向你发出邀请',
        '在印刷厂认识了新的材料供应商可以做特殊工艺',
        '受邀参加一个书籍设计的学术研讨会',
    ],
}

def check_spec_event(state):
    '''Trigger specialization event every 12-15 turns.'''
    turn = state.get('turn_count', 0)
    last = state.get('_last_spec_event', 0)
    spec = state.get('specialization')
    if not spec or turn - last < random.randint(12, 15):
        return None
    events = SPEC_EVENTS.get(spec.get('id', ''), [])
    if not events: return None
    state['_last_spec_event'] = turn
    return random.choice(events)

# ============================================================
# 8. Year-in-Review — 年度回顾 (每48回合)
# ============================================================
def check_year_review(state):
    '''Trigger year review at turn 48, 96, 144...'''
    turn = state.get('turn_count', 0)
    if turn <= 0 or turn % 48 != 0:
        return None
    log = state.get('story_log', [])
    projects = [e for e in log if e.get('event_tag') == '项目推进']
    turning = [e for e in log if e.get('event_tag') == '转折点']
    title = state.get('title', {}).get('title', '设计师')
    savings = state.get('savings', 0)
    age = state.get('player', {}).get('age', 24) + turn // 48
    return (
        f'【年度回顾】{age}岁·{title}·完成{len(projects)}个项目·{len(turning)}个转折·储蓄{savings}元。'
        f'请生成150-200字的年终回顾叙事，审视这一年的成长与得失。'
    )

# ============================================================
# 9. Focus System — 近期重心
# ============================================================
FOCUS_ATTRS = {
    'skill':     {'attrs': ['审美判断力','执行能力','创意深度'], 'hint': '专注提升设计技能'},
    'network':   {'attrs': ['表达能力'], 'hint': '专注拓展人脉和社交'},
    'project':   {'attrs': ['执行能力','作品集厚度'], 'hint': '专注完成项目和积累作品'},
    'finance':   {'attrs': ['商业思维'], 'hint': '专注收入和财务稳定'},
}

def apply_focus_bonus(state):
    focus = state.get('_focus')
    if not focus: return
    fc = FOCUS_ATTRS.get(focus.get('type', ''))
    if not fc: return
    xp = state.get('attribute_xp', {})
    for attr in fc['attrs']:
        xp[attr] = xp.get(attr, 0) + 5
    state['attribute_xp'] = xp

# ============================================================
# I6: Design Trends System — 设计趋势迭代
# ============================================================
DESIGN_TRENDS = [
    {'name': '极简主义回潮', 'era': '白空间、无衬线、留白至上', 'boost_attr': '审美判断力', 'penalty_attr': '创意深度'},
    {'name': '赛博朋克浪潮', 'era': '霓虹色调、故障艺术、暗黑未来感', 'boost_attr': '创意深度', 'penalty_attr': '商业思维'},
    {'name': '新中式美学',   'era': '国潮复兴、水墨元素、东方哲学', 'boost_attr': '表达能力', 'penalty_attr': '执行能力'},
    {'name': '复古未来主义', 'era': '80年代像素风、合成器波、怀旧再造', 'boost_attr': '审美判断力', 'penalty_attr': '作品集厚度'},
    {'name': '有机自然设计', 'era': '自然形态、可持续材料、流动线条', 'boost_attr': '创意深度', 'penalty_attr': '商业思维'},
]
TREND_CYCLE_TURNS = 48  # ~12 months per trend cycle
_current_trend_index = {}  # {session_id: index}

def get_current_trend(state, seed_override=None):
    '''Get current design trend. Changes every 48 turns.'''
    idx = (state.get('turn_count', 0) // TREND_CYCLE_TURNS) % len(DESIGN_TRENDS)
    return DESIGN_TRENDS[idx]

def apply_trend_to_economy(state, base_amount):
    '''Adjust project budget based on trend alignment.'''
    trend = get_current_trend(state)
    attrs = state.get('attributes', {})
    boost_val = attrs.get(trend['boost_attr'], 5)
    penalty_val = attrs.get(trend['penalty_attr'], 5)

    # If boosting attribute is high, reward goes up; if penalty attribute is low, reward goes down
    modifier = 1.0
    if boost_val >= 7:
        modifier += 0.1
    if boost_val >= 12:
        modifier += 0.1
    if penalty_val <= 4:
        modifier -= 0.15
    if penalty_val <= 2:
        modifier -= 0.1

    return max(5000, int(base_amount * modifier)), modifier, trend

# ============================================================
# I7: Ending System — 结局检测
# ============================================================
ENDING_TYPES = [
    {'id': 'peak',       'name': '巅峰设计师', 'icon': '🌟', 'type': 'he'},
    {'id': 'career_switch', 'name': '华丽转身', 'icon': '🔄', 'type': 'he'},
    {'id': 'retirement', 'name': '平稳着陆', 'icon': '🏡', 'type': 'he'},
    {'id': 'bankruptcy', 'name': '黯然离场', 'icon': '💸', 'type': 'be'},
]

def check_endings(state):
    '''Check all ending conditions. Returns ending dict or None.'''
    turn = state.get('turn_count', 0)
    attrs = state.get('attributes', {})
    savings = state.get('savings', 3000)
    title = state.get('title', {}).get('title', '')
    log = state.get('story_log', [])

    # Peak ending: any attr >= 18 AND top title
    if any(v >= 18 for v in attrs.values()) and title in ('独立设计大师', '创意合伙人', '设计总监'):
        return {'id': 'peak', 'name': '巅峰设计师', 'icon': '🌟', 'type': 'he',
                'text': '你的名字在行业里已经成为一个标签。从默默无闻到巅峰，这一路每一步都算数。'}

    # Career switch ending: turn > 80, high business + expression
    if turn > 80 and attrs.get('商业思维', 0) >= 15 and attrs.get('表达能力', 0) >= 15:
        return {'id': 'career_switch', 'name': '华丽转身', 'icon': '🔄', 'type': 'he',
                'text': '你发现自己在商业策略上的嗅觉远超设计本身。创立了自己的设计咨询公司，开始以另一种方式推动这个行业。'}

    # Bankruptcy ending
    if savings < -10000:
        return {'id': 'bankruptcy', 'name': '黯然离场', 'icon': '💸', 'type': 'be',
                'text': '财务的窟窿已经大到无法填补。你把最后的设备卖了还债，在出租屋里看着空白的屏幕。'}

    # Retirement ending: 30 turns without 转折点
    recent = log[-30:] if len(log) >= 30 else log
    no_turning_point = all(e.get('event_tag') != '转折点' for e in recent[-20:]) if len(recent) >= 20 else False
    if turn > 50 and no_turning_point and attrs.get('作品集厚度', 0) >= 8:
        return {'id': 'retirement', 'name': '平稳着陆', 'icon': '🏡', 'type': 'he',
                'text': '你没有成为传奇，但你在行业中找到了自己的位置。稳定的客户、不错的收入、有意义的作品——这或许就是最好的结局。'}

    return None

# ============================================================
# I8: Industry News System — 行业动态
# ============================================================
_industry_news_cache = {}  # {seed: [(date, news_text)]}

INDUSTRY_NEWS_PROMPT = '''你是设计行业观察媒体。请根据当前游戏状态生成 2-3 条行业新闻（每条 ≤40 字）。
格式：纯JSON数组，每项{ "text": "新闻内容" }。
新闻应覆盖：行业大事件、设计趋势、竞争对手动态、技术革新、市场变化等。
只输出JSON数组。'''

def generate_industry_news(state, cfg):
    '''Generate industry news. Cached per 12-turn cycle keyed by state turn range.'''
    turn = state.get('turn_count', 0)
    cycle = turn // 12
    cache_key = f'{cycle}'
    if cache_key in _industry_news_cache:
        return _industry_news_cache[cache_key]

    player = state.get('player', {})
    npcs = state.get('npcs', [])

    context = f'当前回合：{turn}，玩家：{player.get("name","")}，头衔：{state.get("title",{}).get("title","")}\n'
    if npcs:
        context += '活跃NPC：' + ', '.join(f'{n["name"]}({n["role"]})' for n in npcs[:3])

    messages = [
        {'role': 'system', 'content': INDUSTRY_NEWS_PROMPT},
        {'role': 'user', 'content': context}
    ]

    try:
        result, err = call_llm(messages, cfg['api_base'], cfg['api_key'], cfg['model'])
        if err or not isinstance(result, list):
            return []
        news = [item for item in result if isinstance(item, dict) and item.get('text')]
        _industry_news_cache[cache_key] = news
        return news
    except:
        return []

def get_cached_news(state):
    '''Get pre-generated news for current cycle.'''
    turn = state.get('turn_count', 0)
    cycle = turn // 12
    return _industry_news_cache.get(f'{cycle}', [])

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
    return {'npc_name': npc['name'], 'npc_id': npc['id'], 'text': text, 'turn': turn}

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
    '应届生':   {'name': '学院派底子',   'desc': '理论扎实，对新风格吸收快。培训学习效果+20%', 'train_boost': 1.2, 'init_attr': {'创意深度': 2}},
    '乙方执行': {'name': '执行力基因',   'desc': '高强度执行训练出的习惯。所有行动精力消耗-2，但创意空间受限', 'stamina_discount': 2, 'init_attr': {'执行能力': 2, '创意深度': -1}},
    '甲方品牌': {'name': '商业嗅觉',     'desc': '从品牌方视角理解设计价值。薪资谈判+25%，但设计自由受限', 'salary_mod': 0.25, 'init_attr': {'商业思维': 2, '审美判断力': -1}},
    '媒体编辑': {'name': '信息敏感',     'desc': '对行业动态敏锐，NPC活动触发概率翻倍。手上功夫需磨练', 'npc_event_boost': True, 'init_attr': {'表达能力': 3, '执行能力': -2}},
    '自由职业': {'name': '独狼基因',     'desc': '靠自己成长，无固定薪资和办公开销。精力消耗更大', 'no_salary': True, 'expense_discount': 0.4, 'stamina_penalty': 3},
    '印刷厂':   {'name': '工艺基因',     'desc': '对材料和落地有直觉。作品集积累速度+50%，但商业思维需要补课', 'portfolio_boost': 1.5, 'init_attr': {'作品集厚度': 2, '商业思维': -1}},
    '自定义':   {'name': '无标签',       'desc': '你的道路由自己定义，不设任何框架', 'init_attr': {}},
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
    if attrs.get('作品集厚度', 0) >= 10: unlock('portfolio_10')
    if attrs.get('作品集厚度', 0) >= 15: unlock('portfolio_15')
    if attrs.get('表达能力', 0) >= 12: unlock('expression_12')
    if attrs.get('表达能力', 0) >= 16: unlock('expression_16')
    if attrs.get('审美判断力', 0) >= 14: unlock('aesthetic_14')

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
    if all(attrs.get(k, 0) >= 10 for k in all_attrs): unlock('all_rounder')

    # First project — check if any log entry has event_tag '项目推进'
    if any(e.get('event_tag') == '项目推进' for e in state.get('story_log', [])):
        unlock('first_project')

    return new_unlocks, unlocked
def build_messages(state, player_action=None, is_forced_rest=False, hospital_fee=0):
    player = state.get('player', {})
    attrs = state.get('attributes', {})
    npcs = state.get('npcs', [])
    story_len = len(state.get('story_log', []))

    # Phase 1: Fixed prefix (all cacheable — never changes across turns)
    parts = [
        '# 状态',
        f'{player.get("name","?")} | {player.get("city","上海")} | {player.get("origin","?")} → {player.get("goal","?")}',
        f'资源:{player.get("resources","?")} 节奏:{player.get("pace","标准")}',
    ]
    # Goal hint
    goal = player.get('goal', '')
    goal_hints = {
        '成为顶级独立设计师': '独立创作/私单/竞赛',
        '做到创意总监/合伙人': '晋升/管理/谈判',
        '创立自己的设计品牌/厂牌': '创业/品牌/融资',
        '成为行业话语权拥有者': '论坛/媒体/行业影响力',
        '活着就好': '稳定收入/轻松节奏',
    }
    if goal in goal_hints:
        parts.append(f'倾向: {goal_hints[goal]}')
    parts.append(f'公司: {state.get("company",{}).get("name","待定")} | {state.get("company",{}).get("position","设计师")}')
    # Trait (FIXED per origin — cacheable)
    trait = state.get('trait', {})
    if trait:
        parts.append(f'特质: {trait.get("name","")}—{trait.get("desc","")[:40]}')
    # Phase 2: Variable content (cache break starts here)
    parts.append(f'{int(player.get("age","0") or 0) + state.get("turn_count", 0) // 48}岁 | {get_game_date(state)} | {state.get("title",{}).get("title","见习")} | 第{story_len+1}回合')
    parts.append(f'精力:{state.get("stamina",80)} 储蓄:{state.get("savings",3000)}')
    # Attributes (compact)
    attr_parts = []
    for k, v in attrs.items():
        attr_parts.append(f'{k}:{v}')
    parts.append(f'属性: {", ".join(attr_parts)}')
    # Time + season
    game_date = get_game_date(state)
    season, events = get_season_and_events(game_date)
    try:
        month_num = int(game_date.split('年')[1].replace('月', ''))
    except:
        month_num = datetime.now().month
    season_hint = get_season_llm_hint(month_num)
    parts.append(f'时间: {game_date} {season} | {season_hint["tag"]} {season_hint["hint"][:30]}')
    # NPCs (with relation + desc)
    npc_parts = []
    for n in npcs[:6]:
        rel = n.get('relation','')
        desc = n.get('desc','')
        npc_parts.append(f'{n["name"]}({n["role"]}{"|"+rel if rel and rel!="待剧情展开" else ""}{"|"+desc[:20] if desc else ""})')
    parts.append(f'NPC: {", ".join(npc_parts)}')

    if state.get('current_project'):
        cp = state['current_project']
        parts.append(f'项目: {cp.get("name","无")} ({cp.get("phase","")}) 预算{cp.get("budget",0)} 质量{cp.get("quality",0)} 满意{cp.get("client_satisfaction",50)}')
    elif state.get('_project_cooldown', 0) > 0:
        parts.append(f'项目间歇, {state["_project_cooldown"]}周后可接')
    else:
        parts.append('项目间歇, 可接新项目')
    # Milestone
    ms = state.get('milestone')
    if ms:
        parts.append(f'阶段目标: {ms.get("description","")} 截止{ms.get("deadline_turn",0)}回 进度{ms.get("progress",0)}%')
    # Stamina + trait ctx
    status, _ = get_stamina_status(state.get('stamina', 80))
    parts.append(f'精力: {status}({state.get("stamina",80)})')
    trait_ctx = get_trait_context(state)
    if trait_ctx:
        parts.append(f'特质倾向: {trait_ctx}')
    # Arc
    arc = state.get('_narrative_arc')
    if arc:
        phases = arc.get('phases', [])
        idx = arc.get('phase_idx', 0)
        phase_name = phases[idx] if idx < len(phases) else '完结'
        parts.append(f'叙事弧: {arc.get("name","")} {phase_name}')
    # Crisis
    if state.get('_savings_crisis_level', 0) > 0:
        parts.append(f'财务危机 Lv{state.get("_savings_crisis_level")}')
    # Recent turns (with narrative context — LLM has no memory between calls)
    parts.append('最近:')
    for e in state.get('story_log', [])[-3:]:
        parts.append(f'  [{e.get("event_tag","")}] {e.get("player_action","")[:30]}')
        if e.get('narrative'):
            parts.append(f'  → {e["narrative"][:80]}')
    msg = '\n'.join(parts)

    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': msg},
    ]

    if player_action:
        if is_forced_rest:
            messages.append({'role': 'user', 'content': f'玩家精力耗尽，被迫去医院/躺了几天。花费了 {hospital_fee} 元。请叙述这次健康危机的场景（150-200字），并给出 2-3 个恢复后的新选择。必须包含 choices 数组。只输出纯JSON。'})
        else:
            messages.append({'role': 'user', 'content': f'玩家刚才的行动: {player_action}\n\n请叙述这个选择带来的后果，并给出接下来的 2-3 个新选择。记住：每个回合代表约1周的时间。只输出纯JSON，不要```json标记。'})
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
        opening_prompt += '每个回合代表约1周。只输出纯JSON，不要```json标记，不要任何额外文字。'
        messages.append({'role': 'user', 'content': opening_prompt})

    # 10: Project decision prompt
    phase_changed = state.pop('_project_phase_changed', '')
    if phase_changed:
        proj = state.get('current_project', {})
        parts.append(f'\n# 项目阶段变更: {phase_changed} — {proj.get("name","")}')
        parts.append('请在本回合选项中包含一个与项目推进相关的决策（如：选择设计风格、如何回应甲方反馈、是否加班赶工等）。')

    return messages

# ============================================================
# API Routes
# ============================================================
MOBILE_UA_KEYWORDS = [
    'Android', 'iPhone', 'iPad', 'iPod', 'webOS', 'BlackBerry', 'Windows Phone',
    'Mobile', 'mobile', 'Mobi', 'Opera Mini', 'IEMobile', 'Symbian',
]

def is_mobile_device():
    ua = request.headers.get('User-Agent', '')
    return any(kw in ua for kw in MOBILE_UA_KEYWORDS)

@app.route('/')
def index():
    view = request.args.get('view', '')
    if view == 'desktop':
        return send_from_directory('static', 'desktop.html')
    if view == 'mobile':
        return send_from_directory('static', 'mobile.html')
    if is_mobile_device():
        return send_from_directory('static', 'mobile.html')
    return send_from_directory('static', 'desktop.html')

@app.route('/api/focus', methods=['POST'])
def api_set_focus():
    state = load_state()
    if not state:
        return jsonify({'error': '没有存档'}), 404
    data = request.get_json(silent=True) or {}
    focus_type = data.get('type', '')
    if focus_type not in FOCUS_ATTRS:
        return jsonify({'error': '无效的重心类型'}), 400
    state['_focus'] = {'type': focus_type, 'turns_left': 5}
    save_state(state)
    return jsonify({'ok': True, 'focus': state['_focus']})

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
        attributes['表达能力'] = min(ATTR_CAP, attributes['表达能力'] + 2)
    if '人脉' in player['resources']:
        attributes['表达能力'] = min(ATTR_CAP, attributes['表达能力'] + 1)
        attributes['作品集厚度'] = min(ATTR_CAP, attributes['作品集厚度'] + 1)

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
        'attribute_xp': {k: level_to_xp_target(v) for k, v in attributes.items()},
        'start_date': '2010-01-01T00:00:00',
        'created_at': datetime.now().isoformat(),
    }
    # I3: Assign trait based on origin
    trait = ORIGIN_TRAITS.get(origin_key, ORIGIN_TRAITS['自定义'])
    state['trait'] = {'name': trait['name'], 'desc': trait['desc']}
    # I5: Set specialization if provided
    spec_id = data.get('specialization', '')
    if spec_id in SPECIALIZATIONS:
        spec = SPECIALIZATIONS[spec_id]
        state['specialization'] = spec
        # Apply specialization bonus
        bonus_attr = spec['bonus_attr']
        state['attributes'][bonus_attr] = min(ATTR_CAP, state['attributes'].get(bonus_attr, 5) + spec['bonus_amount'])
        state['attribute_xp'][bonus_attr] = level_to_xp_target(state['attributes'][bonus_attr])
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
    # XP: apply trends, derive attributes
    apply_trend_to_xp(state, result.get('attr_trend', {}))
    apply_focus_bonus(state)
    focus = state.get('_focus')
    if focus:
        focus['turns_left'] = max(0, focus.get('turns_left', 0) - 1)
        if focus['turns_left'] <= 0: state.pop('_focus', None)
    state['attributes'] = xp_to_attrs(state)

    state['story_log'].append({
        'turn': 1,
        'player_action': '开始游戏',
        'narrative': result['narrative'],
        'choices': result['choices'],
        'atmosphere': result.get('atmosphere', ''),
        'attr_display': dict(state['attributes']),
        'event_tag': result.get('event_tag', '游戏开始'),
    })
    state['turn_count'] = 1
    state['title'] = calculate_title(state['attributes'])
    state['unlocked_achievements'] = []
    # S1: Generate first milestone
    state['milestone'] = generate_milestone(state)
    new_ach, unlocked = check_achievements(state)
    state['unlocked_achievements'] = list(unlocked)
    with get_player_lock():
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
    # Reset NPC interaction tracking for new turn (memory, not persisted)
    get_npc_interactions().clear()
    # Collect NPC events from last turn for LLM context
    npc_context = flush_npc_event_log()
    chosen_effect = ''
    if choice_id and not action_text:
        last_entry = state['story_log'][-1] if state['story_log'] else None
        if last_entry and last_entry.get('choices'):
            for ch in last_entry['choices']:
                if ch['id'] == choice_id:
                    action_text = ch['text']
                    chosen_effect = ch.get('effects', [])
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

    # Apply origin trait mechanics
    # Stamina penalty (freelancer)
    if trait_def.get('stamina_penalty'):
        state['stamina'] = max(0, state.get('stamina', 80) - trait_def.get('stamina_penalty', 0))
    # Stamina discount (乙方执行)
    if trait_def.get('stamina_discount'):
        state['stamina'] = min(100, state.get('stamina', 80) + trait_def['stamina_discount'])

    applied_effects = apply_effect_xp(state, chosen_effect)

    # Apply train boost from trait
    if trait_def.get('train_boost') and applied_effects:
        boost = trait_def['train_boost']
        xp = state.get('attribute_xp', {})
        for attr in applied_effects:
            bonus = int(50 * (boost - 1.0))  # 20% boost = 10 extra XP per +1
            if bonus > 0:
                xp[attr] = xp.get(attr, 0) + bonus
        state['attribute_xp'] = xp

    # F-EXTRA: Forced rest when stamina depleted
    is_forced_rest = False
    hospital_fee = 0
    if state.get('stamina', 80) <= 0:
        state['stamina'] = min(100, state['stamina'] + 30)
        hospital_fee = min(state.get('savings', 0), random.randint(1000, 3000))
        state['savings'] = max(0, state.get('savings', 3000) - hospital_fee)
        action_text = f'精力耗尽，强制休息，就医花费 {hospital_fee} 元'
        is_forced_rest = True

    messages = build_messages(state, action_text, is_forced_rest, hospital_fee)

    # Inject NPC interaction context from last turn
    spotlight = tick_npc_spotlight()
    if npc_context or spotlight:
        npc_lines = []
        for n_name, n_act in npc_context:
            npc_lines.append(f'  · 本回合和{n_name}互动：{n_act}')
        if spotlight:
            npc_lines.append(f'  · 以下人物最近与你接触过，可能在生活中自然出现：')
            for s_name, s_turns in spotlight:
                npc_lines.append(f'    - {s_name}（已接触，剩余活跃{s_turns}回合）')
        if npc_lines:
            messages.append({'role': 'user', 'content': '[系统提示] 请在叙事中自然地融入以下信息。如果有机会，让最近接触过的人物在场景中自然地出现，不需要强行插入：\n' + '\n'.join(npc_lines)})

    # Run attribute checks and inject results
    last_narrative = state['story_log'][-1].get('narrative', '') if state['story_log'] else ''
    check_results = run_attribute_checks(state, last_narrative, state.get('story_log', []))
    if check_results:
        check_text = '\n\n[D M 属性检定结果 - 必须融入叙事]\n'
        for cr in check_results:
            check_text += f'  {cr["trigger"]}检定: {cr["attr"]}({cr["value"]}) + D10({cr["roll"]}) = {cr["total"]} vs 难度{cr["difficulty"]} → {"✅成功" if cr["success"] else "❌失败"}\n'
            check_text += f'  叙事方向: {cr["message"]}\n'
        messages.append({'role': 'user', 'content': check_text})

    # I5-A / 8: Inject spec event & year review
    if spec_event:
        messages.append({'role': 'user', 'content': f'【专精事件】{spec_event} 请融入叙事。'})
    if year_review:
        messages.append({'role': 'user', 'content': year_review})
    # 9: Focus
    focus = state.get('_focus')
    if focus:
        fc = FOCUS_ATTRS.get(focus.get('type', ''))
        if fc:
            messages.append({'role': 'user', 'content': f'【重心】{fc["hint"]}，剩{focus.get("turns_left",0)}周。'})

    result, error = call_llm(messages, cfg['api_base'], cfg['api_key'], cfg['model'])

    if error:
        result = validate_and_fix_result({}, state['turn_count'], state['attributes'])

    result = validate_and_fix_result(result, state['turn_count'], state['attributes'])
    if result.get('npc_updates'):
        state['npcs'] = apply_npc_updates(state['npcs'], result['npc_updates'])
    if result.get('company_update'):
        apply_company_update(state, result['company_update'])

    turn = state['turn_count'] + 1
    # XP: apply LLM trends, derive attributes
    apply_trend_to_xp(state, result.get('attr_trend', {}))
    apply_focus_bonus(state)
    focus = state.get('_focus')
    if focus:
        focus['turns_left'] = max(0, focus.get('turns_left', 0) - 1)
        if focus['turns_left'] <= 0: state.pop('_focus', None)
    state['attributes'] = xp_to_attrs(state)
    entry = {
        'turn': turn,
        'player_action': action_text,
        'narrative': result['narrative'],
        'choices': result['choices'],
        'atmosphere': result.get('atmosphere', ''),
        'attr_display': dict(state['attributes']),
        'event_tag': result.get('event_tag', '日常'),
    }
    state['story_log'].append(entry)
    state['stamina'] = max(0, min(100, state.get('stamina', 80) + result.get('stamina_change', -5)))
    state['savings'] = max(0, state.get('savings', 3000) + result.get('savings_change', 0))
    state['turn_count'] = turn

    # Decrement project cooldown
    cd = state.get('_project_cooldown', 0)
    if cd > 0:
        state['_project_cooldown'] = cd - 1

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

    # I5-A: Specialization event
    spec_event = check_spec_event(state)

    # 8: Year review
    year_review = check_year_review(state)

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
    # Store for NPC tab response indicator
    if npc_event:
        pid = get_session_id()
        if pid not in _npc_pending_events:
            _npc_pending_events[pid] = {}
        _npc_pending_events[pid][npc_event['npc_id']] = npc_event['text']
    # I7: Endings check
    ending = check_endings(state)
    # I8: Generate industry news (every 12 turns)
    generate_industry_news(state, cfg)
    # I6: Design trend
    trend = get_current_trend(state)

    lock = get_player_lock()
    with lock:
        state['_trend'] = trend
        state['_industry_news'] = get_cached_news(state)
        state['_npc_pending'] = _npc_pending_events.get(get_session_id(), {})
        save_state(state)
    # S2: Get stamina status for response
    stamina_status, status_debuff = get_stamina_status(state['stamina'])

    return jsonify({
        'ok': True,
        'entry': entry,
        'attributes': state['attributes'],
        'stamina': state['stamina'],
        'savings': state['savings'],
        'attribute_xp': state.get('attribute_xp', {}),
        'game_date': get_game_date(state),
        'player_age': int(state.get('player', {}).get('age', '24') or 24) + state['turn_count'] // 48,
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
        'turn': turn,
        'ending': ending,
        'trend': trend,
        'industry_news': get_cached_news(state),
        'npc_pending': _npc_pending_events.get(get_session_id(), {}),
    })

@app.route('/api/state', methods=['GET'])
def api_state():
    state = load_state()
    if state:
        state['trend'] = state.get('_trend')
        state['industry_news'] = state.get('_industry_news', [])
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
    lock = get_player_lock()
    with lock:
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

    # One interaction per NPC per turn (memory, not persisted)
    interacted = get_npc_interactions()
    if interacted.get(npc_id):
        return jsonify({'error': f'本回合已经和{npc["name"]}互动过了'}), 400

    role = npc.get('role', '职场关系')
    interactions = NPC_INTERACTIONS.get(role, NPC_INTERACTIONS['职场关系'])
    action = None

    # Handle special "respond to AI-initiated event" action
    if action_id == 'respond_event':
        pid = get_session_id()
        if pid in _npc_pending_events and npc_id in _npc_pending_events[pid]:
            event_text = _npc_pending_events[pid].pop(npc_id, '')
            action = {'id': 'respond_event', 'text': f'回应：{event_text[:20]}...', 'effect': '表达+1', 'stamina_cost': 2}
        else:
            return jsonify({'error': '没有待回应的消息'}), 400
    else:
        action = next((a for a in interactions if a['id'] == action_id), None)

    if not action:
        return jsonify({'error': '无效的互动'}), 400
    stamina = state.get('stamina', 80)
    cost = action['stamina_cost']
    if stamina < cost:
        return jsonify({'error': '精力不足'}), 400
    state['stamina'] = max(0, min(100, stamina - cost))

    # NPC interactions influence narrative, not direct stat changes
    # The LLM will incorporate the interaction outcome into future attr_trend

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

    # Mark interaction and record for next turn's LLM context
    interacted[npc_id] = True
    push_npc_event(npc['name'], action['text'])
    # Clear pending AI-initiated event for this NPC
    pid = get_session_id()
    if pid in _npc_pending_events:
        _npc_pending_events[pid].pop(npc_id, None)

    lock = get_player_lock()
    with lock:
        save_state(state)
    return jsonify({
        'ok': True,
        'result': f'与{npc["name"]}互动：{action["text"]}',
        'npc_name': npc['name'],
        'action_text': action['text'],
        'effect': action.get('effect', ''),
        'stamina': state['stamina'],
        'savings': state.get('savings', 0),
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

    # If NPC has a pending AI-initiated event, add a "回应" option first
    pid = get_session_id()
    pending = _npc_pending_events.get(pid, {})
    if npc_id in pending:
        event_text = pending[npc_id]
        options.append({
            'id': 'respond_event',
            'text': f'回应：{event_text[:20]}...',
            'effect': '表达+1',
            'stamina_cost': 2,
            'available': True,
            'is_response': True,
            'event_text': event_text,
        })

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
        # Check cooldown after previous project completion
        cooldown = state.get('_project_cooldown', 0)
        if cooldown > 0:
            proj_info = {'phase': '休息', 'name': '项目间歇', 'cooldown': cooldown}
            return jsonify({'project': proj_info, 'attrs': state.get('attributes', {}),
                'savings': state.get('savings', 0), 'stamina': state.get('stamina', 80)})
        # Auto-generate a project if none exists
        import random as _random
        spec = state.get('specialization', {})
        spec_id = spec.get('id', '')
        spec_types = SPEC_PROJECTS.get(spec_id, ['品牌VI升级', '产品发布会设计', '年度画册'])
        generic_types = ['品牌VI升级', '产品发布会设计', '年度画册', '空间导视系统', 'APP界面改版', '包装设计'] if not spec_id else ['产品发布会设计', '年度画册']
        import random as _random
        clients = ['森屿集团', '云帆科技', '墨白文化', '青禾品牌', '知味餐饮', '星辰互娱']
        # 60% chance to get a specialization project
        proj_types = [_random.choice(spec_types)] if _random.random() < 0.6 else generic_types
        types = proj_types
        base_budget = _random.choice([5000, 8000, 12000, 15000, 20000])
        adjusted_budget, trend_mod, trend = apply_trend_to_economy(state, base_budget)
        proj = {
            'name': f'{_random.choice(clients)}-{_random.choice(types)}',
            'client': _random.choice(clients),
            'budget': adjusted_budget,
            'base_budget': base_budget,
            'trend_mod': round(trend_mod, 2),
            'trend': trend['name'] if trend else '',
            'deadline_turns': _random.choice([5, 6, 7, 8]),
            'quality': max(10, state.get('attributes', {}).get('审美判断力', 5) * 10),
            'client_satisfaction': max(10, state.get('attributes', {}).get('表达能力', 5) * 10),
            'phase': '竞标',
            'start_turn': state.get('turn_count', 0)
        }
        state['current_project'] = proj
    lock = get_player_lock()
    with lock:
        state['_npc_pending'] = _npc_pending_events.get(get_session_id(), {})
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
@app.route('/api/industry_news', methods=['GET'])
def api_industry_news():
    state = load_state()
    if not state:
        return jsonify({'news': []})
    return jsonify({'news': get_cached_news(state)})

@app.route('/api/portfolio/generate', methods=['POST'])
def api_portfolio_generate():
    '''Return cached portfolio entries from state — no LLM call needed.'''
    state = load_state()
    if not state:
        return jsonify({'entries': []})
    return jsonify({'entries': state.get('portfolio', [])})

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
    if action_key in ('train', 'train_intensive'):
        if not action_attr:
            attrs = state.get('attributes', {})
            non_portfolio = {k: v for k, v in attrs.items() if k != '作品集厚度'}
            action_attr = min(non_portfolio, key=non_portfolio.get) if non_portfolio else '审美判断力'
        if action_attr in state.get('attributes', {}):
            boost = 1 if action_key == 'train' else 2
            xp = state.get('attribute_xp', {})
            xp[action_attr] = xp.get(action_attr, 0) + 50 * boost
            state['attribute_xp'] = xp
            state['attributes'] = xp_to_attrs(state)
            verb = '报班学习' if action_key == 'train' else '参加封闭集训，高强度学习'
            action_context = f'主动行动：{verb}{action_attr}，属性提升+{boost}。'
            result_msg = f'{action_attr} +{boost}'
    elif action_key == 'rest_short':
        state['stamina'] = min(100, state.get('stamina', 80) + 15)
        action_context = f'主动行动：周末休整，精力恢复+15。这个月节奏比较舒缓。'
        result_msg = '精力 +15'
    elif action_key == 'rest_long':
        state['stamina'] = min(100, state.get('stamina', 80) + 35)
        action_context = f'主动行动：请了一周假，深度休息，精力恢复+35。但项目进度可能受到了一些影响。'
        result_msg = '精力 +35'
    elif action_key == 'portfolio':
        xp = state.get('attribute_xp', {})
        xp['作品集厚度'] = xp.get('作品集厚度', 0) + 200
        state['attribute_xp'] = xp
        state['attributes'] = xp_to_attrs(state)
        action_context = f'主动行动：花了大量时间整理和打磨作品集。这段时间你的设计产出减少了，但作品质量在提升。'
        result_msg = '作品集厚度提升'
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
    # Apply trends + XP + cooldown (same as api_action)
    apply_trend_to_xp(state, result.get('attr_trend', {}))
    apply_focus_bonus(state)
    focus = state.get('_focus')
    if focus:
        focus['turns_left'] = max(0, focus.get('turns_left', 0) - 1)
        if focus['turns_left'] <= 0: state.pop('_focus', None)
    state['attributes'] = xp_to_attrs(state)
    # Decrement project cooldown
    cd = state.get('_project_cooldown', 0)
    if cd > 0:
        state['_project_cooldown'] = cd - 1

    # Run all post-turn systems (same as api_action)
    arc_msg = detect_and_start_arc(state)
    challenge = check_career_challenge(state)
    economy_event = process_economy(state)
    crisis_event = check_savings_crisis(state)
    project_phase_hint = advance_project_phase(state)
    prev_stamina = state.get('_prev_stamina', state.get('stamina', 80))
    state['title'] = calculate_title(state['attributes'])
    new_ach, unlocked = check_achievements(state, prev_stamina)
    state['unlocked_achievements'] = list(unlocked)
    state['_prev_stamina'] = state['stamina']
    milestone_done, milestone_reward = check_milestone(state)
    npc_event = generate_npc_event(state)
    if npc_event:
        pid = get_session_id()
        if pid not in _npc_pending_events:
            _npc_pending_events[pid] = {}
        _npc_pending_events[pid][npc_event['npc_id']] = npc_event['text']
    stamina_status, status_debuff = get_stamina_status(state['stamina'])
    # I7: Endings check (active_action)

    lock = get_player_lock()
    with lock:
        save_state(state)
    return jsonify({
        'ok': True,
        'action': action_key,
        'result': result_msg,
        'entry': entry,
        'attributes': state['attributes'],
        'stamina': state['stamina'],
        'savings': state['savings'],
        'attribute_xp': state.get('attribute_xp', {}),
        'game_date': get_game_date(state),
        'player_age': int(state.get('player', {}).get('age', '24') or 24) + state['turn_count'] // 48,
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
        'turn': turn,
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
    lock = get_player_lock()
    with lock:
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

@app.route('/api/ending/resolve', methods=['POST'])
def api_ending_resolve():
    state = load_state()
    if not state:
        return jsonify({'error': '没有存档'}), 404
    data = request.get_json(silent=True) or {}
    ending = check_endings(state)
    if ending:
        state['ending_result'] = ending
        state['phase'] = 'ended'
        save_state(state)
        return jsonify({'ok': True, 'ending': ending})
    return jsonify({'error': '未触发结局'}), 400

FEEDBACK_FILE = os.path.join(BASE_DIR, 'player_feedback.jsonl')

@app.route('/api/feedback', methods=['POST'])
def api_feedback():
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': '反馈内容不能为空'}), 400
    entry = {
        'time': datetime.now().isoformat(),
        'turn': data.get('turn', 0),
        'player': data.get('player', ''),
        'text': text,
    }
    with open(FEEDBACK_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return jsonify({'ok': True})

if __name__ == '__main__':
    print('=' * 50)
    print('  平面设计师模拟器 - http://localhost:8765')
    print('=' * 50)
    app.run(host='0.0.0.0', port=8765, debug=False, use_reloader=False, threaded=True)
