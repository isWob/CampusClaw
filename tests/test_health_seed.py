"""/health、六类预置数据与种子幂等（tasks 3.3、6.1，specs/service-health）。"""

from app import repositories as repos
from app.db import get_db
from app.seed import seed_data

from .conftest import A1_PASS, B1_PASS, TEACHER_PASS, login


def test_health_200_anonymous(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_six_seed_categories_present(app, client):
    with app.app_context():
        db = get_db()
        assert repos.count_classes(db) == 2
        assert repos.count_users(db) == 3
        assert repos.count_materials(db) == 2

        names = {r["name"] for r in db.execute("SELECT name FROM classes")}
        assert names == {"A班", "B班"}

        users = {
            r["username"]: r for r in db.execute(
                "SELECT username, role, class_id, password_hash FROM users"
            )
        }
        assert users["teacher_a"]["role"] == "teacher"
        assert users["student_a1"]["role"] == "student"
        assert users["student_b1"]["role"] == "student"
        class_ids = {n: db.execute(
            "SELECT id FROM classes WHERE name = ?", (n,)).fetchone()[0]
            for n in ("A班", "B班")}
        assert users["teacher_a"]["class_id"] == class_ids["A班"]
        assert users["student_a1"]["class_id"] == class_ids["A班"]
        assert users["student_b1"]["class_id"] == class_ids["B班"]

        # 口令仅以加盐哈希存储
        for username, plain in (
            ("teacher_a", TEACHER_PASS),
            ("student_a1", A1_PASS),
            ("student_b1", B1_PASS),
        ):
            h = users[username]["password_hash"]
            assert h != plain and "$" in h


def test_seed_identities_see_own_class_materials(client):
    teacher = client
    assert login(teacher, "teacher_a", TEACHER_PASS).status_code == 200
    teacher_list = teacher.get("/api/materials").get_json()
    assert any("A班" in m["class_name"] for m in teacher_list)
    assert all(m["class_name"] == "A班" for m in teacher_list)

    a1 = client.application.test_client()
    login(a1, "student_a1", A1_PASS)
    assert all(m["class_name"] == "A班" for m in a1.get("/api/materials").get_json())

    b1 = client.application.test_client()
    login(b1, "student_b1", B1_PASS)
    b_list = b1.get("/api/materials").get_json()
    assert all(m["class_name"] == "B班" for m in b_list)
    assert any("B班" in m["filename"] for m in b_list)


def test_seed_is_idempotent(app):
    with app.app_context():
        db = get_db()
        counts = (
            repos.count_classes(db),
            repos.count_users(db),
            repos.count_materials(db),
        )
        seed_data()  # 再跑一次
        assert (
            repos.count_classes(db),
            repos.count_users(db),
            repos.count_materials(db),
        ) == counts
