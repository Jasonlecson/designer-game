# 平面设计师模拟器 · 职业生涯版

基于 LLM 的交互式职业生涯模拟游戏。玩家扮演一名平面设计师，通过回合制选择推进职业发展，AI 实时生成剧情、事件和选项。

## 技术栈

- **后端**: Python Flask
- **前端**: 原生 HTML/CSS/JS
- **AI 引擎**: OpenAI 兼容 API（支持 GPT-4、DeepSeek、通义千问等）

## 快速开始

### 1. 安装依赖

```bash
pip install flask requests
```

### 2. 启动服务

```bash
python server.py
```

### 3. 打开游戏

浏览器访问 `http://localhost:8765`，先点击「API 配置」填入你的 API Key，然后创建角色开始游戏。

## 项目结构

```
designer-game/
├── server.py          # Flask 后端（DM 引擎 + LLM 调用）
├── static/
│   └── index.html     # 前端游戏界面
├── .gitignore
└── README.md
```

## 游戏特色

- 7 种职业起点，5 种职业目标
- 8 项动态职业属性系统
- LLM 实时剧情生成
- 多结局（行业立足 / 顶级突破 / 淘汰 / 枯竭）
- 仪表盘式管理面板 UI
