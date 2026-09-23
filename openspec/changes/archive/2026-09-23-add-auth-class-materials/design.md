## Context

全新仓库：目前没有任何源码，只有 `openspec/` 规划目录。待建一个单一后端服务，提供用户名/密码登录、教师/学生角色、按班级的材料访问与 `GET /health`，通过 Docker Compose 启动。动机见 `proposal.md - Why`；外部可观察行为定义在 `specs/user-auth`、`specs/class-materials`、`specs/service-health`，本文档说明"如何做"。

技术栈：**Python 3 + Flask + SQLite（文件型数据库）+ Werkzeug 密码哈希 + Flask 服务端签名会话**，用 Docker Compose 容器化。选 Flask + SQLite 是因其零外部 DB 依赖、依赖少、单条 compose 即可跑起课程 demo。

## Goals / Non-Goals

**Goals:**
- 一个满足三个 spec 的可部署后端服务。
- 认证与班级数据边界在服务端强制，任何客户端行为都无法绕过。
- 密码仅以加盐哈希存储；所有密钥在运行时从环境变量读取。
- 一条命令启动（`docker compose up`）且 `GET /health` 可用；预置数据开箱可登录、可演示跨班隔离。

**Non-Goals:**
- 不做 SSO/OAuth、无密码或多因子认证 —— 只做用户名 + 密码。
- 不做比 `teacher`/`student` + 班级归属更细的权限模型。
- 不做单独 SPA 前端；登录与受保护页面由后端服务端渲染（Jinja2）。
- 不做材料版本管理、编辑、全文检索、在线预览、转码。
- 不做作业提交与批改、检索问答、对话助手、生产级 HA（见 `proposal.md - Non-Goals`）。
- 不迁移已有数据（库从空开始；种子数据见下）。

## Decisions

### Decision 1: 单一 Flask 应用 + SQLite 文件库
一个 Flask app，按 blueprint 拆 `auth`/`materials`/`health`；SQLite 单文件数据库挂载到卷。理由：课程范围小、零外部 DB 依赖、compose 简单。替代：FastAPI + Postgres（更强但偏重）、多服务拆分（否决）。

### Decision 2: 会话与密码 —— 采用会话（Session），不采用 Token（JWT）
- **会话**：结论是**采用会话（Session，签名 Cookie），不采用 Token（JWT）**。用 Flask 内置 `session`（基于 `itsdangerous` 签名 Cookie），`SECRET_KEY` 来自环境变量；会话存 `user_id` + `role`，不存密码。理由：重定向到登录面向浏览器，Flask session 开箱即用，密钥留在服务端；登出/改角色只需清 Cookie。替代：无状态 JWT —— 登出/改角色失效难、密钥管理面大，否决。
- **密码**：用 `werkzeug.security.generate_password_hash` / `check_password_hash`（默认现代算法如 scrypt/pbkdf2，自带盐），**仅存加盐哈希、禁止明文**；明文不落库、不记日志、不返回。校验时对提交内容做哈希与存储比较，绝不读取或比较明文。替代：passlib argon2（可，稍重）、裸 SHA-2（否决，过快）。
- **Cookie 属性与会话固定**：会话 Cookie 设 `HttpOnly`（脚本不可读）+ `SameSite=Lax`（同源限制跨站携带）；本机 HTTP 演示不设 `Secure`（否则浏览器拒绝写入 Cookie）。登录成功先 `session.clear()` 再写入身份，换发新会话以防会话固定（session fixation）。登录失败统一响应"凭据无效"，不区分用户名不存在与密码错误；用户不存在时也执行一次哑哈希比较（dummy hash）使两条失败路径耗时与响应同形，防账号枚举。
- **当前会话身份**：`GET /api/me` 返回 `{username, role, class_id}`（未登录 401），供页面判定身份与是否渲染上传入口；授权仍只以服务端会话为准，不信客户端任何自报身份。

### Decision 3: 密钥只来自环境变量，缺失快速失败
`SECRET_KEY`、`DATABASE_PATH`、`UPLOAD_DIR`、`MAX_UPLOAD_BYTES` 与种子账号口令（`SEED_TEACHER_A_PASSWORD`、`SEED_STUDENT_A1_PASSWORD`、`SEED_STUDENT_B1_PASSWORD`）均从环境变量读取；缺失 `SECRET_KEY` 或任一种子口令时拒绝启动。`.env` 被 git 忽略，仅用于本地/开发；镜像不打包密钥，`.env.example` 入库并给出可复现的占位/演示值。

### Decision 4: 班级边界在数据访问层强制（服务端过滤）
每次材料读取/列表按会话中调用方的 `class_id` 过滤；上传以教师自身 `class_id` 写入；列表查询无条件附加 `WHERE materials.class_id = ?`；客户端在 query/Header/表单传入的 `class_id` 一律忽略；**班级过滤放在服务端**，不靠前端隐藏按钮。按 id 直取材料采用"先取行再校验"（fetch-then-check）：先按 id 取行，再比对材料 `class_id` 与会话 `class_id`。**跨班访问与 id 不存在统一返回同形 404**（不返回 403，避免泄露资源存在性；真实原因只写服务端日志），该返回码约定写进 README。理由：spec 要求服务端不可绕过的过滤；同形 404 防资源枚举。替代：仅路由中间件（新路由易遗漏，否决）、跨班返 403（泄露存在性，否决）。

### Decision 5: 上传端点按角色授权，服务端返回 403
上传路由检查会话角色，学生则返回 `403 Forbidden` 且不触达存储。独立于前端。理由：spec 要求端点本身拒绝学生并返回 403。

### Decision 6: 材料存储 —— 元数据在 SQLite，文件块在挂载卷
`materials` 表存元数据（`id, class_id, uploader_id, filename, stored_path, created_at`）；上传文件块写入挂载卷 `UPLOAD_DIR`，路径记入元数据。理由：简单、单 compose。替代：对象存储（未来替换点，存储接口隔离，不影响 spec）。

### Decision 7: 数据模型（SQLite 表）
- `classes(id, name)`
- `users(id, username UNIQUE, password_hash, role, class_id)`
- `materials(id, class_id, uploader_id, filename, stored_path, created_at)`
用户的 `class_id` 即其归属边界；教师携带其执教班级的 `class_id`，使上传落入教师本班。

### Decision 8: 预置（种子）数据
启动初始化/种子脚本预置两个班级（A 班、B 班）、每班一名教师 + 一名学生（`teacher_a`/A 班、`student_a1`/A 班、`student_b1`/B 班，密码以哈希存储，明文口令来自 Decision 3 的环境变量），并为 A/B 两班各放一条标题可区分的材料（标题各自带班级标识，如"A 班…/B 班…"，种子文件落 `UPLOAD_DIR`，元数据落 materials 表），使登录与跨班 demo 开箱可用。脚本幂等：以 `username`/班级名唯一约束做"存在即跳过"，重复执行不产生重复账号或材料，也不覆盖教师后续上传。理由：课程演示需要可登录账号与可对比的跨班隔离样例。

### Decision 9: 服务端渲染登录 + 受保护页面，与 JSON/表单 API 并存
Flask 用 Jinja2 渲染登录页与受保护材料页，并提供上传/列表/健康的 JSON/表单端点。会话闸门：未认证浏览器请求重定向 `/login`，未认证 JSON API 调用返回"需要认证"状态；`/health` 与 `/login` 在闸门白名单。端点约定：`POST /api/login`（JSON，成功 200/失败 401）、`POST /api/logout`、`GET /api/me`、`GET /api/materials`（列表 JSON）、`POST /api/materials`（multipart 上传，成功 201）、`GET /api/materials/<id>`（详情 JSON）、`GET /api/materials/<id>/download`（文件下载）；页面路由 `GET /login` 与 `GET /materials`（受保护，服务端渲染）。判定"浏览器页面 vs API"以路径前缀 `/api/` 与 `Accept` 头区分：页面导航未登录 302 到 `/login`，`/api/*` 未登录一律 401 且响应体不含材料标题、正文或路径。

### Decision 10: 上传校验链 —— 白名单先行、服务端生成存储名、失败无残留
上传按"会话 → 角色 → 校验 → 落盘 → 入库"顺序，任何一步失败都回到"无文件、无记录"：
1. 扩展名白名单仅 `.txt` / `.md`（取小写后缀，黑名单否决），不匹配返回 400，不触盘。
2. 大小上限 `MAX_UPLOAD_BYTES` 经 Flask `MAX_CONTENT_LENGTH` 配置，超限由框架返回 413（不读完请求体）。
3. 内容须为非空 UTF-8 文本，解码失败/空内容返回 400，不触盘。
4. 存储名由服务端用 `uuid4` + 白名单后缀生成（`UPLOAD_DIR/<uuid>.<ext>`）；客户端文件名经 `werkzeug.utils.secure_filename` 净化后仅存入 `materials.filename` 作展示，绝不参与路径拼接（防路径穿越）。
5. 先落盘、后写 materials 行；写库抛错则删除已落盘文件，杜绝孤儿文件；上传整体在 try/except 中保证无残留。
替代：先入库再落盘（产生孤儿记录，否决）、对象存储（未来替换点，不影响 spec）。

### Decision 11: 材料详情与下载走鉴权接口，上传目录不静态暴露
`GET /api/materials/<id>` 与 `GET /api/materials/<id>/download` 都先过会话闸门，再按 Decision 4 fetch-then-check：本班返回 200（详情元数据不含 `stored_path` 等磁盘绝对路径；下载用 `send_from_directory` 且目录固定为 `UPLOAD_DIR`、文件名为服务端生成的存储名），跨班/不存在同形 404。不为 `/uploads` 配置任何静态路由或 Static 文件目录，直接猜测磁盘路径取不到文件。替代：静态目录 + 前端隐藏（无鉴权，否决）。

## 隔离与上传链路

班级过滤放在服务端（Decision 4）；上传链路按 **文件 → 解析 → 入库 → 列表** 四阶段：

1. **文件**：客户端 `POST /materials`（multipart，文件 + 可选元数据）；会话校验（未登录 → 重定向/返回 401），角色校验（`role != teacher` → 返回 `403 Forbidden`，结束，不落盘、不写记录）。
2. **解析**：解析 multipart 与文件（类型/大小校验）；班级取自会话 `user.class_id`（不接受客户端传值，服务端强制）。
3. **入库**：文件落盘到 `UPLOAD_DIR/<uuid>-<filename>`；写入 `materials` 行（`class_id = 教师班`、`uploader_id = user.id`、`filename`、`stored_path`、`created_at`）。
4. **列表**：`GET /materials` 经 Decision 4 按本班 `class_id` 过滤，本班列表可查到该记录。

## 部署：Docker Compose 启动、volume 持久化与 GET /health

- **Docker Compose 启动**：`docker-compose.yml` 定义 `web`（Flask，gunicorn 或 `flask run`）服务；`SECRET_KEY` 等密钥经 `environment` 注入（绝不打包进镜像）。
- **volume 持久化**：命名卷挂载 SQLite 文件与上传目录，数据跨容器重建保留（`docker compose down` 不丢数据，回滚只需换镜像）。
- **GET /health**：无需认证，返回 `200` + `{"status":"ok"}`；不在会话闸门内（白名单），就绪即上报成功。
- 启动顺序：建表/迁移 → 灌种子数据（幂等）→ 读环境变量（缺 `SECRET_KEY` 即失败）→ 服务就绪，`GET /health` 上报成功。

## Risks / Trade-offs

- [签名 Cookie 会话登出/改角色不能即时吊销] → 登出清客户端 Cookie，会话设较短有效期；日后可加服务端黑名单且不影响 spec。
- [SQLite 单文件不支持多写副本水平扩展] → 课程范围足够；需扩展时换 Postgres，存储接口已隔离。
- [教师仅关联一个班级] → 符合当前需求；多班加关联表，属非破坏性扩展。
- [Werkzeug 哈希参数须跟进] → 用其默认现代算法（scrypt），勿手设弱参数。
- [数据访问层集中过滤，新路由直接查材料可绕过] → 通过统一材料读取仓库函数强制；任何新增材料查询须代码评审把关。

## Deployment Plan

1. `docker-compose.yml` 定义 `web` 服务，命名卷挂载 SQLite 文件与上传目录（volume 持久化）。
2. `SECRET_KEY` 等经 `environment` 从被 git 忽略的 `.env` 注入；镜像不含密钥。
3. 启动：建表 → 种子（幂等）→ 读密钥（缺失即拒）→ 服务。就绪后 `GET /health` 上报成功。
4. 回滚：`docker compose down` + 重新部署前一镜像；SQLite 数据在其卷上持久化。

## Open Questions

- 无影响 spec 或任务分解的问题。（栈 = Flask/SQLite 已定；若用户日后倾向独立 SPA，spec 不变 —— 仅 design 与 tasks 需修订。）
