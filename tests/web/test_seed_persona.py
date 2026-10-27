"""seed_persona contract: format-agnostic id acceptance (Task 13).

The persona id is a DATASET ACCOUNT id. The indo corpus names accounts
`dummy_NNNN`; MIND used `U#####`. The check must be membership in
`user_map` only — no id-format gate — so an `I...`-shaped account id (the
indo article-id namespace, if it ever names an account) is accepted too.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
for p in (str(SRC), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)


class FakeRecommender:
    def __init__(self, user_map):
        self._d = {"user_map": user_map}


def _run_seed(monkeypatch, tmp_path, persona_id, user_map):
    import web.seed_persona as sp

    monkeypatch.setattr(sp, "load_config", lambda: SimpleNamespace(
        persona_user_id=persona_id,
        persona_email="t@example.com",
        persona_password="throwaway-pw",
        db_path=str(tmp_path / "web.db"),
    ))
    import api.main as frozen
    monkeypatch.setattr(frozen, "load_recommender",
                        lambda: FakeRecommender(user_map))
    return sp.main()


def test_seed_accepts_indo_account_ids(monkeypatch, tmp_path):
    assert _run_seed(monkeypatch, tmp_path, "dummy_0000",
                     {"dummy_0000": 0}) == 0


def test_seed_accepts_any_id_type_in_user_map(monkeypatch, tmp_path):
    # no format gate: whatever the era names accounts, membership decides
    assert _run_seed(monkeypatch, tmp_path, "Iabc123def4",
                     {"Iabc123def4": 0}) == 0


def test_seed_rejects_unknown_id(monkeypatch, tmp_path):
    assert _run_seed(monkeypatch, tmp_path, "U99999999",
                     {"dummy_0000": 0}) == 3


def test_seed_skips_without_env(monkeypatch, tmp_path):
    import web.seed_persona as sp

    monkeypatch.setattr(sp, "load_config", lambda: SimpleNamespace(
        persona_user_id=None, persona_email=None, persona_password=None,
        db_path=str(tmp_path / "web.db"),
    ))
    assert sp.main() == 2
