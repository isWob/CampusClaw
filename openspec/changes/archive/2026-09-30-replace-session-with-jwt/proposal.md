# Replace Session with JWT

## Why

第 3 课采用服务端会话（签名 Cookie + sessions 表），课件"认证方案选型"页将 JWT 列为对比方案并明确"本课不采用"。本次任务要求改用 token 方案（JWT）实现登录认证：登录成功后签发 JWT 而非设置服务端会话，鉴权时验证 JWT 签名而非查会话表。通过改造体会两种方案在状态存放、登出语义、角色变更生效时机与风险类型上的本质差异。

## What Changes

- 登录成功后不再写入服务端会话表、不再下发签名 Cookie 会话标识，改为签发 JWT（三段结构 header.payload.signature），载荷含 user_id、role、class_id、签发时间（iat）、过期时间（exp）与唯一标识（jti）。
- JWT 通过 JSON 响应体返回给客户端，同时以 HttpOnly Cookie 下发给浏览器，使页面直接导航时浏览器自动携带。
- 客户端可将 JWT 存于 localStorage，后续 API 调用以 `Authorization: Bearer` 头携带；页面直接导航时由 Cookie 回退携带。
- 鉴权中间件不再查会话表，改为从 `Authorization: Bearer` 头或 Cookie 中提取 JWT、验证签名与过期时间、检查 jti 不在吊销清单中，从载荷提取 user_id 后回库查询真实角色与班级（Complete Mediation，不纯信载荷中的 role/class_id 声明）。
- 登出不再清除服务端会话记录（JWT 无服务端状态），改为将 JWT 的唯一标识（jti）加入服务端吊销清单，并清除客户端 Cookie 与 localStorage 中的 token。
- 页面路由：未登录浏览器导航重定向到登录页（从 Cookie 回退取 JWT 判断）；API 路由：未登录返回 401（从 Authorization 头判断）。
- **安全**：JWT 签名密钥复用 SECRET_KEY 环境变量，绝不嵌入源码或镜像；载荷默认可见（base64），不得存放敏感信息（如密码哈希）；HttpOnly Cookie 防 XSS 读取，localStorage 中的 token 仍存在 XSS 风险（JWT 方案的固有取舍，记录于 design）。

## Capabilities

### Modified Capabilities

- `user-auth`：登录签发 JWT 替代服务端会话；鉴权从验证 JWT 签名替代查会话表；登出改为吊销清单替代清除会话记录；角色与班级取自 JWT 载荷并回库复核。

## Impact

- **新增依赖**：`PyJWT`（JWT 签发与验证）。
- **新增代码**：JWT 签发函数、JWT 验证中间件（替代 session_gate）、token 吊销清单（SQLite 表）、前端 token 管理（localStorage 存取与 fetch 拦截器）。
- **数据模型**：新增 `revoked_tokens` 表（jti、exp，定期清理已过期项）；sessions 表不再写入，可保留以兼容。
- **配置**：新增 `JWT_EXPIRES`（token 有效期，默认 3600 秒）可选环境变量；密钥复用 `SECRET_KEY`。
- **兼容性**：修改登录、登出、鉴权中间件的行为；既有材料上传/列表/详情/下载的鉴权逻辑不变（仍要求已认证），但鉴权方式从 Cookie 会话改为 JWT 验证。

## Non-Goals

- 刷新令牌（refresh token）与滑动过期机制。
- 多设备会话管理与设备列表。
- OAuth/SSO/OpenID Connect 等第三方认证。
- 无密码登录与 MFA。
- 令牌加密（JWE）；载荷仅签名不加密，敏感信息不入载荷。
