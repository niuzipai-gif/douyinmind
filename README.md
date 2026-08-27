# DouyinMind · 抖音收藏夹 RAG 知识库

> 把你的抖音收藏夹变成可搜索、可对话的个人知识库

## 它能做什么

登录抖音 → 同步收藏夹 → 一键入库（音频下载 → AI转写 → 向量化）→ 对话问答

```
收藏夹视频 → yt-dlp下载音频 → DashScope ASR转写 → 文本切块 → Embedding向量化 → ChromaDB → RAG对话
```

## 快速开始

### 前置条件

- Python 3.12+
- Node.js 18+
- ffmpeg（加入 PATH）
- Chrome 或 Edge 浏览器

### 1. 安装后端依赖

```powershell
cd backend
pip install uv
uv sync --python 3.12
playwright install chromium
```

### 2. 配置环境变量

```powershell
cp .env.example .env
# 编辑 .env，至少填入：
#   DASHSCOPE_API_KEY=你的百炼API Key
#   DEEPSEEK_API_KEY=你的DeepSeek API Key
```

### 3. 安装前端依赖

```powershell
cd frontend
npm install
```

### 4. 启动

```powershell
# 终端1：后端
cd backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend

# 终端2：前端
cd frontend
npm run dev
```

打开 http://localhost:5173

## 使用流程

1. 点击「扫码登录」→ 浏览器自动打开抖音登录页 → 扫码
2. 登录成功后，点击「同步」拉取收藏夹
3. 点击「一键入库」→ 后台自动下载音频、转写、向量化
4. 入库完成后，在右侧对话区提问

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy + SQLite |
| 向量库 | ChromaDB |
| LLM | DeepSeek（OpenAI 兼容） |
| Embedding | DashScope text-embedding-v4 |
| ASR | DashScope paraformer-v2 |
| 音频下载 | yt-dlp + ffmpeg |
| 浏览器 | Playwright + Chromium |
| 前端 | React 19 + Vite + TypeScript + Tailwind CSS |

## 项目结构

```
douyinrag/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── core/config.py          # Pydantic 配置
│   │   ├── db/                     # SQLAlchemy ORM
│   │   ├── models/entities.py      # 数据表实体
│   │   ├── api/routes/             # 14 个 API 接口
│   │   └── services/
│   │       ├── douyin_collector.py # Playwright 登录 + 数据抓取
│   │       ├── favorites_service.py # 收藏夹同步
│   │       ├── media_service.py    # yt-dlp 音频下载
│   │       ├── asr_service.py      # DashScope 语音转写
│   │       ├── text_processing.py  # 文本清洗 + 切块
│   │       ├── chroma_service.py   # 向量库操作
│   │       ├── llm_service.py      # DeepSeek + DashScope Embedding
│   │       ├── rag_service.py      # RAG 问答引擎
│   │       ├── knowledge_service.py # 入库编排
│   │       └── worker.py           # 后台任务队列
│   ├── pyproject.toml
│   └── tests/
├── frontend/
│   └── src/
│       ├── App.tsx                 # 根组件
│       ├── api.ts                  # API 封装
│       ├── pages/                  # Landing + Workspace
│       └── components/             # LoginModal + SourcesPanel + ChatPanel
├── CLAUDE.md                       # 项目行为规范
└── DEVELOPMENT_PLAN.md             # 完整开发方案
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/douyin/login/start` | 启动扫码登录 |
| GET  | `/api/auth/douyin/login/status` | 查询登录状态 |
| POST | `/api/auth/douyin/logout` | 退出登录 |
| POST | `/api/favorites/sync` | 同步收藏夹 |
| GET  | `/api/favorites/collections` | 收藏夹列表 |
| GET  | `/api/favorites/collections/{id}/videos` | 视频列表 |
| POST | `/api/knowledge/sync` | 一键入库 |
| GET  | `/api/knowledge/sync/{id}` | 入库进度 |
| GET  | `/api/knowledge/stats` | 知识库统计 |
| POST | `/api/chat/ask` | 非流式问答 |
| POST | `/api/chat/ask/stream` | SSE 流式问答 |
| GET  | `/api/chat/sessions` | 会话列表 |
| GET  | `/api/chat/sessions/{id}/messages` | 消息历史 |
| DELETE | `/api/chat/sessions/{id}` | 删除会话 |

## 费用说明

| 服务 | 计费方式 | 说明 |
|------|---------|------|
| DeepSeek LLM | 按 Token | 对话问答，非常便宜 |
| DashScope ASR | 按时长 | 约 ¥0.5-2/小时，有免费额度 |
| DashScope Embedding | 按 Token | 有免费额度，日常使用通常免费 |

## License

MIT

## 个人部署说明

本仓库是 DouyinMind 的个人部署副本：前端通过 GitHub Actions 发布到 GitHub Pages，后端部署到 Render。

### GitHub Pages + Render

1. Render 部署后端，填写 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` 和 `DOUYIN_BRIDGE_TOKEN`。
2. 在本机 `backend/.env` 填入同一个 `DOUYIN_BRIDGE_TOKEN`。
3. 双击 `backend/start_local_login.cmd`，在本机浏览器扫码并完成抖音验证。
4. 打开 GitHub Pages；登录态上传成功后，页面会自动进入知识库。

当前个人站点默认不启用访问口令。抖音登录只在本机浏览器完成，登录态通过独立的 `DOUYIN_BRIDGE_TOKEN` 上传到云端；不要把任何 API Key 或桥接口令提交到 Git。

### DashScope API Key

在阿里云百炼控制台的「密钥管理」中创建 API Key，选择默认业务空间即可。DouyinMind 用它做 Paraformer 语音转写和 text-embedding-v4 向量化；DeepSeek Key 仅用于对话生成。
