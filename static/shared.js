// ============================================================
// shared.js — 前后端通信 & 全部业务逻辑
// 由 mobile.html 和 desktop.html 共同引用
// 每个 HTML 文件只需提供：renderAll() / renderTab() / 渲染函数 / CSS / HTML
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

// ========== Global State ==========
let gameState = null;
let isProcessing = false;
let _prevTitle = '';
let currentScreen = 'cover';
let currentTab = 'dashboard';
let selections = {origin:'',resources:'',goal:'',pace:''};
let createStep = 0;
let currentPlayer = {name:'林知夏',age:'24',city:'上海',custom_origin:'',specialization:''};

// ========== State Update ==========
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
function attrClass(v) { return v >= 7 ? 'high' : v >= 4 ? 'mid' : 'low'; }
function attrColor(v) { return v >= 7 ? '#6b8f71' : v >= 4 ? '#d4a853' : '#d4846a'; }
function formatDate(turnCount) {
  if (!gameState || !gameState.start_date) return `第 ${turnCount} 回合`;
  try {
    const start = new Date(gameState.start_date);
    const d = new Date(start.getTime() + turnCount * 7 * 86400000);
    return `${d.getFullYear()}年${d.getMonth()+1}月 · 第${turnCount}周`;
  } catch(e) { return `第 ${turnCount} 回合`; }
}
function getCurrentAge() { return gameState?.player_age ?? 24; }

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
      n.style.bottom = bottomOffset + 'px'; n.style.top = 'auto';
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

// ========== Process action response ==========
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
  if (d.ending) { window._pendingEnding = d.ending; }
  if (d.trend) gameState.trend = d.trend;
  if (d.industry_news) gameState.industry_news = d.industry_news;
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

// ============================================================
// SCREEN MANAGEMENT
// ============================================================
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  currentScreen = id;
}

// ============================================================
// CREATE CHARACTER FLOW
// ============================================================
function startCreate() {
  selections = {origin:'',resources:'',goal:'',pace:''};
  currentPlayer = {name:'林知夏',age:'24',city:'上海',custom_origin:'',specialization:''};
  createStep = 0;
  showScreen('create');
  renderCreateStep();
}

function selectOpt(type, id) { selections[type] = id; renderCreateStep(); }

function nextStep() {
  if (createStep === 0) {
    currentPlayer.name = document.getElementById('c-name')?.value || currentPlayer.name;
    currentPlayer.age = document.getElementById('c-age')?.value || currentPlayer.age;
    currentPlayer.city = document.getElementById('c-city')?.value || currentPlayer.city;
  }
  if (createStep === 1) {
    const ci = document.getElementById('custom-origin');
    if (ci) currentPlayer.custom_origin = ci.value;
  }
  if (createStep === 5) {
    currentPlayer.specialization = selections.specialization || '';
  }
  createStep++;
  if (createStep > 5) { createStep = 5; }
  renderCreateStep();
}

function prevStep() {
  createStep = Math.max(0, createStep - 1);
  renderCreateStep();
}

function renderCreateStep() {
  const container = document.getElementById('create-container');
  if (!container) return;
  let html = `<div class="create-progress">${STEP_LABELS.map((l,i) =>
    `<span class="cp-step${i===createStep?' active':''}${i<createStep?' done':''}">${i+1}. ${l}</span>`
  ).join('')}</div>`;

  if (createStep === 0) {
    html += `<div class="create-step active">
      <div class="field"><label>姓名</label><input id="c-name" value="${esc(currentPlayer.name)}" maxlength="8"></div>
      <div class="field"><label>年龄</label><input id="c-age" value="${esc(currentPlayer.age)}" type="number" min="18" max="60"></div>
      <div class="field"><label>城市</label><input id="c-city" value="${esc(currentPlayer.city)}"></div>
      <div class="create-nav"><button class="btn btn-primary" onclick="nextStep()">下一步 →</button></div></div>`;
  } else if (createStep === 1) {
    html += `<div class="create-step active">`;
    ORIGINS.forEach(o => {
      html += `<div class="select-card${selections.origin===o.id?' selected':''}" onclick="selectOpt('origin','${o.id}')">
        <div class="sc-radio"></div><div class="sc-body"><div class="sc-title">${o.id}. ${o.title}</div><div class="sc-desc">${o.desc}</div>
        <div class="sc-tags">${o.good?`<span class="sc-tag-good">✦ ${o.good}</span>`:''}${o.warn?`<span class="sc-tag-warn">△ ${o.warn}</span>`:''}</div></div></div>`;
    });
    html += `<div class="field" style="margin-top:8px"><label>自定义描述（仅选G需填）</label><input id="custom-origin" placeholder="描述你的职业"></div>`;
    html += `<div class="create-nav"><button class="btn btn-back" onclick="prevStep()">← 上一步</button><button class="btn btn-primary" onclick="nextStep()">下一步 →</button></div></div>`;
  } else if (createStep === 2) {
    html += `<div class="create-step active">`;
    RESOURCES.forEach(r => {
      html += `<div class="select-card${selections.resources===r.id?' selected':''}" onclick="selectOpt('resources','${r.id}')">
        <div class="sc-radio"></div><div class="sc-body"><div class="sc-title">${r.id}. ${r.title}</div><div class="sc-desc">${r.desc}</div></div></div>`;
    });
    html += `<div class="create-nav"><button class="btn btn-back" onclick="prevStep()">← 上一步</button><button class="btn btn-primary" onclick="nextStep()">下一步 →</button></div></div>`;
  } else if (createStep === 3) {
    html += `<div class="create-step active">`;
    GOALS.forEach(g => {
      html += `<div class="select-card${selections.goal===g.id?' selected':''}" onclick="selectOpt('goal','${g.id}')">
        <div class="sc-radio"></div><div class="sc-body"><div class="sc-title">${g.id}. ${g.title}</div><div class="sc-desc">${g.desc}</div></div></div>`;
    });
    html += `<div class="create-nav"><button class="btn btn-back" onclick="prevStep()">← 上一步</button><button class="btn btn-primary" onclick="nextStep()">下一步 →</button></div></div>`;
  } else if (createStep === 4) {
    html += `<div class="create-step active">`;
    PACES.forEach(p => {
      html += `<div class="select-card${selections.pace===p.id?' selected':''}" onclick="selectOpt('pace','${p.id}')">
        <div class="sc-radio"></div><div class="sc-body"><div class="sc-title">${p.id}. ${p.title}</div><div class="sc-desc">${p.desc}</div></div></div>`;
    });
    html += `<div class="create-nav"><button class="btn btn-back" onclick="prevStep()">← 上一步</button><button class="btn btn-primary" onclick="nextStep()">下一步 →</button></div></div>`;
  } else if (createStep === 5) {
    html += `<div class="create-step active">`;
    SPECIALIZATIONS.forEach(s => {
      html += `<div class="select-card${selections.specialization===s.id?' selected':''}" onclick="selectOpt('specialization','${s.id}')">
        <div class="sc-radio"></div><div class="sc-body"><div class="sc-title">${s.icon} ${s.name}</div><div class="sc-desc">${s.desc}</div><div class="sc-tags"><span class="sc-tag-good">✦ ${s.attr}</span></div></div></div>`;
    });
    html += `<div class="create-nav"><button class="btn btn-back" onclick="prevStep()">← 上一步</button><button class="btn btn-primary" onclick="startGame()">🎮 开始游戏</button></div></div>`;
  }
  container.innerHTML = html;
}

// ============================================================
// GAME START / LOAD / RESET
// ============================================================
async function startGame() {
  if (createStep === 1) { const ci = document.getElementById('custom-origin'); if (ci) currentPlayer.custom_origin = ci.value; }
  showScreen('game');
  renderLoading(true);
  isProcessing = true;
  try {
    const d = await API.newGame({...currentPlayer, ...selections});
    gameState = d.state;
    _prevTitle = d.state?.title?.title || '';
    isProcessing = false;
    renderAll();
  } catch (e) {
    renderLoading(false, esc(e.message));
    isProcessing = false;
  }
}

async function loadGame() {
  try {
    const d = await API.getState();
    if (!d.state) { alert('没有存档'); return; }
    gameState = d.state;
    _prevTitle = d.state?.title?.title || '';
    showScreen('game');
    renderAll();
  } catch (e) { alert('连接失败'); }
}

async function resetGame() {
  if (!confirm('确定结束当前游戏？存档将被删除。')) return;
  try { await API.reset(); } catch(e) {}
  gameState = null;
  showScreen('cover');
}

// ============================================================
// DEFAULT renderLoading (can be overridden by each HTML)
// ============================================================
function renderLoading(on, msg) {
  // Override in each HTML file for custom loading UI
  if (on) console.log('Loading...');
  else if (msg) console.log('Error:', msg);
}

// ============================================================
// GAME ACTIONS
// ============================================================
async function makeChoice(choiceId) {
  if (isProcessing) return;
  if (gameState && gameState.stamina <= 0) return;
  isProcessing = true;
  renderLoading(true);
  try {
    const d = await API.doAction(choiceId);
    processActionResponse(d);
    isProcessing = false;
    renderAll();
  } catch (e) {
    renderLoading(false, esc(e.message));
    isProcessing = false;
  }
}

async function doActiveAction(actionKey) {
  if (isProcessing) return;
  isProcessing = true;
  renderLoading(true);
  try {
    const d = await API.activeAction(actionKey);
    processActionResponse(d);
    isProcessing = false;
    renderAll();
  } catch (e) {
    renderLoading(false, esc(e.message));
    isProcessing = false;
  }
}

// ============================================================
// ACTIVE ACTIONS SUBMENU
// ============================================================
function toggleAA() {
  const s = document.getElementById('aa-sub');
  if (s) s.style.display = s.style.display === 'block' ? 'none' : 'block';
}

function buildActiveActionButtons() {
  if (!gameState) return '';
  const st = gameState;
  return ACTIVE_ACTIONS_LIST.filter(a => !a.disabled || !a.disabled(st)).map(a => {
    const d = a.disabled ? a.disabled(st) : false;
    return `<button class="aa-btn" ${d?'disabled':''} onclick="event.stopPropagation();${d?'':'doActiveAction(\''+a.key+'\')'}">${a.name}<span class="aa-desc">${a.desc}</span></button>`;
  }).join('');
}

// ============================================================
// NPC INTERACTIONS
// ============================================================
async function showNPCSheet(npcId) {
  if (isProcessing) return;
  try {
    const d = await API.getNPCs(npcId);
    if (d.error) { alert(d.error); return; }
    let html = `<div class="npc-sheet-header">
      <div class="npc-sheet-avatar" style="background:${AVATAR_COLORS[Math.abs(hashCode(npcId))%6]}">${d.name?.[0]||'?'}</div>
      <div><h3>${esc(d.name)}</h3><div style="color:var(--text-secondary);font-size:0.78rem">${esc(d.relation||'')}</div></div>
    </div>`;
    if (d.options && d.options.length) {
      html += '<div style="margin-top:12px">';
      d.options.forEach(o => {
        html += `<button class="npc-option-btn" onclick="doNPC('${npcId}','${o.id}')">
          <div>${esc(o.text)}</div><div style="font-size:0.68rem;color:var(--text-secondary)">${esc(o.hint||'')}</div></button>`;
      });
      html += '</div>';
    }
    openModal(html);
  } catch(e) { alert('NPC 加载失败'); }
}

async function doNPC(npcId, actionId) {
  closeModal();
  try {
    const d = await API.doNPC(npcId, actionId);
    if (d.result) showNotification('npc', d.result);
    if (d.npc_event) showNotification('npc', `${d.npc_event.npc_name}：${d.npc_event.text}`);
    if (d.stamina !== undefined) gameState.stamina = d.stamina;
    if (d.savings !== undefined) gameState.savings = d.savings;
    if (d.attributes) gameState.attributes = d.attributes;
    renderAll();
  } catch (e) { alert('互动失败'); }
}

function hashCode(s) { let h=0; for(let i=0;i<(s||'').length;i++) h=(h<<5)-h+s.charCodeAt(i)|0; return h; }

// ============================================================
// MODAL
// ============================================================
function openModal(html) {
  const m = document.getElementById('modal');
  if (!m) return;
  m.innerHTML = `<div class="modal-card">${html}</div>`;
  m.classList.add('active');
}
function closeModal() {
  const m = document.getElementById('modal');
  if (m) m.classList.remove('active');
}

// ============================================================
// FEEDBACK
// ============================================================
async function showFeedback() {
  let html = '<h3 style="font-family:var(--font-serif);margin-bottom:12px">💬 反馈</h3>';
  html += '<div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:12px">有什么想法、建议或 bug？告诉我们</div>';
  html += '<textarea id="fb-text" style="width:100%;height:80px;padding:10px;border:1px solid var(--surface-3);border-radius:var(--radius);font-size:0.82rem;font-family:var(--font-sans);resize:vertical" placeholder="请输入反馈..."></textarea>';
  html += '<button class="btn btn-primary" style="margin-top:10px;width:100%" onclick="submitFeedback()">发送反馈</button>';
  openModal(html);
}

async function submitFeedback() {
  const el = document.getElementById('fb-text');
  if (!el || !el.value.trim()) return;
  try {
    await API.sendFeedback(el.value, gameState?.turn_count || 0, gameState?.player?.name || '');
    closeModal();
    showNotification('milestone', '感谢反馈！');
  } catch(e) { alert('发送失败'); }
}

// ============================================================
// ENDINGS
// ============================================================
function showEnding(ending) {
  let html = `<div class="ending-panel"><h2 style="font-family:var(--font-serif)">${esc(ending.name)}</h2>
    <p style="white-space:pre-wrap">${esc(ending.description)}</p>`;
  if (ending.options && ending.options.length) {
    ending.options.forEach(o => {
      html += `<button class="btn btn-primary" style="margin:6px;width:100%" onclick="resolveEnding('${o.id}')">${esc(o.text)}</button>`;
    });
  }
  html += '</div>';
  openModal(html);
}

async function resolveEnding() { closeModal(); }

// ============================================================
// SAVES
// ============================================================
async function showSaves() {
  let html = '<h3 style="font-family:var(--font-serif);margin-bottom:12px">💾 存档管理</h3>';
  try {
    const d = await API.getSaves();
    const saves = d.saved || [];
    for (let i = 1; i <= 5; i++) {
      const s = saves.find(x => x.slot === i);
      const info = s ? `${s.title || ''} · 回合${s.turn||0} · ${s.date||''}` : '空槽位';
      html += `<div class="save-row">
        <span style="font-size:0.78rem;color:var(--text-secondary)">槽 ${i}: ${esc(info)}</span>
        <div>${s ? `<button class="btn btn-sm" onclick="doLoad(${i})">读取</button><button class="btn btn-sm" style="color:var(--danger)" onclick="doDelete(${i})">删除</button>` : ''}
        <button class="btn btn-sm" onclick="doSave(${i})">保存</button></div></div>`;
    }
    html += `<div style="margin-top:12px"><button class="btn btn-primary" style="width:100%" onclick="API.export()">📤 导出存档</button></div>`;
    html += `<button class="btn" style="width:100%;margin-top:6px" onclick="importSave()">📥 导入存档</button>`;
  } catch(e) { html += '<div style="color:var(--danger)">加载失败</div>'; }
  openModal(html);
}

async function doSave(s) {
  try { await API.saveSlot(s); showNotification('milestone', '已保存'); showSaves(); } catch(e) { alert('保存失败'); }
}

async function doLoad(s) {
  if (!confirm(`确定读取槽位${s}？`)) return;
  try {
    const d = await API.loadSlot(s);
    gameState = d.state;
    _prevTitle = d.state?.title?.title || '';
    closeModal();
    renderAll();
    showNotification('milestone', '已读取');
  } catch(e) { alert('读取失败'); }
}

async function doDelete(s) {
  if (!confirm(`确定删除槽位${s}？`)) return;
  try { await API.deleteSlot(s); showSaves(); } catch(e) { alert('删除失败'); }
}

async function importSave() {
  const i = document.createElement('input');
  i.type = 'file'; i.accept = '.json';
  i.onchange = async e => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      const s = JSON.parse(await f.text());
      if (!s.player || !s.attributes) { alert('格式无效'); return; }
      await API.importState(s);
      gameState = s;
      _prevTitle = s?.title?.title || '';
      closeModal();
      renderAll();
      showNotification('milestone', '导入成功');
    } catch(err) { alert('导入失败: ' + err.message); }
  };
  i.click();
}

// ============================================================
// INDUSTRY NEWS
// ============================================================
let _newsCache = null;
async function renderIndustryNews() {
  const el = document.getElementById('tb-trend');
  if (!el) return;
  try {
    if (!_newsCache) { const d = await API.getIndustryNews(); _newsCache = d.news || []; }
    if (_newsCache.length) {
      const n = _newsCache[Math.floor(Math.random() * _newsCache.length)];
      el.textContent = `📐 ${n}`;
      el.style.display = '';
    }
  } catch(e) {}
}

// ============================================================
// PORTFOLIO & ACHIEVEMENTS (cached render helpers)
// ============================================================
function renderCachedPortfolio(entries) {
  if (!entries || !entries.length) return '<div style="color:var(--text-secondary);font-size:0.8rem;text-align:center;padding:20px">暂无作品记录<br>完成项目后自动生成</div>';
  return entries.map(e => `<div class="folio-card">
    <div class="folio-title">${esc(e.name)}</div>
    <div class="folio-meta">${esc(e.time||'')} · ${esc(e.client||'')} · ¥${(e.budget||0).toLocaleString()}</div>
    <div class="folio-summary">${esc(e.summary||'')}</div>
  </div>`).join('');
}

function renderCachedAchievements(allAch, unlocked) {
  const uset = new Set(unlocked || []);
  return allAch.map(a => `<div class="ach-card${uset.has(a.id)?' unlocked':''}">
    <div class="ach-icon">${a.icon||'🏅'}</div>
    <div class="ach-name">${esc(a.name)}</div>
    <div class="ach-desc">${esc(a.desc)}</div>
  </div>`).join('');
}

async function loadPortfolio() {
  try { return (await API.genPortfolio()).entries || []; } catch(e) { return []; }
}

async function loadAchievements() {
  try { return (await fetchAchievements()) || []; } catch(e) { return []; }
}

// ============================================================
// INIT — global click delegation
// ============================================================
document.addEventListener('click', function(e) {
  const btn = e.target.closest('.choice-btn');
  if (btn && !btn.disabled && !isProcessing) {
    if (gameState && gameState.stamina <= 0 && btn.dataset.choice !== '__action__') return;
    const choiceId = btn.getAttribute('data-choice');
    if (choiceId) makeChoice(choiceId);
  }
  // Close AA submenu on outside click
  const aaSub = document.getElementById('aa-sub');
  if (aaSub && aaSub.style.display === 'block' && !e.target.closest('#aa-sub') && !e.target.closest('.choice-btn-auto')) {
    aaSub.style.display = 'none';
  }
});
