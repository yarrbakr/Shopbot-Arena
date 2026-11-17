"""The arena round loop: red attacks, the judge scores, blue switches on defences, repeat.

    python -m arena.run --rounds 4 --attempts 3 --normal 10

Each round: every goal gets `attempts` attack conversations; `normal` ordinary chats measure false
alarms under the same defences; blue then picks what to switch on for the next round. Everything is
written to the arena database, so the dashboard shows the run live and can replay it later.
"""
import argparse
import json
import time
from pathlib import Path

from arena import blue, config, red
from arena import metrics as metrics_mod
from arena.judge import judge
from arena.run_normal import CHATS
from arena.shop.agent import ShopBot
from arena.store import Store

ROOT = Path(__file__).resolve().parent.parent


def metrics(red_results, normal_results):
    # A session where the red team never sent a message is not an attack: leave it out of the rates
    skipped = sum(1 for r in red_results if r.get("attack_sent") is False)
    red_results = [r for r in red_results if r.get("attack_sent") is not False]
    n = len(red_results)
    by_goal = {}
    for r in red_results:
        g = by_goal.setdefault(r["goal"], {"attacks": 0, "hits": 0})
        g["attacks"] += 1
        g["hits"] += int(r["hit"])
    outcomes = {}
    for r in red_results:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
    m = len(normal_results)
    return {
        "attacks": n,
        "skipped_no_attack": skipped,
        "asr": round(sum(r["hit"] for r in red_results) / n, 3) if n else 0,
        "breach_rate": round(sum(bool(r["breaches"]) for r in red_results) / n, 3) if n else 0,
        "detection_rate": round(sum(bool(r["detections"]) for r in red_results) / n, 3) if n else 0,
        "by_goal": by_goal,
        "outcomes": outcomes,
        "normal_chats": m,
        "false_alarm_rate": round(sum(bool(r["detections"]) for r in normal_results) / m, 3) if m else 0,
        "spontaneous_breach_rate": round(sum(bool(r["breaches"]) for r in normal_results) / m, 3) if m else 0,
    }


def run_round(bot, store, on, attempts, normal, memory, memory_notes, log=print):
    rnd = store.start_round(sorted(on))
    log(f"\n=== Round {rnd} | defences on: {', '.join(sorted(on)) or 'none'}")
    red_results = []
    for goal in red.GOALS:
        for tactic in red.pick_tactics(goal, attempts, memory):
            t0 = time.time()
            r = red.run_attack(bot, goal, tactic, rnd, red.notes_for(goal, memory_notes), defenses=sorted(on))
            red_results.append(r)
            log(f"  {goal:20} {r['tactic']:16} {'HIT ' if r['hit'] else 'miss'} {r['outcome']:15} "
                f"{time.time() - t0:5.0f}s  {'; '.join(b['type'] for b in r['breaches'])}")
    normal_results = []
    step = max(1, len(CHATS) // normal) if normal else 0
    for chat in CHATS[::step][:normal]:
        sid = bot.new_session("normal", chat["customer"], rnd, sorted(on))
        for turn in chat["turns"]:
            bot.chat(sid, turn)
        normal_results.append(judge(store.session(sid), store.events(sid, limit=100000)))
    red.learn(red_results, memory, memory_notes)
    picks, reasons = blue.decide(red_results + normal_results, on)
    summary = {**metrics(red_results, normal_results),
               "reach": metrics_mod.reach(red_results),
               "propagation": len(metrics_mod.propagation(store)),
               "blue_next": picks, "blue_reasons": reasons}
    store.finish_round(rnd, summary)
    log(f"  ASR {summary['asr']:.0%} | detected {summary['detection_rate']:.0%} | "
        f"false alarms {summary['false_alarm_rate']:.0%} | spontaneous leaks {summary['spontaneous_breach_rate']:.0%}")
    log(f"  blue switches on next: {', '.join(picks) or 'nothing new'}  ({'; '.join(reasons)})")
    return set(on) | set(picks), summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--normal", type=int, default=10)
    args = ap.parse_args()

    store = Store(config.DB_PATH)
    bot = ShopBot(store)
    on, memory, memory_notes, summaries = set(), {}, {}, []
    for _ in range(args.rounds):
        on, s = run_round(bot, store, on, args.attempts, args.normal, memory, memory_notes)
        summaries.append(s)
    out = ROOT / "docs" / "results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"args": vars(args), "rounds": store.rounds()[-args.rounds:]}, indent=2), encoding="utf-8")
    print(f"\nResults written to {out}")


if __name__ == "__main__":
    main()
