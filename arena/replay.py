"""Import an old Milestone 1 log (lab/logs*.jsonl) into the arena store so the judge can score it.

    python -m arena.replay lab/logs_run1.jsonl
"""
import json
import sys
from pathlib import Path

from arena import config
from arena.judge import judge
from arena.store import Store

# Milestone 1 event names -> arena (actor, event)
MAP = {"user": ("customer", "message"), "tool_call": ("target", "tool_call"),
       "tool_result": ("tool", "tool_result"), "assistant": ("target", "reply")}


def import_jsonl(store, path):
    """Returns {old session id: new session id}. Milestone 1 had no defences and no customer identity."""
    ids = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e["session"] not in ids:
            ids[e["session"]] = store.new_session("replay", {}, None)
        actor, event = MAP[e["event"]]
        store.log(ids[e["session"]], actor, event, e["data"])
    return ids


if __name__ == "__main__":
    store = Store(config.DB_PATH)
    for old, new in import_jsonl(store, sys.argv[1]).items():
        result = judge(store.session(new), store.events(new))
        print(f"{old} -> {new}: {result['outcome']}")
        for b in result["breaches"]:
            print(f"   {b['type']} ({b['vector']}): {b['evidence']}")
