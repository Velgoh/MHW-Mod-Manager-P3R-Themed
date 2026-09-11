"""
Edge case test suite for Pod 006 engine:
- 7z archive handling via 7z.exe
- Root DLLs and Plugins mapping
- Bare MHW subfolders mapping (e.g., wp/ -> nativePC/wp/)
- Skip colliding file action
- Destination root override
"""

import os
import sys
import shutil
import tempfile
import subprocess
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pod006.engine import (
    get_7z_binary,
    build_preinstall_blueprint,
    execute_all_out_attack,
    uninstall_mod,
    resolve_dest_path,
    detect_archive_structure,
    ManifestManager,
)


class TestPod006EdgeCases(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="pod006_edge_"))
        self.mock_game_dir = self.test_dir / "Monster Hunter World"
        self.mock_game_dir.mkdir(parents=True, exist_ok=True)
        (self.mock_game_dir / "MonsterHunterWorld.exe").write_text("DUMMY EXE", encoding="utf-8")
        self.exe_7z = get_7z_binary()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_7z_archive_creation_and_install(self):
        # Create a sample directory to compress with 7z
        sample_dir = self.test_dir / "sample_mod_files"
        wp_dir = sample_dir / "nativePC" / "wp" / "gun"
        wp_dir.mkdir(parents=True, exist_ok=True)
        (wp_dir / "gun001.mod").write_text("GUN MOD DATA", encoding="utf-8")

        archive_7z = self.test_dir / "TestMod.7z"
        # Compress with 7z.exe
        proc = subprocess.run(
            [self.exe_7z, "a", str(archive_7z), "*"],
            cwd=str(sample_dir),
            capture_output=True,
            text=True
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(archive_7z.exists())

        # Now blueprint & install TestMod.7z
        bp = build_preinstall_blueprint(str(archive_7z), str(self.mock_game_dir))
        self.assertEqual(bp["total_files"], 1)
        self.assertEqual(bp["file_plans"][0]["target_rel_path"], "nativePC/wp/gun/gun001.mod")

        res = execute_all_out_attack(str(archive_7z), "Test 7z Mod", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])
        target_file = self.mock_game_dir / "nativePC" / "wp" / "gun" / "gun001.mod"
        self.assertTrue(target_file.exists())
        self.assertEqual(target_file.read_text(encoding="utf-8"), "GUN MOD DATA")

    def test_bare_mhw_folders_auto_map_to_nativepc(self):
        # Mod has 'wp/axe/axe.mod' without nativePC prefix
        sample_dir = self.test_dir / "bare_mod"
        axe_dir = sample_dir / "wp" / "axe"
        axe_dir.mkdir(parents=True, exist_ok=True)
        (axe_dir / "axe999.mod").write_text("AXE 999", encoding="utf-8")

        archive_7z = self.test_dir / "BareMod.7z"
        subprocess.run([self.exe_7z, "a", str(archive_7z), "*"], cwd=str(sample_dir), capture_output=True)

        bp = build_preinstall_blueprint(str(archive_7z), str(self.mock_game_dir))
        # Auto-maps to nativePC/wp/axe/axe999.mod
        self.assertEqual(bp["file_plans"][0]["target_rel_path"], "nativePC/wp/axe/axe999.mod")

    def test_root_dll_mapping(self):
        # Mod has root files like loader.dll or dinput8.dll
        sample_dir = self.test_dir / "dll_mod"
        sample_dir.mkdir(parents=True, exist_ok=True)
        (sample_dir / "loader.dll").write_text("LOADER DLL DATA", encoding="utf-8")
        (sample_dir / "loader-config.json").write_text("{}", encoding="utf-8")

        archive_7z = self.test_dir / "LoaderMod.7z"
        subprocess.run([self.exe_7z, "a", str(archive_7z), "*"], cwd=str(sample_dir), capture_output=True)

        bp = build_preinstall_blueprint(str(archive_7z), str(self.mock_game_dir))
        targets = [p["target_rel_path"] for p in bp["file_plans"]]
        self.assertIn("loader.dll", targets)
        self.assertIn("loader-config.json", targets)

    def test_skip_collision_action(self):
        # Create an existing file
        existing_file = self.mock_game_dir / "nativePC" / "wp" / "sword" / "sword.mod"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("OLD SWORD", encoding="utf-8")

        sample_dir = self.test_dir / "sword_mod"
        sw_dir = sample_dir / "nativePC" / "wp" / "sword"
        sw_dir.mkdir(parents=True, exist_ok=True)
        (sw_dir / "sword.mod").write_text("NEW SWORD", encoding="utf-8")
        (sw_dir / "extra.tex").write_text("EXTRA TEX", encoding="utf-8")

        archive_7z = self.test_dir / "SwordMod.7z"
        subprocess.run([self.exe_7z, "a", str(archive_7z), "*"], cwd=str(sample_dir), capture_output=True)

        bp = build_preinstall_blueprint(str(archive_7z), str(self.mock_game_dir))
        self.assertEqual(bp["collisions_count"], 1)

        # Explicitly set collision action to skip
        for plan in bp["file_plans"]:
            if plan["collision"]:
                plan["action"] = "skip"

        res = execute_all_out_attack(str(archive_7z), "Sword Mod", bp["file_plans"], str(self.mock_game_dir))
        self.assertTrue(res["success"])
        self.assertEqual(res["files_installed"], 1)  # Only extra.tex installed
        self.assertEqual(res["files_backed_up"], 0)  # No backup made
        self.assertEqual(existing_file.read_text(encoding="utf-8"), "OLD SWORD")  # Unchanged!

    def test_out_of_order_fifo_uninstall(self):
        """Mod A -> Mod B. Uninstall Mod A out of order. Mod B must remain active on disk."""
        sample_a = self.test_dir / "mod_a_src"
        sample_b = self.test_dir / "mod_b_src"
        (sample_a / "nativePC" / "common").mkdir(parents=True, exist_ok=True)
        (sample_b / "nativePC" / "common").mkdir(parents=True, exist_ok=True)
        (sample_a / "nativePC" / "common" / "data.txt").write_text("MOD A CONTENT", encoding="utf-8")
        (sample_b / "nativePC" / "common" / "data.txt").write_text("MOD B CONTENT", encoding="utf-8")

        arc_a = self.test_dir / "ModA.7z"
        arc_b = self.test_dir / "ModB.7z"
        subprocess.run([self.exe_7z, "a", str(arc_a), "*"], cwd=str(sample_a), capture_output=True)
        subprocess.run([self.exe_7z, "a", str(arc_b), "*"], cwd=str(sample_b), capture_output=True)

        bp_a = build_preinstall_blueprint(str(arc_a), str(self.mock_game_dir))
        res_a = execute_all_out_attack(str(arc_a), "Mod A", bp_a["file_plans"], str(self.mock_game_dir))

        bp_b = build_preinstall_blueprint(str(arc_b), str(self.mock_game_dir))
        res_b = execute_all_out_attack(str(arc_b), "Mod B", bp_b["file_plans"], str(self.mock_game_dir))

        target_file = self.mock_game_dir / "nativePC" / "common" / "data.txt"
        self.assertEqual(target_file.read_text(encoding="utf-8"), "MOD B CONTENT")

        # Uninstall Mod A (FIFO out-of-order)
        res_un_a = uninstall_mod(res_a["mod_id"], str(self.mock_game_dir))
        self.assertTrue(res_un_a["success"])
        self.assertTrue(target_file.exists(), "Target file must NOT be deleted while Mod B is still installed!")
        self.assertEqual(target_file.read_text(encoding="utf-8"), "MOD B CONTENT")

        # Uninstall Mod B
        res_un_b = uninstall_mod(res_b["mod_id"], str(self.mock_game_dir))
        self.assertTrue(res_un_b["success"])
        self.assertFalse(target_file.exists(), "Target file must be removed after Mod B is uninstalled!")

    def test_middle_layer_mod_uninstall(self):
        """Mod A -> Mod B -> Mod C. Uninstall Mod B. Mod C must remain active. Uninstall Mod C -> Mod A restored."""
        sample_a = self.test_dir / "src_a"
        sample_b = self.test_dir / "src_b"
        sample_c = self.test_dir / "src_c"
        for s in (sample_a, sample_b, sample_c):
            (s / "nativePC").mkdir(parents=True, exist_ok=True)
        (sample_a / "nativePC" / "item.txt").write_text("VERSION 1", encoding="utf-8")
        (sample_b / "nativePC" / "item.txt").write_text("VERSION 2", encoding="utf-8")
        (sample_c / "nativePC" / "item.txt").write_text("VERSION 3", encoding="utf-8")

        arc_a = self.test_dir / "A.7z"
        arc_b = self.test_dir / "B.7z"
        arc_c = self.test_dir / "C.7z"
        subprocess.run([self.exe_7z, "a", str(arc_a), "*"], cwd=str(sample_a), capture_output=True)
        subprocess.run([self.exe_7z, "a", str(arc_b), "*"], cwd=str(sample_b), capture_output=True)
        subprocess.run([self.exe_7z, "a", str(arc_c), "*"], cwd=str(sample_c), capture_output=True)

        bp_a = build_preinstall_blueprint(str(arc_a), str(self.mock_game_dir))
        res_a = execute_all_out_attack(str(arc_a), "Mod A", bp_a["file_plans"], str(self.mock_game_dir))

        bp_b = build_preinstall_blueprint(str(arc_b), str(self.mock_game_dir))
        res_b = execute_all_out_attack(str(arc_b), "Mod B", bp_b["file_plans"], str(self.mock_game_dir))

        bp_c = build_preinstall_blueprint(str(arc_c), str(self.mock_game_dir))
        res_c = execute_all_out_attack(str(arc_c), "Mod C", bp_c["file_plans"], str(self.mock_game_dir))

        target_file = self.mock_game_dir / "nativePC" / "item.txt"
        self.assertEqual(target_file.read_text(encoding="utf-8"), "VERSION 3")

        # Uninstall Mod B (middle layer)
        res_un_b = uninstall_mod(res_b["mod_id"], str(self.mock_game_dir))
        self.assertTrue(res_un_b["success"])
        self.assertTrue(target_file.exists())
        self.assertEqual(target_file.read_text(encoding="utf-8"), "VERSION 3", "Mod C must stay active on disk!")

        # Uninstall Mod C - restores Mod A
        res_un_c = uninstall_mod(res_c["mod_id"], str(self.mock_game_dir))
        self.assertTrue(res_un_c["success"])
        self.assertTrue(target_file.exists())
        self.assertEqual(target_file.read_text(encoding="utf-8"), "VERSION 1", "Mod A must be restored!")

        # Uninstall Mod A - clean removal
        res_un_a = uninstall_mod(res_a["mod_id"], str(self.mock_game_dir))
        self.assertTrue(res_un_a["success"])
        self.assertFalse(target_file.exists())

    def test_base_game_file_backup_and_out_of_order_restore(self):
        """Original base game file preserved across out-of-order uninstalls."""
        base_file = self.mock_game_dir / "nativePC" / "common" / "equip.am_dat"
        base_file.parent.mkdir(parents=True, exist_ok=True)
        base_file.write_text("ORIGINAL BASE GAME DATA", encoding="utf-8")

        sample_a = self.test_dir / "bg_a"
        sample_b = self.test_dir / "bg_b"
        (sample_a / "nativePC" / "common").mkdir(parents=True, exist_ok=True)
        (sample_b / "nativePC" / "common").mkdir(parents=True, exist_ok=True)
        (sample_a / "nativePC" / "common" / "equip.am_dat").write_text("MOD A OVERWRITE", encoding="utf-8")
        (sample_b / "nativePC" / "common" / "equip.am_dat").write_text("MOD B OVERWRITE", encoding="utf-8")

        arc_a = self.test_dir / "BGA.7z"
        arc_b = self.test_dir / "BGB.7z"
        subprocess.run([self.exe_7z, "a", str(arc_a), "*"], cwd=str(sample_a), capture_output=True)
        subprocess.run([self.exe_7z, "a", str(arc_b), "*"], cwd=str(sample_b), capture_output=True)

        bp_a = build_preinstall_blueprint(str(arc_a), str(self.mock_game_dir))
        res_a = execute_all_out_attack(str(arc_a), "Mod A", bp_a["file_plans"], str(self.mock_game_dir))

        bp_b = build_preinstall_blueprint(str(arc_b), str(self.mock_game_dir))
        res_b = execute_all_out_attack(str(arc_b), "Mod B", bp_b["file_plans"], str(self.mock_game_dir))

        self.assertEqual(base_file.read_text(encoding="utf-8"), "MOD B OVERWRITE")

        # Uninstall Mod A first
        uninstall_mod(res_a["mod_id"], str(self.mock_game_dir))
        self.assertEqual(base_file.read_text(encoding="utf-8"), "MOD B OVERWRITE")

        # Uninstall Mod B
        uninstall_mod(res_b["mod_id"], str(self.mock_game_dir))
        self.assertTrue(base_file.exists())
        self.assertEqual(base_file.read_text(encoding="utf-8"), "ORIGINAL BASE GAME DATA")

    def test_destination_routing_no_double_nesting(self):
        """Verify resolve_dest_path avoids duplicate folders."""
        p1 = resolve_dest_path(["nativePC", "wp", "bow", "bow.wp_dat"], "nativePC")
        self.assertEqual(p1, "nativePC/wp/bow/bow.wp_dat")

        p2 = resolve_dest_path(["wp", "bow", "bow.wp_dat"], "nativePC")
        self.assertEqual(p2, "nativePC/wp/bow/bow.wp_dat")

        p3 = resolve_dest_path(["Lua", "scripts", "main.lua"], "Lua")
        self.assertEqual(p3, "Lua/scripts/main.lua")

        p4 = resolve_dest_path(["nativePC", "sound", "bgm.pck"], "nativePC/sound/wwise")
        self.assertEqual(p4, "nativePC/sound/wwise/sound/bgm.pck")

        p5 = resolve_dest_path(["loader.dll"], "root")
        self.assertEqual(p5, "loader.dll")

    def test_ambiguity_detection(self):
        """Verify detect_archive_structure correctly flags ambiguous vs standard mods."""
        amb_files = [
            {"path": "my_texture.dds", "size": 100},
            {"path": "docs/readme.txt", "size": 50},
        ]
        res_amb = detect_archive_structure(amb_files, "loose_files.zip")
        self.assertTrue(res_amb["is_ambiguous"])

        std_files = [
            {"path": "nativePC/wp/bow/bow.wp_dat", "size": 200},
        ]
        res_std = detect_archive_structure(std_files, "standard_bow.zip")
        self.assertFalse(res_std["is_ambiguous"])

        dll_files = [
            {"path": "loader.dll", "size": 50000},
        ]
        res_dll = detect_archive_structure(dll_files, "loader.zip")
        self.assertFalse(res_dll["is_ambiguous"])


if __name__ == "__main__":
    unittest.main()
