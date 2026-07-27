# 抖音收藏夹 RAG 知识库 — 项目行为规范

## 项目目标

将抖音收藏夹变成可搜索、可对话的个人知识库。
核心流程：登录抖音 → 拉取收藏夹 → 下载音频 → 语音转文字(ASR) → 文本切块 → 向量化 → RAG 对话问答。

---

## 一、开发流程

### 1.1 开发顺序

```
Pencil UI 设计 → 用户确认 → 后端核心 → 用户确认 → 前端 → 用户确认 → 联调测试
```

### 1.2 每步确认

每个模块完成后必须停下来等用户确认，不得连续推进多个模块。确认节点包括但不限于：
- UI 设计稿完成后
- 数据库模型定义完成后
- 每个核心 Service 完成后
- 每个 API 路由完成后
- 前端页面/组件完成后

### 1.3 遇到问题的解决顺序

1. **先查参考项目**：Jonesxq/douyin_RAG（主）、lys2-14/douyin-knowledge-rag、via007/bilibili-rag
2. 参考项目无解时，再自行设计方案
3. 自行设计方案需先说明思路，征得同意后再实现

---

## 二、代码规范

### 2.1 注释与文档

- **每个函数**必须有文档字符串，包含：
  - 功能描述
  - 参数说明（`:param name: description`）
  - 返回值说明（`:return: description`）
- **每个模块**文件头部有模块说明
- **类型注解**：所有函数参数和返回值必须标注类型
- 注释语言：**中文**

### 2.2 命名规范

- 文件名：`snake_case`（如 `rag_service.py`）
- 类名：`PascalCase`（如 `RagService`）
- 函数/变量名：`snake_case`（如 `build_context`）
- 常量：`UPPER_SNAKE_CASE`（如 `MAX_CHUNK_SIZE`）

### 2.3 文件组织

参考 Jonesxq/douyin_RAG 的标准分层：

```
backend/
  app/
    main.py                 # FastAPI 入口
    api/
      router.py             # 路由聚合
      routes/
        auth.py             # 登录
        favorites.py        # 收藏夹
        knowledge.py        # 入库
        chat.py             # 对话
    core/
      config.py             # 配置（基于 Pydantic Settings）
      logging.py            # 日志
    db/
      base.py               # ORM Base
      session.py            # Engine / Session
    models/
      entities.py           # 数据表实体
    schemas/
      dto.py                # API DTO（Pydantic）
    services/
      douyin_collector.py   # 抖音登录与收藏抓取
      favorites_service.py  # 收藏差异同步
      knowledge_service.py  # 入库任务
      media_service.py      # 音频下载
      asr_service.py        # 语音识别
      text_processing.py    # 清洗与切块
      chroma_service.py     # 向量库操作
      llm_service.py        # LLM/Embedding 客户端
      rag_service.py        # RAG 检索与答案生成
      worker.py             # 后台任务
    storage/                # 本地数据存放（DB、Chroma、音频缓存）
```

---

## 三、UI 设计规范

### 3.1 Pencil First

所有 UI 界面和组件：
1. 先向我询问设计想法和偏好
2. 用 Pencil MCP 工具绘制设计稿
3. 设计稿经我确认后，才能开始写前端代码

### 3.2 Pencil 使用范围

- ✅ 页面布局、组件外观
- ❌ 数据库 ER 图、架构图、流程图（不需要用 Pencil）

---

## 四、技术约束

### 4.1 运行环境

- **仅 Windows**：所有路径使用 Windows 风格，脚本优先 `.bat`
- Python 3.12+
- Node.js 18+

### 4.2 技术选型原则

- 以 Jonesxq/douyin_RAG 为主要参考起点
- 综合参考其他两个项目的优点
- 技术选型变更需先说明理由并征得同意

### 4.3 要求

- 需要写测试
- 敏感信息不做特殊管理（个人项目）

---

## 五、禁止事项

1. 不得在未征得同意的情况下自行决定 UI 设计方案
2. 不得跨过确认节点连续推进
3. 不得在参考项目有现成方案时自行造轮子
4. 不得修改 `.env` 之外的项目配置文件而不告知
