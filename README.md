# CampusClaw

CampusClaw 是面向中小学的教研智能体。本仓库交付**迭代 1：教研材料与知识库底座**——
登录与角色权限、按班级的服务端数据边界、教研材料上传入库，通过 Docker Compose 一键启动。
判定标准不是界面是否好看，而是：能登录、能隔离、能上传入库、第三方能按本 README 复现。

技术栈：Python 3 + Flask + SQLite + Werkzeug 密码哈希 + Flask 签名 Cookie 会话 + Jinja2 服务端渲染。

## 快速开始

```bash
cp .env.example .env          # 按需修改 SECRET_KEY 与预置账号口令
docker compose up --build -d  # 一条命令启动（建表 → 幂等种子 → gunicorn）
```

- 应用地址：<http://localhost:8080>（宿主机端口可用 `.env` 的 `WEB_PORT` 修改）
- 健康检查：`GET http://localhost:8080/health` → `200 {"status":"ok"}`（无需登录）

停止与数据：

```bash
docker compose down           # 停止并删除容器，命名卷保留，数据不丢
docker compose up -d          # 再次启动，账号与材料仍在
docker compose down -v        # 一并删除数据卷，仅用于主动重置
```

## 预置账号（种子数据，幂等）

| 用户名 | 角色 | 班级 | 口令来源 |
|---|---|---|---|
| `teacher_a` | 教师 | A班 | `SEED_TEACHER_A_PASSWORD` |
| `student_a1` | 学生 | A班 | `SEED_STUDENT_A1_PASSWORD` |
| `student_b1` | 学生 | B班 | `SEED_STUDENT_B1_PASSWORD` |

`.env.example` 给出可直接演示的口令；种子另含 A/B 两班各一条标题可区分的材料。
种子脚本可重复执行，不产生重复账号/材料，也不覆盖后续上传。

## 能力范围（本迭代做什么）

- **认证（user-auth）**：用户名/密码登录、登出、签名 Cookie 会话；未登录访问受保护页面 302 跳 `/login`，未登录调用 `/api/*` 返回 401 且不含任何材料数据；密码仅以加盐哈希存储；`SECRET_KEY` 只来自环境变量，缺失即拒绝启动。
- **授权（class-materials）**：仅教师可上传（学生调用上传端点返回 403，且不触达存储）；教师/学生均可查看、下载本班材料。
- **班级隔离（服务端强制）**：所有材料读取按**会话中的** `class_id` 过滤，query/Header/表单传入的 `class_id` 一律忽略；按 id 访问采用"先取行再校验"。
- **上传入库**：仅接受 `.txt` / `.md` 非空 UTF-8 文本，大小受 `MAX_UPLOAD_BYTES` 限制（默认 5 MiB，超限 413）；服务端生成 uuid 存储名，客户端文件名不参与路径；任一步失败，磁盘与数据库均无残留。
- **运维（service-health）**：`GET /health` 免认证存活检查；Docker Compose 单服务启动；命名卷持久化 SQLite 与上传目录。

### HTTP 接口约定

| 方法与路径 | 说明 | 未登录 | 越权 |
|---|---|---|---|
| `GET /health` | 存活检查 | 200 | — |
| `POST /api/login` | JSON 登录 | — | 凭据错误 401（统一文案，不区分用户名/密码） |
| `POST /api/logout` | 登出 | 200 | — |
| `GET /api/me` | 当前会话身份 | 401 | — |
| `GET /api/materials` | 本班材料列表 | 401 | 只返回会话所属班级 |
| `POST /api/materials` | 上传（multipart，字段名 `file`） | 401 | 学生 403 |
| `GET /api/materials/<id>` | 材料详情 | 401 | **跨班 404** |
| `GET /api/materials/<id>/download` | 文件下载 | 401 | **跨班 404** |
| `GET /login`、`GET /materials` | 服务端渲染页面 | 302 → `/login` | — |

**跨班访问统一返回 404，且与"材料 id 不存在"响应完全同形**（不返回 403，避免泄露资源是否存在；
真实原因只记录在服务端日志）。上传目录不做静态暴露，直接猜测 `/uploads/...` 路径取不到文件。

## 明确不做（Non-Goals）

- 检索与问答：不做全文/语义检索、RAG、基于材料的问答（本迭代知识库只负责存正文）。
- 对话助手：不提供聊天式 AI。
- 作业提交与批改：不支持提交、批改、评分。
- SSO/OAuth、MFA、无密码登录、生产级高可用与多副本负载均衡。
- 超出 教师/学生 + 班级归属 的更细权限模型（不设跨班超级管理员）。
- 材料版本管理、在线编辑、预览渲染、转码、去重。

## 部署形态与边界

- **单实例**：会话为签名 Cookie、SQLite 为单文件库，本迭代只声明单容器实例；多副本/水平扩展留待后续迭代。
- Compose 中只有 `web` 一个服务并映射宿主端口，无其他端口对外暴露；密钥全部经 `environment` 从被 git 忽略的 `.env` 注入，镜像内不含任何密钥值。

## 本地开发与测试

```bash
pip install -r requirements.txt
python -m pytest -q          # 33 项单元/集成测试
python -m app.bootstrap      # 初始化库 + 种子（需要环境变量，参考 .env.example）
flask --app wsgi:app run     # 本地运行（也可由 gunicorn wsgi:app 启动）
```

## 迭代 1 说明（验收结论与设计决策）

- **流程**：本变更走 OpenSpec 的 Apply → Verify → Archive；任务清单见
  `openspec/changes/add-auth-class-materials/tasks.md`，勾选均以 `python -m pytest` 实际结果与
  Compose 实跑命令为准。
- **ADR（用自己的话记录的关键取舍）**：
  1. **会话而非 JWT**：同源浏览器站点，用 Flask 签名 Cookie 会话，密钥不出服务端，登出即时生效；
     JWT 登出难作废、载荷易被当成授权依据，否决。
  2. **跨班返同形 404 而非 403**：403 等于告诉调用方"资源存在但你没权"，便于枚举；
     对外统一 404，把真实原因留到服务端日志。
  3. **班级边界只在服务端数据访问层**：租户标识只取自会话，任何客户端传入一律忽略；
     前端隐藏按钮只降低误操作，不构成访问控制（curl 携 Cookie 改 id 同样被拒）。
- **Scenario 判定结论**：教师登录→上传 201→列表可见、学生上传 403 无残留、A 班访问 B 班 id 同形 404、
  未登录页面 302/API 401 且无材料数据泄露、`.exe` 400/超限 413/空文件 400 均无残留、
  down 再 up 数据仍在——以上均由 pytest 与 Compose 实跑证据支持。
