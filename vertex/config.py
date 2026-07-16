"""Config loader — non-secret settings from config.yaml, secrets from .env (git-ignored).

Keeping secrets out of the tree is the v2 hygiene fix: v1 committed its Telegram token
and Groq key to git history. Here they only ever come from the environment / .env.
"""

import os

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env(path):
    """Minimal .env parser (no python-dotenv dependency). Does not overwrite real env vars."""
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def load_config(root=None):
    """Return the merged config dict. `secrets` is populated from the environment only;
    `_root` is the project root so modules can resolve data/ paths."""
    root = root or PROJECT_ROOT
    _load_env(os.path.join(root, ".env"))
    with open(os.path.join(root, "config.yaml")) as f:
        cfg = yaml.safe_load(f)
    cfg["secrets"] = {
        "telegram_token": os.environ.get("TELEGRAM_TOKEN", ""),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "groq_api_key": os.environ.get("GROQ_API_KEY", ""),
    }
    # Per-machine override (set in .env): lets the SAME config.yaml run on the Mac and on
    # a Windows VPS, where the MT5 Files folder lives at a different path.
    qd = os.environ.get("QUEUE_DIR")
    if qd:
        cfg.setdefault("execution", {})["queue_dir"] = qd
    cfg["_root"] = root
    return cfg
