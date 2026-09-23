## 1. 项目脚手架与依赖

- [x] 1.1 创建 Flask 项目结构（`app/` 含 `__init__.py`、`config.py`、`db.py`，`blueprints/` 下 `auth`、`materials`、`health`，`templates/` 放登录与材料页），验证 `flask --app app` 可导入且无报错。
- [x] 1.2 把依赖（`flask`、`gunicorn`、`werkzeug`、`python-multipart`、`jinja2`）写入 `requirements.txt`，验证 `pip install -r requirements.txt` 成功。
- [x] 1.3 添加 `.gitignore`（覆盖 `.env`、`__pycache__/`、`instance/`、`uploads/`），验证 `git status` 不追踪密钥与上传文件。

## 2. 配置与密钥来自环境变量

- [x] 2.1 实现 `config.py`：从环境变量读 `SECRET_KEY`、`DATABASE_PATH`、`UPLOAD_DIR`、`MAX_UPLOAD_BYTES`、`SEED_TEACHER_A_PASSWORD`、`SEED_STUDENT_A1_PASSWORD`、`SEED_STUDENT_B1_PASSWORD` 并暴露配置对象，验证可读取各值。
- [x] 2.2 当 `SECRET_KEY` 或任一种子口令缺失时应用拒绝启动（导入/启动时快速失败），验证变量未设时启动以清晰错误失败。
- [x] 2.3 创建已提交的 `.env.example` 说明所需变量并确认不含真实密钥值（仅占位/演示值）；验证 `.env` 被 git 忽略。

## 3. SQLite 模型与建表/种子

- [x] 3.1 用 `sqlite3` 或 SQLAlchemy 定义 `classes`/`users`/`materials` 表（见 design 决策 7），验证在空库建出三张表。
- [x] 3.2 编写建表/迁移脚本（`create_all` 或 `schema.sql`），验证 fresh DB 建表成功。
- [x] 3.3 编写幂等种子脚本：六类核心数据——班级 A/B、教师 A（teacher_a）、学生 A1（student_a1）/B1（student_b1）、A 与 B 两班各至少一条标题可区分的材料（文件名分别带 A/B 班标识，种子文件落 UPLOAD_DIR；账号口令来自 SEED_* 环境变量并以哈希存储），验证重复执行不报错、不产生重复记录，且以教师 A/学生 A1/B1 登录可查到对应班级材料、用 B 班标题在 A 班列表查不到。

## 4. 密码哈希

- [x] 4.1 用 `werkzeug.security` 实现 `hash_password`/`check_password`，验证 `check_password(pw, hash_password(pw))` 为 True 且存储输出不含明文。
- [x] 4.2 加单元测试：错误密码时不把明文写进任何抛出/日志信息。

## 5. 会话、登录/登出与认证闸门

- [x] 5.1 配置 Flask 签名 Cookie 会话（`SECRET_KEY`），存 `user_id` + `role` + `class_id`（不存密码），Cookie 设 HttpOnly、SameSite=Lax（本机 HTTP 不设 Secure），验证可签发并校验会话、会话中可读出 role ∈ {teacher, student} 与 class_id，且 Set-Cookie 含 HttpOnly/SameSite 属性。
- [x] 5.2 实现 `POST /api/login`：成功返回 2xx 并设会话（登录成功先 `session.clear()` 换发防会话固定）；失败返回 401 且不设会话、统一文案"凭据无效"不指明哪个字段错（用户不存在也做哑哈希比较），验证两条路径由测试覆盖且响应同形。
- [x] 5.3 实现 `POST /api/logout` 清除会话，验证 Cookie 被清除且登出后受保护资源不可访问（302→/login 或 401）。
- [x] 5.4 实现会话闸门：未认证浏览器页面请求（`GET /materials`）返回 302 重定向 `/login`，未认证 `/api/*` 调用返回 401 且响应体不含材料标题/正文/路径，验证受保护页 302、受保护 API 401（`/health`、`/login` 在白名单）。
- [x] 5.5 实现 `GET /api/me` 返回当前会话 `{username, role, class_id}`，验证已登录返回 200 且 role 正确、未登录返回 401。

## 6. 健康端点

- [x] 6.1 实现 `GET /health` 无需认证返回 `200` + `{"status":"ok"}`，验证未认证请求得 200 而非登录重定向。

## 7. 材料上传（仅教师，403）入知识库

- [x] 7.1 实现材料仓库单一读取路径，按调用方 `class_id` 过滤每次查询（design 决策 4）：列表 SQL 带 `WHERE class_id = ?`，按 id 查询先取行再核对班级（fetch-then-check），验证两条路径都存在且跨班与 id 不存在返回同形 404。
- [x] 7.2 实现 `POST /api/materials`：会话 + `role != teacher` 返回 `403 Forbidden` 且不触达存储，验证学生上传返回 403、无落盘、无记录。
- [x] 7.3 教师上传成功返回 201：文件以服务端 uuid 存储名落 `UPLOAD_DIR`、插入 `materials` 行（教师班 `class_id` + `uploader_id`，忽略表单任何 class_id），验证响应 201、记录存在且文件在磁盘上。
- [x] 7.4 上传校验链（design 决策 10）：扩展名白名单 `.txt`/`.md`（其他 400）、超 `MAX_UPLOAD_BYTES` 返回 413、非空 UTF-8 校验失败 400；存储名服务端生成、客户端文件名经 `secure_filename` 净化不参与路径；落盘后写库失败须删除文件。验证 `.exe`/超限/空文件/`../` 文件名各一次，库与磁盘均无残留。
- [x] 7.5 实现鉴权详情与下载：`GET /api/materials/<id>`（本班 200，元数据不含磁盘绝对路径）、`GET /api/materials/<id>/download`（本班 200 返回文件）；验证未登录 401、跨班 404，且不为 `/uploads` 配置静态路由、直接猜测文件路径取不到文件。

## 8. 按班级隔离的材料列表

- [x] 8.1 实现 `GET /api/materials` 经仓库读取按调用方 `class_id` 范围返回，验证 A 班调用方即使按 id 或在 query/表单携带他班 class_id 也看不到 B 班材料（404 且无他班记录）。
- [x] 8.2 加集成测试：跨班访问不返回 B 班材料（不论客户端如何指定目标），确认边界在服务端（design 决策 4）；并验证教师上传后本班列表可查到该记录。

## 9. Docker Compose 启动与持久化

- [x] 9.1 编写 `docker-compose.yml`：`web`（Flask）服务 + 命名卷（SQLite 文件与上传目录），验证 `docker compose config` 通过校验。
- [x] 9.2 编写 `Dockerfile`：装依赖、建表/种子、启动 gunicorn，密钥仅经 `environment` 来自被 git 忽略的 `.env`，验证镜像构建成功且不含密钥值。
- [x] 9.3 运行 `docker compose up`，验证 `GET /health` 返回 200 且 `SECRET_KEY` 来自环境变量；再 `docker compose down` 后重新 `up`（复用卷），验证 /health 仍 200 且此前材料记录与预置账号仍在（volume 持久化）。

## 10. 端到端验证

- [x] 10.1 在 compose 下跑全流程：教师登录(2xx+会话) → 上传 .txt/.md(201+入库) → 列表见新记录 → 详情/下载本班 200；学生登录 → 上传返回 403（无入库） → 列表只见本班；A 班用户读 B 班材料 id 得到与不存在 id 同形 404；`.exe` 400、超限 413 且无残留；验证每步对应 `specs/user-auth`、`specs/class-materials`、`specs/service-health` 场景。
- [x] 10.2 验证未登录访问受保护页 302/登录、受保护 API 401（无标题/正文/路径泄露）；`/api/me` 身份正确；密码仅哈希、密钥只在环境变量；六类核心数据可查且预置脚本幂等。

## 11. 规划校验

- [x] 11.1 在仓库根运行 `openspec validate --strict --changes add-auth-class-materials`，验证严格校验通过、无 error 与 warning。
