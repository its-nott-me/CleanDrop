# CleanDrop Installer

A Tkinter wizard that handles everything the manual setup previously required by hand: copying the companion exes, registering the native messaging host, setting up the persistent scheduler as a logon task, and optionally downloading + configuring a local LLM for AI-powered renaming.

## Files

- `wizard.py` — the wizard UI (page-based: Welcome → Location → AI options → Install progress → Extension setup → Finish)
- `steps.py` — all actual installation logic, kept separate from the UI so it's independently testable
- `prepare_resources.py` — copies the built exes + extension folder into `resources/` before packaging
- `wizard.spec` — PyInstaller spec that bundles `resources/` into the final installer exe

## Building the installer

```powershell
# 1. Build the two companion exes first (from companion/)
cd companion
pyinstaller cleandrop-host.spec
pyinstaller cleandrop-scheduler.spec
cd ..

# 2. Gather them + the extension into installer/resources/
cd installer
python prepare_resources.py

# 3. Build the installer itself
pyinstaller wizard.spec
```

The final installer is at `installer/dist/CleanDropSetup.exe` — a single file you can hand to anyone.

## Running during development (no packaging needed)

```powershell
cd installer
python prepare_resources.py   # still needed, so wizard.py finds resources/
python wizard.py
```

## What it automates

| Manual step (before) | Wizard step (now) |
|---|---|
| Copy exes, edit `com.cleandrop.host.json` path by hand | Copies files, writes manifest with the correct path automatically |
| `reg import install-host.reg` | Registers the same registry key directly via `winreg` |
| `schtasks /create ...` / `schtasks /run ...` | Same commands, run automatically |
| Manually edit `LLAMA_URL` if port 8080 conflicted | Picks a free port starting from 58080 (IANA dynamic range), writes it to `config.json`, both the installer and the companion app read from there |
| Manually download llama.cpp + a GGUF model, run `llama-server.exe` by hand | Downloads the latest Windows CPU build from GitHub releases + a pinned small model, launches it |

## Before you ship this

- **`steps.CHROME_WEBSTORE_URL` / `CHROME_WEBSTORE_EXTENSION_ID`** are `None` right now. Once you publish to the Chrome Web Store, fill these in — the extension page switches from "load unpacked + paste your ID" instructions to a one-click Web Store link automatically.
- **`DEFAULT_MODEL_URL`** in `wizard.py` is pinned to a specific Qwen2.5-0.5B GGUF quant — verify that URL still resolves before shipping (Hugging Face repos occasionally reorganize file layouts), and swap it for a different model if you'd rather.
- Test the actual Windows-specific parts (`register_native_host`, `register_scheduled_task`) on a real Windows machine — I validated everything else here (file copying, manifest writing, port selection, the full page-navigation flow, and the GitHub releases API lookup) by actually running this code, but `winreg` and `schtasks` can only be exercised on Windows itself.