# user-auth Delta

## MODIFIED Requirements

### Requirement: 账号使用用户名和密码登录

系统须（SHALL）允许教师和学生通过提交用户名和密码进行认证。凭据正确时系统须（SHALL）签发 JWT（JSON Web Token，三段结构 header.payload.signature）并返回给调用方，载荷须（SHALL）包含用户标识（sub）、角色（role）、班级标识（class_id）、签发时间（iat）、过期时间（exp）与唯一标识（jti）；凭据错误时系统须（SHALL）拒绝登录且不签发令牌，并不透露是哪个字段错误。系统不得（MUST NOT）在登录成功后创建服务端会话记录或下发服务端会话标识。

#### Scenario: 教师登录成功

- **WHEN** 教师提交正确的用户名和密码
- **THEN** 系统返回 2xx，响应体含 JWT，且 JWT 载荷含 sub、role=teacher、class_id、iat 与 exp（判定通过：响应 2xx + 响应体含三段式 token + 解码载荷含上述字段 + 无服务端会话记录创建）

#### Scenario: 学生登录成功

- **WHEN** 学生提交正确的用户名和密码
- **THEN** 系统返回 2xx 并签发 JWT（判定通过：同上，role=student）

#### Scenario: 凭据错误不建立会话

- **WHEN** 调用方提交不存在的用户名或错误密码
- **THEN** 系统返回失败状态且不签发 JWT，并以通用"凭据无效"错误拒绝、不指明哪个字段错（判定通过：响应非 2xx + 无 JWT 返回 + 响应体不区分用户名/密码错误）

### Requirement: 未登录访问受保护资源被引导到登录页

系统须（SHALL）对每个受保护页面与端点要求有效 JWT。JWT 须（SHALL）从 Authorization: Bearer 头或 HttpOnly Cookie 中提取、经签名验证与过期检查且其唯一标识（jti）不在吊销清单中。未认证的浏览器页面导航须（SHALL）被重定向到登录页；未认证的 API 调用须（SHALL）返回需要认证状态，且不返回受保护内容。系统不得（MUST NOT）通过查服务端会话表来判定调用方是否已认证。

#### Scenario: 未登录访问页面被重定向到登录页

- **WHEN** 未携带有效 JWT 的用户导航到受保护页面
- **THEN** 系统返回 302 重定向到 /login 且不返回受保护内容（判定通过：响应 302 + Location 指向 /login）

#### Scenario: 未登录调用 API 被拒

- **WHEN** 未携带有效 JWT 的调用方调用受保护 API 端点
- **THEN** 系统返回 401 且响应体不含任何受保护数据（判定通过：响应 401 + 无受保护数据）

#### Scenario: 已登录请求通过闸门

- **WHEN** 已登录用户携带有效 JWT 请求受保护资源
- **THEN** 系统返回 200 且提供该受保护资源（判定通过：响应 200 且非重定向）

#### Scenario: 伪造或过期的 JWT 被拒

- **WHEN** 调用方携带签名无效、已过期或已被吊销的 JWT
- **THEN** 系统视为未认证并返回 401 或 302 → /login（判定通过：篡改签名 → 401 + 过期 token → 401 + 已吊销 token → 401）

### Requirement: 教师与学生角色

系统须（SHALL）为每个账号指定唯一角色：教师或学生。JWT 载荷须（SHALL）携带调用方角色，使 API 响应可快速取用；但鉴权中间件须（SHALL）在验证 JWT 签名后以载荷中的用户标识回库查询真实角色与班级，以库中真实值为准，不纯信载荷中的角色声明。

#### Scenario: 会话携带角色

- **WHEN** 用户登录成功并签发 JWT
- **THEN** JWT 载荷含 role 字段，且后续请求中鉴权中间件以 user_id 回库查真实 role 并覆盖载荷值（判定通过：载荷含 role + 中间件查库所得 role 与库一致 + 角色被更改后旧 token 的载荷 role 被库值覆盖）

### Requirement: 登出清除已认证会话

系统须（SHALL）提供登出操作以使调用方的 JWT 失效。登出时系统须（SHALL）将 JWT 的唯一标识（jti）加入服务端吊销清单，并须（SHALL）清除客户端令牌存储（Cookie 与 localStorage）。登出后该 JWT 须（SHALL）不再可用于访问任何受保护资源，即使其签名与过期时间仍有效。

#### Scenario: 登出后受保护资源不可访问

- **WHEN** 已登录用户登出后再携带原 JWT 请求受保护资源
- **THEN** 系统返回 302 重定向到 /login 或 401，因 jti 已在吊销清单中（判定通过：登出后用原 token 访问受保护资源得 302 或 401）

#### Scenario: 登出清除客户端令牌存储

- **WHEN** 已登录用户登出
- **THEN** 系统清除 HttpOnly Cookie 中的 token，且响应指示客户端清除 localStorage 中的 token（判定通过：响应 Set-Cookie 清空 token + 响应体含清除 localStorage 指示）

## NEW Requirements

### Requirement: JWT 签名与载荷结构

系统须（SHALL）使用 HS256 算法与 SECRET_KEY 环境变量签发 JWT。载荷须（SHALL）至少包含用户标识（sub）、角色（role）、班级标识（class_id）、签发时间（iat）、过期时间（exp）与唯一标识（jti）。载荷不得（MUST NOT）包含密码、密码哈希或其他敏感凭据。过期时间须（SHALL）由环境变量配置（默认值须（SHALL）不超过 3600 秒）。

#### Scenario: JWT 结构与签名算法

- **WHEN** 登录成功签发 JWT
- **THEN** JWT 由三段以点号连接的 base64url 字符串组成，header.alg 为 HS256，payload 含 sub/role/class_id/iat/exp/jti（判定通过：token 三段 + header.alg=HS256 + 载荷含全部字段）

#### Scenario: 载荷不含敏感信息

- **WHEN** 解码任意 JWT 载荷
- **THEN** 载荷不含密码、密码哈希或 SECRET_KEY（判定通过：base64 解码载荷后无上述值）

### Requirement: 吊销清单使登出即时生效

系统须（SHALL）维护一个 JWT 吊销清单，登出时把 JWT 的 jti 写入该清单，鉴权时检查 jti 是否在清单中。已过期的 jti 条目须（SHALL）被定期清理。系统不得（MUST NOT）在吊销清单中存储 JWT 全文或载荷正文，仅存储 jti 与过期时间。

#### Scenario: 登出写入吊销清单

- **WHEN** 用户登出
- **THEN** 系统将该 JWT 的 jti 写入吊销清单表（判定通过：登出后吊销清单含该 jti + 鉴权时拒绝该 jti 的 token）

#### Scenario: 过期条目被清理

- **WHEN** 启动时或定期维护
- **THEN** 系统删除吊销清单中 exp 早于当前时间的条目（判定通过：过期 jti 被删除 + 未过期 jti 保留）
