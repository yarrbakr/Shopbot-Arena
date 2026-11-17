"""Give every test a fresh in-memory World, so write-tools can't pollute the real world.db
or leak state between tests. Patches the shared WORLD everywhere it's referenced."""
import pytest

from arena.shop import world as world_mod


@pytest.fixture(autouse=True)
def fresh_world(monkeypatch):
    w = world_mod.World(":memory:")
    monkeypatch.setattr("arena.shop.world.WORLD", w, raising=False)
    monkeypatch.setattr("arena.shop.tools.WORLD", w, raising=False)
    monkeypatch.setattr("arena.shop.agent.WORLD", w, raising=False)
    yield w
