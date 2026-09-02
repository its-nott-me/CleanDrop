import json
from pathlib import Path


APP_DIR = Path.home() / ".cleandrop"
CONFIG_PATH = APP_DIR / "config.json"

# 58080 sits in IANA's dynamic/private port range (49152-65535),
# reserved specifically for unregistered local use — chosen instead
# of a common dev port like 8080 (Tomcat and countless other local
# servers default there) specifically to avoid collisions.
DEFAULT_LLM_PORT = 58080

_DEFAULTS = {
    "llm_port": DEFAULT_LLM_PORT,
}


def load_config():

    if not CONFIG_PATH.exists():
        return dict(_DEFAULTS)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)

    merged = dict(_DEFAULTS)
    merged.update(data)

    return merged


def save_config(updates):

    APP_DIR.mkdir(parents=True, exist_ok=True)

    current = load_config()
    current.update(updates)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)

    return current


def get_llm_port():
    return load_config().get("llm_port", DEFAULT_LLM_PORT)


def get_llm_url():
    port = get_llm_port()
    return f"http://127.0.0.1:{port}/v1/chat/completions"