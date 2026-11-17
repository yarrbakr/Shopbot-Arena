"""Phase C: the write-tools that mutate shared shop state (and open the cross-session channel)."""
from arena.shop import tools
from arena.shop.defenses import Defenses

OFF = Defenses()
OWNER = Defenses(on=["ownership_check"])


def test_update_shipping_address_is_ownership_gated(fresh_world):
    assert "No order found" in tools.update_shipping_address({"order_id": "1043", "address": "X"}, OWNER, "Bilal Khan")
    assert "updated" in tools.update_shipping_address({"order_id": "1043", "address": "9 New Rd"}, OWNER, "Ayesha Raza")
    assert fresh_world.order("1043")["shipping_address"] == "9 New Rd"


def test_cancel_order_sets_status(fresh_world):
    assert "cancelled" in tools.cancel_order({"order_id": "1044"}, OFF, "Usman Tariq")
    assert fresh_world.order("1044")["status"] == "cancelled"


def test_post_review_persists_and_is_visible_to_other_sessions(fresh_world):
    tools.post_review({"order_id": "1044", "text": "Brilliant little case."}, OFF, "Usman Tariq")
    # read_review (any session) now sees it - this is the cross-session content channel
    seen = tools.run("read_review", {"order_id": "1042"}, OFF, "Bilal Khan")   # 1042 is also a phone-case
    assert "Brilliant little case." in seen


def test_tickets_capture_customer_messages(fresh_world):
    out = tools.open_ticket({"subject": "late delivery", "message": "where is 1044?", "order_id": "1044"}, OFF, "Usman Tariq")
    assert out == "Ticket #1 opened."
    (ticket,) = fresh_world.open_tickets()
    assert ticket["account"] == "Usman Tariq" and ticket["status"] == "open"
    assert fresh_world.messages_for(1)[0]["text"] == "where is 1044?"
    assert "Reply added" in tools.reply_ticket({"ticket_id": 1, "message": "still waiting"}, OFF, "Usman Tariq")
    assert len(fresh_world.messages_for(1)) == 2


def test_reply_to_missing_ticket_is_handled(fresh_world):
    assert "No ticket found" in tools.reply_ticket({"ticket_id": 999, "message": "hi"}, OFF, "Usman Tariq")


def test_apply_coupon(fresh_world):
    ok = tools.apply_coupon({"order_id": "1044", "code": "WELCOME10"}, OFF, "Usman Tariq")
    assert "10%" in ok and "-$1.45" in ok                     # 10% of $14.50
    assert "invalid or inactive" in tools.apply_coupon({"order_id": "1044", "code": "NOPE"}, OFF, "Usman Tariq")


def test_check_loyalty(fresh_world):
    assert "300 loyalty points" in tools.check_loyalty({}, OFF, "Ayesha Raza")


def test_gift_points_transfers_between_accounts(fresh_world):
    assert "Gifted 50" in tools.gift_points({"to_account": "Bilal Khan", "amount": 50}, OFF, "Ayesha Raza")
    assert fresh_world.loyalty("Ayesha Raza") == 250 and fresh_world.loyalty("Bilal Khan") == 90


def test_gift_points_guards_against_abuse(fresh_world):
    assert "enough" in tools.gift_points({"to_account": "Bilal Khan", "amount": 99999}, OFF, "Ayesha Raza")
    assert "No account found for Nobody" in tools.gift_points({"to_account": "Nobody", "amount": 10}, OFF, "Ayesha Raza")
    assert "positive" in tools.gift_points({"to_account": "Bilal Khan", "amount": 0}, OFF, "Ayesha Raza")


def test_run_dispatches_write_tools_with_role(fresh_world):
    out = tools.run("gift_points", {"to_account": "Bilal Khan", "amount": 10}, OFF, "Ayesha Raza", role="customer")
    assert "Gifted 10" in out


def test_issue_refund_records_the_refund(fresh_world):
    tools.issue_refund({"order_id": "1042", "amount": 14.5}, OFF, "Bilal Khan")
    assert fresh_world.refunds_for("1042")[0]["amount"] == 14.5
    assert fresh_world.order("1042")["status"] == "refunded"
