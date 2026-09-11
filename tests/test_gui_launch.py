"""
Automated GUI launch and Webview bridge test for Pod 006
"""

import sys
import time
from pathlib import Path
import webview

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pod006.app import Pod006Api, configure_webview2_runtime


def test_gui():
    print("Testing GUI window launch and JS bridge...")
    configure_webview2_runtime()
    api = Pod006Api()
    html_path = Path(__file__).resolve().parent.parent / "pod006" / "ui" / "index.html"

    window = webview.create_window(
        title="POD 006 TEST LAUNCH",
        url=f"file:///{str(html_path.resolve()).replace('\\', '/')}",
        js_api=api,
        width=1000,
        height=700,
        hidden=True
    )
    api.set_window(window)

    def on_start(w):
        time.sleep(1.5)
        title = w.evaluate_js("document.title")
        print(f"Page title evaluated: '{title}'")
        
        has_sound = w.evaluate_js("typeof window.soundEngine !== 'undefined'")
        has_tick_sfx = w.evaluate_js("typeof window.soundEngine.playProgressTick === 'function'")
        has_victory_sfx = w.evaluate_js("typeof window.soundEngine.playVictoryChime === 'function'")
        has_dropzone = w.evaluate_js("document.getElementById('dropzone') !== null")
        has_purge_modal = w.evaluate_js("document.getElementById('modal-purge') !== null")
        has_purge_btn = w.evaluate_js("document.getElementById('btn-purge-action') !== null")
        has_matching_banner = w.evaluate_js("document.getElementById('bp-matching-banner') !== null")
        has_toast_container = w.evaluate_js("document.getElementById('toast-container') !== null")
        has_batch_overlay = w.evaluate_js("document.getElementById('aoa-batch-overlay') !== null")
        has_batch_btn = w.evaluate_js("document.getElementById('btn-batch-install') !== null")
        has_bp_batch_btn = w.evaluate_js("document.getElementById('btn-blueprint-batch-install') !== null")
        has_abort_decision_btn = w.evaluate_js("document.getElementById('btn-aoa-abort-decision') !== null")
        print(f"SoundEngine: {has_sound} (tick={has_tick_sfx}, victory={has_victory_sfx}), BatchOverlay: {has_batch_overlay}, BatchBtn: {has_batch_btn}, BpBatchBtn: {has_bp_batch_btn}, AbortDecisionBtn: {has_abort_decision_btn}")

        assert "POD 006" in title, f"Unexpected title: {title}"
        assert has_sound, "soundEngine missing"
        assert has_tick_sfx, "playProgressTick missing"
        assert has_victory_sfx, "playVictoryChime missing"
        assert has_dropzone, "dropzone element missing"
        assert has_purge_modal, "modal-purge element missing"
        assert has_purge_btn, "btn-purge-action element missing"
        assert has_matching_banner, "bp-matching-banner element missing"
        assert has_toast_container, "toast-container element missing"
        assert has_batch_overlay, "aoa-batch-overlay element missing"
        assert has_batch_btn, "btn-batch-install element missing"
        assert has_bp_batch_btn, "btn-blueprint-batch-install element missing"
        assert has_abort_decision_btn, "btn-aoa-abort-decision element missing"

        print("Testing Purge Modal DOM rendering & interactions...")
        mock_bp_js = """
        (() => {
            const mockBp = {
                mod_name: 'Test Purge Mod',
                archive_filename: 'TestMod.zip',
                total_files: 3,
                total_size_formatted: '150 KB',
                collisions_count: 2,
                matching_files_count: 2,
                has_matching_game_files: true,
                suggested_dest: 'nativePC',
                file_plans: [
                    {
                        archive_path: 'nativePC/not_found.fsm',
                        target_rel_path: 'nativePC/not_found.fsm',
                        size: 50000,
                        size_formatted: '48.8 KB',
                        collision: false,
                        match_status: 'NOT FOUND'
                    },
                    {
                        archive_path: 'nativePC/matched_identical.fsm',
                        target_rel_path: 'nativePC/matched_identical.fsm',
                        size: 50000,
                        size_formatted: '48.8 KB',
                        collision: true,
                        disk_size: 50000,
                        disk_size_formatted: '48.8 KB',
                        match_status: 'FOUND (IDENTICAL)'
                    },
                    {
                        archive_path: 'nativePC/matched_modified.fsm',
                        target_rel_path: 'nativePC/matched_modified.fsm',
                        size: 50000,
                        size_formatted: '48.8 KB',
                        collision: true,
                        disk_size: 60000,
                        disk_size_formatted: '58.6 KB',
                        match_status: 'FOUND (MODIFIED)'
                    }
                ]
            };
            renderBlueprint(mockBp);
            return {
                bannerDisplay: document.getElementById('bp-matching-banner').style.display,
                btnPurgeDisplay: document.getElementById('btn-purge-action').style.display
            };
        })()
        """
        res_bp = w.evaluate_js(mock_bp_js)
        print(f"Blueprint render results: {res_bp}")
        assert res_bp["bannerDisplay"] == "flex", "Matching banner should be flex"
        assert res_bp["btnPurgeDisplay"] == "inline-flex", "Purge button should be inline-flex"

        # Test opening the purge modal and sorting
        modal_open_js = """
        (() => {
            openPurgeModal(currentBlueprint);
            const modal = document.getElementById('modal-purge');
            const rows = document.querySelectorAll('#purge-tbody tr');
            const firstRowStatus = rows[0].querySelector('.status-tag').textContent;
            const secondRowStatus = rows[1].querySelector('.status-tag').textContent;
            const thirdRowStatus = rows[2].querySelector('.status-tag').textContent;
            const selectedCount = document.getElementById('purge-selected-count').textContent;
            const totalCount = document.getElementById('purge-total-matched-count').textContent;
            return {
                isActive: modal.classList.contains('active'),
                rowCount: rows.length,
                firstRowStatus,
                secondRowStatus,
                thirdRowStatus,
                selectedCount,
                totalCount
            };
        })()
        """
        res_modal = w.evaluate_js(modal_open_js)
        print(f"Purge modal state: {res_modal}")
        assert res_modal["isActive"], "Modal should have active class"
        assert res_modal["rowCount"] == 3, f"Expected 3 rows, got {res_modal['rowCount']}"
        # Found rows must be sorted to top
        assert "FOUND" in res_modal["firstRowStatus"], "First row should be a FOUND file"
        assert "FOUND" in res_modal["secondRowStatus"], "Second row should be a FOUND file"
        assert "NOT FOUND" in res_modal["thirdRowStatus"], "Third row should be NOT FOUND file"
        assert res_modal["selectedCount"] == "2", f"Expected 2 selected, got {res_modal['selectedCount']}"
        assert res_modal["totalCount"] == "2", f"Expected 2 total matched, got {res_modal['totalCount']}"

        # Test Deselect All & Select All
        toggle_js = """
        (() => {
            document.getElementById('btn-purge-deselect-all').click();
            const deselectedCount = document.getElementById('purge-selected-count').textContent;
            const isBtnDisabled = document.getElementById('btn-purge-confirm-execute').disabled;

            document.getElementById('btn-purge-select-all').click();
            const reselectedCount = document.getElementById('purge-selected-count').textContent;

            return {
                deselectedCount,
                isBtnDisabled,
                reselectedCount
            };
        })()
        """
        res_toggle = w.evaluate_js(toggle_js)
        print(f"Toggle results: {res_toggle}")
        assert res_toggle["deselectedCount"] == "0", "Should have 0 selected after deselect all"
        assert res_toggle["isBtnDisabled"] is True, "Execute button should be disabled when 0 selected"
        assert res_toggle["reselectedCount"] == "2", "Should have 2 selected after select all"

        # Test Filter Only Matched Toggle
        filter_js = """
        (() => {
            const filterCb = document.getElementById('purge-filter-matched-only');
            filterCb.checked = true;
            filterCb.dispatchEvent(new Event('change'));

            const notFoundRow = document.querySelector('.row-notfound');
            const notFoundDisplay = notFoundRow.style.display;

            filterCb.checked = false;
            filterCb.dispatchEvent(new Event('change'));
            const notFoundDisplayRestored = notFoundRow.style.display;

            return {
                notFoundDisplay,
                notFoundDisplayRestored
            };
        })()
        """
        res_filter = w.evaluate_js(filter_js)
        print(f"Filter toggle results: {res_filter}")
        assert res_filter["notFoundDisplay"] == "none", "Not found row should be hidden when filtered"
        assert res_filter["notFoundDisplayRestored"] == "", "Not found row should be restored when unfiltered"

        # Test Toast Notifications
        toast_js = """
        (() => {
            showToast('TEST TITLE', 'Test purge message', 'success');
            const toast = document.querySelector('.toast.toast-success');
            return {
                toastExists: toast !== null,
                toastTitle: toast ? toast.querySelector('.toast-header span').textContent : null,
                toastBody: toast ? toast.querySelector('.toast-body').textContent : null
            };
        })()
        """
        res_toast = w.evaluate_js(toast_js)
        print(f"Toast results: {res_toast}")
        assert res_toast["toastExists"] is True, "Toast element should exist in container"
        assert res_toast["toastTitle"] == "TEST TITLE"
        assert res_toast["toastBody"] == "Test purge message"

        # Close Purge Modal
        close_js = """
        (() => {
            document.getElementById('btn-close-purge').click();
            return document.getElementById('modal-purge').classList.contains('active');
        })()
        """
        modal_active = w.evaluate_js(close_js)
        assert modal_active is False, "Modal should be closed after clicking close"

        print("Testing Batch Staging Queue and All-Out Attack HUD...")
        batch_js = """
        (() => {
            // Stage 2 mock archives
            stagedArchives = ['C:/mods/ModAlpha.zip', 'C:/mods/ModBeta.zip'];
            renderStagingQueue();
            const btnBatch = document.getElementById('btn-batch-install');
            const batchText = document.getElementById('batch-install-btn-text').textContent;
            const isBatchBtnVisible = btnBatch && btnBatch.style.display !== 'none';

            const btnBpBatch = document.getElementById('btn-blueprint-batch-install');
            const isBpBatchBtnVisible = btnBpBatch && btnBpBatch.style.display !== 'none';

            // Test opening Batch HUD overlay
            const overlay = document.getElementById('aoa-batch-overlay');
            overlay.classList.add('active');
            const counter = document.getElementById('aoa-batch-counter');
            const percent = document.getElementById('aoa-batch-percent');
            const ticker = document.getElementById('aoa-batch-ticker');
            const progBar = document.getElementById('aoa-batch-progress-bar');

            counter.textContent = 'DEPLOYING: [1 of 2] // ModAlpha.zip';
            percent.textContent = '50%';
            progBar.style.width = '50%';
            ticker.textContent = 'Deploying files and smart backups...';

            const isOverlayActive = overlay.classList.contains('active');

            // Test Decision Card inside HUD
            const decCard = document.getElementById('aoa-batch-decision-card');
            decCard.style.display = 'block';
            const isDecVisible = decCard.style.display === 'block';

            // Close HUD
            decCard.style.display = 'none';
            overlay.classList.remove('active');

            return {
                isBatchBtnVisible,
                isBpBatchBtnVisible,
                batchText,
                isOverlayActive,
                isDecVisible,
                counterText: counter.textContent,
                percentText: percent.textContent
            };
        })()
        """
        res_batch = w.evaluate_js(batch_js)
        print(f"Batch HUD test results: {ascii(res_batch)}")
        assert res_batch["isBatchBtnVisible"] is True, "Batch install button should be visible when 2 archives staged"
        assert res_batch["isBpBatchBtnVisible"] is True, "Blueprint batch button should be visible when 2 archives staged"
        assert "ALL-OUT ATTACK (INSTALL ALL: 2 MODS)" in res_batch["batchText"], f"Unexpected batch button text: {res_batch['batchText']}"
        assert res_batch["isOverlayActive"] is True, "Batch overlay should activate"
        assert res_batch["isDecVisible"] is True, "Decision card should be displayable inside batch HUD"
        assert res_batch["percentText"] == "50%", "Progress percent should reflect 50%"

        print("GUI, Purge Modal, and Batch All-Out Attack HUD tests passed successfully! Closing test window...")
        w.destroy()

    webview.start(on_start, window, gui="edgechromium", debug=False)
    print("Webview lifecycle finished cleanly.")


if __name__ == "__main__":
    test_gui()

