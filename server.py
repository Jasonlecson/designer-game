#!/usr/bin/env python
# -*- coding: utf-8 -*-
'平面设计师职业生涯模拟器 - 游戏服务器 v2'

import json, os, random, traceback
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='static', static_url_path='')

BASE_DIR = os.path.dirname(__file__)
STATE_FILE = os.path.join(BASE_DIR, 'game_state.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# ============================================================
# Config
# ============================================================
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'api_base': 'https://api.openai.com/v1', 'api_key': '', 'model': 'gpt-4o-mini'}

def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ============================================================
# System Prompt
# ============================================================
SYSTEM_PROMPT = '''# 你是平面设计师模拟器的 Game Master (DM)

## 你的身份
你是本游戏的 DM，负责剧情推进、NPC 扮演、事件生成、职业属性结算。

## 核心基调
- 写实向职业生涯模拟，非爽文，非恋爱向。
- 女主不是天才，成长必须有代价、犹豫、自我怀疑。
- 没有天降贵人。所有人脉、机会、信任都必须通过作品、判断力和职业信誉去挣。
- 叙事信息有限性：只描述第一视角所见所闻，不透露 NPC 隐藏意图。
- 没有恋爱线。NPC 限于：同事、导师、竞争对手、甲方、合作者、行业前辈。

## 核心属性（1-10分）
审美判断力 — 视觉品味、风格把控、设计决策
执行能力   — 落地速度、改稿效率、抗压韧性
商业思维   — 定价谈判、理解客户需求、市场嗅觉
表达能力   — 提案说服、建立人脉、行业声誉
创意深度   — 概念思考、原创性、独立判断
作品集厚度 — 综合产出指标，积累优质作品

## 资源系统
精力值：0-100，每次行动消耗 5-15（加班消耗大，休息可恢复）
月收入：数字，随雇主/职级变化，不够时产生生存压力
当精力<20 时女主表现出疲劳、效率下降、易出错
当月收入不足以支撑生活时产生焦虑叙事

## 选项后果系统（CRITICAL）
每个选项必须标注「短期后果」和「属性影响」，让玩家知道选择在改变什么：

短期后果：本回合的直接结果（≤12字），如「甲方同意了方案」「熬夜赶工到凌晨」
属性影响：格式 "属性名±数字"，如 "审美+1 执行-2"
- 每回合的属性总变化幅度控制在 -3 ~ +3 之间
- 不要所有选项都纯正面——好的东西需要代价

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
  "income_change": 0,
  "event_tag": "项目推进 / 行业事件 / 日常 / 转折点 / 倦怠预警",
  "npc_updates": [
    {"name": "陈知夏", "relation": "新的关系描述", "desc": "新的简介"}
  ],
  "company_update": {"name": "XX设计工作室", "position": "初级设计师", "action": "入职"}
}

## stamina_change / income_change 规则
- stamina_change: 本轮精力的变化量（正=休息恢复，负=消耗），范围 -15 ~ +20
- income_change: 月收入的增减（正=加薪/奖金，负=降薪/罚款），单位：元/月
- 加班、改稿、提案通常消耗精力；休息、度假、完成项目获得恢复
- 升职、跳槽成功带来收入增加；被裁、降薪带来收入减少

## choice.effect 规则
- effect 格式："属性简称±数字 属性简称±数字"，空格分隔
- 属性简称映射：审美=审美判断力 执行=执行能力 商业=商业思维 表达=表达能力 创意=创意深度 作品=作品集厚度 精力=精力值 收入=月收入
- 必须至少包含一个属性变化
- 示例: "审美+1" / "执行-2 精力-10" / "商业+1 表达+1 精力-5"

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
        if content.startswith('```'):
            lines = content.split('\n')
            content = '\n'.join(lines[1:])
            if content.rstrip().endswith('```'):
                content = content.rstrip()[:-3]
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
        {'id': 'B', 'text': '主动寻求新机会', 'hint': '冒险但可能突破', 'effect': '商业+1 精力-8'},
        {'id': 'C', 'text': '停下来复盘和思考', 'hint': '恢复和规划', 'effect': '创意+1 精力+15'},
    ]
    if turn_count % 7 == 0:
        return [
            {'id': 'A', 'text': '抓住这个转折机会', 'hint': '职业跃升', 'effect': '表达+1 商业+1 精力-10'},
            {'id': 'B', 'text': '谨慎观望再做决定', 'hint': '保守安全', 'effect': '执行+2'},
            {'id': 'C', 'text': '和信任的人商量一下', 'hint': '借助他人视角', 'effect': '表达+2'},
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
    # Stamina & income
    if 'stamina_change' not in result:
        result['stamina_change'] = -5
    if 'income_change' not in result:
        result['income_change'] = 0
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
        f'  月收入: {state.get("income",5000)}元',
        '',
        '# 属性',
    ]
    for k, v in attrs.items():
        bar = '\u2587' * v + '\u2581' * (10 - v)
        parts.append(f'  {k}: {bar} ({v}/10)')

    parts.append('')
    parts.append('# NPC（含当前关系）')
    for n in npcs[:6]:
        parts.append(f'  {n["name"]} - {n["role"]} | 关系: {n.get("relation","待展开")} | {n.get("desc","")}')

    if state.get('current_project'):
        cp = state['current_project']
        parts.append(f'\n# 当前项目: {cp.get("name","无")} ({cp.get("phase","进行中")})')

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
        messages.append({'role': 'user', 'content': f'玩家刚才的行动: {player_action}\n\n请叙述这个选择带来的后果，并给出接下来的 2-3 个新选择。记住：必须包含 choices 数组。只输出JSON。'})
    else:
        messages.append({'role': 'user', 'content': '请生成游戏开场剧情，女主刚踏入设计行业。记住：必须包含 choices 数组。只输出JSON。'})

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
        '应届生': {'审美判断力': 6, '执行能力': 4, '商业思维': 2, '表达能力': 4, '创意深度': 6, '作品集厚度': 1},
        '乙方执行': {'审美判断力': 5, '执行能力': 7, '商业思维': 4, '表达能力': 5, '创意深度': 3, '作品集厚度': 4},
        '甲方品牌': {'审美判断力': 4, '执行能力': 5, '商业思维': 7, '表达能力': 6, '创意深度': 3, '作品集厚度': 3},
        '媒体编辑': {'审美判断力': 7, '执行能力': 3, '商业思维': 5, '表达能力': 8, '创意深度': 5, '作品集厚度': 1},
        '自由职业': {'审美判断力': 5, '执行能力': 6, '商业思维': 3, '表达能力': 5, '创意深度': 6, '作品集厚度': 2},
        '印刷厂':   {'审美判断力': 4, '执行能力': 8, '商业思维': 3, '表达能力': 4, '创意深度': 2, '作品集厚度': 0},
        '自定义':   {'审美判断力': 5, '执行能力': 5, '商业思维': 5, '表达能力': 5, '创意深度': 5, '作品集厚度': 0},
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

    state = {
        'phase': 'playing',
        'player': player,
        'attributes': attributes,
        'npcs': npcs,
        'story_log': [],
        'current_project': None,
        'turn_count': 0,
        'stamina': 80,
        'income': 5000,
        'created_at': datetime.now().isoformat(),
    }

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
    check_achievements(state)
    save_state(state)
    return jsonify({'ok': True, 'state': state})

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

    if choice_id and not action_text:
        last_entry = state['story_log'][-1] if state['story_log'] else None
        if last_entry and last_entry.get('choices'):
            for ch in last_entry['choices']:
                if ch['id'] == choice_id:
                    action_text = ch['text']
                    break
    if not action_text:
        action_text = '玩家做出了选择'

    messages = build_messages(state, action_text)
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
    state['attributes'] = result['attr_display']
    state['stamina'] = max(0, min(100, state.get('stamina', 80) + result.get('stamina_change', -5)))
    state['income'] = max(0, state.get('income', 5000) + result.get('income_change', 0))
    state['turn_count'] = turn

    # Title & achievements
    prev_stamina = state.get('_prev_stamina', state.get('stamina', 80))
    state['title'] = calculate_title(state['attributes'])
    new_ach, unlocked = check_achievements(state, prev_stamina)
    state['unlocked_achievements'] = list(unlocked)
    state['_prev_stamina'] = state['stamina']

    save_state(state)
    return jsonify({
        'ok': True,
        'entry': entry,
        'attributes': state['attributes'],
        'stamina': state['stamina'],
        'income': state['income'],
        'title': state['title'],
        'new_achievements': [a for a in ACHIEVEMENTS if a['id'] in new_ach],
        'turn': turn
    })

@app.route('/api/state', methods=['GET'])
def api_state():
    state = load_state()
    return jsonify({'state': state})

@app.route('/api/reset', methods=['POST'])
def api_reset():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    return jsonify({'ok': True})

if __name__ == '__main__':
    print('=' * 50)
    print('  平面设计师模拟器 - http://localhost:8765')
    print('=' * 50)
    app.run(host='0.0.0.0', port=8765, debug=False, use_reloader=False)
