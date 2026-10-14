# CleanDrop Installer

CleanDrop includes a Tkinter-based installation wizard that automates setup, eliminating the need for manual configuration. It installs the companion executables, registers the native messaging host, configures the persistent scheduler as a logon task, and optionally downloads and configures a local LLM for AI-powered filename suggestions.

## Files

- `wizard.py` — Page-based installation wizard: Welcome → Location → AI Options → Install Progress → Extension Setup → Finish.
- `steps.py` — Installation logic, separated from the UI for independent testing.
- `prepare_resources.py` — Copies the built executables and extension files into `resources/` before packaging.
- `wizard.spec` — PyInstaller specification for bundling resources into the installer executable.

## Building the Installer

```powershell
# 1. Build the companion executables
cd companion
pyinstaller cleandrop-host.spec
pyinstaller cleandrop-scheduler.spec
cd ..

# 2. Prepare installer resources
cd installer
python prepare_resources.py

# 3. Build the installer
pyinstaller wizard.spec
```

The installer is generated at `installer/dist/CleanDropSetup.exe`.

## Running During Development

No packaging is required to run the wizard directly.

```powershell
cd installer
python prepare_resources.py
python wizard.py
```

## Automated Setup

| Manual Setup | Automated Installation |
|---|---|
| Copy executables and manually configure the `com.cleandrop.host.json` path | Copies files and generates the manifest with the correct path |
| Run `reg import install-host.reg` | Registers the native messaging host through `winreg` |
| Run `schtasks /create ...` and `schtasks /run ...` | Executes the equivalent commands automatically |
| Manually resolve `LLAMA_URL` port conflicts | Selects an available port starting at `58080` and stores it in `config.json`, shared by the installer and companion app |
| Download llama.cpp and a GGUF model, then launch `llama-server.exe` manually | Downloads the latest Windows CPU build from GitHub Releases and a pinned lightweight model, then launches the local server |
