"""ShopBot as a local service. Run:  python -m uvicorn arena.server:app --port 8008

The chat page is at http://127.0.0.1:8008/ ; the red team, judge and dashboards use the /api routes.
"""
import random
import threading
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from arena import config, red
from arena.auth import Auth
from arena.judge import judge
from arena.shop import tools
from arena.shop import world as world_mod
from arena.shop.agent import ShopBot
from arena.shop.defenses import CATALOG
from arena.shop.triage import TriageBot
from arena.store import Store


class NewSession(BaseModel):
    source: str = "human"
    customer: str | None = None
    round: int | None = None


class RunOne(BaseModel):
    goal: str
    tactic: str | None = None


class ChatIn(BaseModel):
    session: str | None = None
    message: str
    customer: str | None = None   # used only when this call starts a new session
    token: str | None = None      # when set, the authenticated account overrides `customer`


class Login(BaseModel):
    name: str


class Token(BaseModel):
    token: str


def create_app(store=None, bot=None, auth=None):
    store = store or Store(config.DB_PATH)
    bot = bot or ShopBot(store)
    auth = auth or Auth(world_mod.WORLD)
    static = Path(__file__).parent / "static"
    app = FastAPI(title="ShopBot Arena")

    def require_identity(token):
        ident = auth.identity(token) if token else None
        if not ident:
            raise HTTPException(401, "Not logged in (or the session expired).")
        return ident

    @app.get("/")
    def page():
        return FileResponse(static / "chat.html")

    @app.get("/login")
    def login_page():
        return FileResponse(static / "login.html")

    @app.get("/account")
    def account_page():
        return FileResponse(static / "account.html")

    @app.get("/staff")
    def staff_page():
        return FileResponse(static / "staff.html")

    # ---- auth + account ----

    @app.post("/api/login")
    def login(body: Login):
        token = auth.login(body.name)
        if not token:
            raise HTTPException(401, f"No account named {body.name!r}.")
        return {"token": token, **auth.identity(token)}

    @app.post("/api/logout")
    def logout(body: Token):
        auth.logout(body.token)
        return {"ok": True}

    @app.get("/api/me")
    def me(token: str):
        return require_identity(token)

    @app.get("/api/account")
    def account(token: str):
        ident = require_identity(token)
        name, world = ident["name"], world_mod.WORLD
        orders = {oid: o for oid, o in world.orders().items() if o["customer_name"] == name}
        tickets = [t for t in world.open_tickets() if t.get("account") == name]
        return {"account": ident, "loyalty": world.loyalty(name), "orders": orders, "open_tickets": tickets}

    # ---- staff / internal agent ----

    @app.get("/api/staff/queue")
    def staff_queue(token: str):
        if require_identity(token)["role"] != "staff":
            raise HTTPException(403, "Staff only.")
        return world_mod.WORLD.open_tickets()

    @app.post("/api/staff/triage/run_once")
    def staff_triage(body: Token):
        if require_identity(body.token)["role"] != "staff":
            raise HTTPException(403, "Staff only.")
        return {"sessions": TriageBot(bot=bot, world=world_mod.WORLD).run_once()}

    @app.get("/api/health")
    def health():
        try:
            r = requests.get(config.BASE_URL.rsplit("/v1", 1)[0] + "/api/tags",
                             headers={"Authorization": f"Bearer {config.API_KEY}"}, timeout=8)
            kaggle = r.status_code == 200
        except Exception:
            kaggle = False
        return {"ok": True, "kaggle": kaggle, "brain": bot.models["target"]}

    @app.get("/api/customers")
    def customers():
        return tools.customers()

    @app.post("/api/sessions")
    def new_session(body: NewSession):
        return {"session": bot.new_session(body.source, body.customer, body.round)}

    @app.post("/api/chat")
    def chat(body: ChatIn):
        customer = body.customer
        if body.token:
            customer = require_identity(body.token)["name"]   # the chat acts as the logged-in account
        sid = body.session or bot.new_session("human", customer)
        if sid not in bot.sessions:
            raise HTTPException(404, "Unknown session (sessions live in memory and reset when the server restarts).")
        return {"session": sid, **bot.chat(sid, body.message)}

    @app.get("/api/sessions")
    def sessions(limit: int = 50):
        return store.sessions(limit)

    @app.get("/api/events")
    def events(session: str | None = None, since: int = 0, limit: int = 500):
        return store.events(session, since, limit)

    @app.get("/api/judge/{session}")
    def judge_one(session: str):
        row = store.session(session)
        if not row:
            raise HTTPException(404, "Unknown session")
        return judge(row, store.events(session, limit=100000))

    @app.get("/api/scoreboard")
    def scoreboard(source: str | None = None, round: int | None = None, limit: int = 1000):
        rows = [s for s in store.sessions(limit)
                if (source is None or s["source"] == source) and (round is None or s["round"] == round)]
        results = [judge(s, store.events(s["id"], limit=100000)) for s in rows]
        outcomes, breach_types = {}, {}
        for r in results:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
            for b in r["breaches"]:
                breach_types[b["type"]] = breach_types.get(b["type"], 0) + 1
        return {"sessions": len(results), "outcomes": outcomes, "breaches": breach_types, "results": results}

    # ---- arena views (dashboard) ----

    def attack_result(s):
        return {**red.score(store, s), "created": s["created"]}

    @app.get("/dashboard")
    def dashboard():
        return FileResponse(Path(__file__).parent / "static" / "dashboard.html")

    @app.get("/api/rounds")
    def rounds():
        return store.rounds()

    @app.get("/api/attacks")
    def attacks(limit: int = 300):
        return [attack_result(s) for s in store.sessions(limit) if s["source"] == "red"]

    @app.get("/api/session/{session}")
    def session_detail(session: str):
        row = store.session(session)
        if not row:
            raise HTTPException(404, "Unknown session")
        evs = store.events(session, limit=100000)
        return {"session": row, "events": evs,
                "judge": attack_result(row) if row["source"] == "red" else judge(row, evs)}

    @app.get("/api/events/last")
    def last_event():
        return {"id": store.last_event_id()}

    @app.get("/api/verdicts")
    def verdicts(limit: int = 100):
        evs = store.events(limit=100000, event="verdict")
        return evs[-limit:][::-1]

    @app.get("/api/swarm")
    def swarm_view(limit: int = 1000):
        """Live view of the coordinated multi-agent campaign: the squad's roles, how far it reached,
        the worm hops into the internal agent, and the shared-blackboard intel - all from the log."""
        from arena import metrics

        sess = store.sessions(limit)

        def first_goal(sid):
            for e in store.events(sid, limit=100000):
                if e["actor"] == "red" and e["event"] == "goal":
                    return e["data"].get("goal")
            return None

        roles, results = [], []
        for s in sess:
            if s["source"] != "red":
                continue
            goal = first_goal(s["id"])
            if not goal or not goal.startswith("swarm_"):
                continue
            r = judge(s, store.events(s["id"], limit=100000))
            r["role"] = goal.replace("swarm_", "")
            results.append(r)
            roles.append({"session": s["id"], "role": r["role"], "customer": s["customer"],
                          "round": s["round"], "created": s["created"],
                          "breaches": [b["type"] for b in r["breaches"]]})
        intel = []
        for s in sess:
            if s["source"] == "swarm":
                intel += [e["data"] for e in store.events(s["id"], limit=100000) if e["event"] == "intel"]
        campaigns = [e["data"] for e in store.events(limit=100000, event="campaign")]
        return {"campaigns": campaigns, "roles": roles[:24], "reach": metrics.reach(results),
                "breaches": sum(len(r["breaches"]) for r in results),
                "propagation": metrics.propagation(store), "intel": intel[-40:]}

    running = {"session": None, "goal": None}

    @app.post("/api/red/run_one")
    def run_one(body: RunOne):
        if body.goal not in red.GOALS:
            raise HTTPException(400, f"Unknown goal: {body.goal}")
        if running["goal"]:
            raise HTTPException(409, f"An attack on {running['goal']} is already running.")
        tactic = body.tactic if body.tactic in red.TACTICS else random.choice(list(red.TACTICS))
        running["goal"] = body.goal

        def go():
            try:
                red.run_attack(bot, body.goal, tactic)
            finally:
                running["goal"] = None
        threading.Thread(target=go, daemon=True).start()
        return {"started": True, "goal": body.goal, "tactic": tactic}

    @app.get("/api/red/status")
    def red_status():
        return {"running": running["goal"], "goals": list(red.GOALS), "tactics": red.TACTICS}

    @app.get("/api/defenses")
    def get_defenses():
        return {name: {"on": bot.defenses.on(name), "description": desc} for name, desc in CATALOG.items()}

    @app.put("/api/defenses")
    def set_defenses(changes: dict[str, bool]):
        for name, value in changes.items():
            if name not in CATALOG:
                raise HTTPException(400, f"Unknown defence: {name}")
            bot.defenses.set(name, value)
        return get_defenses()

    return app


app = create_app()
