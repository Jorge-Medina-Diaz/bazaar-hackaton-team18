"""Append-only JSONL logs under logs/<stream>.jsonl: every round, deal and error, for later analysis."""
import json, os, time  # noqa: E401

LOG_DIR = os.environ.get("BAZAAR_LOGS", "logs")


def log(stream: str, **row) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, f"{stream}.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": round(time.time(), 2), **row}, ensure_ascii=False) + "\n")
