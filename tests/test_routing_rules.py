"""
Unit and integration test suite for Pod 006:
- The NativePC Anchor Rule (Rule 1)
- The Plugin Default Rule (Rule 2)
- Mixed Batch Installation
"""

import os
import sys
import shutil
import tempfile
import zipfile
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pod006.engine import (
    detect_archive_structure,
    resolve_dest_path,
    build_preinstall_blueprint,
    execute_all_out_attack,
    BatchInstaller,
    ManifestManager,
    KNOWN_ROOT_HOOKS,
)


class TestRoutingRules(unittest.TestCase):

    def setUp(self):
        # Strictly isolate test directory in tempdir - NEVER touch real game folder
        self.test_dir = Path(tempfile.mkdtemp(prefix="pod006_rule_test_"))
        self.mock_game_dir = self.test_dir / "Monster Hunter World"
        self.mock_game_dir.mkdir(parents=True, exist_ok=True)
        (self.mock_game_dir / "MonsterHunterWorld.exe").write_text("DUMMY MHW EXE", encoding="utf-8")
        (self.mock_game_dir / "chunk").mkdir(exist_ok=True)
        (self.mock_game_dir / "nativePC").mkdir(exist_ok=True)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_zip(self, filename: str, files_dict: dict) -> Path:
        p = self.test_dir / filename
        with zipfile.ZipFile(p, "w") as zf:
            for arc_path, content in files_dict.items():
                zf.writestr(arc_path, content)
        return p

    def test_loose_dll_and_ini_routes_to_plugins(self):
        """
        Rule 2: Archive with only loose DLL and companion INI (like ResultAutoSkip)
        must automatically route to nativePC/plugins/<filename>.
        """
        arc_name = "ResultAutoSkip 8711 1 2026-07-22T17-03Z YwMYrNjJS.zip"
        zip_path = self._create_zip(arc_name, {
            "ResultAutoSkip.dll": "RESULT AUTO SKIP BINARY DATA",
            "ResultAutoSkip.ini": "[Settings]\nAutoSkip=1\n",
        })

        bp = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir))

        self.assertFalse(bp["is_ambiguous"])
        self.assertEqual(bp["suggested_dest"], "plugins")
        self.assertEqual(bp["total_files"], 2)

        plans = {p["archive_path"]: p["target_rel_path"] for p in bp["file_plans"]}
        self.assertEqual(plans["ResultAutoSkip.dll"], "nativePC/plugins/ResultAutoSkip.dll")
        self.assertEqual(plans["ResultAutoSkip.ini"], "nativePC/plugins/ResultAutoSkip.ini")

        # Execute installation
        res = execute_all_out_attack(str(zip_path), "ResultAutoSkip", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])
        self.assertEqual(res["files_installed"], 2)

        # Verify files exist on disk in nativePC/plugins
        installed_dll = self.mock_game_dir / "nativePC" / "plugins" / "ResultAutoSkip.dll"
        installed_ini = self.mock_game_dir / "nativePC" / "plugins" / "ResultAutoSkip.ini"
        self.assertTrue(installed_dll.exists())
        self.assertTrue(installed_ini.exists())
        self.assertEqual(installed_dll.read_text(encoding="utf-8"), "RESULT AUTO SKIP BINARY DATA")
        self.assertEqual(installed_ini.read_text(encoding="utf-8"), "[Settings]\nAutoSkip=1\n")

    def test_loose_dll_with_wrapper_routes_to_plugins(self):
        """
        Rule 2: Archive with a single wrapper directory around loose DLL and config
        must strip wrapper and route to nativePC/plugins/<filename>.
        """
        zip_path = self._create_zip("CutsceneSkipMod.zip", {
            "CutsceneSkipMod/CutsceneSkip.dll": "CUTSCENE SKIP DATA",
            "CutsceneSkipMod/CutsceneSkip.json": '{"enabled": true}',
            "CutsceneSkipMod/readme.txt": "Cutscene Skip Instructions",
        })

        bp = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir))

        self.assertFalse(bp["is_ambiguous"])
        self.assertEqual(bp["suggested_dest"], "plugins")
        self.assertEqual(bp["total_files"], 3)

        plans = {p["archive_path"]: p["target_rel_path"] for p in bp["file_plans"]}
        self.assertEqual(plans["CutsceneSkipMod/CutsceneSkip.dll"], "nativePC/plugins/CutsceneSkip.dll")
        self.assertEqual(plans["CutsceneSkipMod/CutsceneSkip.json"], "nativePC/plugins/CutsceneSkip.json")
        self.assertEqual(plans["CutsceneSkipMod/readme.txt"], "nativePC/plugins/readme.txt")

        res = execute_all_out_attack(str(zip_path), "CutsceneSkip", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])

        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "CutsceneSkip.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "CutsceneSkip.json").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "readme.txt").exists())

    def test_nativepc_anchor_with_root_dlls_beside(self):
        """
        Rule 1: Stracker's Loader structure.
        Archive has nativePC/plugins/... AND loader.dll, dinput8.dll beside nativePC.
        Root files must go to game root; nativePC files must stay inside nativePC.
        """
        zip_path = self._create_zip("StrackersLoader.zip", {
            "loader.dll": "LOADER DLL BINARY",
            "dinput8.dll": "DINPUT8 PROXY BINARY",
            "loader-config.json": '{"logLevel": "INFO"}',
            "nativePC/plugins/QuestLoader.dll": "QUEST LOADER PLUGIN",
            "nativePC/plugins/MonsterLoader.dll": "MONSTER LOADER PLUGIN",
        })

        bp = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir))

        self.assertFalse(bp["is_ambiguous"])
        self.assertEqual(bp["suggested_dest"], "nativePC")
        self.assertEqual(bp["total_files"], 5)

        plans = {p["archive_path"]: p["target_rel_path"] for p in bp["file_plans"]}
        # Files beside nativePC go to game root
        self.assertEqual(plans["loader.dll"], "loader.dll")
        self.assertEqual(plans["dinput8.dll"], "dinput8.dll")
        self.assertEqual(plans["loader-config.json"], "loader-config.json")
        # Files inside nativePC stay inside nativePC
        self.assertEqual(plans["nativePC/plugins/QuestLoader.dll"], "nativePC/plugins/QuestLoader.dll")
        self.assertEqual(plans["nativePC/plugins/MonsterLoader.dll"], "nativePC/plugins/MonsterLoader.dll")

        # Execute installation
        res = execute_all_out_attack(str(zip_path), "StrackersLoader", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])
        self.assertEqual(res["files_installed"], 5)

        # Verify disk locations
        self.assertTrue((self.mock_game_dir / "loader.dll").exists())
        self.assertTrue((self.mock_game_dir / "dinput8.dll").exists())
        self.assertTrue((self.mock_game_dir / "loader-config.json").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "QuestLoader.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "MonsterLoader.dll").exists())

    def test_nativepc_anchor_with_single_wrapper(self):
        """
        Rule 1: Single wrapper around Stracker's Loader structure.
        Wrapper must be stripped: beside-nativePC files go to root, nativePC files stay in nativePC.
        """
        zip_path = self._create_zip("StrackerPack.zip", {
            "StrackersLoader/loader.dll": "LOADER DLL",
            "StrackersLoader/dinput8.dll": "DINPUT8 DLL",
            "StrackersLoader/loader-config.json": "{}",
            "StrackersLoader/nativePC/plugins/QuestLoader.dll": "QUEST LOADER",
        })

        bp = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir))

        self.assertFalse(bp["is_ambiguous"])
        self.assertEqual(bp["suggested_dest"], "nativePC")

        plans = {p["archive_path"]: p["target_rel_path"] for p in bp["file_plans"]}
        self.assertEqual(plans["StrackersLoader/loader.dll"], "loader.dll")
        self.assertEqual(plans["StrackersLoader/dinput8.dll"], "dinput8.dll")
        self.assertEqual(plans["StrackersLoader/loader-config.json"], "loader-config.json")
        self.assertEqual(plans["StrackersLoader/nativePC/plugins/QuestLoader.dll"], "nativePC/plugins/QuestLoader.dll")

        res = execute_all_out_attack(str(zip_path), "StrackerPack", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])

        self.assertTrue((self.mock_game_dir / "loader.dll").exists())
        self.assertTrue((self.mock_game_dir / "dinput8.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "QuestLoader.dll").exists())

    def test_nativepc_autoq9_structure(self):
        """
        Rule 1: AutoQ9 archive with nativePC/plugins/AutoQ9.dll and .ini.
        Must stay in nativePC/plugins/.
        """
        arc_name = "AutoQ9 2.0-8494-2-0-1772832537.zip"
        zip_path = self._create_zip(arc_name, {
            "nativePC/plugins/AutoQ9.dll": "AUTO Q9 BINARY",
            "nativePC/plugins/AutoQ9.ini": "[AutoQ9]\nSpeed=2.0\n",
        })

        bp = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir))

        self.assertFalse(bp["is_ambiguous"])
        self.assertEqual(bp["suggested_dest"], "nativePC")

        plans = {p["archive_path"]: p["target_rel_path"] for p in bp["file_plans"]}
        self.assertEqual(plans["nativePC/plugins/AutoQ9.dll"], "nativePC/plugins/AutoQ9.dll")
        self.assertEqual(plans["nativePC/plugins/AutoQ9.ini"], "nativePC/plugins/AutoQ9.ini")

        res = execute_all_out_attack(str(zip_path), "AutoQ9", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])

        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "AutoQ9.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "AutoQ9.ini").exists())

    def test_nativepc_beside_with_arbitrary_files_and_lua(self):
        """
        Rule 1: When nativePC is present, files and folders beside nativePC
        (like readme.txt or Lua/) go beside nativePC in the game root.
        """
        zip_path = self._create_zip("HybridMod.zip", {
            "nativePC/wp/axe/axe001.mod": "AXE DATA",
            "readme.txt": "README CONTENT",
            "Lua/scripts/autorun.lua": "print('hello')",
        })

        bp = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir))

        self.assertFalse(bp["is_ambiguous"])
        plans = {p["archive_path"]: p["target_rel_path"] for p in bp["file_plans"]}
        self.assertEqual(plans["nativePC/wp/axe/axe001.mod"], "nativePC/wp/axe/axe001.mod")
        self.assertEqual(plans["readme.txt"], "readme.txt")
        self.assertEqual(plans["Lua/scripts/autorun.lua"], "Lua/scripts/autorun.lua")

        res = execute_all_out_attack(str(zip_path), "HybridMod", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])

        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "axe" / "axe001.mod").exists())
        self.assertTrue((self.mock_game_dir / "readme.txt").exists())
        self.assertTrue((self.mock_game_dir / "Lua" / "scripts" / "autorun.lua").exists())

    def test_root_loader_only_without_nativepc(self):
        """
        Known root hooks (loader.dll, dinput8.dll) without nativePC route to game root.
        """
        zip_path = self._create_zip("RootLoaderOnly.zip", {
            "loader.dll": "LOADER",
            "dinput8.dll": "DINPUT8",
            "loader-config.json": "{}",
        })

        bp = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir))

        self.assertFalse(bp["is_ambiguous"])
        self.assertEqual(bp["suggested_dest"], "root")

        plans = {p["archive_path"]: p["target_rel_path"] for p in bp["file_plans"]}
        self.assertEqual(plans["loader.dll"], "loader.dll")
        self.assertEqual(plans["dinput8.dll"], "dinput8.dll")
        self.assertEqual(plans["loader-config.json"], "loader-config.json")

    def test_batch_install_mixed_archives(self):
        """
        Batch installation with mixed archives:
        1. ResultAutoSkip (loose DLL + ini, no nativePC) -> routes to nativePC/plugins/
        2. AutoQ9 (nativePC/plugins/AutoQ9.dll + ini) -> routes to nativePC/plugins/
        3. StrackersLoader (root DLLs beside nativePC) -> root DLLs to root, plugins to nativePC/plugins/
        4. AxeMod (standard nativePC/wp/axe) -> routes to nativePC/wp/axe/

        All must be classified as clean and install sequentially in batch without prompting.
        """
        zip_result_auto_skip = self._create_zip("ResultAutoSkip 8711 1 2026-07-22T17-03Z YwMYrNjJS.zip", {
            "ResultAutoSkip.dll": "RESULT AUTO SKIP DLL",
            "ResultAutoSkip.ini": "AUTO SKIP INI",
        })
        zip_auto_q9 = self._create_zip("AutoQ9 2.0-8494-2-0-1772832537.zip", {
            "nativePC/plugins/AutoQ9.dll": "AUTO Q9 DLL",
            "nativePC/plugins/AutoQ9.ini": "AUTO Q9 INI",
        })
        zip_stracker = self._create_zip("StrackersLoader.zip", {
            "loader.dll": "LOADER DLL",
            "dinput8.dll": "DINPUT8 DLL",
            "nativePC/plugins/QuestLoader.dll": "QUEST LOADER DLL",
        })
        zip_axe = self._create_zip("AxeMod.zip", {
            "nativePC/wp/axe/axe001.mod": "AXE 001 DATA",
        })

        installer = BatchInstaller(str(self.mock_game_dir))

        decision_needed_calls = []
        def on_decision_needed(bp):
            decision_needed_calls.append(bp)
            return {"action": "install"}

        progress_events = []
        def on_progress(p):
            progress_events.append(p)

        res = installer.install_batch(
            [
                str(zip_result_auto_skip),
                str(zip_auto_q9),
                str(zip_stracker),
                str(zip_axe),
            ],
            on_progress=on_progress,
            on_decision_needed=on_decision_needed,
        )

        # None of these 4 should require interactive tactical decision
        self.assertEqual(len(decision_needed_calls), 0, "No clean mods should pause for tactical decisions")
        self.assertTrue(res["success"])
        self.assertEqual(res["total_staged"], 4)
        self.assertEqual(res["installed_count"], 4)
        self.assertEqual(res["skipped_count"], 0)
        self.assertFalse(res["aborted"])

        # Check all files installed on disk in their correct locations
        # 1. ResultAutoSkip -> nativePC/plugins
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "ResultAutoSkip.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "ResultAutoSkip.ini").exists())

        # 2. AutoQ9 -> nativePC/plugins
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "AutoQ9.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "AutoQ9.ini").exists())

        # 3. Stracker -> root files in root, plugin files in nativePC/plugins
        self.assertTrue((self.mock_game_dir / "loader.dll").exists())
        self.assertTrue((self.mock_game_dir / "dinput8.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "QuestLoader.dll").exists())

        # 4. Axe -> nativePC/wp/axe
        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "axe" / "axe001.mod").exists())

        # Verify ManifestManager tracked all 4 mods
        manifest = ManifestManager(str(self.mock_game_dir))
        installed = manifest.get_installed_mods()
        self.assertEqual(len(installed), 4)

    def test_resolve_dest_path_direct_unit_cases(self):
        """Direct unit tests for resolve_dest_path function covering all branches."""
        # 1. Loose DLL with no context -> defaults to nativePC/plugins/
        self.assertEqual(
            resolve_dest_path(["ResultAutoSkip.dll"]),
            "nativePC/plugins/ResultAutoSkip.dll"
        )
        self.assertEqual(
            resolve_dest_path(["AutoQ9.dll"]),
            "nativePC/plugins/AutoQ9.dll"
        )

        # 2. Known root hooks -> default to root
        for hook in ["loader.dll", "dinput8.dll", "winmm.dll", "dxgi.dll"]:
            self.assertEqual(resolve_dest_path([hook]), hook)

        # 3. archive_has_native_pc=True
        # File inside nativePC
        self.assertEqual(
            resolve_dest_path(["nativePC", "plugins", "AutoQ9.dll"], archive_has_native_pc=True),
            "nativePC/plugins/AutoQ9.dll"
        )
        self.assertEqual(
            resolve_dest_path(["nativepc", "wp", "axe", "axe.mod"], archive_has_native_pc=True),
            "nativePC/wp/axe/axe.mod"
        )
        # File beside nativePC
        self.assertEqual(
            resolve_dest_path(["loader.dll"], archive_has_native_pc=True),
            "loader.dll"
        )
        self.assertEqual(
            resolve_dest_path(["dinput8.dll"], archive_has_native_pc=True),
            "dinput8.dll"
        )
        self.assertEqual(
            resolve_dest_path(["readme.txt"], archive_has_native_pc=True),
            "readme.txt"
        )

        # 4. is_plugin_archive=True with companion files
        self.assertEqual(
            resolve_dest_path(["ResultAutoSkip.ini"], is_plugin_archive=True),
            "nativePC/plugins/ResultAutoSkip.ini"
        )
        self.assertEqual(
            resolve_dest_path(["subfolder", "config.json"], is_plugin_archive=True),
            "nativePC/plugins/subfolder/config.json"
        )

        # 5. Custom destination override "plugins"
        self.assertEqual(
            resolve_dest_path(["ResultAutoSkip.dll"], custom_dest_override="plugins"),
            "nativePC/plugins/ResultAutoSkip.dll"
        )
        self.assertEqual(
            resolve_dest_path(["plugins", "ResultAutoSkip.dll"], custom_dest_override="plugins"),
            "nativePC/plugins/ResultAutoSkip.dll"
        )
        self.assertEqual(
            resolve_dest_path(["nativePC", "plugins", "ResultAutoSkip.dll"], custom_dest_override="plugins"),
            "nativePC/plugins/ResultAutoSkip.dll"
        )

        # 6. Explicit override "root"
        self.assertEqual(
            resolve_dest_path(["ResultAutoSkip.dll"], custom_dest_override="root"),
            "ResultAutoSkip.dll"
        )

        # 7. is_root_archive=True routes companion files to game root
        self.assertEqual(
            resolve_dest_path(["readme.txt"], is_root_archive=True),
            "readme.txt"
        )
        self.assertEqual(
            resolve_dest_path(["config.ini"], is_root_archive=True),
            "config.ini"
        )

        # 8. Deep nested nativePC anchor in rel_parts
        self.assertEqual(
            resolve_dest_path(["Nested", "Sub", "nativePC", "plugins", "QuestLoader.dll"], archive_has_native_pc=True),
            "nativePC/plugins/QuestLoader.dll"
        )

    def test_custom_destination_override_blueprint(self):
        """Verify user manual override on blueprint takes precedence over auto rules."""
        zip_path = self._create_zip("LooseDll.zip", {
            "CustomMod.dll": "DLL DATA",
        })
        # Default auto -> plugins
        bp_auto = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir), custom_dest_override="auto")
        self.assertEqual(bp_auto["file_plans"][0]["target_rel_path"], "nativePC/plugins/CustomMod.dll")

        # Explicit override -> root
        bp_root = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir), custom_dest_override="root")
        self.assertEqual(bp_root["file_plans"][0]["target_rel_path"], "CustomMod.dll")

        # Explicit override -> custom subdirectory
        bp_custom = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir), custom_dest_override="nativePC/custom/sub")
        self.assertEqual(bp_custom["file_plans"][0]["target_rel_path"], "nativePC/custom/sub/CustomMod.dll")

    def test_loose_dll_with_subfolders_preserves_subfolder_structure(self):
        """
        Verify that an archive with loose DLL at root and subfolders
        does NOT falsely treat a subfolder as a wrapper or as variants.
        All subfolders must be preserved under nativePC/plugins/.
        """
        zip_path = self._create_zip("LooseDllWithSubfolders.zip", {
            "MyPlugin.dll": "PLUGIN BINARY DATA",
            "MyPlugin.ini": "[Config]\nKey=1\n",
            "config/settings.json": '{"setting": true}',
            "assets/icon.png": "PNG DATA",
            "sounds/click.wav": "WAV DATA",
        })

        analysis = detect_archive_structure(
            [
                {"path": "MyPlugin.dll", "size": 100},
                {"path": "MyPlugin.ini", "size": 20},
                {"path": "config/settings.json", "size": 30},
                {"path": "assets/icon.png", "size": 50},
                {"path": "sounds/click.wav", "size": 40},
            ],
            "LooseDllWithSubfolders.zip"
        )

        self.assertIsNone(analysis["single_wrapper"], "Root files exist, so single_wrapper must be None")
        self.assertFalse(analysis["has_variants"], "Subfolders must NOT be falsely identified as variants")
        self.assertEqual(analysis["suggested_dest"], "plugins")
        self.assertFalse(analysis["is_ambiguous"])

        bp = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir))
        plans = {p["archive_path"]: p["target_rel_path"] for p in bp["file_plans"]}

        self.assertEqual(plans["MyPlugin.dll"], "nativePC/plugins/MyPlugin.dll")
        self.assertEqual(plans["MyPlugin.ini"], "nativePC/plugins/MyPlugin.ini")
        self.assertEqual(plans["config/settings.json"], "nativePC/plugins/config/settings.json")
        self.assertEqual(plans["assets/icon.png"], "nativePC/plugins/assets/icon.png")
        self.assertEqual(plans["sounds/click.wav"], "nativePC/plugins/sounds/click.wav")

        res = execute_all_out_attack(str(zip_path), "MyPlugin", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])
        self.assertEqual(res["files_installed"], 5)

        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "MyPlugin.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "config" / "settings.json").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "assets" / "icon.png").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "sounds" / "click.wav").exists())

    def test_double_nested_wrapper_nativepc_anchor(self):
        """
        Verify that nested wrapper directories (e.g. Pack/Nested/nativePC/...)
        properly anchor nativePC to game nativePC/ and beside files to game root.
        """
        zip_path = self._create_zip("DoubleNestedMod.zip", {
            "Pack/Nested/loader.dll": "LOADER BINARY",
            "Pack/Nested/version.dll": "VERSION HOOK BINARY",
            "Pack/Nested/nativePC/plugins/QuestLoader.dll": "QUEST LOADER PLUGIN",
            "Pack/Nested/nativePC/wp/axe/axe001.mod": "AXE DATA",
        })

        bp = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir))
        plans = {p["archive_path"]: p["target_rel_path"] for p in bp["file_plans"]}

        self.assertEqual(plans["Pack/Nested/loader.dll"], "loader.dll")
        self.assertEqual(plans["Pack/Nested/version.dll"], "version.dll")
        self.assertEqual(plans["Pack/Nested/nativePC/plugins/QuestLoader.dll"], "nativePC/plugins/QuestLoader.dll")
        self.assertEqual(plans["Pack/Nested/nativePC/wp/axe/axe001.mod"], "nativePC/wp/axe/axe001.mod")

        res = execute_all_out_attack(str(zip_path), "DoubleNestedMod", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])

        self.assertTrue((self.mock_game_dir / "loader.dll").exists())
        self.assertTrue((self.mock_game_dir / "version.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "QuestLoader.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "axe" / "axe001.mod").exists())

    def test_root_loader_archive_with_companion_files(self):
        """
        Verify root loader archive with companion files (readme, instructions)
        routes all files to game root, not splitting companion files to nativePC/.
        """
        zip_path = self._create_zip("RootLoaderPack.zip", {
            "loader.dll": "LOADER",
            "dinput8.dll": "DINPUT8",
            "readme.txt": "READ ME",
            "instructions.txt": "INSTRUCTIONS",
        })

        bp = build_preinstall_blueprint(str(zip_path), str(self.mock_game_dir))
        self.assertEqual(bp["suggested_dest"], "root")
        self.assertFalse(bp["is_ambiguous"])

        plans = {p["archive_path"]: p["target_rel_path"] for p in bp["file_plans"]}
        self.assertEqual(plans["loader.dll"], "loader.dll")
        self.assertEqual(plans["dinput8.dll"], "dinput8.dll")
        self.assertEqual(plans["readme.txt"], "readme.txt")
        self.assertEqual(plans["instructions.txt"], "instructions.txt")

        res = execute_all_out_attack(str(zip_path), "RootLoaderPack", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])

        self.assertTrue((self.mock_game_dir / "loader.dll").exists())
        self.assertTrue((self.mock_game_dir / "dinput8.dll").exists())
        self.assertTrue((self.mock_game_dir / "readme.txt").exists())
        self.assertTrue((self.mock_game_dir / "instructions.txt").exists())
        self.assertFalse((self.mock_game_dir / "nativePC" / "readme.txt").exists())

    def test_batch_install_with_subfolder_plugins_and_nested_wrappers(self):
        """
        Verify that BatchInstaller seamlessly deploys:
        1. Loose DLL with companion subfolders (config, assets)
        2. Double nested wrapped nativePC + root loader archive
        3. Root loader with readme
        4. Standard nativePC mod
        All must be classified as clean mods and install sequentially without pauses.
        """
        zip1 = self._create_zip("PluginWithSubfolders.zip", {
            "MyPlugin.dll": "DLL DATA",
            "config/settings.json": "{}",
            "assets/icon.png": "PNG",
        })
        zip2 = self._create_zip("NestedStracker.zip", {
            "ModPack/Files/loader.dll": "LOADER",
            "ModPack/Files/nativePC/plugins/Loader.dll": "PLUGIN",
        })
        zip3 = self._create_zip("RootWithReadme.zip", {
            "bink2w64.dll": "BINK HOOK",
            "readme.txt": "README",
        })
        zip4 = self._create_zip("StandardAxe.zip", {
            "nativePC/wp/axe/axe001.mod": "AXE",
        })

        installer = BatchInstaller(str(self.mock_game_dir))
        decision_calls = []

        res = installer.install_batch(
            [str(zip1), str(zip2), str(zip3), str(zip4)],
            on_decision_needed=lambda bp: decision_calls.append(bp) or {"action": "install"}
        )

        self.assertEqual(len(decision_calls), 0, "All 4 archives must be clean with no paused decision prompts")
        self.assertTrue(res["success"])
        self.assertEqual(res["installed_count"], 4)

        # 1. Plugin with subfolders
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "MyPlugin.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "config" / "settings.json").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "assets" / "icon.png").exists())

        # 2. Nested Stracker
        self.assertTrue((self.mock_game_dir / "loader.dll").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "plugins" / "Loader.dll").exists())

        # 3. Root with readme
        self.assertTrue((self.mock_game_dir / "bink2w64.dll").exists())
        self.assertTrue((self.mock_game_dir / "readme.txt").exists())

        # 4. Standard axe
        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "axe" / "axe001.mod").exists())


if __name__ == "__main__":
    unittest.main()


