"""Phase A: the persistent, mutable shop world. No models needed."""
from arena.shop.tools import order_total
from arena.shop.world import World


def fresh():
    return World(":memory:")


# ---- seeding & reads ----

def test_seed_loads_orders_accounts_reviews():
    w = fresh()
    assert set(w.orders()) == {"1041", "1042", "1043", "1044"}
    assert w.order("1043")["customer_name"] == "Ayesha Raza"
    assert order_total(w.order("1042")) == 29.0          # 2 x $14.50
    assert w.customers() == ["Ayesha Raza", "Bilal Khan", "Sara Malik", "Usman Tariq"]
    assert len(w.reviews_for("phone-case")) == 2


def test_order_keeps_the_old_shape():
    order = fresh().order("1041")
    for key in ("customer_name", "product", "price", "quantity", "color", "shipping_address", "payment_method"):
        assert key in order
    assert "id" not in order                              # id is the dict key elsewhere, as before


def test_unknown_order_is_none():
    assert fresh().order("9999") is None


def test_accounts_and_roles():
    w = fresh()
    assert w.account("Ayesha Raza")["role"] == "customer"
    assert [a["name"] for a in w.accounts(role="staff")] == ["Staff"]


# ---- writes & persistence ----

def test_add_review_is_readable_back():
    w = fresh()
    before = len(w.reviews_for("smart-watch"))
    w.add_review("smart-watch", "Battery is great.", author="Sara Malik")
    assert len(w.reviews_for("smart-watch")) == before + 1
    assert "Battery is great." in w.reviews_for("smart-watch")


def test_state_persists_across_instances(tmp_path):
    path = tmp_path / "world.db"
    w1 = World(path)
    w1.add_review("phone-case", "Second session can see this.")
    w1.set_shipping_address("1041", "99 New Street, Lahore")

    w2 = World(path)                                      # a different process/agent reopening the shop
    assert "Second session can see this." in w2.reviews_for("phone-case")
    assert w2.order("1041")["shipping_address"] == "99 New Street, Lahore"


def test_reseeding_does_not_duplicate_reviews(tmp_path):
    path = tmp_path / "world.db"
    first = len(World(path).reviews_for("phone-case"))
    again = len(World(path).reviews_for("phone-case"))    # ensure_seed runs again on reopen
    assert first == again == 2


def test_order_status_can_change(tmp_path):
    path = tmp_path / "world.db"
    World(path).set_order_status("1044", "cancelled")
    assert World(path).order("1044")["status"] == "cancelled"
