"""Arena settings, read from .env (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE_URL = os.getenv("ARENA_BASE_URL", "")
API_KEY = os.getenv("ARENA_API_KEY", "")

MODELS = {
    "red_strategist": os.getenv("RED_STRATEGIST_MODEL", ""),
    "red_attacker": os.getenv("RED_ATTACKER_MODEL", ""),
    "target": os.getenv("TARGET_MODEL", ""),
    "blue_guard": os.getenv("BLUE_GUARD_MODEL", ""),
    "blue_judge": os.getenv("BLUE_JUDGE_MODEL", ""),
}

DB_PATH = Path(os.getenv("ARENA_DB", ROOT / "arena" / "data" / "arena.db"))
WORLD_DB = Path(os.getenv("ARENA_WORLD_DB", ROOT / "arena" / "data" / "world.db"))
