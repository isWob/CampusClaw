-- CampusClaw 迭代 1 数据模型（design Decision 7）
-- 单库多租户：class_id 是非空租户列并建索引，是所有班级隔离查询的地基。

CREATE TABLE IF NOT EXISTS classes (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
    class_id      INTEGER NOT NULL REFERENCES classes (id)
);
CREATE INDEX IF NOT EXISTS idx_users_class ON users (class_id);

CREATE TABLE IF NOT EXISTS materials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id    INTEGER NOT NULL REFERENCES classes (id),
    uploader_id INTEGER NOT NULL REFERENCES users (id),
    filename    TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_materials_class ON materials (class_id);

CREATE TABLE IF NOT EXISTS revoked_tokens (
    jti TEXT PRIMARY KEY,
    exp INTEGER NOT NULL
);

-- 知识库切片表
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id   INTEGER NOT NULL REFERENCES materials(id),
    class_id      INTEGER NOT NULL,
    chunk_index   INTEGER NOT NULL,
    chunk_text    TEXT NOT NULL,
    char_start    INTEGER NOT NULL,
    char_end      INTEGER NOT NULL,
    embed_status  TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_chunks_material ON knowledge_chunks(material_id);
CREATE INDEX IF NOT EXISTS idx_chunks_class ON knowledge_chunks(class_id);

-- FTS5 全文索引（2-gram 预切分中文）
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    bigram_text,
    tokenize='unicode61'
);

-- 解题助手：每班级一行，存当前生效提示词与解题引导技能开关
CREATE TABLE IF NOT EXISTS tutor_prompts (
    class_id      INTEGER PRIMARY KEY REFERENCES classes (id),
    prompt_text   TEXT NOT NULL DEFAULT '',
    skill_enabled INTEGER NOT NULL DEFAULT 0 CHECK (skill_enabled IN (0, 1)),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by    INTEGER NOT NULL REFERENCES users (id)
);

-- 解题助手会话：归属用户与班级，跨用户/跨班不可复用
CREATE TABLE IF NOT EXISTS tutor_sessions (
    id         TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users (id),
    class_id   INTEGER NOT NULL REFERENCES classes (id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tutor_sessions_user ON tutor_sessions (user_id);

-- 会话消息：user/assistant 成对，seq 会话内自增
CREATE TABLE IF NOT EXISTS tutor_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES tutor_sessions (id),
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    seq        INTEGER NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tutor_messages_session ON tutor_messages (session_id, seq);
