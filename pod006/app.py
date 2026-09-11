"""
POD 006 - Monster Hunter World Mod Manager
Persona 3 Reload Tactical System Desktop Application
"""

import os
import sys
from pathlib import Path
import webview

# Ensure module path is accessible
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pod006.engine import (
    get_base_dir,
    detect_game_directory,
    is_valid_game_directory,
    load_config,
    save_config,
    build_preinstall_blueprint,
    execute_all_out_attack,
    uninstall_mod,
    clean_slate_all_mods,
    purge_archive_matching_files,
    BatchInstaller,
    ManifestManager,
)


class Pod006Api:
    """JS Bridge API for pywebview."""

    def __init__(self):
        self._window = None
        self.game_dir = detect_game_directory()

    def set_window(self, window):
        self._window = window

    def get_status(self):
        val = is_valid_game_directory(self.game_dir)
        manifest = ManifestManager(self.game_dir)
        installed = manifest.get_installed_mods()
        return {
            "game_dir": self.game_dir,
            "game_dir_valid": val.get("valid", False),
            "game_dir_warning": val.get("warning"),
            "installed_mods": installed,
            "total_installed": len(installed),
        }

    def select_game_directory(self):
        if not self._window:
            return {"updated": False}
        initial_dir = self.game_dir if os.path.isdir(self.game_dir) else None
        result = self._window.create_file_dialog(
            webview.FOLDER_DIALOG,
            directory=initial_dir
        )
        if result and len(result) > 0:
            chosen = result[0]
            if chosen and os.path.isdir(chosen):
                self.game_dir = chosen
                cfg = load_config()
                cfg["game_directory"] = chosen
                save_config(cfg)
                val = is_valid_game_directory(self.game_dir)
                return {
                    "updated": True,
                    "game_dir": self.game_dir,
                    "game_dir_valid": val.get("valid", False),
                    "game_dir_warning": val.get("warning"),
                }
        return {"updated": False}

    def open_game_directory(self):
        if os.path.isdir(self.game_dir):
            os.startfile(self.game_dir)

    def open_backup_directory(self):
        bdir = os.path.join(self.game_dir, ".pod006_backup")
        os.makedirs(bdir, exist_ok=True)
        os.startfile(bdir)

    def browse_archive_files(self):
        if not self._window:
            return []
        file_types = (
            "Mod Archives (*.zip;*.7z;*.rar)",
            "Zip Archives (*.zip)",
            "7z Archives (*.7z)",
            "RAR Archives (*.rar)",
            "All Files (*.*)"
        )
        cfg = load_config()
        initial_dir = cfg.get("last_archive_dir")
        if not initial_dir or not os.path.isdir(initial_dir):
            default_archive_dir = r"C:\Users\Yonah\Downloads\Machine Archives\Monster Hunter World"
            if os.path.isdir(default_archive_dir):
                initial_dir = default_archive_dir
            else:
                initial_dir = os.path.expanduser(r"~\Downloads")

        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=file_types,
            directory=initial_dir
        )
        if result and len(result) > 0:
            cfg["last_archive_dir"] = str(Path(result[0]).parent)
            save_config(cfg)
            return list(result)
        return []

    def inspect_archive(self, archive_path, selected_variants=None, custom_dest="auto"):
        return build_preinstall_blueprint(
            archive_path,
            self.game_dir,
            selected_variant_ids=selected_variants,
            custom_dest_override=custom_dest
        )

    def execute_install(self, archive_path, mod_name, file_plans, variant_name="Default"):
        return execute_all_out_attack(
            archive_path,
            mod_name,
            file_plans,
            self.game_dir,
            variant_name
        )

    def uninstall_mod(self, mod_id):
        return uninstall_mod(mod_id, self.game_dir)

    def clean_slate(self):
        return clean_slate_all_mods(self.game_dir)

    def purge_matching_files(self, archive_path, selected_relative_paths, variant_name=None):
        return purge_archive_matching_files(
            archive_path,
            selected_relative_paths,
            self.game_dir,
            variant_name
        )

    def get_installed_mods(self):
        return ManifestManager(self.game_dir).get_installed_mods()

    def batch_install(self, archive_paths):
        installer = BatchInstaller(self.game_dir)
        return installer.install_batch(archive_paths)


def configure_webview2_runtime():
    """Auto-detects Edge WebView2 runtime path to force modern Edge Chromium rendering."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\EdgeCore",
        r"C:\Program Files\Microsoft\EdgeCore",
        r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application",
        r"C:\Program Files\Microsoft\EdgeWebView\Application",
        r"C:\Program Files (x86)\Microsoft\Edge\Application",
        r"C:\Program Files\Microsoft\Edge\Application",
    ]
    for base in candidates:
        if os.path.isdir(base):
            for root, _, files in os.walk(base):
                if "msedgewebview2.exe" in files:
                    webview.settings["WEBVIEW2_RUNTIME_PATH"] = root
                    return root
    return None


def main():
    configure_webview2_runtime()
    api = Pod006Api()
    base_dir = get_base_dir()
    html_path = base_dir / "ui" / "index.html"
    
    if not html_path.exists():
        html_path = Path(__file__).resolve().parent / "ui" / "index.html"

    window = webview.create_window(
        title="POD 006 // S.E.E.S. TACTICAL MOD INTERFACE",
        url=f"file:///{str(html_path.resolve()).replace('\\', '/')}",
        js_api=api,
        width=1140,
        height=760,
        min_size=(960, 640),
        background_color="#000c1e"
    )
    api.set_window(window)

    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
