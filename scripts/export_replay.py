"""Export the recorded swarm campaigns from the event log into one JSON file for the replay site.

    python scripts/export_replay.py --db arena/data/arena.db

Reads results/swarm_baseline.json and results/swarm_defended.json for the session ids, then copies each
session's events out of the SQLite event log into site/data/campaigns.json. Nothing is re-scored here:
the trap, staff and leak flags come straight from the results files, which the code judge wrote.
"""
import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = [("baseline", "No defenses", ROOT / "results" / "swarm_baseline.json"),
        ("defended", "Five defenses on", ROOT / "results" / "swarm_defended.json")]
MAX_TEXT = 2500  # long tool results are cut; the payload itself is under 1,300 characters

# "red attack" repeats the customer message, and "red goal" only names the role
SKIP = {("red", "attack")}


def trim(value):
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + " [cut]"
    if isinstance(value, dict):
        return {k: trim(v) for k, v in value.items() if k != "raw"}
    if isinstance(value, list):
        return [trim(v) for v in value]
    return value


def role_of(events):
    for e in events:
        if e["event"] == "goal":
            return {"swarm_scout": "scout", "swarm_plant": "planter", "swarm_close": "closer"}.get(e["data"].get("goal"))
        if e["actor"] == "triage":
            return "triage"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "arena" / "data" / "arena.db"))
    ap.add_argument("--out", default=str(ROOT / "site" / "data" / "campaigns.json"))
    args = ap.parse_args()
    db = sqlite3.connect(args.db)

    def events(session):
        rows = db.execute("select ts, actor, event, data from events where session=? order by id", (session,))
        return [{"t": ts, "actor": a, "event": e, "data": trim(json.loads(d))}
                for ts, a, e, d in rows if (a, e) not in SKIP]

    # campaign summaries live in their own session, keyed here by the closer's session id
    campaigns = {}
    for session, data in db.execute("select session, data from events where event='campaign'"):
        info = json.loads(data)
        closer = next((r["session"] for r in info["roles"] if r["role"] == "closer"), None)
        intel = [json.loads(d) for (d,) in db.execute(
            "select data from events where session=? and event='intel' order by id", (session,))]
        campaigns[closer] = {"breaches": info["breaches"], "propagation": info["propagation"], "intel": intel}

    out = {"runs": [], "sessions": {}}
    for run_id, label, path in RUNS:
        res = json.loads(path.read_text(encoding="utf-8"))
        run = {"id": run_id, "label": label, "batch": res["batch"], "defenses": res["defenses"],
               "models": res["models"], "summary": res["summary"], "pairs": []}
        for p in res["pairs"]:
            pair = {"pair": p["pair"], "canary": p["canary"], "payload": p.get("payload", "")}
            for arm in ("team", "alone"):
                roles = {}
                for sid in p[f"{arm}_sessions"]:
                    evs = events(sid)
                    role = role_of(evs)
                    roles[role] = sid
                    out["sessions"][sid] = {"role": role, "events": evs}
                closer = roles.get("closer")
                pair[arm] = {**p[arm], "roles": roles, **campaigns.get(closer, {"intel": []})}
            run["pairs"].append(pair)
        out["runs"].append(run)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # the shop as it starts every campaign, for the site's Shop tab
    seed = json.loads((ROOT / "arena" / "shop" / "world_seed.json").read_text(encoding="utf-8"))
    (Path(args.out).parent / "shop.json").write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    n = sum(len(s["events"]) for s in out["sessions"].values())
    print(f"wrote {args.out}: {len(out['sessions'])} sessions, {n} events")


if __name__ == "__main__":
    main()
