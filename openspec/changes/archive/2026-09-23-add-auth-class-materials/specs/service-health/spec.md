## Purpose

提供无需认证的存活检查端点、基于 Docker Compose 的一键部署与 volume 持久化，以及六类核心预置数据，使服务可启动、健康可检、并开箱演示登录与跨班隔离。

## ADDED Requirements

### Requirement: 健康存活端点

系统须（SHALL）提供无需认证的 `GET /health` 端点以上报服务存活状态。服务运行时必须（MUST）返回成功状态，且不得（MUST NOT）要求认证。

#### Scenario: 健康端点返回成功

- **WHEN** 调用方对运行中的服务发起 `GET /health`
- **THEN** 系统返回 200（判定通过：响应状态码 = 200）

#### Scenario: 健康端点无需认证

- **WHEN** 未认证调用方发起 `GET /health`
- **THEN** 系统返回 200 而非 302 重定向到 /login（判定通过：响应 200 且非登录重定向）

### Requirement: Docker Compose 启动与数据持久化

系统须（SHALL）可通过 `docker compose up` 使用提供的 `docker-compose.yml` 启动。密钥与配置必须（MUST）通过环境变量提供给容器，且不得（MUST NOT）打包进镜像。重建容器后数据须（SHALL）仍在。

#### Scenario: 按 README 起 Compose 可访问

- **WHEN** 运维人员按 README 用 `docker compose up` 启动
- **THEN** 服务可访问且 `GET /health` 返回 200（判定通过：compose up 后 `curl /health` 得 200）

#### Scenario: 密钥通过环境注入且不在镜像

- **WHEN** 服务在 Compose 下运行
- **THEN** 签名密钥与密钥通过环境变量提供且不存在于镜像中（判定通过：镜像内搜索不到密钥值）

#### Scenario: 重建容器后数据仍在

- **WHEN** 运维人员 `docker compose down` 后再次 `docker compose up`（复用卷、不复用容器）
- **THEN** 重建后此前上传的材料记录与预置账号仍可查到（判定通过：重建后 `GET /materials` 仍含原记录、预置账号仍可登录）

### Requirement: 六类核心预置数据

系统须（SHALL）随服务提供幂等的预置数据，至少包含六类核心数据：班级 A、班级 B、教师 A（属 A 班）、学生 A1（属 A 班）、学生 B1（属 B 班）、A 与 B 两班各至少一条材料；账号密码须（SHALL）以哈希存储。各身份须（SHALL）能查到其对应班级的数据，且重复执行不产生重复记录。

#### Scenario: 六类核心数据均可查到

- **WHEN** 服务在空库上完成初始化
- **THEN** 班级 A 与 B、教师 A、学生 A1 与 B1、A/B 两班材料均存在且可查（判定通过：班级 A、B 各存在 1 条；教师 A 与学生 A1/B1 各存在 1 个；以教师 A 登录可查到 A 班材料；以学生 A1 与 B1 登录分别可查到 A、B 班材料）

#### Scenario: 预置数据可重复执行

- **WHEN** 预置数据脚本被重复执行
- **THEN** 系统不报错且不产生重复账号或材料记录（判定通过：重复执行后班级/用户/材料记录数与首次一致）
