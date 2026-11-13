"""Packaging must ship the git tree, not a dirty worktree (live 257e811 F13)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "scripts/package_lambda.sh").read_text()


def test_package_lambda_uses_git_archive_not_worktree_copy():
    assert 'archive HEAD "$APP_TREE"' in SCRIPT
    assert 'APP_TREE="${REPO_PREFIX}backend/app"' in SCRIPT
    assert 'git -C "$GIT_ROOT" ls-files -- "$APP_TREE"' in SCRIPT
    assert "_build_manifest.txt" in SCRIPT
    assert "hash-object" in SCRIPT
    assert not re.search(r"\bcp\s+-R\b", SCRIPT)


def test_parse_llm_json_still_keeps_complete_repaired_last_claim():
    """Do not revive cut = not body.endswith('}'). Semantics stay incomplete_last only."""
    from app.services.generator import parse_llm_json

    src = (ROOT / "backend/app/services/generator.py").read_text()
    assert "incomplete_last" in src
    assert "not body.rstrip().endswith" not in src
    raw = (
        '{"answer":"The grant covers a conference pass, flight, and hotel.",'
        '"claims":['
        '{"text":"pass","source":"P1.U0","quote":"A full conference pass"},'
        '{"text":"flight","source":"P1.U0","quote":"Roundtrip flight"},'
        '{"text":"hotel","source":"P1.U0","quote":"Hotel accommodations in Event Location"}'
        "]"
    )
    data, how = parse_llm_json(raw)
    assert how == "repaired"
    assert len(data["claims"]) == 3
    assert "hotel" in data["claims"][-1]["quote"].lower()
