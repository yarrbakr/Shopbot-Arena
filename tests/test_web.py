"""Phase E: the lean web shell - login, account page, staff queue, chat bound to identity."""
from fastapi.testclient import TestClient
from test_shopbot import MODELS, FakeChat, call, reply

from arena.server import create_app
from arena.shop.agent import ShopBot
from arena.store import Store


def app_with(fake):
    store = Store(":memory:")
    return TestClient(create_app(store, ShopBot(store, chat=fake, models=MODELS)))


def test_pages_are_served():
    c = app_with(FakeChat())
    for path, needle in [("/login", "sign in"), ("/account", "my account"), ("/staff", "triage")]:
        r = c.get(path)
        assert r.status_code == 200 and needle in r.text.lower()


def test_login_rejects_unknown_and_issues_a_token():
    c = app_with(FakeChat())
    assert c.post("/api/login", json={"name": "Nobody"}).status_code == 401
    d = c.post("/api/login", json={"name": "Ayesha Raza"}).json()
    assert d["token"] and d["role"] == "customer"
    assert c.get("/api/me", params={"token": d["token"]}).json()["name"] == "Ayesha Raza"
    assert c.get("/api/me", params={"token": "bad"}).status_code == 401


def test_account_shows_only_my_orders():
    c = app_with(FakeChat())
    token = c.post("/api/login", json={"name": "Ayesha Raza"}).json()["token"]
    d = c.get("/api/account", params={"token": token}).json()
    assert "1043" in d["orders"] and "1041" not in d["orders"]      # 1041 is Sara's
    assert d["loyalty"] == 300


def test_chat_binds_to_the_logged_in_account():
    fake = FakeChat(brain=[call("lookup_order", order_id="1042"), reply("Midnight blue.")])
    c = app_with(fake)
    token = c.post("/api/login", json={"name": "Bilal Khan"}).json()["token"]
    out = c.post("/api/chat", json={"message": "colour of my 1042?", "token": token}).json()
    assert out["reply"] == "Midnight blue."
    assert c.get("/api/sessions").json()[0]["customer"] == "Bilal Khan"


def test_staff_queue_and_triage(fresh_world):
    fresh_world.open_ticket("Usman Tariq", "late delivery", order_id="1044")
    fresh_world.add_message(1, "Usman Tariq", "customer", "where is it?")
    c = app_with(FakeChat(brain=[reply("It shipped today.")]))

    staff = c.post("/api/login", json={"name": "Staff"}).json()["token"]
    queue = c.get("/api/staff/queue", params={"token": staff}).json()
    assert len(queue) == 1 and queue[0]["account"] == "Usman Tariq"

    out = c.post("/api/staff/triage/run_once", json={"token": staff}).json()
    assert len(out["sessions"]) == 1
    assert fresh_world.ticket(1)["status"] == "resolved"

    customer = c.post("/api/login", json={"name": "Bilal Khan"}).json()["token"]
    assert c.get("/api/staff/queue", params={"token": customer}).status_code == 403
