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

## 职业属性（1-10分）
审美判断力、执行力、商业理解力、表达与说服力、行业信用、自主判断力、作品集厚度、抗压阈值

## 输出格式（严格JSON，只输出JSON，不要任何额外文字）
{
  "narrative": "用第二人称「你」叙述本回合剧情，150-300字，生动具体",
  "choices": [
    {"id": "A", "text": "选项A（≤20字）", "hint": "后果提示（≤15字）"},
    {"id": "B", "text": "选项B（≤20字）", "hint": "后果提示（≤15字）"},
    {"id": "C", "text": "选项C（≤20字）", "hint": "后果提示（≤15字）"}
  ],
  "atmosphere": "场景氛围（≤10字）",
  "attr_display": {"审美判断力": 7, "执行力": 6, "商业理解力": 5, "表达与说服力": 6, "行业信用": 5, "自主判断力": 4, "作品集厚度": 3, "抗压阈值": 7},
  "event_tag": "项目推进 / 行业事件 / 日常 / 转折点 / 倦怠预警",
  "npc_updates": [
    {"name": "陈知夏", "relation": "新的关系描述", "desc": "新的简介"},
    {"name": "林墨", "relation": "竞争加剧"}
  ]
}

## npc_updates 规则
- npc_updates 是可选的，如果没有 NPC 参与本回合剧情可以为空数组 []
- 仅在剧情中确实出现了该 NPC 时才更新其 relation 和/或 desc
- name 必须与给定 NPC 列表中的名字完全一致
- relation 用简短中文描述当前关系状态，如「建立了信任」「首次合作」「产生矛盾」「渐行渐远」
- desc 可更新该 NPC 的简介，反映你对 ta 的新认知
- 不需要更新所有 NPC，只更新本回合剧情涉及到的

CRITICAL: choices 数组必须始终包含 2-3 个有意义的选项，分别代表不同的行动方向。绝对不能返回空数组。如果当前场景是结局时刻，可以在 narrative 中描述结局，但 choices 仍应至少包含 2 个选项（如「开始新篇章」「回顾这段旅程」等）。'''

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
        {'id': 'A', 'text': '继续当前的工作节奏', 'hint': '稳扎稳打'},
        {'id': 'B', 'text': '主动寻求新机会', 'hint': '冒险但可能突破'},
        {'id': 'C', 'text': '停下来复盘和思考', 'hint': '恢复和规划'},
    ]
    if turn_count % 7 == 0:
        return [
            {'id': 'A', 'text': '抓住这个转折机会', 'hint': '职业跃升的可能'},
            {'id': 'B', 'text': '谨慎观望再做决定', 'hint': '保守但安全'},
            {'id': 'C', 'text': '和信任的人商量一下', 'hint': '借助他人视角'},
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
            result['choices'][i] = {'id': chr(65+i), 'text': f'继续推进', 'hint': '下一步'}
        if 'id' not in ch:
            ch['id'] = chr(65+i)
        if 'text' not in ch:
            ch['text'] = '继续推进'
        if 'hint' not in ch:
            ch['hint'] = ''
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
    # Ensure all 8 attributes are present
    for key in ['审美判断力', '执行力', '商业理解力', '表达与说服力', '行业信用', '自主判断力', '作品集厚度', '抗压阈值']:
        if key not in result['attr_display']:
            result['attr_display'][key] = attrs.get(key, 5)
        result['attr_display'][key] = max(1, min(10, int(result['attr_display'][key])))
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

# ============================================================
# Build Messages
# ============================================================
def build_messages(state, player_action=None):
    player = state.get('player', {})
    attrs = state.get('attributes', {})
    npcs = state.get('npcs', [])
    story_len = len(state.get('story_log', []))

    parts = [
        '# 游戏状态',
        f'女主: {player.get("name","?")}, {player.get("age","?")}岁, {player.get("city","上海")}',
        f'职业: {player.get("origin","?")} → 目标: {player.get("goal","?")}',
        f'资源: {player.get("resources","?")}, 节奏: {player.get("pace","标准")}',
        f'当前回合: 第{story_len+1}回合',
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
        '应届生': {'审美判断力': 6, '执行力': 3, '商业理解力': 2, '表达与说服力': 4, '行业信用': 2, '自主判断力': 5, '作品集厚度': 1, '抗压阈值': 6},
        '乙方执行': {'审美判断力': 5, '执行力': 7, '商业理解力': 4, '表达与说服力': 5, '行业信用': 5, '自主判断力': 3, '作品集厚度': 4, '抗压阈值': 7},
        '甲方品牌': {'审美判断力': 4, '执行力': 5, '商业理解力': 7, '表达与说服力': 6, '行业信用': 5, '自主判断力': 3, '作品集厚度': 3, '抗压阈值': 5},
        '媒体编辑': {'审美判断力': 7, '执行力': 3, '商业理解力': 5, '表达与说服力': 8, '行业信用': 4, '自主判断力': 6, '作品集厚度': 1, '抗压阈值': 5},
        '自由职业': {'审美判断力': 5, '执行力': 6, '商业理解力': 3, '表达与说服力': 5, '行业信用': 3, '自主判断力': 7, '作品集厚度': 2, '抗压阈值': 4},
        '印刷厂': {'审美判断力': 4, '执行力': 8, '商业理解力': 3, '表达与说服力': 4, '行业信用': 4, '自主判断力': 4, '作品集厚度': 0, '抗压阈值': 6},
        '自定义': {'审美判断力': 5, '执行力': 5, '商业理解力': 5, '表达与说服力': 5, '行业信用': 5, '自主判断力': 5, '作品集厚度': 0, '抗压阈值': 5},
    }

    origin_key = '应届生' if '应届' in player['origin'] else \
                 '乙方执行' if '乙方' in player['origin'] else \
                 '甲方品牌' if '甲方' in player['origin'] else \
                 '媒体编辑' if '媒体' in player['origin'] else \
                 '自由职业' if '自由' in player['origin'] else \
                 '印刷厂' if '印刷' in player['origin'] else '自定义'

    attributes = attr_base.get(origin_key, attr_base['自定义']).copy()
    if '引路人' in player['resources']:
        attributes['行业信用'] = min(10, attributes['行业信用'] + 2)
    if '人脉' in player['resources']:
        attributes['行业信用'] = min(10, attributes['行业信用'] + 1)
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
    state['turn_count'] = turn

    # Ending check (minimum 5 rounds before BE can trigger, 15 rounds for HE)
    attrs = state['attributes']
    ending = None
    if state['turn_count'] >= 5 and attrs.get('行业信用', 5) <= 1:
        ending = {'type': 'be_eliminated', 'text': '行业淘汰——你的行业信用已经跌至冰点。没有人愿意把项目交给你了。'}
    elif state['turn_count'] >= 5 and attrs.get('抗压阈值', 5) <= 1:
        ending = {'type': 'be_burnout', 'text': '创作枯竭——你还有能力，但已经没有了继续下去的心力。'}
    elif attrs.get('作品集厚度', 0) >= 9 and attrs.get('行业信用', 0) >= 8 and state['turn_count'] >= 15:
        ending = {'type': 'he_breakthrough', 'text': '顶级突破——你的作品集和行业信用都已达到最高水准，你终于站在了你想站的地方。'}

    if ending:
        state['phase'] = 'ended'
        state['ending'] = ending

    save_state(state)
    return jsonify({
        'ok': True,
        'entry': entry,
        'attributes': state['attributes'],
        'ending': state.get('ending'),
        'phase': state['phase'],
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
