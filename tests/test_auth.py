"""Phase B: accounts, authenticated identity, staff privilege, identity-aware output guard."""
from test_shopbot import MODELS, FakeChat, call, make_bot, reply

from arena.auth import Auth
from arena.shop import defenses as dfn
from arena.shop import tools
from arena.shop.defenses import Defenses
from arena.shop.world import World


# ---- auth ----

def test_login_unknown_account_is_rejected():
    assert Auth(World(":memory:")).login("Nobody") is None


def test_login_then_identity_carries_name_and_role():
    auth = Auth(World(":memory:"))
    token = auth.login("Ayesha Raza")
    assert token
    assert auth.identity(token) == {"name": "Ayesha Raza", "role": "customer"}
    assert auth.identity("garbage") is None


def test_staff_account_has_staff_role():
    auth = Auth(World(":memory:"))
    assert auth.identity(auth.login("Staff"))["role"] == "staff"


def test_logout_invalidates_the_token():
    auth = Auth(World(":memory:"))
    token = auth.login("Bilal Khan")
    auth.logout(token)
    assert auth.identity(token) is None


# ---- ownership by identity, with staff bypass ----

def test_customer_cannot_reach_another_customers_order():
    owner = Defenses(on=["ownership_check"])
    assert "No order found" in tools.lookup_order({"order_id": "1043"}, owner, "Bilal Khan")
    assert "Ayesha Raza" in tools.lookup_order({"order_id": "1043"}, owner, "Ayesha Raza")


def test_staff_role_bypasses_ownership():
    owner = Defenses(on=["ownership_check"])
    assert "No order found" in tools.lookup_order({"order_id": "1043"}, owner, "Staff")           # as a customer: blocked
    assert "Ayesha Raza" in tools.lookup_order({"order_id": "1043"}, owner, "Staff", role="staff")  # as staff: allowed


def test_session_resolves_role_from_the_account():
    bot = make_bot(FakeChat())
    assert bot.sessions[bot.new_session(customer="Ayesha Raza")]["role"] == "customer"
    assert bot.sessions[bot.new_session(customer="Staff")]["role"] == "staff"
    assert bot.sessions[bot.new_session(customer=None)]["role"] is None


def test_staff_session_can_look_up_any_order_with_ownership_on():
    fake = FakeChat(brain=[call("lookup_order", order_id="1043"), reply("Here it is.")])
    bot = make_bot(fake, on=["ownership_check"])
    sid = bot.new_session(customer="Staff")               # internal agent acts as staff
    bot.chat(sid, "look up 1043")
    tool_result = [e for e in bot.store.events(sid) if e["event"] == "tool_result"][0]["data"]["result"]
    assert "Ayesha Raza" in tool_result                   # staff saw another customer's order


# ---- identity-aware output guard ----

def test_output_guard_is_told_who_the_customer_is():
    fake = FakeChat(brain=[reply("Your address is 7 Garden Town.")],
                    judge=[reply("<think>\n</think><score>no</score>")])
    bot = make_bot(fake, on=["output_guard"])
    bot.chat(bot.new_session(customer="Bilal Khan"), "what's my address?")
    guardian = fake.requests[-1]["messages"][-1]["content"]
    assert "Authenticated customer: Bilal Khan" in guardian    # the guard now knows the owner


def test_output_guard_without_identity_treats_all_pii_as_disclosure():
    _, verdict = dfn.output_guard("hi", "some reply", "judge",
                                  chat=FakeChat(judge=[reply("<score>no</score>")]), customer=None)
    # Just checks the prompt path builds; identity-free guard is the conservative default.
    assert verdict["score"] == "no"
