# Design: replace-session-with-jwt

## Context

第 3 课已交付 Flask + SQLite 单服务，认证采用服务端会话：登录成功写入 sessions 表、下发签名 Cookie（HttpOnly, SameSite=Lax）；session_gate 中间件每请求验签 Cookie → 取 user_id → 回库查真实角色/班级（Complete Mediation）。第 3 课课件"认证方案选型"页将 JWT 列为对比方案，核心差异：状态存放于客户端（载荷可见）、登出≠立即失效（须吊销清单）、角色变更须待令牌过期、主要风险为 XSS 读走 localStorage。

本次任务把认证从服务端会话切换为 JWT（token 方案），使行为与第 3 课课件描述的 JWT 方案一致。

## Goals / Non-Goals

- [x] 登录签发 JWT、鉴权验证 JWT 签名，替代查会话表。
- [x] 保留 Complete Mediation：验签取 user_id 后仍回库查真实角色/班级。
- [x] 登出通过吊销清单使 JWT 失效，体会"须额外维护"的成本。
- [x] 保持既有材料上传/列表/详情/下载/同形 404 行为不变。
- [x] 不做刷新令牌、不加密载荷、不做 SSO/MFA。

## Decisions

### D1. JWT 签发：HS256 + 复用 SECRET_KEY

- 签名算法 HS256（对称），复用现有 `SECRET_KEY` 环境变量，无需引入公私钥对。
- 载荷字段：`sub`（user_id）、`role`（teacher/student）、`class_id`、`iat`（签发时间）、`exp`（过期时间）、`jti`（唯一标识，用于吊销）。
- 载荷默认 base64 可见，不得存放密码哈希等敏感信息；role/class_id 写入载荷仅为便捷，鉴权时仍回库复核（见 D3）。
- 过期时间由 `JWT_EXPIRES` 环境变量配置（默认 3600 秒）。
- 备选：RS256 非对称签名——否决：单服务部署无需公私钥对，HS256 最简且密钥已在环境变量中。

### D2. 双通道下发：JSON 响应体 + HttpOnly Cookie

- 登录成功后，JWT 同时通过两条通道下发：
  1. JSON 响应体 `{"token": "<jwt>"}`——前端 JS 存入 localStorage，后续 fetch 以 `Authorization: Bearer <jwt>` 携带。
  2. `Set-Cookie: token=<jwt>; HttpOnly; SameSite=Lax; Path=/`——浏览器导航（地址栏直接访问页面）自动携带。
- 鉴权中间件优先从 `Authorization: Bearer` 头取 token，回退到 Cookie 中的 `token` 字段。
- 这样浏览器直接导航页面和 JS 调用 API 均可鉴权，无需把前端改为纯 SPA。
- Cookie 设 HttpOnly 防止 XSS 读取（第 3 课课件指出的 localStorage 风险），但 localStorage 中的 token 仍可被 XSS 读取——这是 JWT 方案的固有取舍，在 design 中记录而非规避。

### D3. Complete Mediation：验签后仍回库查真实身份

- 鉴权中间件：取 JWT → 验签名 → 验过期 → 验 jti 不在吊销清单 → 取 `sub`（user_id）→ 回库查 users 表获取真实 role 与 class_id。
- 不纯信载荷中的 role/class_id 声明：若用户角色在签发后被更改（如学生升为教师），载荷中的旧 role 须被库中真实值覆盖。
- 这保留了第 3 课 ADR"会话而非 JWT"决策中唯一仍适用于 token 方案的安全原则——Complete Mediation。代价是每个请求仍查一次库，但与查 sessions 表开销相当。
- 备选：纯信任载荷（不回库）——否决：角色变更须待令牌过期才生效是第 3 课课件指出的 JWT 缺点，回库查可消除此缺点。

### D4. 登出：jti 吊销清单 + 客户端清除

- 登出时：服务端把 JWT 的 `jti` 写入 `revoked_tokens` 表（含 exp，供定期清理），客户端清 localStorage 与 Cookie。
- 鉴权中间件检查 jti 是否在吊销清单中——在则视为无效 token（401）。
- 过期 token 的 jti 行定期清理（bootstrap 或启动时清理 `exp < now` 的行）。
- 这是第 3 课课件指出的 JWT 缺点"登出≠立即失效（须额外维护吊销清单）"的直接实现：登出确实需要额外维护服务端状态，与服务端会话的"删除会话行即失效"对比鲜明。
- 备选：不维护吊销清单、仅靠短 exp——否决：无法实现主动登出，不符合"登出后受保护资源不可访问"的既有规约。

### D5. 页面路由与 API 路由的鉴权差异

- 页面路由（/login、/materials 等）：中间件从 Cookie 取 JWT 判断，未登录返回 302 → /login（与第 3 课行为一致，前端无感）。
- API 路由（/api/*）：中间件优先从 Authorization 头取 JWT，回退 Cookie；未登录返回 401。
- /health 保持免认证。
- 登录页/登出端点保持免认证。

## Risks / Trade-offs

- JWT 在 localStorage 可被 XSS 读取 → 课件指出的固有风险；通过 HttpOnly Cookie 提供一条不依赖 localStorage 的回退通道。
- 吊销清单增加服务端状态 → JWT"无状态"的优势被部分抵消；这是课件对比中 JWT 的固有代价，通过体验来理解。
- 角色变更后旧 token 中的 role 与 class_id 被回库查覆盖 → 消除"角色变更须待过期"缺点，但增加每请求查库开销（与原方案相当）。
- 双通道下发（Cookie + JSON） → token 在两处各存一份，登出须同时清理。

## Migration Plan

1. 安装 PyJWT → 2. JWT 签发与验证函数 → 3. 鉴权中间件改造 → 4. 登录端点改造 → 5. 登出与吊销清单 → 6. 前端 token 管理 → 7. 测试与 E2E。

## Open Questions

- 无（密钥复用 SECRET_KEY，JWT_EXPIRES 可选配置默认 3600 秒）。
