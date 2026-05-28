// ============================================================
// shared.js — 前后端通信 & 通用逻辑
// 由 mobile.html 和 desktop.html 共同引用
// ============================================================

// ========== API Layer ==========
const API = {
  async fetch(url, opts = {}) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 120000);
    try {
      const r = await fetch(url, { ...opts, signal: ctrl.signal });
      clearTimeout(t);
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      return d;
    } catch (e) {
      clearTimeout(t);
      throw e;
    }
  },

  newGame(data)    { return this.fetch('/api/new_game', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) }); },
  getState()       { return this.fetch('/api/state'); },
  doAction(choiceId){ return this.fetch('/api/action', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({choice_id:choiceId}) }); },
  activeAction(action, attr) { return this.fetch('/api/active_action', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action, attr}) }); },
  getNPCs(npcId)   { return this.fetch('/api/npc/options', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({npc_id:npcId}) }); },
  doNPC(npcId, actionId) { return this.fetch('/api/npc/interact', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({npc_id:npcId, action_id:actionId}) }); },
  getProject()     { return this.fetch('/api/project'); },
  getIndustryNews() { return this.fetch('/api/industry_news'); },
  resolveEnding(endingId) { return this.fetch('/api/ending/resolve', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ending_id:endingId}) }); },
  sendFeedback(text, turn, player) { return this.fetch('/api/feedback', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text, turn, player}) }); },
  getAchievements(){ return this.fetch('/api/achievements'); },
  genPortfolio()   { return this.fetch('/api/portfolio/generate', { method:'POST', headers:{'Content-Type':'application/json'} }); },
  reset()          { return this.fetch('/api/reset', { method:'POST' }); },
  export()         { window.open('/api/export', '_blank'); },
  importState(state){ return this.fetch('/api/import', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({state}) }); },
  getSaves()       { return this.fetch('/api/saves'); },
  saveSlot(slot)   { return this.fetch('/api/saves/save', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({slot}) }); },
  loadSlot(slot)   { return this.fetch('/api/saves/load', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({slot}) }); },
  deleteSlot(slot) { return this.fetch('/api/saves/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({slot}) }); },
};

// ========== Constants ==========
const ATTR_NAMES = ['审美判断力', '执行能力', '商业思维', '表达能力', '创意深度', '作品集厚度'];
const ATTR_ICONS = { '审美判断力': '🎨', '执行能力': '🔧', '商业思维': '💼', '表达能力': '🗣', '创意深度': '💡', '作品集厚度': '📦' };

const ORIGINS = [
  {id:'A',title:'设计专业应届生',desc:'刚走出校园，理论扎实但缺乏实战经验。作品集里大多是课程作业。',good:'审美悟性好',warn:'执行经验不足'},
  {id:'B',title:'乙方设计公司执行设计师',desc:'经历过高强度执行磨练，改稿效率一流。但审美可能被甲方磨平了。',good:'执行力强',warn:'创意空间受限'},
  {id:'C',title:'甲方品牌部设计师',desc:'在品牌部内部，懂商业逻辑和汇报。但设计语言可能已经公式化了。',good:'商业思维清晰',warn:'设计自由度低'},
  {id:'D',title:'设计媒体编辑/自媒体运营',desc:'见多识广，能写会说。但手上功夫可能不如执行设计师扎实。',good:'表达能力强',warn:'执行深度不够'},
  {id:'E',title:'自由职业/兼职设计师',desc:'灵活自由但收入不稳定。什么都得自己来，包括催款和谈价格。',good:'综合能力均衡',warn:'收入和稳定性差'},
  {id:'F',title:'印刷厂/材料商对接人',desc:'从下游切入，了解生产和物料。但"设计师"的名分都要从头争取。',good:'懂生产工艺',warn:'设计认知需提升'},
  {id:'G',title:'自定义',desc:'你心中已有答案。请描述你自己的身份。',good:'自由定义',warn:''},
];

const RESOURCES = [
  {id:'A',title:'零资源白手起家',desc:'没有背景，没有人脉，只有一台电脑和一份决心。'},
  {id:'B',title:'有行业引路人',desc:'有一位前辈在关键时刻给你指过路。'},
  {id:'C',title:'有基础人脉网络',desc:'通过同学和实习已经积累了一些行业联系人。'},
  {id:'D',title:'背负关系债',desc:'欠过人情，开局就要还。但这份关系也可能带来机会。'},
];

const GOALS = [
  {id:'A',title:'成为顶级独立设计师',desc:'靠作品说话，不被甲方和公司束缚。'},
  {id:'B',title:'做到创意总监/合伙人',desc:'在公司体系内爬到最高处。'},
  {id:'C',title:'创立自己的设计品牌',desc:'用设计语言表达自己对世界的理解。'},
  {id:'D',title:'成为行业话语权拥有者',desc:'不只是做设计，更是定义设计。'},
  {id:'E',title:'活着就好',desc:'在这个行业里体面地活下去，就是最大的胜利。'},
];

const PACES = [
  {id:'A',title:'标准节奏',desc:'不急不缓，跟着行业潮流行走。'},
  {id:'B',title:'加速冲刺',desc:'愿意付出更多时间精力换取更快成长。'},
  {id:'C',title:'慢生活',desc:'设计是工作，不是全部。保持工作与生活的平衡。'},
];

const SPECIALIZATIONS = [
  {id:'brand',name:'品牌设计',icon:'🏷',desc:'企业VI、包装、品牌全案',attr:'商业思维'},
  {id:'ui_ux',name:'UI/UX 设计',icon:'📱',desc:'界面设计、交互逻辑、产品体验',attr:'执行能力'},
  {id:'illustration',name:'商业插画',icon:'🖌',desc:'商业插画、角色设计、视觉表达',attr:'创意深度'},
  {id:'motion',name:'动态设计',icon:'🎬',desc:'动画短片、动态品牌、视效制作',attr:'审美判断力'},
  {id:'print',name:'印刷与物料',icon:'📄',desc:'书籍装帧、印刷工艺、空间导视',attr:'作品集厚度'},
];

const STEP_LABELS = ['基本信息', '出身选择', '开局资源', '职业目标', '节奏偏好', '专精方向'];

const ACTIVE_ACTIONS_LIST = [
  {key:'rest_short',name:'☕ 周末休整',desc:'+15精力',disabled:function(st){return st.stamina>=95;}},
  {key:'rest_long',name:'🏖️ 请假休假',desc:'+35精力 -1k',disabled:function(st){return st.stamina>=80||(st.savings||0)<1000;}},
  {key:'portfolio',name:'🎨 整理作品集',desc:'作品+1 -5精力',disabled:function(st){return(st.attributes['作品集厚度']||0)>=10;}},
  {key:'train',name:'📚 报班学习',desc:'选属性+1 -3k',disabled:function(st){return(st.savings||0)<3000;}},
  {key:'train_intensive',name:'🎓 封闭集训',desc:'属性+2 -8k -20精力',disabled:function(st){return(st.savings||0)<8000||st.stamina<30;}},
  {key:'jobhunt_targeted',name:'🎯 精准投递',desc:'-15精力 投3家公司',disabled:function(st){return st.stamina<20;}},
  {key:'networking',name:'🤝 社交拓展',desc:'-1.5k -8精力',disabled:function(st){return(st.savings||0)<1500||st.stamina<15;}},
];

const TAG_COLORS = {
  '项目推进': {bg:'#edf5ee',color:'#6b8f71'},
  '行业事件': {bg:'#e8f0fe',color:'#7b8fa1'},
  '转折点':   {bg:'#fdf8e8',color:'#c4a43e'},
  '倦怠预警': {bg:'#fdf0ed',color:'#b55b4a'},
  '日常':     {bg:'#fdf5e6',color:'#b8862d'},
};

const AVATAR_COLORS = ['#d4846a','#6b8f71','#7b8fa1','#c4a43e','#8e6b9e','#c4755e'];

// ========== Game State ==========
let gameState = null;
let isProcessing = false;
let _prevTitle = '';

function updateGameState(d) {
  if (d.state) gameState = d.state;
  if (d.entry) gameState.story_log.push(d.entry);
  if (d.attributes) gameState.attributes = d.attributes;
  if (d.stamina !== undefined) gameState.stamina = d.stamina;
  if (d.savings !== undefined) gameState.savings = d.savings;
  if (d.game_date) gameState.game_date = d.game_date;
  if (d.player_age !== undefined) gameState.player_age = d.player_age;
  if (d.title) gameState.title = d.title;
  if (d.npcs) gameState.npcs = d.npcs;
  if (d.company) gameState.company = d.company;
  if (d.career_history) gameState.career_history = d.career_history;
  if (d.unlocked_achievements) gameState.unlocked_achievements = d.unlocked_achievements;
  if (d.milestone) gameState.milestone = d.milestone;
  if (d.trait) gameState.trait = d.trait;
  if (d.stamina_status) gameState.stamina_status = d.stamina_status;
  if (d.status_debuff) gameState.status_debuff = d.status_debuff;
  if (d.trait) gameState.trait = d.trait;
  if (d.turn) gameState.turn_count = d.turn;
  if (d.npc_pending) gameState._npc_pending = d.npc_pending;
}

// ========== Utilities ==========
function xpToLevel(xp) { return Math.floor(Math.sqrt(Math.max(0, xp) / 20)); }
function xpProgress(xp) {
  if (!xp || xp <= 0) return 0;
  const lvl = xpToLevel(xp);
  const xpAtLvl = lvl * lvl * 20;
  const xpNext = (lvl + 1) * (lvl + 1) * 20;
  return Math.min(100, Math.max(0, ((xp - xpAtLvl) / (xpNext - xpAtLvl)) * 100));
}
function esc(s) {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function formatNarrative(text) {
  if (!text) return '';
  return text.split('\n').filter(l => l.trim()).map(l => `<p>${esc(l)}</p>`).join('');
}

function attrClass(v) {
  return v >= 7 ? 'high' : v >= 4 ? 'mid' : 'low';
}

function attrColor(v) {
  return v >= 7 ? '#6b8f71' : v >= 4 ? '#d4a853' : '#d4846a';
}

function getStaminaClass(status) {
  const map = { '精力充沛':'vigorous','正常':'normal','疲劳':'fatigued','严重疲劳':'exhausted','透支':'critical','濒临崩塌':'critical' };
  return map[status] || 'normal';
}

function formatDate(turnCount) {
  if (!gameState || !gameState.start_date) return `第 ${turnCount} 回合`;
  try {
    const start = new Date(gameState.start_date);
    const d = new Date(start.getTime() + turnCount * 7 * 86400000);
    return `${d.getFullYear()}年${d.getMonth()+1}月 · 第${turnCount}周`;
  } catch(e) { return `第 ${turnCount} 回合`; }
}

function getMonthlySalary() {
  const titles = {
    '见习设计师':3500,'初级设计师':5000,'中级设计师':8000,
    '高级设计师':12000,'资深设计师':18000,'设计总监':25000,
    '创意合伙人':35000,'独立设计大师':50000
  };
  const t = (gameState && gameState.title && gameState.title.title) || '见习设计师';
  return titles[t] || 4000;
}

function getCurrentAge() {
  return gameState?.player_age ?? 24;
}

function formatEffectText(effects) {
  if (!effects || !effects.length) return '';
  if (typeof effects === 'string') return effects;
  return effects.map(e => e.text || '').filter(Boolean).join(' ');
}

function formatEffectSummary(effects) {
  if (!effects || !effects.length) return null;
  if (typeof effects === 'string') return {positive:[], negative:[]};
  const pos = effects.filter(e => e.delta > 0).map(e => ({name: e.attr, delta: e.delta}));
  const neg = effects.filter(e => e.delta < 0 && e.attr !== 'stamina' && e.attr !== 'savings').map(e => ({name: e.attr, delta: e.delta}));
  return {positive:pos, negative:neg};
}

// ========== Notifications ==========
function showNotification(type, message) {
  const banner = document.createElement('div');
  const icons = { achievement:'🏅',promotion:'⬆️',milestone:'🎯',expense:'💸',npc:'📨' };
  banner.className = 'notif notif-' + type;
  banner.innerHTML = `<span class="notif-icon">${icons[type]||'📢'}</span><span class="notif-text">${message}</span>`;
  document.body.appendChild(banner);

  const gap = 6;
  const existing = document.querySelectorAll('.notif');
  if (window.innerWidth <= 860) {
    let bottomOffset = 80;
    existing.forEach(n => { bottomOffset += (n.offsetHeight||40)+gap; });
    banner.style.bottom = bottomOffset + 'px';
    banner.style.top = 'auto';
  } else {
    const idx = existing.length - 1;
    banner.style.top = (16 + idx * ((banner.offsetHeight||40) + gap)) + 'px';
  }
  setTimeout(() => {
    banner.style.animation = 'notifOut 0.3s ease forwards';
    setTimeout(() => { banner.remove(); restackNotifs(); }, 300);
  }, 2500);
}

function restackNotifs() {
  const remaining = document.querySelectorAll('.notif');
  const gap = 6;
  if (window.innerWidth <= 860) {
    let bottomOffset = 80;
    remaining.forEach(n => {
      n.style.bottom = bottomOffset + 'px';
      n.style.top = 'auto';
      n.style.transition = 'bottom 0.2s ease';
      bottomOffset += (n.offsetHeight||40)+gap;
    });
  } else {
    remaining.forEach((n,i) => {
      n.style.top = (16 + i * ((n.offsetHeight||40)+gap)) + 'px';
      n.style.transition = 'top 0.2s ease';
    });
  }
}

// ========== Process action/active_action response ==========
function processActionResponse(d) {
  updateGameState(d);
  if (d.new_achievements && d.new_achievements.length > 0) {
    d.new_achievements.forEach(a => showNotification('achievement', `${a.icon} ${a.name} — ${a.desc}`));
  }
  if (d.title && d.title.title !== _prevTitle) {
    showNotification('promotion', `晋升为${d.title.title}！`);
  }
  if (d.milestone_done) {
    showNotification('milestone', d.milestone_reward ? `目标达成！奖励：${d.milestone_reward}` : '阶段目标已过期');
  }
  if (d.economy_event) {
    const ev = d.economy_event;
    showNotification('expense', ev.salary > 0
      ? `月结：工资+${ev.salary}元 开销-${ev.expense}元 净${ev.net>=0?'+':''}${ev.net}元`
      : `月结：暂无固定收入 开销-${ev.expense}元`);
  }
  if (d.npc_event) showNotification('npc', `${d.npc_event.npc_name}：${d.npc_event.text}`);
  if (d.crisis_event) showNotification('expense', '⚠️ ' + d.crisis_event.message);
  if (d.arc_msg) showNotification('npc', '📖 ' + d.arc_msg);
  if (d.challenge) showNotification('milestone', '🔥 ' + d.challenge.name + '：' + d.challenge.message);
  if (d.project_phase_hint) showNotification('milestone', '📋 项目进入「' + d.project_phase_hint + '」阶段');
  if (d.result) showNotification('npc', '⚡ ' + d.result);
  if (d.ending) {
    // Store ending for next render cycle
    window._pendingEnding = d.ending;
  }
  _prevTitle = (d.title && d.title.title) || _prevTitle;
}

// ========== Achievements Cache ==========
let _achievementsCache = null;
async function fetchAchievements() {
  if (_achievementsCache) return _achievementsCache;
  try {
    const d = await API.getAchievements();
    _achievementsCache = (d.achievements || []).map(({unlocked, ...rest}) => rest);
  } catch(e) { _achievementsCache = []; }
  return _achievementsCache;
}
