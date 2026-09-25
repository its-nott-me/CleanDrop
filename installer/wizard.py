"""
CleanDrop installation wizard.

A page-based Tkinter wizard that installs the native messaging host,
registers the persistent scheduler as a logon task, optionally sets
up a local LLM server for AI-powered renaming, and walks the user
through loading the Chrome extension.

Run with:
    python wizard.py

Or build a standalone installer with:
    pyinstaller wizard.spec
"""

import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import steps


def is_admin():
    if sys.platform != "win32":
        return True

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    """
    Re-launches this process with a UAC elevation prompt, then the
    caller should exit. Standard Windows installer behavior — and
    also resolves at least one real case where third-party security
    software (360 Total Security) silently blocked schtasks from a
    non-elevated process while allowing the identical elevated call.
    """

    params = " ".join(
        f'"{arg}"' for arg in sys.argv[1:]
    )

    if getattr(sys, "frozen", False):
        # Packaged exe: relaunch itself directly. wizard.spec
        # already builds with console=False, so there's no
        # console window to worry about here either way.
        executable = sys.executable

    else:
        # Running as a plain script: relaunch through pythonw.exe
        # (no console window at all) rather than python.exe — the
        # wizard is a GUI app and never needs a console, so this
        # avoids a terminal window flashing open during elevation.
        interpreter = Path(sys.executable)
        windowless = interpreter.with_name("pythonw.exe")

        executable = (
            str(windowless)
            if windowless.exists()
            else sys.executable
        )

        params = f'"{Path(__file__).resolve()}" {params}'.strip()

    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", executable, params, None, 1
    )


APP_TITLE = "CleanDrop Setup"
WINDOW_SIZE = "640x480"

# Uses llama.cpp's built-in Hugging Face auto-download (-hf) rather
# than the installer separately downloading and pinning a GGUF file
# itself — llama-server handles fetching and caching the model on
# first launch. Qwen3-0.6B with reasoning disabled is small and fast
# enough for filename suggestions; --reasoning off matters a lot
# here, since Qwen3's default "thinking" mode adds real latency to
# what should be a quick, simple text generation task.
DEFAULT_LLM_MODEL = "ggml-org/Qwen3-0.6B-GGUF:Q4_0"


def _default_thread_count():
    # Leave at least one core free — this runs in the background
    # while the user is actively using their machine, not as a
    # dedicated inference server.
    cpu_count = os.cpu_count() or 4
    return max(1, min(4, cpu_count - 1))


def _resolve_source_dir():
    """
    Resources (the two built exes + the extension folder) are
    expected in a 'resources' folder next to this script during
    development, or bundled alongside the packaged wizard exe via
    wizard.spec's `datas` — same relative layout either way, so
    this behaves identically in both cases.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent

    return base / "resources"


class WizardState:
    """Shared state passed between pages."""

    def __init__(self):
        self.source_dir = _resolve_source_dir()
        self.install_dir = steps.default_install_dir()
        self.enable_ai = tk.BooleanVar(value=True)
        self.extension_id = steps.CHROME_WEBSTORE_EXTENSION_ID or ""
        self.log_lines = []
        self.llm_port = None


def install_uninstaller(log=print):
    """
    Copy the packaged uninstaller to a location outside
    the CleanDrop installation directory.
    """

    uninstaller_dir = steps.default_uninstaller_dir()
    uninstaller_path = steps.default_uninstaller_path()

    source = Path(
        _resolve_source_dir()
    ) / "CleanDropUninstall.exe"

    if not source.exists():
        raise FileNotFoundError(
            f"Uninstaller not found: {source}"
        )

    uninstaller_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    import shutil

    shutil.copy2(
        source,
        uninstaller_path,
    )

    log(
        f"Installed uninstaller: {uninstaller_path}"
    )

    return uninstaller_path


class WizardApp(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.resizable(False, False)

        self.state_data = WizardState()

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)

        self.pages = {}

        for PageClass in (
            WelcomePage,
            LocationPage,
            OptionsPage,
            ProgressPage,
            ExtensionPage,
            FinishPage,
        ):
            page = PageClass(self.container, self)
            self.pages[PageClass] = page
            page.place(x=0, y=0, relwidth=1, relheight=1)

        self.show_page(WelcomePage)

    def show_page(self, page_class):
        page = self.pages[page_class]
        page.on_show()
        page.tkraise()


class WizardPage(ttk.Frame):
    """Base class for a single wizard page."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=24)
        self.app = app
        self.state_data = app.state_data
        self.build()

    def build(self):
        raise NotImplementedError

    def on_show(self):
        pass


class WelcomePage(WizardPage):

    def build(self):
        ttk.Label(
            self, text="Welcome to CleanDrop", font=("Segoe UI", 18, "bold")
        ).pack(anchor="w", pady=(0, 12))

        ttk.Label(
            self,
            wraplength=560,
            justify="left",
            text=(
                "This wizard will set up CleanDrop's background service, "
                "connect it to Chrome, and optionally configure local "
                "AI-powered filename suggestions.\n\n"
                "Everything runs entirely on this machine — no data is "
                "sent anywhere except to a local model server you control."
            ),
        ).pack(anchor="w")

        ttk.Frame(self).pack(fill="both", expand=True)

        ttk.Button(
            self, text="Next >", command=lambda: self.app.show_page(LocationPage)
        ).pack(anchor="e")


class LocationPage(WizardPage):

    def build(self):
        ttk.Label(
            self, text="Install Location", font=("Segoe UI", 14, "bold")
        ).pack(anchor="w", pady=(0, 12))

        ttk.Label(
            self,
            wraplength=560,
            justify="left",
            text="Choose where CleanDrop's background service files will live.",
        ).pack(anchor="w", pady=(0, 12))

        path_frame = ttk.Frame(self)
        path_frame.pack(fill="x", pady=(0, 24))

        self.path_var = tk.StringVar(value=str(self.state_data.install_dir))

        ttk.Entry(path_frame, textvariable=self.path_var, width=60).pack(
            side="left", fill="x", expand=True
        )

        ttk.Button(path_frame, text="Browse...", command=self.browse).pack(
            side="left", padx=(8, 0)
        )

        ttk.Frame(self).pack(fill="both", expand=True)

        nav = ttk.Frame(self)
        nav.pack(fill="x")

        ttk.Button(
            nav, text="< Back", command=lambda: self.app.show_page(WelcomePage)
        ).pack(side="left")

        ttk.Button(nav, text="Next >", command=self.go_next).pack(side="right")

    def browse(self):
        chosen = filedialog.askdirectory()
        if chosen:
            self.path_var.set(chosen)

    def go_next(self):
        self.state_data.install_dir = Path(self.path_var.get())
        self.app.show_page(OptionsPage)


class OptionsPage(WizardPage):

    def build(self):
        ttk.Label(
            self, text="AI-Powered Renaming", font=("Segoe UI", 14, "bold")
        ).pack(anchor="w", pady=(0, 12))

        ttk.Label(
            self,
            wraplength=560,
            justify="left",
            text=(
                "CleanDrop can rename generically-named downloads "
                "(e.g. IMG_2043.jpg) using a small language model that "
                "runs entirely on your machine. This downloads a local "
                "model server now (~50MB); the model itself (~400MB) "
                "downloads automatically the first time the renaming "
                "feature actually runs — no account, no cloud calls."
            ),
        ).pack(anchor="w", pady=(0, 16))

        ttk.Checkbutton(
            self,
            text="Enable AI-powered smart renaming",
            variable=self.state_data.enable_ai,
        ).pack(anchor="w")

        ttk.Label(
            self,
            wraplength=560,
            justify="left",
            foreground="#666666",
            text="You can enable this later even if you skip it now.",
        ).pack(anchor="w", pady=(4, 0))

        ttk.Frame(self).pack(fill="both", expand=True)

        nav = ttk.Frame(self)
        nav.pack(fill="x")

        ttk.Button(
            nav, text="< Back", command=lambda: self.app.show_page(LocationPage)
        ).pack(side="left")

        ttk.Button(
            nav, text="Install >", command=lambda: self.app.show_page(ProgressPage)
        ).pack(side="right")


class ProgressPage(WizardPage):

    def build(self):
        ttk.Label(
            self, text="Installing...", font=("Segoe UI", 14, "bold")
        ).pack(anchor="w", pady=(0, 12))

        self.progress = ttk.Progressbar(
            self, mode="determinate", maximum=100
        )
        self.progress.pack(fill="x", pady=(0, 12))

        self.log_text = tk.Text(self, height=14, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)

        self.nav = ttk.Frame(self)
        self.nav.pack(fill="x", pady=(12, 0))

        self.next_button = ttk.Button(
            self.nav,
            text="Next >",
            command=lambda: self.app.show_page(ExtensionPage),
            state="disabled",
        )
        self.next_button.pack(side="right")

        self._queue = queue.Queue()
        self._started = False

    def on_show(self):
        if self._started:
            return
        self._started = True
        thread = threading.Thread(target=self.run_install, daemon=True)
        thread.start()
        self.after(100, self._poll_queue)

    def log(self, message):
        self._queue.put(("log", message))

    def set_progress(self, percent):
        self._queue.put(("progress", percent))

    def _poll_queue(self):
        try:
            while True:
                kind, value = self._queue.get_nowait()

                if kind == "log":
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", value + "\n")
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")

                elif kind == "progress":
                    self.progress["value"] = value

                elif kind == "done":
                    self.next_button.configure(state="normal")

                elif kind == "error":
                    messagebox.showerror("Installation failed", value)

        except queue.Empty:
            pass

        self.after(100, self._poll_queue)

    def run_install(self):
        try:
            source_dir = self.state_data.source_dir
            install_dir = self.state_data.install_dir

            self.log("Checking for an existing CleanDrop installation...")
            steps.stop_existing_installation(log=self.log)

            self.log("Copying application files...")
            steps.copy_application_files(source_dir, install_dir, log=self.log)
            self.set_progress(20)

            extension_id = (
                steps.CHROME_WEBSTORE_EXTENSION_ID
                or self.state_data.extension_id
                or "PLACEHOLDER_UNTIL_LOADED_UNPACKED"
            )

            manifest_path = steps.write_native_host_manifest(
                install_dir, extension_id, log=self.log
            )
            self.set_progress(35)

            steps.register_native_host(manifest_path, log=self.log)
            self.set_progress(45)

            steps.register_scheduled_task(install_dir, log=self.log)
            self.set_progress(55)

            llm_port = steps.find_free_port(steps.DEFAULT_LLM_PORT)
            self.state_data.llm_port = llm_port
            self.set_progress(60)

            llm_server_exe = None
            llm_server_args = None

            if self.state_data.enable_ai.get():

                def on_progress(pct):
                    scaled = 60 + int(pct * 0.35)
                    self.set_progress(scaled)

                llm_server_exe = steps.setup_llama_server(
                    install_dir,
                    on_progress=on_progress,
                    log=self.log,
                )

                llm_server_args = [
                    "-hf", DEFAULT_LLM_MODEL,
                    "-t", str(_default_thread_count()),
                    "-c", "512",
                    "--reasoning", "off",
                ]

                self.log(
                    "Note: the model itself downloads on first "
                    "actual use of the AI renaming feature, not "
                    "during this install step."
                )

                steps.launch_llm_server(
                    llm_server_exe, llm_port, llm_server_args, log=self.log
                )

            # Written with the resolved LLM config (or None if AI
            # wasn't enabled) so the persistent scheduler's watchdog
            # knows what to relaunch if the server ever goes down —
            # including after a reboot, without you starting it by
            # hand again.
            steps.write_app_config(
                install_dir,
                llm_port,
                llm_server_exe=llm_server_exe,
                llm_server_args=llm_server_args,
                log=self.log,
            )

            self.set_progress(90)
            self.log("Installing uninstaller...")

            uninstaller_path = install_uninstaller(
                log=self.log
            )

            steps.register_uninstaller(
                uninstaller_path,
                install_dir,
                log=self.log,
            )

            self.set_progress(100)
            self.log("\nInstallation complete.")
            self._queue.put(("done", None))

        except Exception as error:
            self.log(f"\nERROR: {error}")
            self._queue.put(("error", str(error)))


class ExtensionPage(WizardPage):

    def build(self):
        ttk.Label(
            self, text="Load the Chrome Extension", font=("Segoe UI", 14, "bold")
        ).pack(anchor="w", pady=(0, 12))

        if steps.CHROME_WEBSTORE_URL:
            self._build_webstore_instructions()
        else:
            self._build_unpacked_instructions()

        ttk.Frame(self).pack(fill="both", expand=True)

        nav = ttk.Frame(self)
        nav.pack(fill="x")

        ttk.Button(
            nav, text="Next >", command=lambda: self.app.show_page(FinishPage)
        ).pack(side="right")

    def _build_webstore_instructions(self):
        ttk.Label(
            self,
            wraplength=560,
            justify="left",
            text="Click below to install CleanDrop from the Chrome Web Store.",
        ).pack(anchor="w", pady=(0, 16))

        ttk.Button(
            self,
            text="Open Chrome Web Store",
            command=lambda: webbrowser.open(steps.CHROME_WEBSTORE_URL),
        ).pack(anchor="w")

    def _build_unpacked_instructions(self):
        extension_path = self.state_data.install_dir / "extension"

        ttk.Label(
            self,
            wraplength=560,
            justify="left",
            text=(
                "CleanDrop isn't on the Chrome Web Store yet, so load it "
                "manually:\n\n"
                "1. Open chrome://extensions\n"
                "2. Enable \"Developer mode\" (top right)\n"
                "3. Click \"Load unpacked\"\n"
                f"4. Select this folder:\n   {extension_path}\n\n"
                "5. Copy the Extension ID Chrome assigns it, and click "
                "\"Update ID\" below to finish connecting it to the "
                "background service."
            ),
        ).pack(anchor="w", pady=(0, 12))

        id_frame = ttk.Frame(self)
        id_frame.pack(fill="x", pady=(0, 8))

        self.id_var = tk.StringVar(value=self.state_data.extension_id)

        ttk.Entry(id_frame, textvariable=self.id_var, width=40).pack(
            side="left", fill="x", expand=True
        )

        ttk.Button(id_frame, text="Update ID", command=self.update_id).pack(
            side="left", padx=(8, 0)
        )

    def update_id(self):
        extension_id = self.id_var.get().strip()

        if not extension_id:
            messagebox.showwarning("Missing ID", "Please paste the extension ID.")
            return

        try:
            manifest_path = steps.write_native_host_manifest(
                self.state_data.install_dir, extension_id, log=lambda m: None
            )
            steps.register_native_host(manifest_path, log=lambda m: None)
            self.state_data.extension_id = extension_id
            messagebox.showinfo(
                "Connected", "Extension connected to the background service."
            )
        except Exception as error:
            messagebox.showerror("Failed to update", str(error))


class FinishPage(WizardPage):

    def build(self):
        ttk.Label(
            self, text="Setup Complete", font=("Segoe UI", 18, "bold")
        ).pack(anchor="w", pady=(0, 12))

        self.summary_label = ttk.Label(
            self, wraplength=560, justify="left"
        )
        self.summary_label.pack(anchor="w")

        ttk.Frame(self).pack(fill="both", expand=True)

        ttk.Button(self, text="Close", command=self.app.destroy).pack(anchor="e")

    def on_show(self):
        lines = [
            f"Installed to: {self.state_data.install_dir}",
            "Background service: running (starts automatically at login)",
        ]

        if self.state_data.enable_ai.get():
            lines.append(
                f"Local AI server: running on port {self.state_data.llm_port}"
            )
            lines.append(
                "Note: the AI model downloads automatically the first "
                "time renaming actually runs, so your first generically-"
                "named download will take longer than usual."
            )
        else:
            lines.append(
                "Local AI server: not installed (renaming falls back to "
                "page-context heuristics only)"
            )

        self.summary_label.configure(text="\n".join(lines))


if __name__ == "__main__":

    if not is_admin():
        relaunch_as_admin()
        sys.exit(0)

    app = WizardApp()
    app.mainloop()