"""容器/本地启动引导：建表 → 幂等灌种子（在对外提供服务之前完成）。

用法：python -m app.bootstrap
环境变量缺失时 config_from_env 抛错，进程以非零码退出（拒绝启动）。
"""

from dotenv import load_dotenv

from . import create_app
from .db import init_db
from .seed import seed_data
from .tokens import cleanup_expired


def main() -> None:
    load_dotenv()
    app = create_app()
    with app.app_context():
        init_db()
        seed_data()
        cleanup_expired()
    print("数据库初始化与种子数据就绪")

    # 补齐存量材料正文与索引
    from .db import get_db
    from .indexing import build_index
    from . import vector_store
    with app.app_context():
        vector_store.ensure_collection()
        db = get_db()
        rows = db.execute(
            "SELECT id, class_id, stored_path, body_text FROM materials WHERE body_text IS NULL OR body_text = ''"
        ).fetchall()
        upload_dir = app.config["UPLOAD_DIR"]
        for row in rows:
            from pathlib import Path
            fpath = Path(upload_dir) / row["stored_path"]
            if fpath.exists():
                body = fpath.read_text(encoding="utf-8", errors="replace")
                db.execute("UPDATE materials SET body_text = ? WHERE id = ?", (body, row["id"]))
                db.commit()
        # 对无切片的材料补建索引
        unindexed = db.execute(
            "SELECT m.id, m.class_id, m.body_text FROM materials m "
            "WHERE m.body_text IS NOT NULL AND m.body_text != '' "
            "AND NOT EXISTS (SELECT 1 FROM knowledge_chunks c WHERE c.material_id = m.id)"
        ).fetchall()
        for row in unindexed:
            try:
                build_index(row["id"], row["class_id"], row["body_text"])
            except Exception as e:
                print(f"[bootstrap] 索引补齐失败 material_id={row['id']}: {e}")


if __name__ == "__main__":
    main()
