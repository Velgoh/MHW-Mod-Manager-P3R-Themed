"""
Unit and integration test suite for Manual Mod Purge and Archive Matching features in Pod 006
"""

import os
import sys
import shutil
import tempfile
import zipfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pod006.engine import (
    build_preinstall_blueprint,
    execute_all_out_attack,
    purge_archive_matching_files,
    ManifestManager,
)


class TestManualModPurge(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="pod006_purge_test_"))
        self.mock_game_dir = self.test_dir / "Monster Hunter World"
        self.mock_game_dir.mkdir(parents=True, exist_ok=True)
        (self.mock_game_dir / "MonsterHunterWorld.exe").write_text("DUMMY EXE", encoding="utf-8")
        (self.mock_game_dir / "chunk").mkdir(exist_ok=True)
        (self.mock_game_dir / "nativePC").mkdir(exist_ok=True)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_archive_matching_detection_and_status(self):
        """Test blueprint matches files on disk and correctly flags IDENTICAL vs MODIFIED vs NOT FOUND."""
        # 1. Place some files manually in mock game dir
        file1 = self.mock_game_dir / "nativePC" / "hm" / "wp" / "wp03" / "action.fsm"
        file1.parent.mkdir(parents=True, exist_ok=True)
        file1.write_text("IDENTICAL CONTENT", encoding="utf-8")

        file2 = self.mock_game_dir / "nativePC" / "hm" / "wp" / "wp03" / "modified.fsm"
        file2.write_text("DIFFERENT MODIFIED CONTENT IN GAME", encoding="utf-8")

        # 2. Create archive with 3 files:
        # - file1: matches size and content exactly
        # - file2: exists on disk but has different size
        # - file3: does not exist on disk
        archive_zip = self.test_dir / "ManualMod.zip"
        with zipfile.ZipFile(archive_zip, "w") as zf:
            zf.writestr("nativePC/hm/wp/wp03/action.fsm", "IDENTICAL CONTENT")
            zf.writestr("nativePC/hm/wp/wp03/modified.fsm", "SHORT")
            zf.writestr("nativePC/hm/wp/wp03/new_file.fsm", "BRAND NEW FILE")

        bp = build_preinstall_blueprint(str(archive_zip), str(self.mock_game_dir))

        self.assertEqual(bp["total_files"], 3)
        self.assertEqual(bp["matching_files_count"], 2)
        self.assertTrue(bp["has_matching_game_files"])

        plan_map = {p["target_rel_path"]: p for p in bp["file_plans"]}

        # Check action.fsm
        self.assertIn("nativePC/hm/wp/wp03/action.fsm", plan_map)
        p1 = plan_map["nativePC/hm/wp/wp03/action.fsm"]
        self.assertTrue(p1["collision"])
        self.assertEqual(p1["match_status"], "FOUND (IDENTICAL)")
        self.assertEqual(p1["disk_size"], len("IDENTICAL CONTENT"))

        # Check modified.fsm
        self.assertIn("nativePC/hm/wp/wp03/modified.fsm", plan_map)
        p2 = plan_map["nativePC/hm/wp/wp03/modified.fsm"]
        self.assertTrue(p2["collision"])
        self.assertEqual(p2["match_status"], "FOUND (MODIFIED)")
        self.assertEqual(p2["disk_size"], len("DIFFERENT MODIFIED CONTENT IN GAME"))

        # Check new_file.fsm
        self.assertIn("nativePC/hm/wp/wp03/new_file.fsm", plan_map)
        p3 = plan_map["nativePC/hm/wp/wp03/new_file.fsm"]
        self.assertFalse(p3["collision"])
        self.assertEqual(p3["match_status"], "NOT FOUND")
        self.assertIsNone(p3["disk_size"])

    def test_purge_backup_and_file_removal(self):
        """Test purging matching files safely creates backup and deletes files from game dir."""
        # 1. Place manual mod files
        f1 = self.mock_game_dir / "nativePC" / "hm" / "wp" / "wp03" / "wp03.col"
        f1.parent.mkdir(parents=True, exist_ok=True)
        f1.write_text("COL DATA 12345", encoding="utf-8")

        f2 = self.mock_game_dir / "nativePC" / "hm" / "wp" / "wp03" / "wp03.lmt"
        f2.write_text("LMT DATA 67890", encoding="utf-8")

        # Unrelated file that should remain intact
        f_keep = self.mock_game_dir / "nativePC" / "hm" / "wp" / "wp03" / "unrelated_other_mod.tex"
        f_keep.write_text("DO NOT TOUCH THIS FILE", encoding="utf-8")

        archive_path = str(self.test_dir / "AggressiveLS_Mock.7z")
        selected_paths = [
            "nativePC/hm/wp/wp03/wp03.col",
            "nativePC/hm/wp/wp03/wp03.lmt",
        ]

        res = purge_archive_matching_files(
            archive_path=archive_path,
            selected_relative_paths=selected_paths,
            game_dir=str(self.mock_game_dir),
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["purged_count"], 2)
        self.assertIn("nativePC/hm/wp/wp03/wp03.col", res["purged_files"])
        self.assertIn("nativePC/hm/wp/wp03/wp03.lmt", res["purged_files"])

        # Target files should no longer exist in game directory
        self.assertFalse(f1.exists())
        self.assertFalse(f2.exists())

        # Unrelated file must remain untouched
        self.assertTrue(f_keep.exists())
        self.assertEqual(f_keep.read_text(encoding="utf-8"), "DO NOT TOUCH THIS FILE")

        # Verify backup exists and has identical contents
        backup_dir = Path(res["backup_dir"])
        self.assertTrue(backup_dir.exists())
        b1 = backup_dir / "nativePC" / "hm" / "wp" / "wp03" / "wp03.col"
        b2 = backup_dir / "nativePC" / "hm" / "wp" / "wp03" / "wp03.lmt"
        self.assertTrue(b1.exists())
        self.assertTrue(b2.exists())
        self.assertEqual(b1.read_text(encoding="utf-8"), "COL DATA 12345")
        self.assertEqual(b2.read_text(encoding="utf-8"), "LMT DATA 67890")

    def test_recursive_empty_folder_pruning(self):
        """Test recursive upward directory cleanup stops at nativePC and never deletes non-empty folders."""
        # Create deep nested path: nativePC/hm/wp/wp03/mot/w03_00/w03_00.lmt
        deep_file = self.mock_game_dir / "nativePC" / "hm" / "wp" / "wp03" / "mot" / "w03_00" / "w03_00.lmt"
        deep_file.parent.mkdir(parents=True, exist_ok=True)
        deep_file.write_text("DEEP LMT CONTENT", encoding="utf-8")

        res = purge_archive_matching_files(
            archive_path="test_mod.zip",
            selected_relative_paths=["nativePC/hm/wp/wp03/mot/w03_00/w03_00.lmt"],
            game_dir=str(self.mock_game_dir)
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["purged_count"], 1)

        # File is gone
        self.assertFalse(deep_file.exists())

        # All empty parent folders up to nativePC should be pruned
        self.assertFalse((self.mock_game_dir / "nativePC" / "hm" / "wp" / "wp03" / "mot" / "w03_00").exists())
        self.assertFalse((self.mock_game_dir / "nativePC" / "hm" / "wp" / "wp03" / "mot").exists())
        self.assertFalse((self.mock_game_dir / "nativePC" / "hm" / "wp" / "wp03").exists())
        self.assertFalse((self.mock_game_dir / "nativePC" / "hm" / "wp").exists())
        self.assertFalse((self.mock_game_dir / "nativePC" / "hm").exists())

        # nativePC itself MUST NOT be deleted (it is a protected directory)
        self.assertTrue((self.mock_game_dir / "nativePC").exists())

    def test_manifest_synchronization_on_purge(self):
        """Test that if a mod was tracked in manifest and purged, manifest updates properly."""
        # 1. Install a mod through execute_all_out_attack so it is tracked
        mod_zip = self.test_dir / "TrackedMod.zip"
        with zipfile.ZipFile(mod_zip, "w") as zf:
            zf.writestr("nativePC/test/file_a.txt", "FILE A")
            zf.writestr("nativePC/test/file_b.txt", "FILE B")

        bp = build_preinstall_blueprint(str(mod_zip), str(self.mock_game_dir))
        install_res = execute_all_out_attack(
            str(mod_zip),
            "Tracked Mod Test",
            bp["file_plans"],
            str(self.mock_game_dir)
        )
        self.assertTrue(install_res["success"])

        manifest_mgr = ManifestManager(str(self.mock_game_dir))
        installed = manifest_mgr.get_installed_mods()
        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0]["file_count"], 2)

        # 2. Manually purge only file_a.txt
        res = purge_archive_matching_files(
            archive_path=str(mod_zip),
            selected_relative_paths=["nativePC/test/file_a.txt"],
            game_dir=str(self.mock_game_dir)
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["purged_count"], 1)

        # Check manifest updated: mod now has 1 file
        installed = manifest_mgr.get_installed_mods()
        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0]["file_count"], 1)
        remaining_paths = [f["target_rel_path"] for f in installed[0]["files"]]
        self.assertIn("nativePC/test/file_b.txt", remaining_paths)
        self.assertNotIn("nativePC/test/file_a.txt", remaining_paths)

        # 3. Purge the remaining file_b.txt -> Mod should be completely removed from manifest
        res2 = purge_archive_matching_files(
            archive_path=str(mod_zip),
            selected_relative_paths=["nativePC/test/file_b.txt"],
            game_dir=str(self.mock_game_dir)
        )
        self.assertTrue(res2["success"])
        self.assertEqual(res2["purged_count"], 1)

        installed = manifest_mgr.get_installed_mods()
        self.assertEqual(len(installed), 0)

    def test_purge_edge_cases(self):
        """Test edge cases: empty list, non-existent files, traversal attacks, invalid directory."""
        # 1. Empty selection list
        res_empty = purge_archive_matching_files("any.zip", [], str(self.mock_game_dir))
        self.assertTrue(res_empty["success"])
        self.assertEqual(res_empty["purged_count"], 0)

        # 2. Non-existent files
        res_nonexistent = purge_archive_matching_files(
            "any.zip",
            ["nativePC/does/not/exist.txt"],
            str(self.mock_game_dir)
        )
        self.assertTrue(res_nonexistent["success"])
        self.assertEqual(res_nonexistent["purged_count"], 0)

        # 3. Path traversal attack attempt
        res_traversal = purge_archive_matching_files(
            "any.zip",
            ["../../outside.txt", "/etc/passwd", "..\\..\\windows\\system32"],
            str(self.mock_game_dir)
        )
        self.assertTrue(res_traversal["success"])
        self.assertEqual(res_traversal["purged_count"], 0)

        # 4. Invalid game directory
        res_invalid_dir = purge_archive_matching_files(
            "any.zip",
            ["nativePC/file.txt"],
            str(self.test_dir / "nonexistent_dir")
        )
        self.assertFalse(res_invalid_dir["success"])
        self.assertIn("error", res_invalid_dir)

    def test_purge_read_only_files_and_directories(self):
        """Test that files and directories marked read-only on Windows are purged and pruned without PermissionError."""
        import stat

        ro_file = self.mock_game_dir / "nativePC" / "hm" / "wp" / "wp03" / "readonly_test.fsm"
        ro_file.parent.mkdir(parents=True, exist_ok=True)
        ro_file.write_text("READONLY CONTENT", encoding="utf-8")
        os.chmod(ro_file, stat.S_IREAD)

        # Also set the parent folder read-only
        os.chmod(ro_file.parent, stat.S_IREAD)

        res = purge_archive_matching_files(
            archive_path="readonly_mod.zip",
            selected_relative_paths=["nativePC/hm/wp/wp03/readonly_test.fsm"],
            game_dir=str(self.mock_game_dir)
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["purged_count"], 1)
        self.assertFalse(ro_file.exists())
        self.assertFalse(ro_file.parent.exists())
        self.assertTrue((self.mock_game_dir / "nativePC").exists())

        # Check backup was created
        backup_dir = Path(res["backup_dir"])
        self.assertTrue((backup_dir / "nativePC" / "hm" / "wp" / "wp03" / "readonly_test.fsm").exists())

    def test_purge_with_variant_and_metadata(self):
        """Test that variant names are included in backup directory and purge_info.json is written."""
        import json

        f = self.mock_game_dir / "nativePC" / "variant_test.fsm"
        f.write_text("VARIANT CONTENT", encoding="utf-8")

        res = purge_archive_matching_files(
            archive_path="SpecialMod.zip",
            selected_relative_paths=["nativePC/variant_test.fsm"],
            game_dir=str(self.mock_game_dir),
            variant_name="Special 4K Edition"
        )

        self.assertTrue(res["success"])
        self.assertIn("Special_4K_Edition", res["backup_dir"])

        # Check purge_info.json
        info_file = Path(res["backup_dir"]) / "purge_info.json"
        self.assertTrue(info_file.exists())
        with open(info_file, "r", encoding="utf-8") as jf:
            info = json.load(jf)
        self.assertEqual(info["variant"], "Special 4K Edition")
        self.assertEqual(info["purged_count"], 1)
        self.assertIn("nativePC/variant_test.fsm", info["purged_files"])

    def test_rapid_successive_purges_unique_backups(self):
        """Test that successive purges within the same timestamp second get unique backup dirs."""
        f1 = self.mock_game_dir / "nativePC" / "file1.fsm"
        f2 = self.mock_game_dir / "nativePC" / "file2.fsm"
        f1.write_text("F1", encoding="utf-8")
        f2.write_text("F2", encoding="utf-8")

        res1 = purge_archive_matching_files("mod.zip", ["nativePC/file1.fsm"], str(self.mock_game_dir))
        res2 = purge_archive_matching_files("mod.zip", ["nativePC/file2.fsm"], str(self.mock_game_dir))

        self.assertTrue(res1["success"])
        self.assertTrue(res2["success"])
        self.assertNotEqual(res1["backup_dir"], res2["backup_dir"])
        self.assertTrue(Path(res1["backup_dir"]).exists())
        self.assertTrue(Path(res2["backup_dir"]).exists())

    def test_mock_aggressive_ls_manual_purge_workflow(self):
        """Test with Aggressive LS archive in temporary mock game dir without touching real game folder."""
        real_7z = Path(r"C:\Users\Yonah\Downloads\Machine Archives\Monster Hunter World\Aggressive LS v1.6-5171-1-6-1643668399.7z")
        if not real_7z.exists():
            self.skipTest("Aggressive LS archive not present in Downloads")

        # Simulate user having manually installed 2 files of Aggressive LS into our temp mock_game_dir
        simulated_rel1 = "nativePC/hm/wp/wp03/collision/wp03.col"
        simulated_rel2 = "nativePC/hm/wp/wp03/mot/w03_00_fs/w03_00_fs.lmt"

        dest1 = self.mock_game_dir / Path(simulated_rel1)
        dest2 = self.mock_game_dir / Path(simulated_rel2)
        dest1.parent.mkdir(parents=True, exist_ok=True)
        dest2.parent.mkdir(parents=True, exist_ok=True)

        # Write exact byte sizes as in the archive (wp03.col is 20408 bytes, w03_00_fs.lmt is 1072 bytes)
        dest1.write_bytes(b"X" * 20408)
        dest2.write_bytes(b"Y" * 1072)

        # 1. Blueprint inspect
        bp = build_preinstall_blueprint(str(real_7z), str(self.mock_game_dir))
        self.assertEqual(bp["matching_files_count"], 2)
        self.assertTrue(bp["has_matching_game_files"])

        matched_plans = [p for p in bp["file_plans"] if p["collision"]]
        self.assertEqual(len(matched_plans), 2)
        for p in matched_plans:
            self.assertEqual(p["match_status"], "FOUND (IDENTICAL)")

        # 2. Execute purge of those 2 files
        res = purge_archive_matching_files(
            archive_path=str(real_7z),
            selected_relative_paths=[simulated_rel1, simulated_rel2],
            game_dir=str(self.mock_game_dir)
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["purged_count"], 2)
        self.assertFalse(dest1.exists())
        self.assertFalse(dest2.exists())

        # Verify backup was created in .pod006_backup/manual_purge
        backup_dir = Path(res["backup_dir"])
        self.assertTrue(backup_dir.exists())
        self.assertTrue((backup_dir / Path(simulated_rel1)).exists())
        self.assertTrue((backup_dir / Path(simulated_rel2)).exists())

        # Verify recomputing blueprint now sees 0 matching files
        bp_after = build_preinstall_blueprint(str(real_7z), str(self.mock_game_dir))
        self.assertEqual(bp_after["matching_files_count"], 0)
        self.assertFalse(bp_after["has_matching_game_files"])


if __name__ == "__main__":
    unittest.main()
