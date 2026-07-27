# 抖音收藏夹 RAG 知识库 — 完整开发方案

> 基于三个参考项目的深度分析，综合最优方案。

---

## 一、技术选型

| 层级 | 技术 | 理由 |
|------|------|------|
| 后端框架 | FastAPI + Uvicorn | 三个项目一致选择，异步支持好 |
| ORM | SQLAlchemy 2.0 | 异步支持，Jonesxq 参考 |
| 数据库 | SQLite + aiosqlite | 本地零配置，个人项目最佳 |
| 向量库 | ChromaDB | 三个项目一致选择，本地持久化 |
| LLM | DeepSeek（OpenAI 兼容协议） | 便宜、中文强、lys2-14 默认 |
| Embedding | DashScope text-embedding-v4（云端） | 即开即用，无需下载模型，1024 维 |
| ASR | DashScope 语音识别（云端） | 速度快（实时5-10x），即开即用 |
| 音频下载 | yt-dlp + ffmpeg | 抖音视频音频提取 |
| 浏览器 | Playwright + Chromium | 抖音扫码登录 + Cookie 抓取 |
| 前端 | React + Vite + TypeScript + Tailwind CSS | Jonesxq 同款，轻量快速 |
| 包管理 | uv (Python) + npm (前端) | Jonesxq 同款 |
| 测试 | pytest | 标准选择 |

### API Key 需求

| 服务 | 提供商 | 用途 |
|------|--------|------|
| `DASHSCOPE_API_KEY` | 阿里百炼 | ASR 语音转写 + Embedding 向量化 |
| `DEEPSEEK_API_KEY` | DeepSeek | LLM 对话问答 |

---

## 二、功能清单

### MVP（第一版必做）

| 功能 | 说明 |
|------|------|
| 抖音扫码登录 | Playwright 启动 Chromium，扫码获取 Cookie |
| 拉取收藏夹列表 | 通过抖音 API 获取所有收藏夹 |
| 收藏夹视频列表 | 查看每个收藏夹下的视频 |
| 手动同步入库 | 选择收藏夹 → 一键入库 |
| 音频下载 | yt-dlp 下载视频音频流 |
| 语音转文字 | ASR 音频 → 文本 |
| 文本切块 | 清洗 + 分段 |
| 向量化存储 | Embedding → ChromaDB |
| RAG 对话问答 | 自然语言提问 → 检索 → LLM 回答（含来源引用） |
| 流式回答 | SSE 流式输出 |
| 会话管理 | 多轮对话，历史记录 |

### 后续迭代

| 功能 | 说明 |
|------|------|
| 收藏夹自动同步 | 定时检测新增/删除视频 |
| 查询改写 | LLM 改写用户问题提升召回 |
| 混合检索 + RRF | Dense + 关键词融合排序 |
| Markdown 导出 | 导出视频内容/AI 笔记 |
| Docker 一键部署 | 容器化 |

---

## 三、数据模型

```
FavoriteCollection（收藏夹）
├── id
├── platform_collection_id   # 抖音收藏夹 ID
├── title                    # 收藏夹名称
├── video_count              # 视频数量
├── is_active
├── created_at / updated_at

FavoriteVideo（收藏夹视频）
├── id
├── collection_id            # FK → FavoriteCollection
├── platform_item_id         # 抖音视频 ID
├── title                    # 视频标题
├── author                   # 作者
├── duration                 # 时长（秒）
├── cover_url                # 封面 URL
├── video_url                # 视频/音频 URL
├── is_active
├── created_at / updated_at

VideoCache（入库缓存/转写结果）
├── id
├── platform_item_id         # 抖音视频 ID
├── title
├── transcript_text          # ASR 转写全文
├── summary                  # AI 摘要
├── status                   # pending/downloading/transcribing/done/failed
├── processed_at
├── created_at / updated_at

ChatSession（对话会话）
├── id
├── title                    # 自动取首条问题前40字
├── created_at / updated_at

ChatMessage（对话消息）
├── id
├── session_id               # FK → ChatSession
├── role                     # user / assistant
├── content                  # 消息内容
├── route_type               # direct / vector / db_list / db_content
├── retrieved_video_ids       # 召回的视频 ID 列表（JSON）
├── retrieved_chunk_ids       # 召回的 chunk ID 列表（JSON）
├── model                    # 使用的 LLM 模型
├── latency_ms               # 延迟（仅 assistant）
├── created_at
```

> 参考 Jonesxq 的数据模型，精简了不必要字段。

---

## 四、API 设计

```
认证
POST   /auth/douyin/login/start       # 启动扫码登录，返回二维码/登录页 URL
GET    /auth/douyin/login/status       # 查询登录状态

收藏夹
POST   /favorites/sync                 # 同步收藏夹列表
GET    /favorites/collections          # 获取收藏夹列表
GET    /favorites/collections/{id}/videos  # 获取某收藏夹的视频列表（分页）

知识库
POST   /knowledge/sync                 # 指定收藏夹一键入库（后台任务）
GET    /knowledge/sync/{task_id}       # 查询入库进度
GET    /knowledge/stats                # 知识库统计（视频数/chunk数）

对话
POST   /chat/ask                       # 非流式问答
POST   /chat/ask/stream                # SSE 流式问答
GET    /chat/sessions                  # 会话列表
GET    /chat/sessions/{id}/messages    # 某会话的消息历史
DELETE /chat/sessions/{id}             # 删除会话
```

---

## 五、数据处理流水线

```
用户点击"入库"
  → worker 拉取待处理视频
  → yt-dlp 下载音频（仅音频流，不下载视频）
  → ffmpeg 转码为 16kHz 单声道 WAV
  → faster-whisper 语音转文字
  → 文本清洗（去重、去语气词、合并短句）
  → 切块（固定大小 1000 字 + 200 字重叠）
  → Embedding 向量化
  → 存入 ChromaDB
  → 更新 VideoCache 状态为 done
```

---

## 六、RAG 问答流程

```
用户提问
  → 查询路由（规则：问候→direct，列表→db_list，总结→db_content，其他→vector）
  → [vector 路由] 向量检索 + 关键词检索 → RRF 融合
  → 构建上下文（截断到 max_context_chars）
  → 注入历史对话窗口
  → LLM 生成回答
  → 后处理（去除 Markdown 符号、口语化合并）
  → 返回回答 + 来源视频列表
  → 存入 ChatMessage
```

---

## 七、项目目录结构

```
douyinrag/
├── CLAUDE.md                    # 行为规范
├── DEVELOPMENT_PLAN.md          # 本文件
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── router.py
│   │   │   └── routes/
│   │   │       ├── auth.py
│   │   │       ├── favorites.py
│   │   │       ├── knowledge.py
│   │   │       └── chat.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── models/
│   │   │   └── entities.py
│   │   ├── schemas/
│   │   │   └── dto.py
│   │   └── services/
│   │       ├── douyin_collector.py
│   │       ├── favorites_service.py
│   │       ├── knowledge_service.py
│   │       ├── media_service.py
│   │       ├── asr_service.py
│   │       ├── text_processing.py
│   │       ├── chroma_service.py
│   │       ├── llm_service.py
│   │       ├── rag_service.py
│   │       └── worker.py
│   ├── pyproject.toml
│   ├── .env.example
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   ├── components/
│   │   └── api.ts
│   ├── package.json
│   └── vite.config.ts
└── scripts/
    └── rebuild_storage.py
```

---

## 八、分阶段计划

### 阶段 1：项目初始化 + 后端骨架
- 创建目录结构
- pyproject.toml、.env.example
- FastAPI 入口 + 配置 + 日志
- 数据库 ORM + 建表

### 阶段 2：认证 + 收藏夹
- 抖音登录（Playwright 扫码）
- 收藏夹列表拉取 + 同步
- 视频列表查询

### 阶段 3：知识库入库
- 音频下载（yt-dlp + ffmpeg）
- 语音转文字（ASR）
- 文本处理 + 切块
- 向量化 + ChromaDB 存储
- 后台任务队列

### 阶段 4：RAG 对话
- LLM 客户端
- 向量检索
- 问答链（含来源引用）
- 流式输出
- 会话管理 CRUD

### 阶段 5：前端
- 登录页
- 收藏夹管理页
- 对话页
- 前后端联调

### 阶段 6：测试 + 文档
- 核心模块测试
- README 文档

---

## 九、已确认的决策

| 决策 | 选择 | 
|------|------|
| ASR | 云端 DashScope |
| Embedding | 云端 DashScope |
| LLM | DeepSeek |
| 总体 | 全云端 + DeepSeek |

### 仍需确认

1. 功能清单是否有要增减的？
2. MVP 范围是否认可？（先做必做项，后续迭代再加）
3. 是否可以开始第一阶段：项目初始化 + 后端骨架？
