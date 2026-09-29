# Design: add-traceable-vector-retrieval

## Context

第 3 课已交付 Flask + SQLite 单服务：会话登录、教师/学生角色、班级隔离（列表 SQL 过滤 + fetch-then-check 同形 404）、材料上传入库（uuid 落盘 + materials 行）、Compose 命名卷持久化。第 4 课在其上追加「切分 → 嵌入 → 入向量库 → 检索 → 溯源/问答」。

课程课件（week04 原型）给出的行为口径：三模式检索、RRF k=60、余弦阈值 0.35、溯源字段（材料标题/切片序号/字符区间/摘录）、空查询 400、无命中固定文案、向量库不对外、跨班检索对外表现为无命中、教师可重建索引、先检索后生成问答。

原型技术栈为 Go + MySQL + Qdrant + 网关；本仓库沿用 Flask + SQLite 主体，向量库引入 Qdrant（Compose 服务），嵌入/对话走 OpenAI 兼容网关。以下决策保证**行为规约与课件一致，实现选型贴合既有栈**。

## Goals / Non-Goals

- [x] 行为规约逐条可对照课件验收：三模式、阈值、RRF、溯源、失败与降级语义、班级隔离。
- [x] 保持第 3 课全部既有契约不变（登录、上传校验链、列表、详情、下载、同形 404）。
- [x] 密钥只在服务端环境变量；向量库与网关无客户端可达入口。
- [x] 不迁移 MySQL/Go；不引入编排框架；不做重排序与流式输出。

## Decisions

### D1. 存储拓扑：关系库存正文与切片，Qdrant 只存向量与标识

- `materials` 增加 `body_text`（上传时从 `.txt`/`.md` 文件内容读出；原文件字节不动）。
- 新表 `knowledge_chunks`：`id`（主键 = 向量主键）、`material_id`、`class_id`、`chunk_index`、`chunk_text`、`char_start`、`char_end`、`embed_status`（`ready`/`failed`）。
- Qdrant 集合 `campusclaw_chunks`，余弦度量；点 id = `knowledge_chunks.id`；payload 仅 `class_id`、`material_id`、`chunk_id`、`chunk_index`，不含正文。
- 摘录永远回 SQLite 取 `chunk_text`；向量库只靠主键回表，不重复存正文。
- 备选：sqlite-vec 同库同事务最简——否决：课件验收点「停止向量库后 keyword 仍可用、vector/hybrid 503」需要真实的独立组件故障语义，且独立向量库贴合「使用向量数据库存储」的作业口径与课件选型。

### D2. 关键字路：SQLite FTS5 + 应用层 2-gram（对齐课件 ngram token=2）

- MySQL `FULLTEXT ... WITH PARSER ngram` 在 SQLite 无等价物：FTS5 `unicode61` 不切中文、`trigram` 无法命中 2 字词（中文检索大量 2 字词）。
- 方案：写入时把 `chunk_text` 切成 2-gram 序列（空格连接）存入 FTS5 虚表；查询词以同一规则 2-gram 化。任意 ≥2 字中文词可命中，BM25 排序即全文相关度。
- FTS 行与 chunks 行同事务增删；「仅检索已完成索引的切片」由「FTS 行存在」表达。关键字路径不触嵌入服务、不访问 Qdrant。

### D3. 嵌入与对话：环境变量注入的 OpenAI 兼容网关（默认课程网关）

- `EMBEDDING_BASE_URL/EMBEDDING_API_KEY/EMBEDDING_MODEL`、`CHAT_BASE_URL/CHAT_API_KEY/CHAT_MODEL`；密钥仅服务端，页面不展示向量分量。
- 向量维度以网关嵌入模型为准，建集合时一次确定；未配置嵌入端点 → 降级模式启动：keyword 可用，vector/hybrid 一律 503（与向量库不可用同一降级语义）。
- `/api/ask` 有命中但对话网关未配置 → 503；无命中仍走固定文案路径（不触网关）。
- 备选：fastembed 本地模型（离线可复现）——留作网络不可行时的替代：接口同形，仅 base_url/模型配置不同，规约不感知。

### D4. 切分器：三策略与课件参数一致

- `auto`：≤800 字窗口、重叠 80 字、优先空行/换行/句号断开；请求中另行填写长度与预处理参数不生效。
- `custom`：长度 100–2000、重叠 0%–50%（越界 400）、无断点按最大长度强制截断；可选预处理（移除 URL/邮箱、折叠连续空白）。
- `hierarchy`：按 `#`/`##`/`###` 分章、标题保留章内，过长章再按 auto 窗口切。
- 偏移量相对预处理后文本；`body_text` 与原文件永不改写。bootstrap 幂等：仅对无切片的材料补建索引（默认 auto），已建不重复切分。

### D5. 检索编排：班级过滤双侧强制 + 回表复核

- keyword：SQL `WHERE class_id = 会话班级`；vector：Qdrant `class_id` 过滤 → 命中主键回 SQLite 再核 `class_id`。仅在单侧过滤不充分。
- hybrid：两路先各自按绝对分数过滤（向量路余弦 ≥ 0.35），再按名次 RRF（k=60），缺席一路不贡献分数；RRF 名次分不是相关性阈值。
- 溯源组装：`material_id`、材料标题、`chunk_index`、`char_start`/`char_end`、`excerpt`（`chunk_text`）、材料详情/下载入口；不含磁盘路径、不含向量分量。
- 跨班与无关词同形：200 + 空 hits +「资料中未找到相关内容」，不用 403/404 泄露存在性（与第 3 课同形 404 一脉相承）。

### D6. Compose：qdrant 服务仅内部网络

- 新增 `qdrant` 服务（官方镜像；网络受限时沿用第 3 课经验经 daocloud 镜像拉取后 `docker tag`），不映射宿主端口；`web` 经 `QDRANT_URL` 访问；独立数据卷 `qdrant-data` 持久化。
- 宿主机与客户端均无法直连向量库；镜像/网关密钥仅经 `.env` → `environment` 注入。

## Risks / Trade-offs

- 网关密钥缺失时 vector/hybrid/ask 不可用 → 以 503 与降级模式明确暴露，keyword 主路径始终可启动、可验收。
- 2-gram 索引体积约为正文 2 倍 → 课程语料量级下可忽略；换来与课件 ngram token=2 一致的中文召回。
- Qdrant 单点 → 单实例课程边界内可接受；降级语义保证关键字检索不受牵连。

## Migration Plan

1. 依赖与配置 → 2. 建表/加列 + FTS → 3. 切分器 → 4. 索引管道 → 5. 检索三模式 → 6. API 与问答 → 7. Compose 加 qdrant → 8. 测试与 E2E。
bootstrap 幂等补齐存量材料正文与索引；无手工迁移、无停机步骤（单实例重启即生效）。

## Open Questions

- 无（课程网关地址与密钥由课程发放，运行时经 `.env` 注入；未配置时按降级语义运行）。
