"""
POD 006 - Monster Hunter World Mod Manager Engine
Persona 3 Reload Tactical System Backend
"""

import os
import sys
import json
import uuid
import shutil
import tempfile
import datetime
import subprocess
import re
import stat
from pathlib import Path


def safe_unlink(path: Path) -> None:
    """Safely unlinks a file, clearing read-only attributes on Windows if necessary."""
    if not path.exists():
        return
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except Exception:
        pass
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            path.unlink(missing_ok=True)
        except Exception:
            raise


def safe_rmdir(path: Path) -> None:
    """Safely removes an empty directory, clearing read-only attributes on Windows if necessary."""
    if not path.exists() or not path.is_dir():
        return
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except Exception:
        pass
    try:
        path.rmdir()
    except PermissionError:
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            path.rmdir()
        except Exception:
            raise


def get_base_dir() -> Path:
    """Returns application base directory, handling PyInstaller _MEIPASS."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def get_7z_binary() -> str:
    """Locates the bundled 7z.exe binary."""
    base_dir = get_base_dir()
    candidates = [
        base_dir / "bin" / "7z.exe",
        base_dir / "7z.exe",
        Path("C:/Program Files/PeaZip/res/bin/7z/7z.exe"),
        Path("C:/Program Files/7-Zip/7z.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    
    # Fallback to PATH
    which_7z = shutil.which("7z.exe") or shutil.which("7z")
    if which_7z:
        return which_7z
    raise FileNotFoundError("Could not locate 7z.exe binary for archive decompression.")


def get_app_data_dir() -> Path:
    """Returns the persistent AppData directory for Pod 006."""
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    p = Path(appdata) / "Pod006"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_config_path() -> Path:
    return get_app_data_dir() / "config.json"


def load_config() -> dict:
    cfg_path = get_config_path()
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg: dict) -> None:
    cfg_path = get_config_path()
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")


def detect_game_directory() -> str:
    """Auto-detects the Monster Hunter World installation directory."""
    # 1. Configured path
    cfg = load_config()
    configured = cfg.get("game_directory")
    if configured and os.path.isdir(configured):
        return configured

    # 2. Default Steam path
    default_path = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Monster Hunter World")
    if default_path.exists() and (default_path / "MonsterHunterWorld.exe").exists():
        return str(default_path)
    elif default_path.exists():
        return str(default_path)

    # 3. Search Steam libraryfolders.vdf
    steam_roots = [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
        Path(r"D:\Steam"),
        Path(r"E:\Steam"),
    ]
    for steam_root in steam_roots:
        vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
        if vdf_path.exists():
            try:
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                # Find all "path" "\path\to\library"
                paths = re.findall(r'"path"\s+"([^"]+)"', content)
                for lib_p in paths:
                    candidate = Path(lib_p.replace(r"\\", "\\")) / "steamapps" / "common" / "Monster Hunter World"
                    if candidate.exists():
                        return str(candidate)
            except Exception:
                pass

    return str(default_path)


def is_valid_game_directory(path_str: str) -> dict:
    """Checks if a directory appears to be a valid Monster Hunter World install."""
    if not path_str or not os.path.isdir(path_str):
        return {"valid": False, "reason": "Directory does not exist."}
    
    p = Path(path_str)
    has_exe = (p / "MonsterHunterWorld.exe").exists()
    has_chunk = (p / "chunk").exists()
    has_native_pc = (p / "nativePC").exists()

    if has_exe:
        return {"valid": True, "warning": None, "has_nativepc": has_native_pc}
    elif has_chunk or has_native_pc:
        return {
            "valid": True,
            "warning": "MonsterHunterWorld.exe not found, but MHW folder structure detected.",
            "has_nativepc": has_native_pc,
        }
    else:
        return {
            "valid": False,
            "reason": "Target folder does not appear to contain Monster Hunter World (MonsterHunterWorld.exe missing).",
        }


def format_size(size_bytes: int) -> str:
    """Formats bytes into human readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class ManifestManager:
    """Manages pod006_manifest.json and backup tracking."""

    def __init__(self, game_dir: str):
        self.game_dir = Path(game_dir)
        self.manifest_path = self.game_dir / "pod006_manifest.json"
        self.backup_dir = self.game_dir / ".pod006_backup"

    def load(self) -> dict:
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "mods" in data:
                        return data
            except Exception as e:
                print(f"Failed to read manifest: {e}")
        return {
            "schema_version": "1.0",
            "game_dir": str(self.game_dir),
            "mods": []
        }

    def save(self, data: dict) -> None:
        try:
            temp_file = self.game_dir / f"pod006_manifest.tmp_{uuid.uuid4().hex[:6]}"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            if self.manifest_path.exists():
                os.replace(temp_file, self.manifest_path)
            else:
                shutil.move(temp_file, self.manifest_path)
        except Exception as e:
            print(f"Failed to save manifest: {e}")
            raise

    def get_installed_mods(self) -> list:
        data = self.load()
        mods = data.get("mods", [])
        result = []
        for m in mods:
            result.append({
                "id": m.get("id"),
                "name": m.get("name"),
                "archive_name": m.get("archive_name"),
                "variant": m.get("variant", "Default"),
                "install_date": m.get("install_date"),
                "file_count": len(m.get("files", [])),
                "total_size": sum(f.get("size", 0) for f in m.get("files", [])),
                "total_size_formatted": format_size(sum(f.get("size", 0) for f in m.get("files", []))),
                "files": m.get("files", [])
            })
        return result

    def find_file_owner(self, rel_path: str) -> str | None:
        """Finds which installed mod owns a relative path."""
        norm_path = rel_path.replace("\\", "/").lower()
        data = self.load()
        for m in reversed(data.get("mods", [])):
            for f in m.get("files", []):
                if f.get("target_rel_path", "").replace("\\", "/").lower() == norm_path:
                    return m.get("name", "Unknown Mod")
        return None

    def add_mod(self, mod_entry: dict) -> None:
        data = self.load()
        mods = [m for m in data.get("mods", []) if m.get("id") != mod_entry.get("id")]
        mods.append(mod_entry)
        data["mods"] = mods
        data["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save(data)

    def remove_mod(self, mod_id: str) -> dict | None:
        data = self.load()
        target_mod = None
        remaining_mods = []
        for m in data.get("mods", []):
            if m.get("id") == mod_id:
                target_mod = m
            else:
                remaining_mods.append(m)
        
        if target_mod:
            data["mods"] = remaining_mods
            data["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save(data)
        return target_mod


MHW_NATIVEPC_SUBFOLDERS = {
    "wp", "pl", "sound", "stage", "quest", "vfx", "gui", "ui",
    "common", "gm", "fsm", "event", "room", "collision", "facility", "arc",
    "plugins"
}

KNOWN_ROOT_HOOKS = {
    "loader.dll", "dinput8.dll", "winmm.dll", "dxgi.dll", "hid.dll",
    "fasmx64.dll", "loader-config.json", "version.dll", "bink2w64.dll",
    "xinput1_3.dll", "xinput1_4.dll"
}

MHW_ROOT_ITEMS = {
    "loader.dll", "dinput8.dll", "winmm.dll", "loader-config.json",
    "fasmx64.dll", "dxgi.dll", "hid.dll", "version.dll", "bink2w64.dll",
    "xinput1_3.dll", "xinput1_4.dll", "lua", "dll", "chunk",
    "monsterhunterworld.exe"
}



def list_archive_contents(archive_path: str) -> list[dict]:
    """Uses 7z to list all files inside an archive without extracting."""
    exe_7z = get_7z_binary()
    cmd = [exe_7z, "l", "-slt", "-ba", "-p-", archive_path]
    
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"7z failed to inspect archive: {proc.stderr or proc.stdout}")

    items = []
    current_item = {}

    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            if current_item and "Path" in current_item:
                items.append(current_item)
            current_item = {}
            continue
        
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            current_item[key] = val

    if current_item and "Path" in current_item:
        items.append(current_item)

    parsed_files = []
    for item in items:
        p = item.get("Path", "").replace("\\", "/").strip("/")
        attrs = item.get("Attributes", "")
        is_folder = item.get("Folder") == "+" or "D" in attrs or p.endswith("/")
        size = int(item.get("Size", "0") or "0")
        if not is_folder and p:
            parsed_files.append({
                "path": p,
                "size": size,
                "modified": item.get("Modified", "")
            })

    return parsed_files


def detect_archive_structure(files: list[dict], archive_filename: str) -> dict:
    """
    Analyzes archive paths to detect:
    - Root wrapper directories (only stripped if ALL files are inside it)
    - Multiple variant options
    - Target mapping classification (nativePC vs Game Root vs Lua vs plugins)
    - Ambiguous archives requiring tactical user input
    """
    if not files:
        return {
            "has_variants": False,
            "variants": [],
            "suggested_dest": "nativePC",
            "is_plugin_or_root": False,
            "single_wrapper": None,
            "is_ambiguous": False,
        }

    paths_parts = [[seg for seg in f["path"].split("/") if seg] for f in files if f.get("path")]
    paths_parts = [parts for parts in paths_parts if parts]

    # Detect common wrapper directory hierarchy: only valid if ALL files in archive are inside it
    wrapper_segments = []
    curr_parts = [p for p in paths_parts if p]
    while curr_parts and all(len(p) > 1 for p in curr_parts):
        first_segs = set(p[0] for p in curr_parts)
        if len(first_segs) == 1:
            candidate = list(first_segs)[0]
            cand_lower = candidate.lower()
            if (
                cand_lower not in ("nativepc", "lua", "dll", "plugins")
                and cand_lower not in MHW_NATIVEPC_SUBFOLDERS
            ):
                wrapper_segments.append(candidate)
                curr_parts = [p[1:] for p in curr_parts]
            else:
                break
        else:
            break

    single_wrapper = "/".join(wrapper_segments) if wrapper_segments else None

    effective_parts = []
    wrapper_parts = [p for p in single_wrapper.split("/") if p] if single_wrapper else []
    for parts in paths_parts:
        if wrapper_parts and len(parts) > len(wrapper_parts) and parts[:len(wrapper_parts)] == wrapper_parts:
            effective_parts.append(parts[len(wrapper_parts):])
        elif parts:
            effective_parts.append(parts)

    effective_parts = [parts for parts in effective_parts if parts]
    effective_top_levels = sorted(list(set(parts[0] for parts in effective_parts if len(parts) > 1)))
    has_loose_files_at_root = any(len(parts) == 1 for parts in effective_parts)

    variant_keywords = re.compile(
        r"(option|version|ver\b|v\d|color|style|variant|type|glow|no[\-_ ]?glow|4k|2k|hd|"
        r"op\b|legit|female|male|preset|part|extra|addon|optional|main|\b\d{1,2}\b|\[\d+\])",
        re.IGNORECASE
    )

    detected_variants = []
    has_standard_game_dirs = any(
        folder.lower() in ("nativepc", "lua", "luaengine", "chunk", "plugins")
        or folder.lower() in MHW_NATIVEPC_SUBFOLDERS
        for folder in effective_top_levels
    )
    if len(effective_top_levels) > 1 and not has_standard_game_dirs and not has_loose_files_at_root:
        matching_count = sum(1 for f in effective_top_levels if variant_keywords.search(f))
        has_nativepc_sub = sum(
            1 for parts in effective_parts if len(parts) > 1 and parts[1].lower() in ("nativepc", "wp", "pl", "sound", "plugins")
        )

        if matching_count >= 1 or has_nativepc_sub >= 1:
            for folder in effective_top_levels:
                folder_files = [
                    files[i] for i, parts in enumerate(effective_parts)
                    if parts[0] == folder
                ]
                is_optional = bool(re.search(r"(optional|addon|extra|patch)", folder, re.IGNORECASE))
                is_main = bool(re.search(r"(main|base|default|core)", folder, re.IGNORECASE))
                total_sz = sum(f["size"] for f in folder_files)

                detected_variants.append({
                    "id": folder,
                    "name": folder,
                    "file_count": len(folder_files),
                    "total_size": total_sz,
                    "total_size_formatted": format_size(total_sz),
                    "is_optional": is_optional,
                    "is_main": is_main,
                    "prefix": f"{single_wrapper + '/' if single_wrapper else ''}{folder}/"
                })

    has_native_pc = any(
        any(seg.lower() == "nativepc" for seg in parts)
        for parts in effective_parts
        if parts
    )

    dll_files = [parts for parts in effective_parts if parts and parts[-1].lower().endswith(".dll")]

    # Loose mod DLL: any DLL file not inside nativePC and not in KNOWN_ROOT_HOOKS
    has_loose_mod_dll = any(
        parts[-1].lower() not in KNOWN_ROOT_HOOKS and not any(seg.lower() == "nativepc" for seg in parts)
        for parts in dll_files
    )

    # Known root hook files (loader.dll, dinput8.dll, etc.)
    has_root_hook = any(
        parts[-1].lower() in KNOWN_ROOT_HOOKS
        for parts in effective_parts
        if parts
    )

    has_bare_mhw_folders = any(
        parts[0].lower() in MHW_NATIVEPC_SUBFOLDERS or (len(parts) > 1 and parts[1].lower() in MHW_NATIVEPC_SUBFOLDERS)
        for parts in effective_parts
        if parts
    )

    has_lua = any(
        parts[0].lower() in ("lua", "luaengine") or (len(parts) > 1 and parts[1].lower() in ("lua", "luaengine"))
        for parts in effective_parts
        if parts
    )

    # Destination mapping and ambiguity evaluation
    if has_native_pc:
        suggested_dest = "nativePC"
        is_ambiguous = False
    elif has_loose_mod_dll:
        # Rule 2: The Plugin Default Rule
        suggested_dest = "plugins"
        is_ambiguous = False
    elif has_root_hook:
        suggested_dest = "root"
        is_ambiguous = False
    elif has_lua:
        suggested_dest = "Lua"
        is_ambiguous = False
    elif has_bare_mhw_folders:
        suggested_dest = "nativePC"
        is_ambiguous = False
    else:
        suggested_dest = "nativePC"
        is_ambiguous = True

    return {
        "has_variants": len(detected_variants) > 1,
        "variants": detected_variants,
        "single_wrapper": single_wrapper,
        "suggested_dest": suggested_dest,
        "is_plugin_or_root": has_loose_mod_dll or has_root_hook or bool(dll_files),
        "is_ambiguous": is_ambiguous,
    }


def sanitize_rel_path(path_str: str) -> str:
    """Normalizes and sanitizes relative path preventing directory traversal."""
    cleaned = path_str.replace("\\", "/").strip("/")
    parts = [seg for seg in cleaned.split("/") if seg and seg not in (".", "..")]
    return "/".join(parts)


def resolve_dest_path(
    rel_parts: list[str],
    custom_dest_override: str | None = None,
    archive_has_native_pc: bool = False,
    is_plugin_archive: bool = False,
    is_root_archive: bool = False,
) -> str:
    """
    Intelligently resolves the relative destination path in the game directory.
    Avoids duplicate folder nesting (e.g. nativePC/nativePC, Lua/Lua).
    Supports arbitrary custom subdirectories (e.g. nativePC/sound/wwise, plugins).
    Implements:
    - Rule 1: The NativePC Anchor Rule (when nativePC is present in archive)
    - Rule 2: The Plugin Default Rule (when nativePC is NOT present and loose DLLs are present)
    """
    if not rel_parts:
        return ""

    # Sanitize each segment of rel_parts
    clean_rel_parts = [sanitize_rel_path(p) for p in rel_parts if p and p not in (".", "..")]
    if not clean_rel_parts:
        return ""

    if custom_dest_override and custom_dest_override != "auto":
        override = sanitize_rel_path(custom_dest_override)
        if override.lower() in ("root", "game root", ".", ""):
            return "/".join(clean_rel_parts)

        # Normalize "plugins" to "nativePC/plugins"
        if override.lower() == "plugins":
            override = "nativePC/plugins"

        override_parts = [p for p in override.split("/") if p]
        rel_lower = [p.lower() for p in clean_rel_parts]
        override_lower = [p.lower() for p in override_parts]

        # Case 1: clean_rel_parts already starts with override (case-insensitive)
        if len(rel_lower) >= len(override_lower) and rel_lower[:len(override_lower)] == override_lower:
            return "/".join(clean_rel_parts)

        # Case 2: Both start with the same root folder (e.g. override="nativePC/sound", clean_rel_parts=["nativePC", "bgm.pck"])
        if rel_lower[0] == override_lower[0]:
            combined = override_parts + clean_rel_parts[1:]
            return "/".join(combined)

        # Case 3: override ends with the same directory clean_rel_parts starts with
        if override_lower[-1] == rel_lower[0]:
            combined = override_parts + clean_rel_parts[1:]
            return "/".join(combined)

        return f"{override}/{'/'.join(clean_rel_parts)}"

    # Auto-detect routing

    # Rule 1: The NativePC Anchor Rule (When nativePC is present in the archive)
    if archive_has_native_pc:
        # Check if the file is inside nativePC
        npc_indices = [idx for idx, seg in enumerate(clean_rel_parts) if seg.lower() == "nativepc"]
        if npc_indices:
            idx = npc_indices[0]
            # Everything inside nativePC retains its relative path inside nativePC/
            return f"nativePC/{'/'.join(clean_rel_parts[idx + 1:])}" if len(clean_rel_parts) > idx + 1 else "nativePC"
        # If the file does not contain nativePC, it is beside nativePC -> routes to game root
        return "/".join(clean_rel_parts)

    # Rule 2: The Plugin Default Rule (When nativePC is NOT present in the archive)
    first_part_lower = clean_rel_parts[0].lower()

    if first_part_lower == "nativepc":
        clean_rel_parts[0] = "nativePC"
        return "/".join(clean_rel_parts)
    elif first_part_lower == "plugins":
        return f"nativePC/{'/'.join(clean_rel_parts)}"
    elif first_part_lower in MHW_NATIVEPC_SUBFOLDERS:
        return f"nativePC/{'/'.join(clean_rel_parts)}"
    elif first_part_lower in ("lua", "luaengine"):
        if len(clean_rel_parts) > 1:
            return f"Lua/{'/'.join(clean_rel_parts[1:])}"
        return "/".join(clean_rel_parts)
    elif len(clean_rel_parts) == 1 and first_part_lower in KNOWN_ROOT_HOOKS:
        return clean_rel_parts[0]
    elif len(clean_rel_parts) == 1 and first_part_lower in MHW_ROOT_ITEMS:
        return clean_rel_parts[0]
    elif is_root_archive:
        # All files in a root loader archive route to game root
        return "/".join(clean_rel_parts)
    elif is_plugin_archive:
        # All loose DLLs, companion configs, and subfolders route to nativePC/plugins/<rel_path>
        return f"nativePC/plugins/{'/'.join(clean_rel_parts)}"
    elif clean_rel_parts[-1].lower().endswith(".dll"):
        if clean_rel_parts[-1].lower() in KNOWN_ROOT_HOOKS:
            return "/".join(clean_rel_parts)
        else:
            return f"nativePC/plugins/{'/'.join(clean_rel_parts)}"
    else:
        return f"nativePC/{'/'.join(clean_rel_parts)}"


def build_preinstall_blueprint(
    archive_path: str,
    game_dir: str,
    selected_variant_ids: list[str] | None = None,
    custom_dest_override: str | None = None,
) -> dict:
    """
    Constructs the pre-installation blueprint ("All-Out Attack Review").
    """
    manifest_mgr = ManifestManager(game_dir)
    files = list_archive_contents(archive_path)
    filename = os.path.basename(archive_path)
    clean_name = re.sub(r"\.(zip|7z|rar)$", "", filename, flags=re.IGNORECASE)

    analysis = detect_archive_structure(files, filename)
    single_wrapper = analysis.get("single_wrapper")
    variants = analysis.get("variants", [])

    if analysis.get("has_variants") and not selected_variant_ids:
        primary = [v for v in variants if not v.get("is_optional")]
        if primary:
            selected_variant_ids = [primary[0]["id"]]
        elif variants:
            selected_variant_ids = [variants[0]["id"]]
        else:
            selected_variant_ids = []

    # First pass: collect active files with wrapper and variants resolved
    active_items = []
    wrapper_parts = [p for p in single_wrapper.split("/") if p] if single_wrapper else []
    for f in files:
        raw_path = f["path"]
        parts = [seg for seg in raw_path.split("/") if seg and seg not in (".", "..")]
        if not parts:
            continue

        if wrapper_parts and len(parts) > len(wrapper_parts) and parts[:len(wrapper_parts)] == wrapper_parts:
            rel_parts = parts[len(wrapper_parts):]
        else:
            rel_parts = parts

        if analysis.get("has_variants"):
            top_folder = rel_parts[0]
            if any(v["id"] == top_folder for v in variants):
                if top_folder not in (selected_variant_ids or []):
                    continue
                rel_parts = rel_parts[1:]

        if not rel_parts:
            continue

        active_items.append((f, rel_parts))

    # Determine nativePC anchor prefix if nativePC is present in active items
    nativepc_prefix = None
    for _, rel_parts in active_items:
        for idx, seg in enumerate(rel_parts):
            if seg.lower() == "nativepc":
                prefix = tuple(rel_parts[:idx])
                if nativepc_prefix is None or len(prefix) < len(nativepc_prefix):
                    nativepc_prefix = prefix
                break

    archive_has_native_pc = nativepc_prefix is not None

    is_plugin_archive = False
    is_root_archive = False
    if not archive_has_native_pc:
        has_loose_mod_dll = any(
            len(rel_parts) > 0 and rel_parts[-1].lower().endswith(".dll") and rel_parts[-1].lower() not in KNOWN_ROOT_HOOKS
            for _, rel_parts in active_items
        )
        if has_loose_mod_dll or analysis.get("suggested_dest") == "plugins":
            is_plugin_archive = True
        elif analysis.get("suggested_dest") == "root":
            is_root_archive = True

    file_plans = []
    collisions_count = 0
    total_planned_size = 0

    for f, rel_parts in active_items:
        raw_path = f["path"]
        if nativepc_prefix and len(rel_parts) >= len(nativepc_prefix) and tuple(rel_parts[:len(nativepc_prefix)]) == nativepc_prefix:
            routed_parts = rel_parts[len(nativepc_prefix):]
        else:
            routed_parts = rel_parts

        dest_rel_path = resolve_dest_path(
            routed_parts,
            custom_dest_override=custom_dest_override,
            archive_has_native_pc=archive_has_native_pc,
            is_plugin_archive=is_plugin_archive,
            is_root_archive=is_root_archive,
        )
        dest_rel_path = sanitize_rel_path(dest_rel_path)
        if not dest_rel_path:
            continue

        full_dest_path = os.path.join(game_dir, *dest_rel_path.split("/"))
        is_collision = os.path.exists(full_dest_path) and os.path.isfile(full_dest_path)
        existing_owner = None
        disk_size = None
        match_status = "NOT FOUND"

        if is_collision:
            collisions_count += 1
            existing_owner = manifest_mgr.find_file_owner(dest_rel_path)
            if not existing_owner:
                existing_owner = "Base Game File / Unmanaged"
            try:
                disk_size = os.path.getsize(full_dest_path)
                if disk_size == f["size"]:
                    match_status = "FOUND (IDENTICAL)"
                else:
                    match_status = "FOUND (MODIFIED)"
            except Exception:
                match_status = "FOUND (IDENTICAL)"

        total_planned_size += f["size"]
        file_plans.append({
            "archive_path": raw_path,
            "target_rel_path": dest_rel_path,
            "size": f["size"],
            "size_formatted": format_size(f["size"]),
            "collision": is_collision,
            "disk_size": disk_size,
            "disk_size_formatted": format_size(disk_size) if disk_size is not None else None,
            "match_status": match_status,
            "existing_owner": existing_owner,
            "action": "overwrite_backup" if is_collision else "install",
            "modified": f.get("modified", "")
        })

    return {
        "mod_name": clean_name,
        "archive_path": archive_path,
        "archive_filename": filename,
        "has_variants": analysis.get("has_variants", False),
        "variants": variants,
        "selected_variants": selected_variant_ids or [],
        "suggested_dest": analysis.get("suggested_dest", "nativePC"),
        "is_ambiguous": analysis.get("is_ambiguous", False),
        "custom_dest": custom_dest_override or "auto",
        "file_plans": file_plans,
        "total_files": len(file_plans),
        "total_size": total_planned_size,
        "total_size_formatted": format_size(total_planned_size),
        "collisions_count": collisions_count,
        "matching_files_count": collisions_count,
        "has_matching_game_files": collisions_count > 0,
    }


def execute_all_out_attack(
    archive_path: str,
    mod_name: str,
    file_plans: list[dict],
    game_dir: str,
    variant_name: str = "Default",
) -> dict:
    """
    Executes the mod installation.
    """
    exe_7z = get_7z_binary()
    manifest_mgr = ManifestManager(game_dir)
    game_dir_path = Path(game_dir)
    backup_dir = game_dir_path / ".pod006_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    stage_dir = Path(tempfile.mkdtemp(prefix="pod006_stage_"))
    installed_files_manifest = []
    mod_id = f"mod_{uuid.uuid4().hex[:10]}"

    try:
        cmd = [exe_7z, "x", "-y", "-p-", f"-o{stage_dir}", archive_path]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"7z extraction failed: {proc.stderr or proc.stdout}")

        backed_up_count = 0
        installed_count = 0

        for plan in file_plans:
            action = plan.get("action", "install")
            if action == "skip":
                continue

            archive_subpath = plan["archive_path"].replace("/", os.sep)
            source_file = stage_dir / archive_subpath
            if not source_file.exists():
                found = None
                for root, _, fs in os.walk(stage_dir):
                    for f in fs:
                        cand = Path(root) / f
                        rel = cand.relative_to(stage_dir).as_posix()
                        if rel.lower() == plan["archive_path"].lower():
                            found = cand
                            break
                    if found:
                        break
                if found:
                    source_file = found
                else:
                    print(f"Warning: Source file {archive_subpath} missing in staging.")
                    continue

            target_rel_path = plan["target_rel_path"]
            target_dest = game_dir_path / Path(target_rel_path.replace("/", os.sep))
            is_collision = target_dest.exists()
            backup_key = None
            backed_up = False
            previous_owner = plan.get("existing_owner")

            if is_collision and action in ("overwrite_backup", "overwrite"):
                clean_filename = target_dest.name
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_key = f"{mod_id}_{ts}_{uuid.uuid4().hex[:6]}_{clean_filename}.bak"
                backup_dest = backup_dir / backup_key
                shutil.copy2(target_dest, backup_dest)
                backed_up = True
                backed_up_count += 1

            target_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_dest)
            installed_count += 1

            installed_files_manifest.append({
                "target_rel_path": target_rel_path,
                "size": plan.get("size", source_file.stat().st_size),
                "backed_up": backed_up,
                "backup_file": backup_key,
                "previous_owner": previous_owner,
                "installed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        mod_record = {
            "id": mod_id,
            "name": mod_name or Path(archive_path).stem,
            "archive_name": Path(archive_path).name,
            "variant": variant_name,
            "install_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_count": installed_count,
            "files": installed_files_manifest
        }
        manifest_mgr.add_mod(mod_record)

        return {
            "success": True,
            "mod_id": mod_id,
            "mod_name": mod_record["name"],
            "files_installed": installed_count,
            "files_backed_up": backed_up_count,
        }

    finally:
        if stage_dir.exists():
            try:
                shutil.rmtree(stage_dir, ignore_errors=True)
            except Exception:
                pass


def uninstall_mod(mod_id: str, game_dir: str) -> dict:
    """
    Uninstalls a mod and restores any overwritten backups.
    Fully layer-aware: handles LIFO, FIFO, and middle-mod out-of-order uninstalls.
    If a newer mod currently owns the file on disk, that file is NOT touched,
    and backup chains are cleanly spliced.
    """
    manifest_mgr = ManifestManager(game_dir)
    game_dir_path = Path(game_dir)
    backup_dir = game_dir_path / ".pod006_backup"

    data = manifest_mgr.load()
    mods = data.get("mods", [])
    target_mod = None
    for m in mods:
        if m.get("id") == mod_id:
            target_mod = m
            break

    if not target_mod:
        return {"success": False, "error": f"Mod with ID '{mod_id}' not found in manifest."}

    files_restored = 0
    files_removed = 0

    protected_dirs = {
        game_dir_path.resolve(),
        (game_dir_path / "nativePC").resolve(),
        (game_dir_path / "chunk").resolve(),
        (game_dir_path / "Lua").resolve(),
        (game_dir_path / "DLL").resolve(),
        (game_dir_path / "DLSS").resolve(),
        (game_dir_path / "logs").resolve(),
    }

    dirs_to_check = set()

    for f in target_mod.get("files", []):
        rel_path = sanitize_rel_path(f.get("target_rel_path", "")).replace("/", os.sep)
        if not rel_path:
            continue
        target_path = game_dir_path / rel_path
        norm_path = f.get("target_rel_path", "").replace("\\", "/").lower()

        # Find all mods claiming this file in installation order
        mods_with_file = [
            m for m in mods
            if any(mf.get("target_rel_path", "").replace("\\", "/").lower() == norm_path for mf in m.get("files", []))
        ]

        # Is target_mod the active owner (top of stack on disk)?
        is_active_owner = bool(mods_with_file and mods_with_file[-1].get("id") == mod_id)

        backed_up = f.get("backed_up", False)
        backup_file = f.get("backup_file")

        if is_active_owner:
            # File on disk was placed by target_mod. Restore backup or remove.
            if backed_up and backup_file:
                backup_path = backup_dir / backup_file
                if backup_path.exists():
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        if target_path.exists():
                            os.chmod(target_path, stat.S_IWRITE | stat.S_IREAD)
                    except Exception:
                        pass
                    shutil.copy2(backup_path, target_path)
                    safe_unlink(backup_path)
                    files_restored += 1
                else:
                    if target_path.exists():
                        safe_unlink(target_path)
                        files_removed += 1
            else:
                if target_path.exists():
                    safe_unlink(target_path)
                    files_removed += 1

            dirs_to_check.add(target_path.parent)
        else:
            # target_mod is buried under a newer mod.
            # Do NOT touch target_path on disk!
            # Splice backup chain to the mod installed directly after target_mod:
            try:
                idx = [m.get("id") for m in mods_with_file].index(mod_id)
                mod_above = mods_with_file[idx + 1]
                f_above = next(
                    mf for mf in mod_above.get("files", [])
                    if mf.get("target_rel_path", "").replace("\\", "/").lower() == norm_path
                )

                if backed_up and backup_file:
                    # mod_above was backing up target_mod's version.
                    # Discard mod_above's backup of target_mod and inherit target_mod's backup:
                    if f_above.get("backup_file"):
                        safe_unlink(backup_dir / f_above["backup_file"])
                    f_above["backup_file"] = backup_file
                    f_above["backed_up"] = True
                    f_above["previous_owner"] = f.get("previous_owner")
                else:
                    # target_mod was the root/original creator. Now mod_above has no prior version to restore to:
                    if f_above.get("backup_file"):
                        safe_unlink(backup_dir / f_above["backup_file"])
                    f_above["backup_file"] = None
                    f_above["backed_up"] = False
                    f_above["previous_owner"] = None
            except Exception as ex:
                print(f"Warning during backup chain splice for {rel_path}: {ex}")

    # Remove target_mod from mods list and save updated manifest
    data["mods"] = [m for m in mods if m.get("id") != mod_id]
    data["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    manifest_mgr.save(data)

    # Prune empty directories
    for d in sorted(dirs_to_check, key=lambda p: len(p.parts), reverse=True):
        curr = d
        while curr.exists() and curr.resolve() not in protected_dirs and curr.resolve() != game_dir_path.resolve():
            try:
                curr.relative_to(game_dir_path)
            except ValueError:
                break
            try:
                if not any(curr.iterdir()):
                    safe_rmdir(curr)
                    curr = curr.parent
                else:
                    break
            except Exception:
                break

    return {
        "success": True,
        "mod_name": target_mod.get("name"),
        "files_restored": files_restored,
        "files_removed": files_removed,
    }


def clean_slate_all_mods(game_dir: str) -> dict:
    """
    Emergency Clean Slate:
    Uninstalls all mods in reverse installation order, restoring all backups.
    """
    manifest_mgr = ManifestManager(game_dir)
    data = manifest_mgr.load()
    mods = list(reversed(data.get("mods", [])))
    
    total_restored = 0
    total_removed = 0
    uninstalled_names = []

    for m in mods:
        res = uninstall_mod(m["id"], game_dir)
        if res.get("success"):
            total_restored += res.get("files_restored", 0)
            total_removed += res.get("files_removed", 0)
            uninstalled_names.append(res.get("mod_name"))

    backup_dir = Path(game_dir) / ".pod006_backup"
    if backup_dir.exists():
        try:
            if not any(backup_dir.iterdir()):
                backup_dir.rmdir()
        except Exception:
            pass

    return {
        "success": True,
        "mods_uninstalled": len(uninstalled_names),
        "mod_names": uninstalled_names,
        "total_files_restored": total_restored,
        "total_files_removed": total_removed,
    }


def purge_archive_matching_files(
    archive_path: str,
    selected_relative_paths: list[str],
    game_dir: str,
    variant_name: str | None = None,
) -> dict:
    """
    Safely uninstalls/purges selected matching files belonging to an archive from the game folder.
    Creates a timestamped backup in .pod006_backup/manual_purge/<timestamp>_<archive_name>[_<variant>]_<uuid>/
    Removes empty parent folders up to (but not including) nativePC or game root.
    Updates pod006_manifest.json if any of the purged files were tracked.
    Resilient against read-only files and directories on Windows.
    """
    if not game_dir or not os.path.isdir(game_dir):
        return {
            "success": False,
            "error": "Game directory does not exist or is invalid.",
            "purged_count": 0,
            "purged_files": [],
            "cleaned_dirs": [],
            "backup_dir": "",
        }

    game_dir_path = Path(game_dir).resolve()
    archive_name = Path(archive_path).name if archive_path else "manual_mod"
    clean_arc_name = re.sub(r'[\s\\/:*?"<>|]+', '_', archive_name)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    rand_suffix = uuid.uuid4().hex[:6]

    if variant_name and variant_name.strip() and variant_name.strip().lower() != "default":
        clean_variant = re.sub(r'[\s\\/:*?"<>|]+', '_', variant_name.strip())
        folder_name = f"{ts}_{clean_arc_name}_{clean_variant}_{rand_suffix}"
    else:
        folder_name = f"{ts}_{clean_arc_name}_{rand_suffix}"

    backup_dir = game_dir_path / ".pod006_backup" / "manual_purge" / folder_name

    purged_files = []
    failed_files = []
    cleaned_dirs = []
    dirs_to_check = set()

    protected_dirs = {
        game_dir_path,
        (game_dir_path / "nativePC").resolve(),
        (game_dir_path / "chunk").resolve(),
        (game_dir_path / "Lua").resolve(),
        (game_dir_path / "DLL").resolve(),
        (game_dir_path / "DLSS").resolve(),
        (game_dir_path / "logs").resolve(),
    }

    try:
        # Deduplicate and normalize selected relative paths
        seen = set()
        for rel_p in selected_relative_paths:
            sanitized = sanitize_rel_path(rel_p)
            if not sanitized or sanitized.lower() in seen:
                continue
            seen.add(sanitized.lower())

            target_file = (game_dir_path / Path(sanitized.replace("/", os.sep))).resolve()

            # Path traversal safety check: target must be inside game_dir_path
            try:
                target_file.relative_to(game_dir_path)
            except ValueError:
                continue

            if target_file.exists() and target_file.is_file():
                try:
                    # Perform safe backup
                    backup_dest = backup_dir / Path(sanitized.replace("/", os.sep))
                    backup_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target_file, backup_dest)

                    # Ensure backup is writable
                    try:
                        os.chmod(backup_dest, stat.S_IWRITE | stat.S_IREAD)
                    except Exception:
                        pass

                    # Remove from game directory safely (handling Windows read-only flags)
                    safe_unlink(target_file)
                    purged_files.append(sanitized)
                    dirs_to_check.add(target_file.parent.resolve())
                except Exception as file_err:
                    failed_files.append({"path": sanitized, "error": str(file_err)})

        # Prune empty parent directories recursively upward stopping at protected_dirs
        for d in sorted(dirs_to_check, key=lambda p: len(p.parts), reverse=True):
            curr = d
            while curr.exists() and curr.resolve() not in protected_dirs and curr.resolve() != game_dir_path:
                try:
                    curr.relative_to(game_dir_path)
                except ValueError:
                    break

                try:
                    if not any(curr.iterdir()):
                        try:
                            rel_dir = curr.relative_to(game_dir_path).as_posix()
                        except Exception:
                            rel_dir = str(curr)
                        if rel_dir not in cleaned_dirs:
                            cleaned_dirs.append(rel_dir)
                        safe_rmdir(curr)
                        curr = curr.parent.resolve()
                    else:
                        break
                except Exception:
                    break

        # Update manifest if any purged files were tracked
        if purged_files:
            manifest_mgr = ManifestManager(game_dir)
            data = manifest_mgr.load()
            purged_norm_set = {p.replace("\\", "/").lower() for p in purged_files}
            mods = data.get("mods", [])
            updated_mods = []
            manifest_modified = False

            for m in mods:
                remaining_files = []
                for f in m.get("files", []):
                    f_norm = f.get("target_rel_path", "").replace("\\", "/").lower()
                    if f_norm in purged_norm_set:
                        manifest_modified = True
                        if f.get("backup_file"):
                            safe_unlink(game_dir_path / ".pod006_backup" / f["backup_file"])
                    else:
                        remaining_files.append(f)

                if remaining_files:
                    if len(remaining_files) != len(m.get("files", [])):
                        m["files"] = remaining_files
                        m["file_count"] = len(remaining_files)
                        manifest_modified = True
                    updated_mods.append(m)
                else:
                    # All files in this mod were purged
                    manifest_modified = True

            if manifest_modified:
                data["mods"] = updated_mods
                data["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                manifest_mgr.save(data)

            # Record purge metadata inside backup folder
            try:
                info = {
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "archive_path": archive_path,
                    "variant": variant_name or "Default",
                    "purged_count": len(purged_files),
                    "purged_files": purged_files,
                    "cleaned_dirs": cleaned_dirs,
                }
                with open(backup_dir / "purge_info.json", "w", encoding="utf-8") as f:
                    json.dump(info, f, indent=2)
            except Exception:
                pass

        success = len(purged_files) > 0 or len(failed_files) == 0
        res = {
            "success": success,
            "purged_count": len(purged_files),
            "purged_files": purged_files,
            "cleaned_dirs": cleaned_dirs,
            "backup_dir": str(backup_dir) if purged_files else "",
        }
        if failed_files:
            res["failed_files"] = failed_files
            if not success:
                res["error"] = f"Failed to purge {len(failed_files)} file(s): {failed_files[0]['error']}"
        return res

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "purged_count": len(purged_files),
            "purged_files": purged_files,
            "cleaned_dirs": cleaned_dirs,
            "backup_dir": str(backup_dir) if backup_dir.exists() else "",
        }


class BatchInstaller:
    """
    Manages sequential batch installation through a queue of archives.
    Persona 3 Reload S.E.E.S. Batch Deployment controller.
    Handles auto-install for clean/unambiguous mods, paused prompt callbacks
    for variant/destination decisions, and error handling/skip/abort flow.
    """

    def __init__(self, game_dir: str):
        self.game_dir = game_dir
        self.manifest_mgr = ManifestManager(game_dir)

    def is_clean_mod(self, blueprint: dict) -> bool:
        """
        Determines whether a mod is clean / unambiguous (can be deployed immediately
        without manual user intervention).
        Clean: no multiple variants to choose from AND routing destination is not ambiguous.
        """
        has_multiple_variants = bool(blueprint.get("has_variants", False) and len(blueprint.get("variants", [])) > 1)
        is_ambiguous = bool(blueprint.get("is_ambiguous", False))
        return not has_multiple_variants and not is_ambiguous

    def install_batch(
        self,
        archive_paths: list[str],
        on_progress=None,
        on_decision_needed=None,
        on_error=None,
    ) -> dict:
        """
        Executes sequential batch installation across multiple archives.

        Args:
            archive_paths: List of archive file paths.
            on_progress: Optional callback(stage_data: dict) -> None
            on_decision_needed: Optional callback(blueprint: dict) -> dict with keys:
                - "action": "install" | "skip" | "abort"
                - "selected_variants": optional list[str]
                - "custom_dest": optional str
                - "mod_name": optional str
            on_error: Optional callback(archive_path: str, exc: Exception) -> "skip" | "abort"
        """
        installed_records = []
        skipped_records = []
        total_files = 0
        total_backups = 0
        aborted = False

        for idx, arc_path in enumerate(archive_paths):
            arc_name = Path(arc_path).name
            if on_progress:
                on_progress({
                    "stage": "inspecting",
                    "index": idx + 1,
                    "total": len(archive_paths),
                    "archive_path": arc_path,
                    "archive_filename": arc_name,
                    "message": f"Analyzing blueprint for {arc_name}...",
                })

            try:
                blueprint = build_preinstall_blueprint(arc_path, self.game_dir)
            except Exception as e:
                action = "skip"
                if on_error:
                    action = on_error(arc_path, e)
                if action == "abort":
                    aborted = True
                    skipped_records.append({
                        "archive_path": arc_path,
                        "archive_filename": arc_name,
                        "reason": f"Inspection error: {e}",
                        "action": "aborted",
                    })
                    break
                else:
                    skipped_records.append({
                        "archive_path": arc_path,
                        "archive_filename": arc_name,
                        "reason": f"Inspection error: {e}",
                        "action": "skipped",
                    })
                    continue

            # Check if user decision is required
            if not self.is_clean_mod(blueprint):
                if on_decision_needed:
                    decision = on_decision_needed(blueprint) or {}
                    dec_action = decision.get("action", "install")
                    if dec_action == "abort":
                        aborted = True
                        skipped_records.append({
                            "archive_path": arc_path,
                            "archive_filename": arc_name,
                            "reason": "Aborted by user during tactical decision",
                            "action": "aborted",
                        })
                        break
                    elif dec_action == "skip":
                        skipped_records.append({
                            "archive_path": arc_path,
                            "archive_filename": arc_name,
                            "reason": "Skipped by user during tactical decision",
                            "action": "skipped",
                        })
                        continue

                    chosen_variants = decision.get("selected_variants")
                    if isinstance(chosen_variants, str):
                        chosen_variants = [chosen_variants]
                    elif chosen_variants is None:
                        chosen_variants = blueprint.get("selected_variants")

                    custom_dest = decision.get("custom_dest") or blueprint.get("custom_dest") or "auto"
                    mod_name = decision.get("mod_name") or blueprint["mod_name"]

                    if chosen_variants is not None or (custom_dest and custom_dest != blueprint.get("custom_dest")):
                        blueprint = build_preinstall_blueprint(
                            arc_path,
                            self.game_dir,
                            selected_variant_ids=chosen_variants,
                            custom_dest_override=custom_dest or "auto",
                        )
                else:
                    mod_name = blueprint["mod_name"]
                    chosen_variants = blueprint.get("selected_variants")
            else:
                mod_name = blueprint["mod_name"]
                chosen_variants = blueprint.get("selected_variants")

            if isinstance(chosen_variants, str):
                chosen_variants = [chosen_variants]

            # Execute deployment
            if on_progress:
                msg = f"Deploying {len(blueprint['file_plans'])} files..."
                if blueprint.get("collisions_count", 0) > 0:
                    msg = f"Deploying {len(blueprint['file_plans'])} files (backing up {blueprint['collisions_count']} collisions)..."
                on_progress({
                    "stage": "deploying",
                    "index": idx + 1,
                    "total": len(archive_paths),
                    "archive_path": arc_path,
                    "archive_filename": arc_name,
                    "mod_name": mod_name,
                    "message": msg,
                })

            variant_label = ", ".join([str(v) for v in chosen_variants if v]) if chosen_variants else "Default"
            try:
                res = execute_all_out_attack(
                    arc_path,
                    mod_name,
                    blueprint["file_plans"],
                    self.game_dir,
                    variant_name=variant_label,
                )
                total_files += res.get("files_installed", 0)
                total_backups += res.get("files_backed_up", 0)
                installed_records.append({
                    "archive_path": arc_path,
                    "archive_filename": arc_name,
                    "mod_name": res.get("mod_name"),
                    "mod_id": res.get("mod_id"),
                    "files_installed": res.get("files_installed", 0),
                    "files_backed_up": res.get("files_backed_up", 0),
                    "variant": variant_label,
                })

                if on_progress:
                    on_progress({
                        "stage": "finished_item",
                        "index": idx + 1,
                        "total": len(archive_paths),
                        "archive_path": arc_path,
                        "archive_filename": arc_name,
                        "mod_name": res.get("mod_name"),
                        "result": res,
                        "message": f"Successfully deployed {res.get('mod_name')}",
                    })
            except Exception as install_err:
                action = "skip"
                if on_error:
                    action = on_error(arc_path, install_err)
                if action == "abort":
                    aborted = True
                    skipped_records.append({
                        "archive_path": arc_path,
                        "archive_filename": arc_name,
                        "reason": f"Installation failed: {install_err}",
                        "action": "aborted",
                    })
                    break
                else:
                    skipped_records.append({
                        "archive_path": arc_path,
                        "archive_filename": arc_name,
                        "reason": f"Installation failed: {install_err}",
                        "action": "skipped",
                    })

        return {
            "success": True,
            "total_staged": len(archive_paths),
            "installed_count": len(installed_records),
            "skipped_count": len(skipped_records),
            "installed_mods": installed_records,
            "skipped_mods": skipped_records,
            "total_files_installed": total_files,
            "total_files_backed_up": total_backups,
            "aborted": aborted,
        }


