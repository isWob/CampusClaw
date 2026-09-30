# Design: add-tutor-agent

## Context

第 4 课已交付本班知识库检索（关键字/向量/混合 RRF）与先检索后生成的非流式问答端点 `/api/ask`：混合检索取前 4 条切片 → 有命中才调对话网关 → `[n]` 标注与 citations 一致 → 客户端 system 丢弃 → 无命中固定文案不触网关。第 5 课要在同一系统上做成解题助手智能体：教师用提示词定角色、用解题引导技能约束回答方式、检索本班知识库提供可回溯依据，三者须在同一轮回答中同时生效，并以 SSE 流式返回支持连续追问。

课程课件（week05）给出的行为口径：提示词由教师编写保存且从下一轮对话生效（学生不可改）、解题引导技能开启时只给思路并引用本班材料标题与位置不直接给最终答案（关闭后回答方式明显不同、学生不可开关）、知识库命中标出处无命中说明「资料中未找到相关内容」不编造、班级只从登录会话读取、SSE 逐段返回支持连续追问、对话历史按会话保存、客户端 system 丢弃。本仓库沿用 Flask + SQLite 主体，对话网关复用第 4 课已引入的 `httpx` 与 `CHAT_BASE_URL/CHAT_API_KEY/CHAT_MODEL`，SSE 用 Flask 原生 `stream_with_context`。以下决策保证**行为规约与课件一致，实现选型贴合既有栈**。

## Goals / Non-Goals

- [x] 提示词、技能、检索三者在同一轮回答中同时生效，逐条可对照课件验收。
- [x] 提示词保存后从下一轮对话生效（当前轮仍用旧提示词），学生不可查看/修改。
- [x] 解题引导技能开启给思路不直接给答案、关闭回答明显不同，学生不可开关。
- [x] SSE 流式逐段返回、支持连续追问、对话历史按会话保存。
- [x] 保持第 4 课非流式 `/api/ask` 端点与既有检索/上传/认证契约不变。
- [x] 不做作业提交/批改、关怀式对话、提示词版本历史、多模型选择、内容审核、跨会话长期记忆。

## Decisions

### D1. 数据模型：三张表，提示词与技能按班级生效

- `tutor_prompts`：每班级一行（`class_id` 唯一），存当前生效提示词 `prompt_text`、解题引导技能开关 `skill_enabled`（0/1）、`updated_at`、`updated_by`（教师 user_id）。无行时视为默认提示词与技能关闭。
- `tutor_sessions`：`id`（uuid4 hex 主键）、`user_id`、`class_id`、`created_at`。会话归属用户与班级，跨班会话不可复用。
- `tutor_messages`：`id`、`session_id`、`role`（`user`/`assistant`）、`seq`（会话内自增序号）、`content`、`created_at`。
- 提示词与技能按班级生效而非按用户：同班学生共享教师设定的助手行为；学生不可查看提示词内容（端点 403），但提问时助手行为受其约束。
- 备选：按用户存提示词——否决：课件明确"教师编写保存"为学生设定助手角色，按班级贴合语义且避免提示词内容通过学生端点泄露。

### D2. "下一轮生效"语义：保存即写表，编排读表取当前值

- 教师保存提示词（PUT /api/tutor/prompt）→ 立即写 `tutor_prompts` 表。
- 助手编排（POST /api/tutor/chat）→ 请求开始时读 `tutor_prompts` 表当前值作为本轮 system 提示词。
- "下一轮生效"在单请求语义下自然满足：保存与提问是不同请求；保存后下一次提问请求读到的就是新值。
- 不引入版本号与"进行中轮次"概念（Non-Goals 明确不做版本历史）；同一请求内不会既保存又提问。
- 技能开关同理：PUT /api/tutor/skill 立即写表，下一次 chat 请求读到新值。

### D3. 解题引导技能：通过 system 提示词约束回答方式

- 技能开启：服务端在 system 提示词中追加约束段——「只给解题思路，引用本班材料的标题与位置（如 [1]、[2]），不直接给出最终答案」。
- 技能关闭：system 提示词中不加该约束段（或明确指示"可直接给出答案"），使同一问题回答方式明显不同。
- 教师保存的提示词规定助手角色与行为边界（写在前面），技能约束段由服务端组装拼接其后；两者都在 system 消息中，单轮同时生效。
- 检索结果作为 system 中的"材料"段附在最后，与前两段一起组装。
- 备选：技能作为独立 tool call——否决：课件要求技能在回答方式上约束，system 提示词最直接且与课件口径一致。

### D4. 助手编排：检索 → 组装 system → 网关流式生成

- 每次提问：①取会话历史最近 `TUTOR_MAX_HISTORY`（默认 6）轮 → ②hybrid 检索取前 `TUTOR_TOP_K`（默认 4）条切片 → ③无命中返回固定文案 + 空 citations 不触网关 → ④有命中组装 system（教师提示词 + 技能约束段 + 材料 + [n] 标注规则）→ ⑤丢弃客户端 system → ⑥调对话网关 `stream=True` → ⑦SSE 逐段转发 → ⑧完整 assistant 消息入库。
- 材料 context 格式与第 4 课 `/api/ask` 一致：`[n] 材料标题（切片n）：正文摘录`。
- citations 字段与第 4 课同构（材料标识、标题、切片序号、字符区间、摘录），通过 SSE 的最终事件下发。
- 无命中时仍以 SSE 返回（单事件 `data: {"answer":"资料中未找到相关内容","citations":[]}`），保持端点响应类型一致。

### D5. SSE 流式：Flask stream_with_context + 网关 stream 透传

- 端点 `POST /api/tutor/chat` 返回 `Response(stream_with_context(generate()), mimetype='text/event-stream')`。
- `generate()` 生成器：先发 `event: citations` 事件下发检索命中；再逐段读对话网关 SSE `data:` 行，原样以 `data: {delta}` 转发；最后发 `event: done` 标记结束。
- 对话网关未配置（`CHAT_BASE_URL` 空）：有命中时返回固定文案"检索到相关内容，但对话服务未配置"（单 SSE 事件），不触网关；无命中仍走固定文案路径。
- EventSource 协议：每条 `data: ...\n\n`；客户端用浏览器 `EventSource` 或 fetch 流消费。
- 备选：WebSocket——否决：单向流式输出 SSE 足够且更简，与课件"服务器推送事件"口径一致。

### D6. 会话管理：session_id 可选，按用户+班级归属

- 请求不带 `session_id`：新建会话（uuid4 hex），写入 `tutor_sessions`，归属当前用户与班级。
- 请求带 `session_id`：取会话行，若 `user_id != 当前用户` 或 `class_id != 当前班级` → 视为不存在（同形 404，不泄露存在性）。
- 用户消息先入库（seq 自增），再调网关；assistant 完整消息在流结束后入库。
- 历史轮次从 `tutor_messages` 取该会话最近 N 轮（user/assistant 成对）作为网关上下文。

### D7. 安全：教师 only 端点 + 班级取自会话 + 网关密钥仅服务端

- `GET/PUT /api/tutor/prompt` 与 `GET/PUT /api/tutor/skill`：仅教师（`role != teacher` → 403），学生不可查看提示词内容或开关技能。
- `POST /api/tutor/chat`：登录即可（教师与学生均可提问）。
- 班级标识仅取自 `g.current_user["class_id"]`；请求体携带的 class_id 被丢弃。
- 跨班检索表现为无命中（沿用第 4 课），跨班会话表现为会话不存在。
- 网关密钥 `CHAT_API_KEY` 仅存服务端环境变量，SSE 响应不含密钥与向量分量。

## Risks / Trade-offs

- 提示词"下一轮生效"无版本机制 → 严格"进行中轮次用旧值"未实现；课程边界内按请求粒度满足，且 Non-Goals 排除版本历史。
- SSE 长连接占 worker → 课程单实例边界内可接受；gunicorn 默认 sync worker 在低并发演示场景足够，必要时可切 gevent worker。
- 网关流式失败中途断流 → assistant 消息以已收片段入库（best-effort），不阻塞会话继续追问。
- 解题引导技能依赖模型遵循 system 约束 → 课程网关模型能力范围内可观察"明显不同"，不保证 100% 可控。

## Migration Plan

1. 数据模型（三表） → 2. 提示词/技能端点（教师 only） → 3. 会话与消息存取 → 4. 助手编排器与 SSE 生成器 → 5. chat 端点 → 6. 前端对话 UI + 教师管理面板 → 7. 测试与 E2E。
bootstrap 幂等建表（IF NOT EXISTS）；无手工迁移、无停机步骤（单实例重启即生效）。

## Open Questions

- 无（对话网关复用第 4 课配置；SSE 用 Flask 原生；提示词与技能配置无新增必填环境变量）。
