"""
CleanDrop installer — core logic.

Kept separate from the Tkinter UI so each step can be tested and
reasoned about independently. Windows-only APIs (winreg, schtasks)
are imported lazily inside the functions that need them, so this
module can still be imported and partially exercised elsewhere.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import zipfile
import urllib.request
from pathlib import Path


APP_NAME = "CleanDrop"
NATIVE_HOST_NAME = "com.cleandrop.host"

UNINSTALLER_DIR_NAME = "CleanDropUninstaller"
UNINSTALLER_EXE_NAME = "CleanDropUninstall.exe"

UNINSTALL_REGISTRY_PATH = (
    "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\"
    + APP_NAME
)

# Fill these in once the extension is published to the Chrome Web
# Store. Until then, the wizard falls back to "load unpacked"
# instructions with a fixed dev-mode ID the user must copy in.
CHROME_WEBSTORE_URL = None
CHROME_WEBSTORE_EXTENSION_ID = None

DEFAULT_LLM_PORT = 58080

CREATE_NO_WINDOW = (
    subprocess.CREATE_NO_WINDOW
    if sys.platform == "win32"
    else 0
)

def default_install_dir():
    base = os.environ.get("LOCALAPPDATA", str(Path.home()))
    return Path(base) / APP_NAME


def default_uninstaller_dir():
    base = os.environ.get(
        "LOCALAPPDATA",
        str(Path.home())
    )

    return Path(base) / UNINSTALLER_DIR_NAME


def default_uninstaller_path():
    return (
        default_uninstaller_dir()
        / UNINSTALLER_EXE_NAME
    )


# ------------------------------------------------------------------
# Port handling
# ------------------------------------------------------------------

def is_port_free(port, host="127.0.0.1"):

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:

        sock.settimeout(0.5)

        try:
            sock.connect((host, port))
            return False  # something answered -> port is taken

        except (ConnectionRefusedError, OSError):
            return True


def find_free_port(preferred=DEFAULT_LLM_PORT, attempts=25):

    port = preferred

    for _ in range(attempts):

        if is_port_free(port):
            return port

        port += 1

    raise RuntimeError(
        f"Could not find a free port near {preferred} "
        f"after {attempts} attempts"
    )


# ------------------------------------------------------------------
# Existing installation handling
# ------------------------------------------------------------------

def stop_existing_installation(log=print):
    names = (
        "cleandrop-host.exe",
        "cleandrop-scheduler.exe",
        "llama-server.exe",
    )

    # Stop scheduled task first.
    subprocess.run(
        ["schtasks", "/end", "/tn", "CleanDrop Scheduler"],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW
    )

    for name in names:
        result = subprocess.run(
            ["taskkill", "/IM", name, "/F", "/T"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW
        )

        if result.returncode == 0:
            log(f"Stopped existing {name}")

    import time
    time.sleep(1)


# ------------------------------------------------------------------
# File installation
# ------------------------------------------------------------------

def copy_application_files(source_dir, install_dir, log=print):

    source_dir = Path(source_dir)
    install_dir = Path(install_dir)

    install_dir.mkdir(parents=True, exist_ok=True)

    for name in ("cleandrop-host.exe", "cleandrop-scheduler.exe"):

        src = source_dir / name

        if not src.exists():
            raise FileNotFoundError(
                f"Missing required file: {src}"
            )

        shutil.copy2(src, install_dir / name)

        log(f"Copied {name}")

    extension_src = source_dir / "extension"
    extension_dst = install_dir / "extension"

    if extension_dst.exists():
        shutil.rmtree(extension_dst)

    shutil.copytree(extension_src, extension_dst)

    log("Copied extension files")

    return install_dir


def write_native_host_manifest(install_dir, extension_id, log=print):

    install_dir = Path(install_dir)

    manifest = {
        "name": NATIVE_HOST_NAME,
        "description": "CleanDrop Native Messaging Host",
        "path": str(install_dir / "cleandrop-host.exe"),
        "type": "stdio",
        "allowed_origins": [
            f"chrome-extension://{extension_id}/"
        ]
    }

    manifest_path = install_dir / f"{NATIVE_HOST_NAME}.json"

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    log(f"Wrote native messaging manifest: {manifest_path}")

    return manifest_path


def register_native_host(manifest_path, log=print):

    import winreg

    key_path = (
        "Software\\Google\\Chrome\\NativeMessagingHosts\\"
        + NATIVE_HOST_NAME
    )

    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)

    winreg.SetValue(
        key, "", winreg.REG_SZ, str(manifest_path)
    )

    winreg.CloseKey(key)

    log("Registered native messaging host in registry")


def register_scheduled_task(install_dir, log=print):

    install_dir = Path(install_dir)
    exe_path = install_dir / "cleandrop-scheduler.exe"

    result = subprocess.run(
        [
            "schtasks", "/create",
            "/tn", "CleanDrop Scheduler",
            "/tr", str(exe_path),
            "/sc", "onlogon",
            "/f"
        ],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW
    )

    if result.returncode != 0:
        raise RuntimeError(
            "schtasks /create failed: "
            + (result.stderr.strip() or result.stdout.strip())
        )

    log("Registered scheduled task: CleanDrop Scheduler")

    result = subprocess.run(
        ["schtasks", "/run", "/tn", "CleanDrop Scheduler"],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW
    )

    if result.returncode != 0:
        raise RuntimeError(
            "schtasks /run failed: "
            + (result.stderr.strip() or result.stdout.strip())
        )

    log("Started CleanDrop Scheduler")


def write_app_config(
    install_dir,
    llm_port,
    llm_server_exe=None,
    llm_model_path=None,
    llm_server_args=None,
    log=print
):

    install_dir = Path(install_dir)

    app_dir = Path.home() / ".cleandrop"
    app_dir.mkdir(parents=True, exist_ok=True)

    config_path = app_dir / "config.json"

    config = {
        "llm_port": llm_port,
        "llm_server_exe":
            str(llm_server_exe) if llm_server_exe else None,
        "llm_model_path":
            str(llm_model_path) if llm_model_path else None,
        "llm_server_args":
            list(llm_server_args) if llm_server_args else None,
        "install_dir": str(install_dir),
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    log(f"Wrote config: {config_path} (llm_port={llm_port})")

    return config_path


# ------------------------------------------------------------------
# Windows uninstall registration
# ------------------------------------------------------------------

def register_uninstaller(uninstaller_path, install_dir, log=print):
    import winreg

    uninstaller_path = Path(uninstaller_path).resolve()
    install_dir = Path(install_dir).resolve()

    key = winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        UNINSTALL_REGISTRY_PATH,
    )

    try:
        winreg.SetValueEx(
            key,
            "DisplayName",
            0,
            winreg.REG_SZ,
            APP_NAME,
        )

        winreg.SetValueEx(
            key,
            "DisplayVersion",
            0,
            winreg.REG_SZ,
            "1.0.0",
        )

        winreg.SetValueEx(
            key,
            "Publisher",
            0,
            winreg.REG_SZ,
            "CleanDrop",
        )

        winreg.SetValueEx(
            key,
            "InstallLocation",
            0,
            winreg.REG_SZ,
            str(install_dir),
        )

        winreg.SetValueEx(
            key,
            "UninstallString",
            0,
            winreg.REG_SZ,
            f'"{uninstaller_path}"',
        )

        winreg.SetValueEx(
            key,
            "NoModify",
            0,
            winreg.REG_DWORD,
            1,
        )

        winreg.SetValueEx(
            key,
            "NoRepair",
            0,
            winreg.REG_DWORD,
            1,
        )

    finally:
        winreg.CloseKey(key)

    log("Registered CleanDrop in Windows Installed Apps")


# ------------------------------------------------------------------
# Local LLM setup
# ------------------------------------------------------------------

def download_with_progress(url, dest_path, on_progress=None):

    def reporthook(block_num, block_size, total_size):

        if on_progress and total_size > 0:
            downloaded = block_num * block_size
            percent = min(100, int(downloaded * 100 / total_size))
            on_progress(percent)

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CleanDrop-Installer"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:

        total_size = int(
            response.headers.get("Content-Length", 0)
        )

        downloaded = 0
        block_size = 65536

        with open(dest_path, "wb") as out_file:

            while True:

                chunk = response.read(block_size)

                if not chunk:
                    break

                out_file.write(chunk)
                downloaded += len(chunk)

                if on_progress and total_size > 0:
                    percent = min(
                        100,
                        int(downloaded * 100 / total_size)
                    )
                    on_progress(percent)


def get_latest_llama_cpp_release_url(log=print):
    """
    Checks the last several llama.cpp releases (not just the literal
    "latest" tag) for one with a Windows build, since a freshly
    tagged release can occasionally be published before its CI-built
    assets finish uploading. Prefers a plain CPU build (no GPU driver
    dependency) but falls back to any Windows build rather than
    failing outright if only GPU-specific builds are available.
    """

    api_url = (
        "https://api.github.com/repos/ggml-org/llama.cpp/"
        "releases?per_page=10"
    )

    request = urllib.request.Request(
        api_url,
        headers={"User-Agent": "CleanDrop-Installer"}
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        releases = json.loads(response.read().decode("utf-8"))

    all_names_seen = []

    for release in releases:

        candidates = []

        for asset in release.get("assets", []):

            name = asset["name"].lower()
            all_names_seen.append(asset["name"])

            if not name.endswith(".zip"):
                continue

            if "win" not in name:
                continue

            gpu_backends = (
                "cuda", "rocm", "hip", "sycl", "vulkan"
            )

            if any(gpu in name for gpu in gpu_backends):
                # Still a candidate (better than nothing), but
                # ranked below a plain CPU build.
                candidates.append(asset)

            elif "cpu" in name:
                candidates.insert(0, asset)

            else:
                candidates.append(asset)

        if candidates:

            chosen = candidates[0]

            log(
                f"Found llama.cpp release asset: {chosen['name']} "
                f"(release {release.get('tag_name')})"
            )

            return chosen["browser_download_url"]

    raise RuntimeError(
        "Could not find a Windows build in the last "
        f"{len(releases)} llama.cpp releases. Actual asset names "
        f"seen: {sorted(set(all_names_seen))}"
    )


def setup_llama_server(
    install_dir,
    on_progress=None,
    log=print
):
    """
    Downloads and extracts just the llama-server binary. The model
    itself is NOT downloaded here — llm_server_args uses llama.cpp's
    own -hf auto-download, so llama-server fetches and caches the
    model itself the first time it actually runs.
    """

    llm_dir = install_dir / "llm"
    staging_dir = install_dir / "llm-staging"

    llm_dir.mkdir(parents=True, exist_ok=True)

    # Clean previous staging directory.
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    staging_dir.mkdir(parents=True)

    log("Looking up latest llama.cpp release...")

    zip_url = get_latest_llama_cpp_release_url(log=log)

    zip_path = staging_dir / "llama_cpp.zip"

    log("Downloading llama.cpp server...")

    download_with_progress(
        zip_url,
        zip_path,
        on_progress=on_progress,
    )

    log("Extracting llama.cpp...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(staging_dir)

    zip_path.unlink()

    server_exe = None

    for path in staging_dir.rglob("llama-server.exe"):
        server_exe = path
        break

    if not server_exe:
        raise RuntimeError(
            "llama-server.exe not found after extracting "
            "the release archive"
        )

    # Replace the live llama.cpp installation only after
    # the download and extraction succeeded.
    if llm_dir.exists():
        shutil.rmtree(llm_dir)

    shutil.move(str(staging_dir), str(llm_dir))

    # Re-resolve the executable because it moved.
    server_exe = next(
        llm_dir.rglob("llama-server.exe"),
        None,
    )

    if not server_exe:
        raise RuntimeError(
            "llama-server.exe not found after installing "
            "the llama.cpp runtime"
        )

    return server_exe


def launch_llm_server(server_exe, port, extra_args, log=print):

    creationflags = 0

    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        [str(server_exe)]
        + list(extra_args)
        + ["--port", str(port), "--host", "127.0.0.1"],
        creationflags=creationflags,
        cwd=str(server_exe.parent)
    )

    log(f"Started llama-server on port {port}")
