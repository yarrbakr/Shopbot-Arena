"""Run the 30 normal customer chats through ShopBot and judge them.

    python -m arena.run_normal                      # all defences off
    python -m arena.run_normal input_guard output_guard   # with these defences on

Normal chats are not attacks, so a guard flag on one is a false alarm and a breach is ShopBot
misbehaving on its own. Sessions are stored with source "normal".
"""
import json
import sys
import time
from pathlib import Path

from arena import config
from arena.judge import judge
from arena.shop.agent import ShopBot
from arena.shop.defenses import Defenses
from arena.store import Store

CHATS = json.loads((Path(__file__).parent / "normal_chats.json").read_text(encoding="utf-8"))


def main(on):
    store = Store(config.DB_PATH)
    bot = ShopBot(store, Defenses(on=on))
    results, t0 = [], time.time()
    for i, chat in enumerate(CHATS, 1):
        sid = bot.new_session("normal", chat["customer"])
        for turn in chat["turns"]:
            bot.chat(sid, turn)
        r = judge(store.session(sid), store.events(sid, limit=100000))
        results.append(r)
        flags = [f"{b['type']}: {b['evidence']}" for b in r["breaches"]] + [f"flagged by {d['defense']}" for d in r["detections"]]
        print(f"{i:2} {sid} {(chat['customer'] or 'anonymous'):12} {r['outcome']:22} {'; '.join(flags)}", flush=True)

    n = len(results)
    breached = sum(1 for r in results if r["breaches"])
    alarms = sum(1 for r in results if r["detections"])
    print(f"\n{n} normal chats in {time.time() - t0:.0f}s, defences on: {', '.join(on) or 'none'}")
    print(f"spontaneous breaches: {breached}/{n}   false alarms: {alarms}/{n}")


if __name__ == "__main__":
    main(sys.argv[1:])
