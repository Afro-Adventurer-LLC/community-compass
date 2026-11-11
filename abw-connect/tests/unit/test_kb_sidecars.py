from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 1024


def test_kb_metadata_sidecars_are_at_most_1kb():
    files = sorted((ROOT / "kb").rglob("*.metadata.json"))
    assert files, "expected kb metadata sidecars"
    over = [f"{p.relative_to(ROOT)} ({p.stat().st_size}B)" for p in files if p.stat().st_size > MAX_BYTES]
    assert not over, "sidecars over 1KB; run python scripts/slim_kb_metadata.py: " + ", ".join(over)
