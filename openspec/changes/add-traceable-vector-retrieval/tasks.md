# Tasks: add-traceable-vector-retrieval

## 1. 依赖、配置与 Compose

- [ ] 1.1 新增依赖 `qdrant-client`、`httpx` 并更新 `requirements.txt`，验证 pip 安装成功。
- [ ] 1.2 配置新增环境变量 `QDRANT_URL`、`EMBEDDING_BASE_URL/EMBEDDING_API_KEY/EMBEDDING_MODEL`、`CHAT_BASE_URL/CHAT_API_KEY/CHAT_MODEL`（均为可选；缺失时以降级模式启动），更新 `.env.example` 与 `config.py`，验证缺失变量时应用仍可启动且关键字检索可用。
- [ ] 1.3 `docker-compose.yml` 增加 `qdrant` 服务（仅内部网络、无宿主端口映射、独立数据卷），验证 `docker compose config` 通过且宿主机访问向量库端口失败。

## 2. 数据模型与迁移

- [ ] 2.1 `materials` 增加 `body_text` 列；上传成功时从文件内容提取正文保存，原文件不改写，验证正文与文件内容一致。
- [ ] 2.2 新建 `knowledge_chunks` 表（id、material_id、class_id、chunk_index、chunk_text、char_start、char_end、embed_status）与 FTS5 虚表（2-gram 预切分），验证建表与同事务增删。
- [ ] 2.3 bootstrap 幂等补齐：对存量材料提取正文并按默认 auto 策略补建切片索引，重复执行不重复切分，验证二次启动切片数不变。

## 3. 切分器

- [ ] 3.1 实现 `auto`：≤800 字窗口、重叠 80 字、优先空行/换行/句号断开，验证切片均 ≤800 字且相邻切片有重叠。
- [ ] 3.2 实现 `custom`：长度 100–2000、重叠 0%–50%（越界拒绝）、无断点强制截断、可选预处理（移除 URL/邮箱、折叠连续空白），验证各边界参数。
- [ ] 3.3 实现 `hierarchy`：按 #/##/### 分章、标题留在章内、过长章按 auto 再切，验证 Markdown 样例切分结果。

## 4. 索引管道与重建

- [ ] 4.1 实现上传后索引管道：切分 → 逐片嵌入（OpenAI 兼容端点）→ 写 Qdrant（向量主键 = 切片 id，payload 仅标识不含正文），验证主键一一对应且 payload 无正文。
- [ ] 4.2 嵌入失败路径：切片标记 failed、材料记录保留、向量库无该主键，验证失败无残缺向量。
- [ ] 4.3 实现教师重建索引端点：先删旧切片与旧向量再按新策略写入，验证旧主键无残留、学生调用被拒（403）。

## 5. 检索三模式

- [ ] 5.1 关键字路：FTS5 查询（查询词同样 2-gram 化）+ 会话班级过滤 + BM25 排序，不触嵌入与向量库，验证原词命中且无嵌入/向量库调用。
- [ ] 5.2 向量路：问句嵌入 → Qdrant 按会话班级过滤 → 余弦 <0.35 丢弃 → 回表取正文并复核班级，验证同义改写命中与低分丢弃。
- [ ] 5.3 混合路：两路各自过滤后 RRF（k=60）融合、缺席一路不贡献分数、默认 hybrid，验证双命中排前与单路缺席行为。

## 6. API、溯源与问答

- [ ] 6.1 实现检索端点：query/mode 参数（默认 hybrid）、空查询 400、未登录 401、请求携带 class_id 被丢弃，验证各失败语义。
- [ ] 6.2 命中溯源字段：材料标识与标题、切片序号、字符区间、摘录（取自关系库）、详情/下载入口；响应无磁盘路径与向量分量，验证字段齐全且可回溯。
- [ ] 6.3 实现问答端点：混合检索取前 4 → 有命中才调对话网关、[n] 标注与 citations 顺序一致；无命中固定文案 + 空 citations 且不触网关；客户端 system 消息丢弃，验证三条路径。
- [ ] 6.4 降级语义：向量库或嵌入不可用时 keyword 仍可用、vector/hybrid 返回 503 且无分数，验证停止 qdrant 容器后的行为。

## 7. 隔离与端到端验证

- [ ] 7.1 班级隔离：A 班会话用 B 班独有词检索得 200 + 空 hits；请求体携带 B 班 class_id 前后两次响应一致；跨班材料详情仍同形 404，验证不泄露存在性。
- [ ] 7.2 `docker compose up --build` 全流程 E2E：教师上传 → 切片与向量就绪 → keyword/vector/hybrid 检索 → 命中溯源可打开材料 → 问答带 [1] 标注；学生同班可检索、跨班无命中，逐条对照 specs 场景留证。
- [ ] 7.3 pytest 全量通过（含切片、检索、隔离、降级新增测试），并运行 `openspec validate add-traceable-vector-retrieval --strict` 通过。
