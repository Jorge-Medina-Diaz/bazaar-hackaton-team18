"""One place to build the team's Bazaar client: reads BAZAAR_URL / BAZAAR_KEY from the environment or a local .env."""
import os

from bazaar_sdk import Bazaar


def _load_env(path: str = ".env") -> None:
    if os.path.exists(path):  # KEY=value lines; never committed (.gitignore)
        for line in open(path, encoding="utf-8"):
            k, sep, v = line.strip().partition("=")
            if sep and not k.startswith("#"):
                os.environ.setdefault(k.removeprefix("export ").strip(), v.strip().strip('"'))


def client() -> Bazaar:
    _load_env()
    return Bazaar(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), os.environ["BAZAAR_KEY"])
