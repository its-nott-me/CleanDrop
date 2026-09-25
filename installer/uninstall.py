"""
CleanDrop GUI uninstaller.

Reverses everything wizard.py sets up:
- running processes
- scheduled task
- native messaging registry key
- installation directory
- app data

Usage:
    python uninstall.py
    python uninstall.py --yes
"""

import ctypes
import shutil
import subprocess
import sys
import os
import threading
import time
import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import steps


APP_TITLE = "CleanDrop Uninstaller"
WINDOW_SIZE = "640x480"

CREATE_NO_WINDOW = (
    subprocess.CREATE_NO_WINDOW
    if sys.platform == "win32"
    else 0
)


# ------------------------------------------------------------------
# Windows / elevation
# ------------------------------------------------------------------

def is_admin():
    if sys.platform != "win32":
        return True

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():

    params = " ".join(
        f'"{arg}"'
        for arg in sys.argv[1:]
    )

    if getattr(sys, "frozen", False):
        executable = sys.executable

    else:
        interpreter = Path(sys.executable)

        # Use pythonw.exe so elevation does not open a console window.
        windowless = interpreter.with_name("pythonw.exe")

        executable = (
            str(windowless)
            if windowless.exists()
            else sys.executable
        )

        params = (
            f'"{Path(__file__).resolve()}" {params}'
        ).strip()

    ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        params,
        None,
        1,
    )


# ------------------------------------------------------------------
# Uninstall operations
# ------------------------------------------------------------------

def kill_running_processes(log=print):

    names = (
        "cleandrop-host.exe",
        "cleandrop-scheduler.exe",
        "llama-server.exe",
    )

    for name in names:

        result = subprocess.run(
            ["taskkill", "/IM", name, "/F", "/T"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        )

        if result.returncode == 0:
            log(f"Stopped {name}")
        else:
            log(f"{name} was not running")

    # Wait until Windows has actually released the file handles.
    for _ in range(20):

        still_running = False

        for name in names:

            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"IMAGENAME eq {name}",
                ],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
            )

            if name.lower() in result.stdout.lower():
                still_running = True
                break

        if not still_running:
            log("All CleanDrop processes have exited.")
            return

        time.sleep(0.25)

    raise RuntimeError(
        "CleanDrop processes are still running after termination."
    )


def remove_scheduled_task(log=print):

    result = subprocess.run(
        [
            "schtasks",
            "/delete",
            "/tn",
            "CleanDrop Scheduler",
            "/f",
        ],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )

    if result.returncode == 0:
        log("Removed scheduled task: CleanDrop Scheduler")
    else:
        log("Scheduled task not found (already removed)")


def remove_registry_key(log=print):

    import winreg

    key_path = (
        "Software\\Google\\Chrome\\NativeMessagingHosts\\"
        + steps.NATIVE_HOST_NAME
    )

    try:

        winreg.DeleteKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
        )

        log("Removed native messaging registry key")

    except FileNotFoundError:

        log("Registry key not found (already removed)")


def remove_install_dir(install_dir, log=print):

    install_dir = validate_install_dir(install_dir)

    if install_dir is None:
        raise RuntimeError(
            "The recorded CleanDrop installation path failed "
            "safety validation. No application files were deleted."
        )

    if not install_dir.exists():
        log(
            f"CleanDrop installation not found: {install_dir}"
        )
        return

    log(f"Validated CleanDrop installation: {install_dir}")

    try:
        shutil.rmtree(install_dir)

    except Exception as error:
        raise RuntimeError(
            f"Could not remove installation directory:\n"
            f"{install_dir}\n\n"
            f"{error}"
        ) from error

    if install_dir.exists():
        raise RuntimeError(
            f"Installation directory still exists after removal:\n"
            f"{install_dir}"
        )

    log(f"Removed install directory: {install_dir}")


def remove_app_data(log=print):

    app_dir = Path.home() / ".cleandrop"

    if app_dir.exists():

        shutil.rmtree(app_dir)

        log(f"Removed app data: {app_dir}")

    else:

        log("App data not found (already removed)")


def get_recorded_install_dir():

    config_path = Path.home() / ".cleandrop" / "config.json"

    if not config_path.exists():
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        install_dir = config.get("install_dir")

        if not install_dir:
            return None

        return Path(install_dir)

    except (OSError, json.JSONDecodeError):
        return None


def validate_install_dir(path):
    """
    Validate that a recorded path is plausibly a CleanDrop
    installation before allowing recursive deletion.

    Returns:
        Path: validated path
        None: unsafe / unknown path
    """

    if path is None:
        return None

    try:
        path = Path(path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return None

    # --------------------------------------------------------------
    # Basic path safety
    # --------------------------------------------------------------

    if not path.is_absolute():
        return None

    # Never delete a filesystem root.
    if path.parent == path:
        return None

    # Must be named CleanDrop.
    if path.name.casefold() != "cleandrop":
        return None

    # Never delete the user's home directory.
    try:
        if path.samefile(Path.home()):
            return None
    except (FileNotFoundError, OSError):
        # samefile requires the path to exist.
        pass

    # If something exists at this path, it must be a directory.
    if path.exists() and not path.is_dir():
        return None

    # --------------------------------------------------------------
    # If directory exists, require CleanDrop markers
    # --------------------------------------------------------------

    if path.exists():

        markers = [
            path / "cleandrop-host.exe",
            path / "cleandrop-scheduler.exe",
        ]

        # At least one of our application executables must exist.
        if not any(marker.is_file() for marker in markers):
            return None

    return path


def remove_uninstaller_later(log=print):

    uninstaller_dir = steps.default_uninstaller_dir()
    uninstaller_exe = steps.default_uninstaller_path()

    if not uninstaller_exe.exists():
        return

    cleanup_script = uninstaller_dir / "_cleanup.bat"

    script = f"""@echo off
timeout /t 2 /nobreak >nul
del /f /q "{uninstaller_exe}"
rmdir /s /q "{uninstaller_dir}"
del /f /q "%~f0"
"""

    try:
        cleanup_script.write_text(
            script,
            encoding="utf-8",
        )

        subprocess.Popen(
            [
                "cmd.exe",
                "/c",
                str(cleanup_script),
            ],
            creationflags=(
                subprocess.CREATE_NO_WINDOW
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

    except Exception as error:
        log(
            f"Could not schedule uninstaller cleanup: {error}"
        )


def remove_uninstall_registration(log=print):

    import winreg

    try:

        winreg.DeleteKey(
            winreg.HKEY_CURRENT_USER,
            steps.UNINSTALL_REGISTRY_PATH,
        )

        log(
            "Removed CleanDrop from Windows Installed Apps"
        )

    except FileNotFoundError:

        log(
            "Windows uninstall registration not found"
        )


# ------------------------------------------------------------------
# GUI
# ------------------------------------------------------------------

class UninstallerApp(tk.Tk):

    def __init__(self):

        super().__init__()

        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.resizable(False, False)

        self.install_dir = get_recorded_install_dir()
        self.app_dir = Path.home() / ".cleandrop"

        self.build_ui()

    def build_ui(self):

        self.container = ttk.Frame(
            self,
            padding=24,
        )

        self.container.pack(
            fill="both",
            expand=True,
        )

        # ----------------------------------------------------------
        # Title
        # ----------------------------------------------------------

        ttk.Label(
            self.container,
            text="Uninstall CleanDrop",
            font=("Segoe UI", 18, "bold"),
        ).pack(
            anchor="w",
            pady=(0, 12),
        )

        ttk.Label(
            self.container,
            text=(
                "This will completely remove CleanDrop from "
                "your computer."
            ),
            wraplength=560,
            justify="left",
        ).pack(
            anchor="w",
            pady=(0, 20),
        )

        # ----------------------------------------------------------
        # What will be removed
        # ----------------------------------------------------------

        ttk.Label(
            self.container,
            text="The following will be removed:",
            font=("Segoe UI", 10, "bold"),
        ).pack(
            anchor="w",
            pady=(0, 8),
        )

        items = [
            "CleanDrop background processes",
            "CleanDrop Scheduler",
            "Chrome native messaging integration",
        ]

        if self.install_dir:
            items.append(
                f"Application files: {self.install_dir}"
            )
        else:
            items.append(
                "Application files: install location not found"
            )

        items.append(
            f"Application data: {self.app_dir}"
        )

        for item in items:

            ttk.Label(
                self.container,
                text=f"• {item}",
                wraplength=560,
                justify="left",
            ).pack(
                anchor="w",
                padx=(12, 0),
                pady=2,
            )

        # Spacer

        ttk.Frame(
            self.container
        ).pack(
            fill="both",
            expand=True,
        )

        # ----------------------------------------------------------
        # Buttons
        # ----------------------------------------------------------

        self.button_frame = ttk.Frame(
            self.container
        )

        self.button_frame.pack(
            fill="x"
        )

        self.cancel_button = ttk.Button(
            self.button_frame,
            text="Cancel",
            command=self.destroy,
        )

        self.cancel_button.pack(
            side="left"
        )

        self.uninstall_button = ttk.Button(
            self.button_frame,
            text="Uninstall",
            command=self.confirm_uninstall,
        )

        self.uninstall_button.pack(
            side="right"
        )

    # --------------------------------------------------------------
    # Confirmation
    # --------------------------------------------------------------

    def confirm_uninstall(self):

        if "--yes" not in sys.argv:

            confirmed = messagebox.askyesno(
                "Confirm Uninstall",
                (
                    "Are you sure you want to uninstall CleanDrop?\n\n"
                    "All CleanDrop application files and local "
                    "configuration will be removed."
                ),
                parent=self,
            )

            if not confirmed:
                return

        self.show_progress()

        thread = threading.Thread(
            target=self.run_uninstall,
            daemon=True,
        )

        thread.start()

    # --------------------------------------------------------------
    # Progress screen
    # --------------------------------------------------------------

    def show_progress(self):

        for widget in self.container.winfo_children():
            widget.destroy()

        ttk.Label(
            self.container,
            text="Uninstalling...",
            font=("Segoe UI", 14, "bold"),
        ).pack(
            anchor="w",
            pady=(0, 12),
        )

        self.progress = ttk.Progressbar(
            self.container,
            mode="determinate",
            maximum=100,
        )

        self.progress.pack(
            fill="x",
            pady=(0, 12),
        )

        self.log_text = tk.Text(
            self.container,
            height=14,
            state="disabled",
            wrap="word",
        )

        self.log_text.pack(
            fill="both",
            expand=True,
        )

        self.close_button = ttk.Button(
            self.container,
            text="Close",
            command=self.destroy,
            state="disabled",
        )

        self.close_button.pack(
            anchor="e",
            pady=(12, 0),
        )

    # --------------------------------------------------------------
    # Thread-safe GUI logging
    # --------------------------------------------------------------

    def log(self, message):

        self.after(
            0,
            self._append_log,
            message,
        )

    def _append_log(self, message):

        self.log_text.configure(
            state="normal"
        )

        self.log_text.insert(
            "end",
            message + "\n",
        )

        self.log_text.see("end")

        self.log_text.configure(
            state="disabled"
        )

    def set_progress(self, value):

        self.after(
            0,
            lambda: self.progress.configure(
                value=value
            ),
        )

    # --------------------------------------------------------------
    # Actual uninstall
    # --------------------------------------------------------------

    def run_uninstall(self):

        try:

            self.log("Stopping CleanDrop processes...")
            self.set_progress(15)

            # Stop processes FIRST.
            self.log("Removing scheduled task...")
            remove_scheduled_task(log=self.log)

            self.set_progress(30)

            self.log("Stopping running services...")
            kill_running_processes(log=self.log)

            self.set_progress(50)

            self.log("Removing Chrome native messaging integration...")
            remove_registry_key(log=self.log)

            self.set_progress(65)

            self.log("Removing application files...")
            remove_install_dir(
                self.install_dir,
                log=self.log,
            )

            self.set_progress(80)

            self.log("Removing application data...")
            remove_app_data(log=self.log)

            self.set_progress(90)

            self.log(
                "Removing Windows uninstall registration..."
            )

            remove_uninstall_registration(
                log=self.log
            )

            self.set_progress(100)

            self.log("")
            self.log("CleanDrop was successfully removed.")

            self.after(
                0,
                self.show_success,
            )

        except Exception as error:

            self.log("")
            self.log(f"ERROR: {error}")

            self.after(
                0,
                lambda: self.show_error(str(error)),
            )

    # --------------------------------------------------------------
    # Completion
    # --------------------------------------------------------------

    def show_success(self):

        self.close_button.configure(
            state="normal"
        )

        self.close_button.focus_set()

        messagebox.showinfo(
            "Uninstall Complete",
            "CleanDrop has been successfully removed.",
            parent=self,
        )

        remove_uninstaller_later()

        self.destroy()

    def show_error(self, error):

        self.close_button.configure(
            state="normal"
        )

        messagebox.showerror(
            "Uninstallation Failed",
            (
                "CleanDrop could not be completely removed.\n\n"
                f"{error}"
            ),
            parent=self,
        )


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":

    if not is_admin():

        relaunch_as_admin()
        sys.exit(0)

    app = UninstallerApp()
    app.mainloop()
