"""Build the write-up's chart and tables from the recorded rounds.

    python -m arena.report      # writes docs/asr_by_round.svg and prints Markdown tables
"""
from pathlib import Path

from arena import config, red
from arena.store import Store

ROOT = Path(__file__).resolve().parent.parent
GOAL_NAMES = {"secret_leak": "Leak the refund code", "refund_over_policy": "Refund over $50",
              "pii_leak": "Another customer's address", "indirect_injection": "Planted review (PIForge)"}


def chart(rounds, path):
    """Attack success and detection by round, drawn to scale, dark Orion-style palette."""
    W, H, L, R, T, B = 720, 360, 56, 64, 48, 92
    n = len(rounds)
    xs = lambda i: (L + W - R) / 2 if n == 1 else L + i * (W - L - R) / (n - 1)
    ys = lambda v: T + (1 - v) * (H - T - B)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Segoe UI, sans-serif">',
         f'<rect width="{W}" height="{H}" rx="18" fill="#15171c"/>',
         f'<text x="{L}" y="30" fill="#eef0f4" font-size="16" font-weight="700">ShopBot Arena: attack success vs detection, by round</text>']
    for v in (0, .25, .5, .75, 1):
        s.append(f'<line x1="{L}" x2="{W - R}" y1="{ys(v)}" y2="{ys(v)}" stroke="#2a2e38" {"" if v == 0 else "stroke-dasharray=\"3 5\""}/>')
        s.append(f'<text x="{L - 8}" y="{ys(v) + 4}" fill="#8d93a0" font-size="11" text-anchor="end">{int(v * 100)}%</text>')
    # Label placement per series so values at the same round don't collide: above, right, below
    for key, col, (dx, dy, anchor) in (("asr", "#ff5d52", (0, -11, "middle")),
                                        ("detection_rate", "#4f86f7", (9, -6, "start")),
                                        ("false_alarm_rate", "#f2b33d", (9, 5, "start"))):
        pts = [(xs(i), ys(r["summary"][key])) for i, r in enumerate(rounds)]
        s.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" stroke="{col}" stroke-width="3"/>')
        for (x, y), r in zip(pts, rounds):
            v = r["summary"][key]
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{col}"/>')
            if v or key == "asr":   # zeros on the baseline would only stack on each other
                s.append(f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" fill="{col}" font-size="11" text-anchor="{anchor}" font-weight="600">{v:.0%}</text>')
    for i, r in enumerate(rounds):
        s.append(f'<text x="{xs(i):.1f}" y="{H - B + 22}" fill="#eef0f4" font-size="12" text-anchor="middle" font-weight="600">Round {r["round"]}</text>')
        s.append(f'<text x="{xs(i):.1f}" y="{H - B + 38}" fill="#8d93a0" font-size="10.5" text-anchor="middle">{len(r["defenses"])} defences on</text>')
    for j, (label, col) in enumerate((("attack success", "#ff5d52"), ("detected by blue", "#4f86f7"), ("false alarms on normal chats", "#f2b33d"))):
        x = L + j * 190
        s.append(f'<circle cx="{x}" cy="{H - 20}" r="5" fill="{col}"/><text x="{x + 10}" y="{H - 16}" fill="#8d93a0" font-size="11.5">{label}</text>')
    s.append("</svg>")
    path.write_text("\n".join(s), encoding="utf-8")


def tables(rounds):
    out = ["| Round | Defences on | Attack success | Detected | False alarms | Spontaneous leaks |",
           "|---|---|---|---|---|---|"]
    for r in rounds:
        m = r["summary"]
        out.append(f"| {r['round']} | {', '.join(r['defenses']) or 'none'} | {m['asr']:.0%} ({sum(g['hits'] for g in m['by_goal'].values())}/{m['attacks']}) "
                   f"| {m['detection_rate']:.0%} | {m['false_alarm_rate']:.0%} | {m['spontaneous_breach_rate']:.0%} |")
    out += ["", "| Goal | " + " | ".join(f"Round {r['round']}" for r in rounds) + " |", "|---|" + "---|" * len(rounds)]
    for g in red.GOALS:
        cells = [f"{r['summary']['by_goal'].get(g, {}).get('hits', 0)}/{r['summary']['by_goal'].get(g, {}).get('attacks', 0)}" for r in rounds]
        out.append(f"| {GOAL_NAMES[g]} | " + " | ".join(cells) + " |")
    out += ["", "| After round | Blue switched on | Why |", "|---|---|---|"]
    for r in rounds:
        out.append(f"| {r['round']} | {', '.join(r['summary']['blue_next']) or 'nothing new'} | {'; '.join(r['summary']['blue_reasons']) or '-'} |")
    return "\n".join(out)


def rescore(store):
    """Re-judge every finished round from its raw events with the current judge.
    Metrics are recomputed; blue's recorded decisions are kept, since they are part of what happened."""
    from arena.judge import judge
    from arena.run import metrics
    sessions = store.sessions(100000)
    for rnd in store.rounds():
        if not rnd["summary"]:
            continue
        rows = [s for s in sessions if s["round"] == rnd["round"]]
        red_results = [red.score(store, s) for s in rows if s["source"] == "red"]
        normal = [judge(s, store.events(s["id"], limit=100000)) for s in rows if s["source"] == "normal"]
        old = rnd["summary"]
        store.update_round_summary(rnd["round"], {**metrics(red_results, normal),
                                                  "blue_next": old["blue_next"], "blue_reasons": old["blue_reasons"]})


if __name__ == "__main__":
    store = Store(config.DB_PATH)
    rescore(store)
    rounds = [r for r in store.rounds() if r["summary"]]
    (ROOT / "docs").mkdir(exist_ok=True)
    chart(rounds, ROOT / "docs" / "asr_by_round.svg")
    import json
    (ROOT / "docs" / "results.json").write_text(json.dumps({"rounds": rounds}, indent=2), encoding="utf-8")
    print(tables(rounds))
    print(f"\nChart: {ROOT / 'docs' / 'asr_by_round.svg'}")
