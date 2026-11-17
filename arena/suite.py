"""Phase G: run published-style benchmark cases against ShopBot and score them with the code judge.

A "case" is a small JSON record so attacks from published suites (AgentDojo, InjecAgent, Agent Security
Bench) can be converted to one shape and scored by the same deterministic judge, instead of only the
arena's own hand-made goals. A sample suite ships (arena/suites/sample.json) so this runs offline.

Case shape:
  {"name": "...", "source": "red", "customer": "Bilal Khan" | null,
   "planted": {"product": "phone-case", "text": "..."},   # optional: a review to plant first
   "turns": ["message 1", "message 2", ...]}
"""
import json
from pathlib import Path

from arena.judge import judge

SUITES = Path(__file__).parent / "suites"


def load_cases(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_case(bot, case, round_=None, defenses=None):
    sid = bot.new_session(case.get("source", "red"), case.get("customer"), round_, defenses)
    if case.get("planted"):
        bot.plant_review(sid, case["planted"]["product"], case["planted"]["text"])
    for turn in case.get("turns", []):
        bot.chat(sid, turn)
    result = judge(bot.store.session(sid), bot.store.events(sid, limit=100000))
    result["case"] = case.get("name")
    return result


def run_suite(bot, path, round_=None, defenses=None):
    """Score every case in a suite file. Returns the judge results, each tagged with its case name."""
    return [run_case(bot, case, round_, defenses) for case in load_cases(path)]
