"""
Unit and integration test suite for Pod 006 engine
"""

import os
import sys
import shutil
import tempfile
import zipfile
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pod006.engine import (
    get_7z_binary,
    detect_game_directory,
    is_valid_game_directory,
    list_archive_contents,
    detect_archive_structure,
    build_preinstall_blueprint,
    execute_all_out_attack,
    uninstall_mod,
    clean_slate_all_mods,
    ManifestManager,
    format_size,
)


class TestPod006Engine(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="pod006_test_"))
        self.mock_game_dir = self.test_dir / "Monster Hunter World"
        self.mock_game_dir.mkdir(parents=True, exist_ok=True)
        # Create dummy exe
        (self.mock_game_dir / "MonsterHunterWorld.exe").write_text("DUMMY EXE", encoding="utf-8")
        (self.mock_game_dir / "chunk").mkdir(exist_ok=True)
        (self.mock_game_dir / "nativePC").mkdir(exist_ok=True)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_7z_binary_found(self):
        binary = get_7z_binary()
        self.assertTrue(os.path.exists(binary), f"7z binary not found at {binary}")

    def test_valid_game_directory(self):
        res = is_valid_game_directory(str(self.mock_game_dir))
        self.assertTrue(res["valid"])
        self.assertIsNone(res.get("warning"))

        # Test invalid directory
        res_invalid = is_valid_game_directory(str(self.test_dir / "nonexistent"))
        self.assertFalse(res_invalid["valid"])

    def test_format_size(self):
        self.assertEqual(format_size(500), "500 B")
        self.assertEqual(format_size(2048), "2.0 KB")
        self.assertEqual(format_size(1048576 * 5), "5.0 MB")

    def test_real_lua_engine_zip(self):
        real_zip = Path(r"C:\Users\Yonah\Downloads\LuaEngine.1.3.0.zip")
        if not real_zip.exists():
            self.skipTest("LuaEngine.1.3.0.zip not in Downloads")

        contents = list_archive_contents(str(real_zip))
        self.assertGreater(len(contents), 5)
        paths = [f["path"] for f in contents]
        self.assertTrue(any("nativePC" in p for p in paths))
        self.assertTrue(any("Lua" in p for p in paths))

        analysis = detect_archive_structure(contents, real_zip.name)
        self.assertEqual(analysis["suggested_dest"], "nativePC")

    def test_variant_detection_and_blueprint(self):
        # Create a mock zip with variants
        zip_path = self.test_dir / "MultiVariantMod.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Variant 1
            zf.writestr("01_Standard_Edition/nativePC/wp/axe/axe001.mod", "Standard Axe Data")
            zf.writestr("01_Standard_Edition/nativePC/wp/axe/axe001.tex", "Standard Axe Tex")
            # Variant 2
            zf.writestr("02_Electric_Glow/nativePC/wp/axe/axe001.mod", "Glow Axe Data")
            zf.writestr("02_Electric_Glow/nativePC/wp/axe/axe001.tex", "Glow Axe Tex")
            # Optional Addon
            zf.writestr("Optional_Custom_SFX/nativePC/sound/wwise/axe_sfx.nbnk", "SFX Data")

        contents = list_archive_contents(str(zip_path))
        self.assertEqual(len(contents), 5)

        analysis = detect_archive_structure(contents, zip_path.name)
        self.assertTrue(analysis["has_variants"])
        variant_ids = [v["id"] for v in analysis["variants"]]
        self.assertIn("01_Standard_Edition", variant_ids)
        self.assertIn("02_Electric_Glow", variant_ids)
        self.assertIn("Optional_Custom_SFX", variant_ids)

        # Build blueprint selecting Variant 2
        blueprint = build_preinstall_blueprint(
            str(zip_path),
            str(self.mock_game_dir),
            selected_variant_ids=["02_Electric_Glow"]
        )
        self.assertEqual(blueprint["total_files"], 2)
        target_paths = [p["target_rel_path"] for p in blueprint["file_plans"]]
        self.assertIn("nativePC/wp/axe/axe001.mod", target_paths)
        self.assertIn("nativePC/wp/axe/axe001.tex", target_paths)

    def test_smart_backup_and_restore_cycle(self):
        # 1. Place a base game / prior file in game dir
        existing_file = self.mock_game_dir / "nativePC" / "wp" / "bow" / "bow001.mod"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("ORIGINAL GAME CONTENT", encoding="utf-8")

        # 2. Create Mod A zip that overwrites bow001.mod and adds bow001.tex
        mod_a_zip = self.test_dir / "ModA.zip"
        with zipfile.ZipFile(mod_a_zip, "w") as zf:
            zf.writestr("nativePC/wp/bow/bow001.mod", "MOD A CONTENT")
            zf.writestr("nativePC/wp/bow/bow001.tex", "MOD A TEX")

        # 3. Build blueprint
        bp = build_preinstall_blueprint(str(mod_a_zip), str(self.mock_game_dir))
        self.assertEqual(bp["collisions_count"], 1)
        collision_file = [f for f in bp["file_plans"] if f["collision"]][0]
        self.assertEqual(collision_file["target_rel_path"], "nativePC/wp/bow/bow001.mod")
        self.assertEqual(collision_file["action"], "overwrite_backup")

        # 4. Execute All-Out Attack
        res = execute_all_out_attack(
            str(mod_a_zip),
            "Mod A Hunter Bow",
            bp["file_plans"],
            str(self.mock_game_dir)
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["files_installed"], 2)
        self.assertEqual(res["files_backed_up"], 1)

        # Verify file content is now Mod A
        self.assertEqual(existing_file.read_text(encoding="utf-8"), "MOD A CONTENT")

        # Verify backup exists in .pod006_backup
        backup_dir = self.mock_game_dir / ".pod006_backup"
        self.assertTrue(backup_dir.exists())
        backups = list(backup_dir.glob("*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "ORIGINAL GAME CONTENT")

        # Verify manifest
        manifest_mgr = ManifestManager(str(self.mock_game_dir))
        installed = manifest_mgr.get_installed_mods()
        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0]["name"], "Mod A Hunter Bow")

        # 5. Now Mod B installs and overwrites bow001.mod again!
        mod_b_zip = self.test_dir / "ModB.zip"
        with zipfile.ZipFile(mod_b_zip, "w") as zf:
            zf.writestr("nativePC/wp/bow/bow001.mod", "MOD B ULTRA CONTENT")

        bp_b = build_preinstall_blueprint(str(mod_b_zip), str(self.mock_game_dir))
        self.assertEqual(bp_b["collisions_count"], 1)
        self.assertEqual(bp_b["file_plans"][0]["existing_owner"], "Mod A Hunter Bow")

        res_b = execute_all_out_attack(
            str(mod_b_zip),
            "Mod B Ultra Bow",
            bp_b["file_plans"],
            str(self.mock_game_dir)
        )
        self.assertTrue(res_b["success"])
        self.assertEqual(existing_file.read_text(encoding="utf-8"), "MOD B ULTRA CONTENT")

        # 6. Uninstall Mod B -> Should restore Mod A content!
        uninst_b = uninstall_mod(res_b["mod_id"], str(self.mock_game_dir))
        self.assertTrue(uninst_b["success"])
        self.assertEqual(existing_file.read_text(encoding="utf-8"), "MOD A CONTENT")

        # 7. Uninstall Mod A -> Should restore ORIGINAL GAME CONTENT!
        uninst_a = uninstall_mod(res["mod_id"], str(self.mock_game_dir))
        self.assertTrue(uninst_a["success"])
        self.assertEqual(existing_file.read_text(encoding="utf-8"), "ORIGINAL GAME CONTENT")

        # Also verify newly added file (bow001.tex) was completely removed
        tex_file = self.mock_game_dir / "nativePC" / "wp" / "bow" / "bow001.tex"
        self.assertFalse(tex_file.exists())

        # Verify manifest is now empty
        self.assertEqual(len(manifest_mgr.get_installed_mods()), 0)

    def test_clean_slate(self):
        # Create and install 2 mods
        for name in ["ModOne", "ModTwo"]:
            zip_p = self.test_dir / f"{name}.zip"
            with zipfile.ZipFile(zip_p, "w") as zf:
                zf.writestr(f"nativePC/test/{name}.txt", f"Content of {name}")
            bp = build_preinstall_blueprint(str(zip_p), str(self.mock_game_dir))
            execute_all_out_attack(str(zip_p), name, bp["file_plans"], str(self.mock_game_dir))

        manifest_mgr = ManifestManager(str(self.mock_game_dir))
        self.assertEqual(len(manifest_mgr.get_installed_mods()), 2)

        # Run Clean Slate
        res = clean_slate_all_mods(str(self.mock_game_dir))
        self.assertTrue(res["success"])
        self.assertEqual(res["mods_uninstalled"], 2)

        # Verify files are gone and manifest empty
        self.assertEqual(len(manifest_mgr.get_installed_mods()), 0)
        self.assertFalse((self.mock_game_dir / "nativePC" / "test").exists())


if __name__ == "__main__":
    unittest.main()
