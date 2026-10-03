"""Test package (M0). Importing it isolates the environment (INV-21): test mode on, no .env, no key, no URL."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["BAZAAR_TEST"] = "1"
os.environ["BAZAAR_NO_DOTENV"] = "1"
os.environ.pop("BAZAAR_KEY", None)
os.environ.pop("BAZAAR_URL", None)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HARVEST = FIXTURES / "harvest"              # copy of logs/harvest/*.json without keys
PROBE = HARVEST / "probe"                   # copy of logs/probe/157/ (latest probe snapshot) without keys
