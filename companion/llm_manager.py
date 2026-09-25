"""
Ensures the local LLM server is running, starting it if it isn't.

Called periodically from the persistent scheduler process (not the
ephemeral host — this needs a process that stays alive to matter).
If AI renaming wasn't enabled at install time, there's nothing
configured here and this quietly does nothing.
"""

import socket
import subprocess
import sys
from pathlib import Path

import config


def is_llm_server_running(port, host="127.0.0.1"):

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:

        sock.settimeout(1.0)

        try:
            sock.connect((host, port))
            return True

        except OSError:
            return False


def _strip_port_and_host_args(args):
    """
    Removes any --port/--host (and their values) from a custom
    args list. llm_port in config.json is meant to be the single
    source of truth — both this watchdog's health check and
    filename_model.py's get_llm_url() read from it — so a
    duplicated --port inside llm_server_args could silently
    drift out of sync with it. Always inject the canonical port
    instead of trusting a copy of it.
    """

    cleaned = []
    skip_next = False

    for arg in args:

        if skip_next:
            skip_next = False
            continue

        if arg in ("--port", "--host"):
            skip_next = True
            continue

        cleaned.append(arg)

    return cleaned


def ensure_llm_server_running(log=print):

    cfg = config.load_config()

    server_exe = cfg.get("llm_server_exe")
    model_path = cfg.get("llm_model_path")
    server_args = cfg.get("llm_server_args")
    port = cfg.get("llm_port", config.DEFAULT_LLM_PORT)

    if not server_exe or not (model_path or server_args):
        # AI renaming wasn't configured — nothing to manage.
        # This is the normal, expected state until config.json
        # has real values in it.
        return

    if not Path(server_exe).exists():
        log(f"[LLM] Configured server exe not found, skipping: {server_exe}")
        return

    # Prefer the exact args list when present — it's whatever
    # command line actually works on this machine (e.g. -hf mode
    # pulling a model from Hugging Face directly, plus any tuning
    # flags like thread count or context size), rather than a
    # reconstruction that might not match. --port/--host are
    # always stripped and re-injected from llm_port below, so
    # there's one canonical port, not two copies that can drift.
    if server_args:
        args = _strip_port_and_host_args(list(server_args))

    else:
        if not Path(model_path).exists():
            log(f"[LLM] Configured model file not found, skipping: {model_path}")
            return

        args = ["--model", model_path]

    args += ["--port", str(port), "--host", "127.0.0.1"]

    if is_llm_server_running(port):
        return

    log(
        f"[LLM] Server not responding on port {port}, "
        f"starting it..."
    )

    creationflags = 0

    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        [server_exe] + args,
        creationflags=creationflags,
        cwd=str(Path(server_exe).parent)
    )

    log(f"[LLM] Launched llama-server on port {port}")