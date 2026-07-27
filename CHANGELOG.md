# CHANGELOG

## 2026-07-23 — 回答质量优化

### 背景
用户问"帮我总结技术类视频的要点"时，回答存在以下问题：
1. 信息罗列，缺乏真正的跨视频总结归纳
2. 段落间用"首先...然后..."硬串，暴露 chunk 拼接底
3. 缺乏优先级和筛选，所有视频不分主次
4. 部分内容与话题不匹配（如"3小时准备面试"被归入技术类）
5. 回答过长，没有前置精炼摘要
6. 缺少来源引用，无法追溯

### 改动文件
`backend/app/services/rag_service.py`

### 改动 1：重写总结类 Prompt
**位置**：`_build_prompts()` — `db_content` 路由

**改动**：
- 从简单一句"用语自然简洁"改为结构化输出格式
- 强制输出 TL;DR（3 条 bullet 精炼摘要）
- 要求提炼跨视频共同主题
- 逐视频列出要点 + `[来源: 标题]` 标注
- 要求过滤不相关视频
- 字数限制 500 字

**同时更新**：`vector` 路由检测到总结类 query 时追加相同的归纳要求

### 改动 2：Map-Reduce 上下文压缩
**新增方法**：`_compress_chunks(query, hits)`

**逻辑**：
- chunk ≤ 3 个：直接拼接（无额外成本）
- chunk > 3 个：每个 chunk 先调 LLM 压缩为 3 条要点（max_tokens=200），再合并
- 最多处理 8 个 chunk
- 压缩失败时回退到原文前 300 字

**调用位置**：`_build_context()` — `vector` 路由

### 改动 3：来源标注检测
**新增方法**：`_ensure_sources(answer, sources)`

**逻辑**：
- 检查回答中是否已包含 `[来源:` 或 `[来源：]` 标注
- 如果有则跳过
- 如果没有则自动追加 `📎 参考来源：` 列表

**调用位置**：`answer()` — `_sanitize_answer()` 之后，`db_content` 和 `vector` 路由

### 影响范围
- 只影响总结/概括类问题
- 不影响问候（direct）、列表（db_list）路由
- Map-Reduce 增加少量 LLM 调用成本：chunk≤3 时零成本，chunk=5 时多 5 次约 200 token 的小调用

---

## 2026-07-23 — 路由修复：总结 + 话题限定词

### 背景
"帮我总结技术类视频的要点"被路由到 `db_content`，该路由直接查 DB（取最近 10 个视频），不做语义检索，导致：
- 8 个视频全部逐一复述（报菜名）
- 向量检索耗时 0ms（根本没检索）
- Map-Reduce 未触发（只绑在 vector 路由）
- 非技术类视频也被纳入（"面试技巧""Git"等）

### 改动

**1. `_route()` 方法**：区分"纯总结"和"话题总结"
- `"总结一下"` → `db_content`（全库概述）
- `"总结技术类视频"` → `vector`（语义检索技术相关内容）

实现：剥离总结关键词和语气词后，检测是否还有话题限定词。

**2. `_build_context()` — `db_content` 路由**：
- 改前：直接调 `_db_content_context()` 查 DB
- 改后：如果有检索结果（hits），走语义检索 + Map-Reduce 压缩

**3. `answer()` / `answer_stream()` — 检索步骤**：
- `if route == "vector"` → `if route in ("vector", "db_content")`
- db_content 路由也触发语义检索

---

## 2026-07-23 — Chunk 重叠去重

### 背景
`chunk_overlap=200` 导致相邻 chunk 的开头高度重复。Map-Reduce 压缩时，这个重复被保留下来，在召回片段预览中表现为前一个 chunk 的末尾和后一个 chunk 的开头完全一样。

### 改动
`_compress_chunks()` 末尾新增去重逻辑：
- 比较相邻压缩后的 chunk
- 找到最长公共前缀（> 30 字符）
- 削去后一个 chunk 中重复的开头部分

---

## 2026-07-23 — 修复 `sources` 变量未定义

### 背景
`_ensure_sources(answer, sources)` 在 `sources` 变量被定义之前调用，导致 `UnboundLocalError`。

### 改动
- 将 `sources` 列表的构建从 Step 6（持久化）提前到 Step 5（LLM 生成后、来源检测前）
- 删除 Step 6 中重复的来源构建代码

---

## 2026-07-23 — MMR + 元信息文档（已回退）

因同步功能异常，暂时回退以下两个功能，待诊断完成后重新实施。
