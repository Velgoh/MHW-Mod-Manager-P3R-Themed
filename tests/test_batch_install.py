"""
Unit and integration test suite for Pod 006 Batch Installation Controller
Persona 3 Reload S.E.E.S. Batch Deployment Protocol Tests
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

import subprocess

from pod006.engine import (
    BatchInstaller,
    build_preinstall_blueprint,
    execute_all_out_attack,
    uninstall_mod,
    ManifestManager,
    get_7z_binary,
)


class TestBatchInstaller(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="pod006_batch_test_"))
        self.mock_game_dir = self.test_dir / "Monster Hunter World"
        self.mock_game_dir.mkdir(parents=True, exist_ok=True)
        (self.mock_game_dir / "MonsterHunterWorld.exe").write_text("MHW DUMMY EXE", encoding="utf-8")
        (self.mock_game_dir / "nativePC").mkdir(exist_ok=True)
        (self.mock_game_dir / "chunk").mkdir(exist_ok=True)
        self.installer = BatchInstaller(str(self.mock_game_dir))

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_clean_zip(self, filename: str, files_dict: dict) -> Path:
        p = self.test_dir / filename
        with zipfile.ZipFile(p, "w") as zf:
            for arc_path, content in files_dict.items():
                zf.writestr(arc_path, content)
        return p

    def test_batch_sequencing_clean_archives(self):
        """Verify sequential batch installation of multiple clean/unambiguous archives."""
        zip1 = self._create_clean_zip("AxeMod.zip", {
            "nativePC/wp/axe/axe001.mod": "Axe Mod 1 Data",
            "nativePC/wp/axe/axe001.tex": "Axe Mod 1 Tex"
        })
        zip2 = self._create_clean_zip("BowMod.zip", {
            "nativePC/wp/bow/bow001.mod": "Bow Mod 2 Data"
        })
        zip3 = self._create_clean_zip("SoundMod.zip", {
            "nativePC/sound/wwise/bgm.pck": "Sound Mod 3 Data"
        })

        progress_events = []
        def on_progress(data):
            progress_events.append(data)

        res = self.installer.install_batch(
            [str(zip1), str(zip2), str(zip3)],
            on_progress=on_progress
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["total_staged"], 3)
        self.assertEqual(res["installed_count"], 3)
        self.assertEqual(res["skipped_count"], 0)
        self.assertFalse(res["aborted"])
        self.assertEqual(res["total_files_installed"], 4)

        # Verify files exist on disk
        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "axe" / "axe001.mod").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "bow" / "bow001.mod").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "sound" / "wwise" / "bgm.pck").exists())

        # Verify progress tracking
        inspect_events = [e for e in progress_events if e.get("stage") == "inspecting"]
        deploy_events = [e for e in progress_events if e.get("stage") == "deploying"]
        finish_events = [e for e in progress_events if e.get("stage") == "finished_item"]
        self.assertEqual(len(inspect_events), 3)
        self.assertEqual(len(deploy_events), 3)
        self.assertEqual(len(finish_events), 3)

        # Verify manifest registration
        manifest = ManifestManager(str(self.mock_game_dir))
        installed = manifest.get_installed_mods()
        self.assertEqual(len(installed), 3)
        mod_names = [m["name"] for m in installed]
        self.assertIn("AxeMod", mod_names)
        self.assertIn("BowMod", mod_names)
        self.assertIn("SoundMod", mod_names)

    def test_batch_paused_prompt_callback_for_variants(self):
        """Verify batch pauses and invokes on_decision_needed callback when an archive has variants."""
        # Variant mod
        var_zip = self.test_dir / "CostumeVariants.zip"
        with zipfile.ZipFile(var_zip, "w") as zf:
            zf.writestr("01_Crimson_Armor/nativePC/pl/f_helm.mod", "Crimson Helm")
            zf.writestr("02_Cobalt_Armor/nativePC/pl/f_helm.mod", "Cobalt Helm")

        clean_zip = self._create_clean_zip("CleanAxe.zip", {
            "nativePC/wp/axe/clean_axe.mod": "Clean Axe"
        })

        decisions_called = []
        def on_decision_needed(bp):
            decisions_called.append(bp)
            self.assertTrue(bp["has_variants"])
            self.assertEqual(len(bp["variants"]), 2)
            # Select Cobalt variant
            return {
                "action": "install",
                "selected_variants": ["02_Cobalt_Armor"],
                "mod_name": "Cobalt Armor Edition"
            }

        res = self.installer.install_batch(
            [str(var_zip), str(clean_zip)],
            on_decision_needed=on_decision_needed
        )

        self.assertEqual(len(decisions_called), 1)
        self.assertEqual(res["installed_count"], 2)

        # Verify only Cobalt Helm was installed
        installed_file = self.mock_game_dir / "nativePC" / "pl" / "f_helm.mod"
        self.assertTrue(installed_file.exists())
        self.assertEqual(installed_file.read_text(encoding="utf-8"), "Cobalt Helm")

        # Verify clean axe was also installed
        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "axe" / "clean_axe.mod").exists())

        # Verify manifest
        manifest = ManifestManager(str(self.mock_game_dir))
        installed = manifest.get_installed_mods()
        self.assertEqual(len(installed), 2)
        cobalt_mod = next(m for m in installed if m["name"] == "Cobalt Armor Edition")
        self.assertEqual(cobalt_mod["variant"], "02_Cobalt_Armor")

    def test_batch_paused_prompt_callback_for_ambiguous_destination(self):
        """Verify batch pauses for ambiguous destination and applies custom dest from callback."""
        amb_zip = self.test_dir / "UnstructuredMod.zip"
        with zipfile.ZipFile(amb_zip, "w") as zf:
            zf.writestr("custom_subfolder/data.bin", "Binary data")

        decision_received = []
        def on_decision(bp):
            decision_received.append(bp)
            self.assertTrue(bp.get("is_ambiguous"))
            return {
                "action": "install",
                "custom_dest": "nativePC/plugins/my_mod",
                "mod_name": "Custom Dest Mod"
            }

        res = self.installer.install_batch(
            [str(amb_zip)],
            on_decision_needed=on_decision
        )

        self.assertEqual(len(decision_received), 1)
        self.assertEqual(res["installed_count"], 1)
        target = self.mock_game_dir / "nativePC" / "plugins" / "my_mod" / "data.bin"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), "Binary data")

    def test_batch_error_handling_skip_flow(self):
        """Verify corrupted archive triggers on_error and skips cleanly while installing the rest."""
        zip_good1 = self._create_clean_zip("GoodOne.zip", {
            "nativePC/wp/one.mod": "One"
        })
        corrupt_zip = self.test_dir / "Corrupt.zip"
        corrupt_zip.write_bytes(b"THIS IS NOT A VALID ZIP ARCHIVE FILE CORRUPTED BYTES")

        zip_good2 = self._create_clean_zip("GoodTwo.zip", {
            "nativePC/wp/two.mod": "Two"
        })

        error_records = []
        def on_error(path, exc):
            error_records.append((path, exc))
            return "skip"

        res = self.installer.install_batch(
            [str(zip_good1), str(corrupt_zip), str(zip_good2)],
            on_error=on_error
        )

        self.assertEqual(len(error_records), 1)
        self.assertEqual(error_records[0][0], str(corrupt_zip))
        self.assertEqual(res["installed_count"], 2)
        self.assertEqual(res["skipped_count"], 1)
        self.assertFalse(res["aborted"])

        # Check skipped records
        self.assertEqual(res["skipped_mods"][0]["archive_filename"], "Corrupt.zip")
        self.assertEqual(res["skipped_mods"][0]["action"], "skipped")

        # Verify good files are installed
        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "one.mod").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "two.mod").exists())

        # Verify manifest has 2 mods
        manifest = ManifestManager(str(self.mock_game_dir))
        installed = manifest.get_installed_mods()
        self.assertEqual(len(installed), 2)

    def test_batch_error_handling_abort_flow(self):
        """Verify on_error returning 'abort' terminates the batch queue immediately."""
        zip_good1 = self._create_clean_zip("GoodOne.zip", {
            "nativePC/wp/one.mod": "One"
        })
        corrupt_zip = self.test_dir / "Corrupt.zip"
        corrupt_zip.write_bytes(b"INVALID DATA")

        zip_good2 = self._create_clean_zip("GoodTwo.zip", {
            "nativePC/wp/two.mod": "Two"
        })

        def on_error(path, exc):
            return "abort"

        res = self.installer.install_batch(
            [str(zip_good1), str(corrupt_zip), str(zip_good2)],
            on_error=on_error
        )

        self.assertTrue(res["aborted"])
        self.assertEqual(res["installed_count"], 1)
        self.assertEqual(res["skipped_count"], 1)

        # GoodOne was installed, GoodTwo was never reached
        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "one.mod").exists())
        self.assertFalse((self.mock_game_dir / "nativePC" / "wp" / "two.mod").exists())

    def test_batch_decision_skip_and_abort(self):
        """Verify user can skip or abort during decision callback."""
        # 1. Skip during decision
        var_zip = self.test_dir / "VariantSkip.zip"
        with zipfile.ZipFile(var_zip, "w") as zf:
            zf.writestr("OptA/nativePC/a.txt", "A")
            zf.writestr("OptB/nativePC/b.txt", "B")

        clean_zip = self._create_clean_zip("CleanAfterSkip.zip", {
            "nativePC/clean.txt": "Clean"
        })

        res_skip = self.installer.install_batch(
            [str(var_zip), str(clean_zip)],
            on_decision_needed=lambda bp: {"action": "skip"}
        )
        self.assertEqual(res_skip["installed_count"], 1)
        self.assertEqual(res_skip["skipped_count"], 1)
        self.assertFalse((self.mock_game_dir / "nativePC" / "a.txt").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "clean.txt").exists())

        # 2. Abort during decision
        res_abort = self.installer.install_batch(
            [str(var_zip), str(clean_zip)],
            on_decision_needed=lambda bp: {"action": "abort"}
        )
        self.assertTrue(res_abort["aborted"])
        self.assertEqual(res_abort["installed_count"], 0)

    def test_batch_collisions_and_rollback(self):
        """Verify colliding files in batch are properly backed up and can be cleanly rolled back."""
        # 1. Base file on disk
        target_file = self.mock_game_dir / "nativePC" / "wp" / "collision.txt"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("BASE GAME TEXT", encoding="utf-8")

        # 2. Batch with 2 mods overwriting the same file sequentially
        zip1 = self._create_clean_zip("BatchModA.zip", {
            "nativePC/wp/collision.txt": "MOD A TEXT"
        })
        zip2 = self._create_clean_zip("BatchModB.zip", {
            "nativePC/wp/collision.txt": "MOD B TEXT"
        })

        res = self.installer.install_batch([str(zip1), str(zip2)])
        self.assertEqual(res["installed_count"], 2)
        self.assertEqual(res["total_files_backed_up"], 2)
        self.assertEqual(target_file.read_text(encoding="utf-8"), "MOD B TEXT")

        # Verify uninstalling Mod B restores Mod A
        manifest = ManifestManager(str(self.mock_game_dir))
        installed = manifest.get_installed_mods()
        mod_b = next(m for m in installed if m["name"] == "BatchModB")
        mod_a = next(m for m in installed if m["name"] == "BatchModA")

        uninst_b = uninstall_mod(mod_b["id"], str(self.mock_game_dir))
        self.assertTrue(uninst_b["success"])
        self.assertEqual(target_file.read_text(encoding="utf-8"), "MOD A TEXT")

        # Verify uninstalling Mod A restores original base game text
        uninst_a = uninstall_mod(mod_a["id"], str(self.mock_game_dir))
        self.assertTrue(uninst_a["success"])
        self.assertEqual(target_file.read_text(encoding="utf-8"), "BASE GAME TEXT")

    def test_empty_batch(self):
        """Verify BatchInstaller handles empty archive list cleanly."""
        res = self.installer.install_batch([])
        self.assertTrue(res["success"])
        self.assertEqual(res["total_staged"], 0)
        self.assertEqual(res["installed_count"], 0)
        self.assertEqual(res["skipped_count"], 0)
        self.assertFalse(res["aborted"])

    def test_single_item_batch(self):
        """Verify BatchInstaller works correctly with 1 item in the queue."""
        zip_single = self._create_clean_zip("SoloMod.zip", {
            "nativePC/solo.txt": "Solo content"
        })
        res = self.installer.install_batch([str(zip_single)])
        self.assertEqual(res["installed_count"], 1)
        self.assertEqual(res["skipped_count"], 0)
        self.assertTrue((self.mock_game_dir / "nativePC" / "solo.txt").exists())

    def test_nonexistent_archive_in_batch(self):
        """Verify non-existent file path in batch queue triggers error handler cleanly."""
        res = self.installer.install_batch(
            [str(self.test_dir / "does_not_exist.zip")],
            on_error=lambda path, err: "skip"
        )
        self.assertEqual(res["installed_count"], 0)
        self.assertEqual(res["skipped_count"], 1)
        self.assertEqual(res["skipped_mods"][0]["archive_filename"], "does_not_exist.zip")

    def test_batch_encrypted_archive_fails_fast_and_skips(self):
        """Verify password-protected archive fails fast with error callback without hanging."""
        # 1. Create a clean mod
        zip_good1 = self._create_clean_zip("CleanA.zip", {
            "nativePC/wp/cleana.mod": "Clean A Data"
        })

        # 2. Create password-protected encrypted 7z archive
        secret_file = self.test_dir / "secret.txt"
        secret_file.write_text("Secret Data", encoding="utf-8")
        enc_7z = self.test_dir / "PasswordProtected.7z"
        exe_7z = get_7z_binary()
        subprocess.run(
            [exe_7z, "a", "-mhe=on", "-pSecretPassword123", str(enc_7z), str(secret_file)],
            capture_output=True,
            check=True
        )

        # 3. Create another clean mod
        zip_good2 = self._create_clean_zip("CleanB.zip", {
            "nativePC/wp/cleanb.mod": "Clean B Data"
        })

        error_records = []
        def on_error(path, err):
            error_records.append((path, err))
            return "skip"

        res = self.installer.install_batch(
            [str(zip_good1), str(enc_7z), str(zip_good2)],
            on_error=on_error
        )

        # Confirm it caught the error, skipped it, and installed the other 2 mods
        self.assertEqual(len(error_records), 1)
        self.assertEqual(error_records[0][0], str(enc_7z))
        self.assertEqual(res["installed_count"], 2)
        self.assertEqual(res["skipped_count"], 1)
        self.assertEqual(res["skipped_mods"][0]["archive_filename"], "PasswordProtected.7z")
        self.assertFalse(res["aborted"])

        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "cleana.mod").exists())
        self.assertTrue((self.mock_game_dir / "nativePC" / "wp" / "cleanb.mod").exists())

    def test_batch_decision_with_string_variant_and_preserved_dest(self):
        """Verify decision callback returning raw string variant normalizes cleanly without character splitting."""
        var_zip = self.test_dir / "StringVariantMod.zip"
        with zipfile.ZipFile(var_zip, "w") as zf:
            zf.writestr("01_Alpha/nativePC/a.txt", "Alpha")
            zf.writestr("02_Beta/nativePC/b.txt", "Beta")

        res = self.installer.install_batch(
            [str(var_zip)],
            on_decision_needed=lambda bp: {
                "action": "install",
                "selected_variants": "02_Beta",
                "mod_name": "Beta String Variant"
            }
        )

        self.assertEqual(res["installed_count"], 1)
        manifest = ManifestManager(str(self.mock_game_dir))
        installed = manifest.get_installed_mods()
        mod = next(m for m in installed if m["name"] == "Beta String Variant")
        self.assertEqual(mod["variant"], "02_Beta")
        self.assertTrue((self.mock_game_dir / "nativePC" / "b.txt").exists())


if __name__ == "__main__":
    unittest.main()
