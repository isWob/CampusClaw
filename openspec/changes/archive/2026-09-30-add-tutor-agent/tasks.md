# Tasks: add-tutor-agent

## 1. 数据模型与配置

- [x] 1.1 `schema.sql` 新增 `tutor_prompts`（class_id 唯一、prompt_text、skill_enabled、updated_at、updated_by）、`tutor_sessions`（id uuid 主键、user_id、class_id、created_at）、`tutor_messages`（id、session_id、role、seq、content、created_at）三表，验证建表可重复执行。
- [x] 1.2 `config.py` 确认 `TUTOR_TOP_K`（默认 4）与 `TUTOR_MAX_HISTORY`（默认 6）已就位，复用 `CHAT_BASE_URL/CHAT_API_KEY/CHAT_MODEL`，无新增必填变量，验证缺失对话网关时应用仍可启动。

## 2. 提示词与技能端点（教师 only）

- [x] 2.1 实现 `GET /api/tutor/prompt`：教师读取本班当前提示词与技能状态；学生 403；未登录 401，验证三角色语义。
- [x] 2.2 实现 `PUT /api/tutor/prompt`：教师保存提示词（写 `tutor_prompts` 表，updated_by 取当前 user_id）；学生 403；验证保存后下一轮对话生效、当前轮不受影响。
- [x] 2.3 实现 `GET /api/tutor/skill` 与 `PUT /api/tutor/skill`：教师读取/切换解题引导技能（写 `skill_enabled`）；学生 403；验证开关状态持久化。

## 3. 会话与消息存取

- [x] 3.1 实现 `tutor_sessions` 创建（uuid4 hex）与按 user_id+class_id 取会话；跨用户/跨班会话视为不存在，验证同形不泄露。
- [x] 3.2 实现 `tutor_messages` 追加（seq 自增）与按会话取最近 N 轮（默认 6）历史，验证 user/assistant 成对作为网关上下文。

## 4. 助手编排器与 SSE 生成器

- [x] 4.1 实现 `app/tutor.py` 编排：取会话历史 → hybrid 检索取前 K → 组装 system（教师提示词 + 技能约束段 + 材料段 + [n] 规则）→ 丢弃客户端 system → 调对话网关 stream，验证三段同轮同时进入 system。
- [x] 4.2 实现技能约束段：开启时追加"只给思路引用出处不直接给答案"、关闭时不追加（或明确"可直接给答案"），验证开关后网关 system 明显不同。
- [x] 4.3 无命中返回固定文案 + 空 citations 不触网关；对话网关未配置时有命中返回"对话服务未配置"固定说明，验证两条降级路径。
- [x] 4.4 实现 SSE 生成器：`event: citations` 先发 → 逐段转发网关 `data:` → `event: done` 结束，验证 SSE 事件格式与顺序。

## 5. chat 端点

- [x] 5.1 实现 `POST /api/tutor/chat`：可选 `session_id`（无则新建）、query 必填空则 400、班级取自会话，返回 `text/event-stream`，验证端点契约。
- [x] 5.2 用户消息先入库、assistant 完整消息流结束后入库，验证会话历史可连续追问。
- [x] 5.3 请求体携带 class_id 被丢弃、跨班检索表现为无命中，验证不泄露他班内容。

## 6. 蓝图注册与前端

- [x] 6.1 `app/blueprints/tutor.py` 蓝图并在 `app/__init__.py` 注册，验证端点纳入 JWT 闸门。
- [x] 6.2 `materials.html` 加助手对话 UI（EventSource 消费 SSE + 连续追问 + citations 展示），验证学生可流式提问。
- [x] 6.3 `materials.html` 加教师提示词编辑与技能开关面板（教师可见，学生隐藏），验证保存后下一轮生效。

## 7. 隔离与端到端验证

- [x] 7.1 班级隔离：A 班教师保存提示词/开关技能后 B 班学生提问不受影响；跨班检索表现为无命中，验证不泄露存在性。
- [x] 7.2 pytest 全量通过（含提示词、技能、SSE、会话、隔离新增测试），并运行 `openspec validate add-tutor-agent --strict` 通过。
