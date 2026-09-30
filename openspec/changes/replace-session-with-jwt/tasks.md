# Tasks: replace-session-with-jwt

## 1. 依赖与配置

- [ ] 1.1 新增依赖 `PyJWT`，更新 requirements.txt，验证安装成功。
- [ ] 1.2 新增环境变量 `JWT_EXPIRES`（默认 3600 秒），更新 .env.example 与 config.py。
- [ ] 1.3 验证缺失 SECRET_KEY 时仍拒绝启动（复用第 3 课校验，不变）。

## 2. JWT 签发与验证

- [ ] 2.1 实现 JWT 签发函数：HS256 + SECRET_KEY，载荷含 sub/role/class_id/iat/exp/jti。
- [ ] 2.2 实现 JWT 验证函数：验签名 → 验过期 → 验 jti 不在吊销清单 → 返回 user_id。
- [ ] 2.3 验证载荷不含敏感信息（密码/哈希/密钥）。

## 3. 鉴权中间件改造

- [ ] 3.1 改造 session_gate 为 JWT 验证中间件：优先从 Authorization: Bearer 头取，回退 Cookie。
- [ ] 3.2 验签后以 user_id 回库查真实 role 与 class_id（Complete Mediation）。
- [ ] 3.3 页面路由：未登录 302 → /login；API 路由：未登录 401。
- [ ] 3.4 伪造/过期/已吊销的 JWT 均视为未认证。
- [ ] 3.5 /health 与登录/登出端点保持免认证。

## 4. 登录端点改造

- [ ] 4.1 JSON 登录成功：签发 JWT，返回 `{"token": "..."}` + Set-Cookie HttpOnly。
- [ ] 4.2 表单登录成功：签发 JWT + Set-Cookie HttpOnly + 303 → /materials。
- [ ] 4.3 凭据错误：不签发 JWT，返回统一"凭据无效"。
- [ ] 4.4 不再创建服务端会话记录。

## 5. 登出与吊销清单

- [ ] 5.1 新建 revoked_tokens 表（jti, exp）。
- [ ] 5.2 登出时写入 jti 到吊销清单 + 清 Cookie + 指示前端清 localStorage。
- [ ] 5.3 bootstrap 时清理已过期的吊销条目。
- [ ] 5.4 验证登出后原 token 不可访问受保护资源。

## 6. 前端 token 管理

- [ ] 6.1 登录成功后存 token 到 localStorage。
- [ ] 6.2 fetch 拦截器：自动加 Authorization: Bearer 头。
- [ ] 6.3 登出时清 localStorage。
- [ ] 6.4 页面加载时检查 token 存在性，不存在则跳转登录页。

## 7. 测试与验证

- [ ] 7.1 pytest：登录签发 JWT、鉴权、登出吊销、伪造/过期 token 被拒。
- [ ] 7.2 E2E：教师登录 → 上传 → 列表可见 → 登出 → 受保护资源不可访问。
- [ ] 7.3 角色变更：签发后改库中角色，旧 token 请求时回库查得新角色。
- [ ] 7.4 `openspec validate replace-session-with-jwt --strict` 通过。
