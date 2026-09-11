/**
 * POD 006 - Persona 3 Reload Tactical Mod Manager Frontend
 * Core Application Controller
 */

// State
let currentBlueprint = null;
let currentArchiveFile = null;
let stagedArchives = [];
let installedMods = [];
let pendingConfirmCallback = null;
let customDestTimeout = null;

// Audio Helper wrapper
function playSound(type) {
  if (!window.soundEngine) return;
  switch (type) {
    case 'hover': window.soundEngine.playHover(); break;
    case 'select': window.soundEngine.playSelect(); break;
    case 'confirm': window.soundEngine.playConfirm(); break;
    case 'alert': window.soundEngine.playAlert(); break;
    case 'cancel': window.soundEngine.playCancel(); break;
    case 'aoa': window.soundEngine.playAllOutAttack(); break;
    case 'tick': window.soundEngine.playProgressTick(); break;
    case 'victory': window.soundEngine.playVictoryChime(); break;
  }
}

// Log to Terminal Tab
function logMessage(text, level = 'info') {
  const terminal = document.getElementById('terminal-logs');
  if (!terminal) return;
  const line = document.createElement('div');
  line.className = `log-line ${level}`;
  const time = new Date().toLocaleTimeString();
  line.textContent = `[${time}] ${text}`;
  terminal.appendChild(line);
  terminal.scrollTop = terminal.scrollHeight;
}

// Attach hover sound to buttons
function attachButtonSounds() {
  document.querySelectorAll('button, .tab-btn, .variant-card').forEach(btn => {
    btn.removeEventListener('mouseenter', onButtonHover);
    btn.addEventListener('mouseenter', onButtonHover);
  });
}

function onButtonHover() {
  playSound('hover');
}

// Initializer
window.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  setupDropZone();
  setupAudioToggle();
  setupActionButtons();
  setupPurgeModalListeners();
  attachButtonSounds();

  // Wait for pywebview API to be ready
  window.addEventListener('pywebviewready', () => {
    logMessage('Neural link to Pod 006 engine established.', 'success');
    refreshAppStatus();
  });

  // Fallback if pywebviewready already fired or in web testing
  setTimeout(() => {
    if (window.pywebview && window.pywebview.api) {
      refreshAppStatus();
    }
  }, 400);
});

// Refresh Status from Python
async function refreshAppStatus() {
  if (!window.pywebview || !window.pywebview.api) return;

  try {
    const status = await window.pywebview.api.get_status();
    updateStatusUI(status);
  } catch (err) {
    console.error('Failed to get status:', err);
    logMessage(`Status error: ${err}`, 'danger');
  }
}

function updateStatusUI(status) {
  const pathDisplay = document.getElementById('game-path-display');
  const statusPill = document.getElementById('game-status-pill');
  const statusText = document.getElementById('game-status-text');

  if (pathDisplay) {
    pathDisplay.textContent = status.game_dir || 'Directory not configured';
  }

  if (status.game_dir_valid) {
    statusPill.style.borderColor = 'var(--cyan-core)';
    statusText.textContent = 'EVOKER READY // GAME DETECTED';
    statusText.style.color = 'var(--cyan-bright)';
  } else {
    statusPill.style.borderColor = 'var(--red-p3r)';
    statusText.textContent = 'MHW EXECUTABLE NOT FOUND';
    statusText.style.color = 'var(--red-p3r)';
  }

  installedMods = status.installed_mods || [];
  renderRoster(installedMods);

  const countBadge = document.getElementById('installed-count');
  if (countBadge) countBadge.textContent = installedMods.length;
}

// Tab Switching
function setupTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      playSound('select');
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const targetId = btn.getAttribute('data-tab');
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) targetPanel.classList.add('active');
    });
  });
}

// Audio Mute Toggle
function setupAudioToggle() {
  const btn = document.getElementById('btn-audio-toggle');
  const icon = document.getElementById('audio-icon');
  btn.addEventListener('click', () => {
    const muted = window.soundEngine.toggleMute();
    icon.textContent = muted ? '🔇 SFX OFF' : '🔊 SFX ON';
    btn.style.borderColor = muted ? 'var(--text-muted)' : 'var(--cyan-core)';
    if (!muted) playSound('select');
  });
}

// Setup Action Buttons
function setupActionButtons() {
  // Browse Game Directory
  document.getElementById('btn-browse-dir').addEventListener('click', async () => {
    playSound('select');
    if (window.pywebview && window.pywebview.api) {
      const res = await window.pywebview.api.select_game_directory();
      if (res && res.updated) {
        logMessage(`Target game directory updated: ${res.game_dir}`, 'success');
        refreshAppStatus();
      }
    }
  });

  // Open Game Directory in Explorer
  document.getElementById('btn-open-dir').addEventListener('click', () => {
    playSound('select');
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.open_game_directory();
    }
  });

  // Open Backup Directory
  document.getElementById('btn-open-backup-dir').addEventListener('click', () => {
    playSound('select');
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.open_backup_directory();
    }
  });

  // Browse Archive Files
  document.getElementById('btn-browse-archive').addEventListener('click', async (e) => {
    e.stopPropagation();
    playSound('select');
    if (window.pywebview && window.pywebview.api) {
      const paths = await window.pywebview.api.browse_archive_files();
      if (paths && paths.length > 0) {
        addArchivesToStage(paths);
      }
    }
  });

  // Staging Error Dismiss
  const dismissBtn = document.getElementById('btn-dismiss-error');
  if (dismissBtn) {
    dismissBtn.addEventListener('click', () => {
      playSound('cancel');
      hideStagingError();
    });
  }

  // Clear Staging Queue
  const clearQueueBtn = document.getElementById('btn-clear-queue');
  if (clearQueueBtn) {
    clearQueueBtn.addEventListener('click', () => {
      clearStagingQueue();
    });
  }

  // Batch All-Out Attack Buttons (Queue Header & Blueprint Action Bar)
  const batchInstallBtn = document.getElementById('btn-batch-install');
  if (batchInstallBtn) {
    batchInstallBtn.addEventListener('click', () => {
      startBatchInstall();
    });
  }

  const bpBatchInstallBtn = document.getElementById('btn-blueprint-batch-install');
  if (bpBatchInstallBtn) {
    bpBatchInstallBtn.addEventListener('click', () => {
      startBatchInstall();
    });
  }

  // Return to Base Button (Batch HUD Finish)
  const returnBaseBtn = document.getElementById('btn-aoa-return-base');
  if (returnBaseBtn) {
    returnBaseBtn.addEventListener('click', () => {
      playSound('confirm');
      const batchOverlay = document.getElementById('aoa-batch-overlay');
      if (batchOverlay) batchOverlay.classList.remove('active');
      const finishView = document.getElementById('aoa-batch-finish');
      if (finishView) finishView.style.display = 'none';

      if (stagedArchives.length === 0) {
        stagedArchives = [];
        currentArchiveFile = null;
        currentBlueprint = null;
        const bpCard = document.getElementById('blueprint-card');
        if (bpCard) bpCard.style.display = 'none';
        renderStagingQueue();
      } else {
        renderStagingQueue();
        if (stagedArchives.length > 0) {
          processSelectedArchive(stagedArchives[0]);
        }
      }

      refreshAppStatus();
      const rosterTabBtn = document.querySelector('[data-tab="tab-roster"]');
      if (rosterTabBtn) rosterTabBtn.click();
    });
  }

  // Refresh Roster
  document.getElementById('btn-refresh-roster').addEventListener('click', () => {
    playSound('select');
    refreshAppStatus();
  });

  // Clean Slate Button
  document.getElementById('btn-clean-slate').addEventListener('click', () => {
    playSound('alert');
    showConfirm(
      'EMERGENCY PURGE // CLEAN SLATE',
      'This protocol will uninstall all tracked mods and restore all backed-up original files. Proceed with emergency rollback?',
      async () => {
        playSound('select');
        if (window.pywebview && window.pywebview.api) {
          logMessage('Executing Emergency Clean Slate Protocol...', 'warning');
          const res = await window.pywebview.api.clean_slate();
          if (res.success) {
            logMessage(`Clean Slate Complete: ${res.mods_uninstalled} mods removed, ${res.total_files_restored} original files restored.`, 'success');
            playSound('confirm');
            refreshAppStatus();
          } else {
            logMessage(`Clean Slate Error: ${res.error}`, 'danger');
          }
        }
      }
    );
  });

  // Close Inspect Modal
  document.getElementById('btn-close-inspect').addEventListener('click', () => {
    playSound('cancel');
    document.getElementById('modal-inspect').classList.remove('active');
  });

  // Confirm Modal Actions
  document.getElementById('btn-confirm-cancel').addEventListener('click', () => {
    playSound('cancel');
    document.getElementById('modal-confirm').classList.remove('active');
    pendingConfirmCallback = null;
  });

  document.getElementById('btn-confirm-ok').addEventListener('click', () => {
    document.getElementById('modal-confirm').classList.remove('active');
    if (pendingConfirmCallback) {
      pendingConfirmCallback();
      pendingConfirmCallback = null;
    }
  });

  // Destination Override Change
  document.getElementById('bp-dest-override').addEventListener('change', () => {
    playSound('select');
    const val = document.getElementById('bp-dest-override').value;
    const customRow = document.getElementById('bp-custom-dest-row');
    if (val === 'custom') {
      if (customRow) customRow.style.display = 'block';
      const customInput = document.getElementById('bp-custom-dest-input');
      if (customInput) customInput.focus();
    } else {
      if (customRow) customRow.style.display = 'none';
      recomputeBlueprint();
    }
  });

  // Custom Destination Input with Debounce
  const customInput = document.getElementById('bp-custom-dest-input');
  if (customInput) {
    customInput.addEventListener('input', () => {
      clearTimeout(customDestTimeout);
      customDestTimeout = setTimeout(() => {
        recomputeBlueprint();
      }, 350);
    });
  }

  // Collision Policy Radio Change
  document.querySelectorAll('input[name="collision-policy"]').forEach(radio => {
    radio.addEventListener('change', () => {
      playSound('select');
      applyCollisionPolicyToPlans();
    });
  });

  // Execute All-Out Attack Button
  document.getElementById('btn-execute-install').addEventListener('click', () => {
    executeDeployment();
  });

  // Filter Search
  document.getElementById('roster-search').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      renderRoster(installedMods);
    } else {
      const filtered = installedMods.filter(m =>
        m.name.toLowerCase().includes(q) ||
        (m.variant && m.variant.toLowerCase().includes(q)) ||
        (m.archive_name && m.archive_name.toLowerCase().includes(q))
      );
      renderRoster(filtered);
    }
  });
}

// Drag & Drop Setup
function setupDropZone() {
  const dropzone = document.getElementById('dropzone');

  ['dragenter', 'dragover'].forEach(eventName => {
    window.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('drag-active');
    }, false);
  });

  ['dragleave', 'dragend'].forEach(eventName => {
    window.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('drag-active');
    }, false);
  });

  window.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove('drag-active');

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const paths = [];
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const filePath = file.pywebviewFullPath || file.path;
        if (filePath) {
          paths.push(filePath);
        }
      }
      if (paths.length > 0) {
        addArchivesToStage(paths);
      } else {
        logMessage('Drag-and-drop: extracting file path. If not loaded, use SELECT ARCHIVE FILES button.', 'info');
      }
    }
  }, false);

  dropzone.addEventListener('click', async () => {
    playSound('select');
    if (window.pywebview && window.pywebview.api) {
      const paths = await window.pywebview.api.browse_archive_files();
      if (paths && paths.length > 0) {
        addArchivesToStage(paths);
      }
    }
  });
}

// Called from Python if drop handled natively
window.onArchivesDropped = function(paths) {
  if (paths && paths.length > 0) {
    addArchivesToStage(paths);
  }
};

// Add Archives to Staging Queue
function addArchivesToStage(paths) {
  if (!paths || paths.length === 0) return;

  const validPaths = [];
  paths.forEach(p => {
    if (p && /\.(zip|7z|rar)$/i.test(p)) {
      if (!stagedArchives.includes(p)) {
        stagedArchives.push(p);
        validPaths.push(p);
      }
    }
  });

  if (stagedArchives.length === 0) {
    showStagingError('No compatible archive files (.zip, .7z, .rar) detected.');
    return;
  }

  renderStagingQueue();

  if (!currentArchiveFile || !stagedArchives.includes(currentArchiveFile)) {
    processSelectedArchive(stagedArchives[0]);
  } else {
    playSound('confirm');
    logMessage(`Staged ${validPaths.length} archive(s). Total in queue: ${stagedArchives.length}`, 'info');
  }

  if (stagedArchives.length >= 2) {
    showToast(
      'ALL-OUT ATTACK READY',
      `${stagedArchives.length} archives staged. Click 'ALL-OUT ATTACK (INSTALL ALL)' or click here to batch deploy!`,
      'info',
      6000,
      () => {
        startBatchInstall();
      }
    );
  }
}

function removeArchiveFromStage(pathToRemove, e) {
  if (e) e.stopPropagation();
  stagedArchives = stagedArchives.filter(p => p !== pathToRemove);
  renderStagingQueue();

  if (currentArchiveFile === pathToRemove) {
    if (stagedArchives.length > 0) {
      processSelectedArchive(stagedArchives[0]);
    } else {
      currentArchiveFile = null;
      currentBlueprint = null;
      document.getElementById('blueprint-card').style.display = 'none';
    }
  }
}

function clearStagingQueue() {
  stagedArchives = [];
  currentArchiveFile = null;
  currentBlueprint = null;
  document.getElementById('blueprint-card').style.display = 'none';
  renderStagingQueue();
  playSound('cancel');
  logMessage('Staging queue cleared.', 'info');
}

function renderStagingQueue() {
  const container = document.getElementById('staging-queue-container');
  const countSpan = document.getElementById('sq-count');
  const chipsDiv = document.getElementById('sq-chips');
  const btnBatch = document.getElementById('btn-batch-install');
  const batchText = document.getElementById('batch-install-btn-text');
  const btnBpBatch = document.getElementById('btn-blueprint-batch-install');
  const bpBatchText = document.getElementById('bp-batch-install-btn-text');

  if (!container || !chipsDiv) return;

  if (stagedArchives.length > 1) {
    container.style.display = 'block';
    if (countSpan) countSpan.textContent = stagedArchives.length;
    if (btnBatch) {
      btnBatch.style.display = 'inline-flex';
      if (batchText) batchText.textContent = `⚡ ALL-OUT ATTACK (INSTALL ALL: ${stagedArchives.length} MODS)`;
    }
    if (btnBpBatch) {
      btnBpBatch.style.display = 'inline-flex';
      if (bpBatchText) bpBatchText.textContent = `⚡ ALL-OUT ATTACK (INSTALL ALL: ${stagedArchives.length} MODS)`;
    }
    chipsDiv.innerHTML = '';

    stagedArchives.forEach((p, idx) => {
      const filename = p.split(/[\\/]/).pop();
      const isActive = p === currentArchiveFile;
      const chip = document.createElement('div');
      chip.className = `sq-chip ${isActive ? 'active' : ''}`;
      chip.title = p;
      chip.innerHTML = `
        <span>${idx + 1}. ${filename}</span>
        <button class="sq-chip-remove" title="Remove from queue">&times;</button>
      `;

      chip.addEventListener('click', (e) => {
        if (!e.target.classList.contains('sq-chip-remove')) {
          playSound('select');
          processSelectedArchive(p);
        }
      });

      chip.querySelector('.sq-chip-remove').addEventListener('click', (e) => {
        removeArchiveFromStage(p, e);
      });

      chipsDiv.appendChild(chip);
    });
  } else {
    container.style.display = 'none';
    if (btnBatch) btnBatch.style.display = 'none';
    if (btnBpBatch) btnBpBatch.style.display = 'none';
  }
}

// Batch All-Out Attack Controller
let isBatchInstalling = false;
let batchAbortRequested = false;

async function startBatchInstall() {
  if (isBatchInstalling || stagedArchives.length === 0) return;
  isBatchInstalling = true;
  batchAbortRequested = false;

  playSound('aoa');
  logMessage(`[ALL-OUT ATTACK] S.E.E.S. batch deployment initiated for ${stagedArchives.length} staged archives.`, 'warning');

  const batchOverlay = document.getElementById('aoa-batch-overlay');
  const batchActiveView = document.getElementById('aoa-batch-active');
  const batchFinishView = document.getElementById('aoa-batch-finish');
  const counterEl = document.getElementById('aoa-batch-counter');
  const percentEl = document.getElementById('aoa-batch-percent');
  const progressBar = document.getElementById('aoa-batch-progress-bar');
  const tickerEl = document.getElementById('aoa-batch-ticker');

  const decisionCard = document.getElementById('aoa-batch-decision-card');
  const errorCard = document.getElementById('aoa-batch-error-card');

  batchOverlay.classList.add('active');
  batchActiveView.style.display = 'block';
  batchFinishView.style.display = 'none';
  decisionCard.style.display = 'none';
  errorCard.style.display = 'none';

  const queue = [...stagedArchives];
  const total = queue.length;
  const installedList = [];
  const skippedList = [];
  let totalFilesWritten = 0;
  let totalBackupsCreated = 0;

  for (let i = 0; i < total; i++) {
    if (batchAbortRequested) break;

    const currentPath = queue[i];
    const currentFilename = currentPath.split(/[\\/]/).pop();
    const basePercent = Math.round((i / total) * 100);

    counterEl.textContent = `DEPLOYING: [${i + 1} of ${total}] // ${currentFilename}`;
    percentEl.textContent = `${basePercent}%`;
    progressBar.style.width = `${basePercent}%`;
    tickerEl.textContent = `Extracting archive & analyzing blueprint...`;
    playSound('tick');

    let blueprint = null;

    // 1. Inspect archive
    try {
      blueprint = await window.pywebview.api.inspect_archive(currentPath, null, 'auto');
    } catch (err) {
      console.error(`Inspection failed for ${currentFilename}:`, err);
      playSound('alert');
      tickerEl.textContent = `Inspection failure for ${currentFilename}.`;

      const errorAction = await promptBatchError(currentFilename, String(err));
      if (errorAction === 'abort') {
        batchAbortRequested = true;
        skippedList.push({
          name: currentFilename,
          path: currentPath,
          reason: `Extraction / parsing failure: ${err}`,
          action: 'Aborted'
        });
        break;
      } else {
        skippedList.push({
          name: currentFilename,
          path: currentPath,
          reason: `Extraction / parsing failure: ${err}`,
          action: 'Skipped'
        });
        stagedArchives = stagedArchives.filter(p => p !== currentPath);
        renderStagingQueue();
        continue;
      }
    }

    let modName = blueprint.mod_name || currentFilename.replace(/\.[^/.]+$/, "");
    counterEl.textContent = `DEPLOYING: [${i + 1} of ${total}] // ${modName}`;
    const inspectPercent = Math.round(((i + 0.3) / total) * 100);
    percentEl.textContent = `${inspectPercent}%`;
    progressBar.style.width = `${inspectPercent}%`;
    tickerEl.textContent = `Analyzing blueprint (${blueprint.total_files} files planned)...`;

    // 2. Determine if Clean or Tactical Decision Needed
    const hasMultipleVariants = Boolean(blueprint.has_variants && blueprint.variants && blueprint.variants.length > 1);
    const isAmbiguous = Boolean(blueprint.is_ambiguous);
    const needsDecision = hasMultipleVariants || isAmbiguous;

    let selectedVariants = blueprint.selected_variants || [];
    let customDest = blueprint.custom_dest || 'auto';

    if (needsDecision) {
      playSound('alert');
      tickerEl.textContent = `TACTICAL DECISION REQUIRED: Select variant/destination for ${modName}...`;

      const decision = await promptBatchDecision(blueprint);
      if (decision.action === 'skip') {
        skippedList.push({
          name: modName,
          path: currentPath,
          reason: 'Bypassed during tactical decision',
          action: 'Skipped'
        });
        stagedArchives = stagedArchives.filter(p => p !== currentPath);
        renderStagingQueue();
        continue;
      } else if (decision.action === 'abort') {
        batchAbortRequested = true;
        skippedList.push({
          name: modName,
          path: currentPath,
          reason: 'Aborted during tactical decision',
          action: 'Aborted'
        });
        break;
      }

      selectedVariants = decision.selectedVariants;
      customDest = decision.customDest;
      modName = decision.modName || modName;
      counterEl.textContent = `DEPLOYING: [${i + 1} of ${total}] // ${modName}`;

      // Re-inspect with user choices
      try {
        blueprint = await window.pywebview.api.inspect_archive(currentPath, selectedVariants, customDest);
      } catch (reErr) {
        console.error('Re-inspect failed:', reErr);
        const reErrAction = await promptBatchError(currentFilename, String(reErr));
        if (reErrAction === 'abort') {
          batchAbortRequested = true;
          skippedList.push({
            name: modName,
            path: currentPath,
            reason: `Re-inspection failure: ${reErr}`,
            action: 'Aborted'
          });
          break;
        } else {
          skippedList.push({
            name: modName,
            path: currentPath,
            reason: `Re-inspection failure: ${reErr}`,
            action: 'Skipped'
          });
          stagedArchives = stagedArchives.filter(p => p !== currentPath);
          renderStagingQueue();
          continue;
        }
      }
    }

    // 3. Deploy
    const deployPercent = Math.round(((i + 0.7) / total) * 100);
    percentEl.textContent = `${deployPercent}%`;
    progressBar.style.width = `${deployPercent}%`;
    if (blueprint.collisions_count > 0) {
      tickerEl.textContent = `Backing up ${blueprint.collisions_count} colliding files & copying assets...`;
    } else {
      tickerEl.textContent = `Copying ${blueprint.total_files} files to game directory...`;
    }
    playSound('tick');

    const variantLabel = (selectedVariants && selectedVariants.filter(Boolean).length > 0) ? selectedVariants.filter(Boolean).join(', ') : 'Default';

    try {
      const res = await window.pywebview.api.execute_install(
        currentPath,
        modName,
        blueprint.file_plans,
        variantLabel
      );

      totalFilesWritten += (res.files_installed || 0);
      totalBackupsCreated += (res.files_backed_up || 0);

      const donePercent = Math.round(((i + 1) / total) * 100);
      percentEl.textContent = `${donePercent}%`;
      progressBar.style.width = `${donePercent}%`;
      tickerEl.textContent = `Registered '${res.mod_name}' into manifest.`;
      playSound('tick');

      installedList.push({
        name: res.mod_name || modName,
        path: currentPath,
        files: res.files_installed || 0,
        backups: res.files_backed_up || 0,
        variant: variantLabel,
        status: 'Success'
      });

      logMessage(`[AOA DEPLOYED] '${res.mod_name}' (${res.files_installed} files, ${res.files_backed_up} backed up).`, 'success');

      // Remove from staging queue behind overlay
      stagedArchives = stagedArchives.filter(p => p !== currentPath);
      renderStagingQueue();

    } catch (installErr) {
      console.error(`Installation failed for ${modName}:`, installErr);
      playSound('alert');
      const errAction = await promptBatchError(currentFilename, String(installErr));
      if (errAction === 'abort') {
        batchAbortRequested = true;
        skippedList.push({
          name: modName,
          path: currentPath,
          reason: `Installation error: ${installErr}`,
          action: 'Aborted'
        });
        break;
      } else {
        skippedList.push({
          name: modName,
          path: currentPath,
          reason: `Installation error: ${installErr}`,
          action: 'Skipped'
        });
        stagedArchives = stagedArchives.filter(p => p !== currentPath);
        renderStagingQueue();
      }
    }
  }

  // 4. Finished
  percentEl.textContent = '100%';
  progressBar.style.width = '100%';
  tickerEl.textContent = batchAbortRequested ? 'Batch deployment suspended.' : 'All-Out Attack complete. All staged mods processed.';

  await new Promise(r => setTimeout(r, 600));

  batchActiveView.style.display = 'none';
  batchFinishView.style.display = 'flex';

  if (batchAbortRequested) {
    document.getElementById('aoa-finish-title').textContent = 'ALL-OUT ATTACK SUSPENDED';
    document.getElementById('aoa-finish-sub').textContent = 'S.E.E.S. BATCH DEPLOYMENT ABORTED BY USER';
  } else {
    document.getElementById('aoa-finish-title').textContent = 'ALL-OUT ATTACK COMPLETE';
    document.getElementById('aoa-finish-sub').textContent = 'S.E.E.S. BATCH DEPLOYMENT SUMMARY';
    playSound('victory');
  }

  document.getElementById('finish-stat-mods').textContent = installedList.length;
  document.getElementById('finish-stat-files').textContent = totalFilesWritten;
  document.getElementById('finish-stat-backups').textContent = totalBackupsCreated;
  document.getElementById('finish-stat-skipped').textContent = skippedList.length;

  const itemsListEl = document.getElementById('finish-items-list');
  itemsListEl.innerHTML = '';

  installedList.forEach(item => {
    const row = document.createElement('div');
    row.className = 'finish-item-row';
    row.innerHTML = `
      <div>
        <strong style="color: #fff;">${item.name}</strong>
        <span style="color: var(--text-muted); font-size: 12px; margin-left: 8px;">[${item.variant}] • ${item.files} files (${item.backups} backed up)</span>
      </div>
      <span class="finish-badge-tag finish-badge-success">DEPLOYED</span>
    `;
    itemsListEl.appendChild(row);
  });

  skippedList.forEach(item => {
    const row = document.createElement('div');
    row.className = 'finish-item-row';
    const badgeClass = item.action === 'Aborted' ? 'finish-badge-danger' : 'finish-badge-skipped';
    row.innerHTML = `
      <div>
        <strong style="color: #ffb3c1;">${item.name}</strong>
        <span style="color: #ffd6df; font-size: 12px; margin-left: 8px;">${item.reason}</span>
      </div>
      <span class="finish-badge-tag ${badgeClass}">${item.action.toUpperCase()}</span>
    `;
    itemsListEl.appendChild(row);
  });

  isBatchInstalling = false;
}

function promptBatchDecision(bp) {
  return new Promise(resolve => {
    const card = document.getElementById('aoa-batch-decision-card');
    const titleEl = document.getElementById('aoa-decision-mod-title');
    const variantBox = document.getElementById('aoa-decision-variant-box');
    const variantList = document.getElementById('aoa-decision-variant-list');
    const destBox = document.getElementById('aoa-decision-dest-box');
    const destSelect = document.getElementById('aoa-decision-dest-select');
    const customDestInput = document.getElementById('aoa-decision-custom-input');

    const btnSkip = document.getElementById('btn-aoa-skip-mod');
    const btnAbort = document.getElementById('btn-aoa-abort-decision');
    const btnConfirm = document.getElementById('btn-aoa-confirm-decision');

    titleEl.textContent = `TACTICAL DECISION REQUIRED: ${bp.mod_name}`;
    card.style.display = 'block';

    // Variants List
    variantList.innerHTML = '';
    let selectedVariants = bp.selected_variants || [];

    if (bp.has_variants && bp.variants && bp.variants.length > 1) {
      variantBox.style.display = 'block';
      bp.variants.forEach((v, idx) => {
        const item = document.createElement('div');
        const isChecked = selectedVariants.includes(v.id) || (selectedVariants.length === 0 && idx === 0);
        if (isChecked && !selectedVariants.includes(v.id)) {
          selectedVariants.push(v.id);
        }
        item.className = `aoa-decision-item ${isChecked ? 'selected' : ''}`;
        item.innerHTML = `
          <input type="${v.is_optional ? 'checkbox' : 'radio'}" name="aoa-var-choice" value="${v.id}" ${isChecked ? 'checked' : ''}>
          <span>${v.name} (${v.file_count} files)</span>
        `;
        item.addEventListener('click', (e) => {
          if (e.target.tagName !== 'INPUT') {
            const input = item.querySelector('input');
            if (input.type === 'radio') {
              input.checked = true;
            } else {
              input.checked = !input.checked;
            }
          }
          playSound('select');
          document.querySelectorAll('.aoa-decision-item').forEach(el => {
            const cb = el.querySelector('input');
            el.classList.toggle('selected', cb.checked);
          });
        });
        variantList.appendChild(item);
      });
    } else {
      variantBox.style.display = 'none';
    }

    // Destination Box
    if (bp.is_ambiguous) {
      destBox.style.display = 'block';
      destSelect.value = 'nativePC';
      customDestInput.style.display = 'none';
    } else {
      destBox.style.display = 'none';
    }

    destSelect.onchange = () => {
      playSound('select');
      customDestInput.style.display = destSelect.value === 'custom' ? 'block' : 'none';
      if (destSelect.value === 'custom') customDestInput.focus();
    };

    function cleanup() {
      btnSkip.onclick = null;
      if (btnAbort) btnAbort.onclick = null;
      btnConfirm.onclick = null;
      destSelect.onchange = null;
      card.style.display = 'none';
    }

    btnSkip.onclick = () => {
      playSound('cancel');
      cleanup();
      resolve({ action: 'skip' });
    };

    if (btnAbort) {
      btnAbort.onclick = () => {
        playSound('alert');
        cleanup();
        resolve({ action: 'abort' });
      };
    }

    btnConfirm.onclick = () => {
      playSound('confirm');
      const chosenVars = [];
      document.querySelectorAll('#aoa-decision-variant-list input:checked').forEach(input => {
        chosenVars.push(input.value);
      });

      let chosenDest = 'auto';
      if (bp.is_ambiguous) {
        chosenDest = destSelect.value === 'custom' ? (customDestInput.value.trim() || 'nativePC') : destSelect.value;
      }

      cleanup();
      resolve({
        action: 'install',
        selectedVariants: chosenVars.length > 0 ? chosenVars : (bp.selected_variants || []),
        customDest: chosenDest,
        modName: bp.mod_name
      });
    };
  });
}

function promptBatchError(archiveName, errorMsg) {
  return new Promise(resolve => {
    const errorCard = document.getElementById('aoa-batch-error-card');
    const titleEl = document.getElementById('aoa-error-archive-title');
    const detailsEl = document.getElementById('aoa-error-details');
    const btnSkip = document.getElementById('btn-aoa-error-skip');
    const btnAbort = document.getElementById('btn-aoa-error-abort');

    titleEl.textContent = `ARCHIVE ERROR: ${archiveName}`;
    detailsEl.textContent = errorMsg;
    errorCard.style.display = 'block';

    function cleanup() {
      btnSkip.onclick = null;
      btnAbort.onclick = null;
      errorCard.style.display = 'none';
    }

    btnSkip.onclick = () => {
      playSound('confirm');
      cleanup();
      resolve('skip');
    };

    btnAbort.onclick = () => {
      playSound('alert');
      cleanup();
      resolve('abort');
    };
  });
}

function showStagingError(msg) {
  const banner = document.getElementById('staging-error-banner');
  const txt = document.getElementById('staging-error-text');
  if (banner && txt) {
    txt.textContent = msg;
    banner.style.display = 'flex';
    playSound('alert');
  }
}

function hideStagingError() {
  const banner = document.getElementById('staging-error-banner');
  if (banner) banner.style.display = 'none';
}

// Process Chosen Archive
async function processSelectedArchive(filePath) {
  if (!filePath) return;
  hideStagingError();
  playSound('confirm');
  logMessage(`Scanning tactical blueprint for: ${filePath}`, 'info');

  currentArchiveFile = filePath;
  renderStagingQueue();

  try {
    const blueprint = await window.pywebview.api.inspect_archive(filePath, null, 'auto');
    renderBlueprint(blueprint);
  } catch (err) {
    console.error('Failed to analyze archive:', err);
    logMessage(`Archive analysis failed: ${err}`, 'danger');
    showStagingError(`Archive inspection failed: ${err}`);
  }
}

// Render Pre-Install Blueprint
function renderBlueprint(bp) {
  currentBlueprint = bp;
  const card = document.getElementById('blueprint-card');
  card.style.display = 'flex';

  document.getElementById('bp-mod-title').textContent = 'ALL-OUT ATTACK BLUEPRINT';
  document.getElementById('bp-archive-label').textContent = `ARCHIVE: ${bp.archive_filename}`;
  document.getElementById('bp-stat-files').textContent = `${bp.total_files} FILES`;
  document.getElementById('bp-stat-size').textContent = bp.total_size_formatted;
  document.getElementById('bp-mod-name-input').value = bp.mod_name;

  // Ambiguous banner
  const ambBanner = document.getElementById('bp-ambiguous-banner');
  if (ambBanner) {
    ambBanner.style.display = bp.is_ambiguous ? 'flex' : 'none';
    if (bp.is_ambiguous) {
      playSound('alert');
    }
  }

  // Variants Section
  const variantSection = document.getElementById('bp-variant-section');
  const variantContainer = document.getElementById('bp-variant-container');
  variantContainer.innerHTML = '';

  if (bp.has_variants && bp.variants.length > 0) {
    variantSection.style.display = 'block';
    bp.variants.forEach(v => {
      const isSelected = bp.selected_variants.includes(v.id);
      const div = document.createElement('div');
      div.className = `variant-card ${isSelected ? 'selected' : ''}`;
      div.innerHTML = `
        <input type="${v.is_optional ? 'checkbox' : 'radio'}" name="variant-choice" value="${v.id}" ${isSelected ? 'checked' : ''}>
        <div class="variant-info">
          <div class="variant-name">${v.name}</div>
          <div class="variant-meta">${v.file_count} files (${v.total_size_formatted}) ${v.is_optional ? '• OPTIONAL' : ''}</div>
        </div>
      `;

      div.addEventListener('click', (e) => {
        if (e.target.tagName !== 'INPUT') {
          const input = div.querySelector('input');
          if (input.type === 'radio') {
            input.checked = true;
          } else {
            input.checked = !input.checked;
          }
        }
        playSound('select');
        onVariantSelectionChanged();
      });

      variantContainer.appendChild(div);
    });
    attachButtonSounds();
  } else {
    variantSection.style.display = 'none';
  }

  // Destination override dropdown & custom input
  const destSelect = document.getElementById('bp-dest-override');
  const customRow = document.getElementById('bp-custom-dest-row');
  const customInput = document.getElementById('bp-custom-dest-input');

  const standardDests = ['auto', 'nativePC', 'plugins', 'root', 'Lua'];
  if (bp.custom_dest && !standardDests.includes(bp.custom_dest)) {
    destSelect.value = 'custom';
    if (customRow) customRow.style.display = 'block';
    if (customInput) customInput.value = bp.custom_dest;
  } else if (bp.custom_dest && bp.custom_dest !== 'auto') {
    destSelect.value = bp.custom_dest;
    if (customRow) customRow.style.display = 'none';
  } else {
    if (bp.suggested_dest === 'root') {
      destSelect.value = 'root';
    } else if (bp.suggested_dest === 'Lua') {
      destSelect.value = 'Lua';
    } else {
      destSelect.value = 'auto';
    }
    if (customRow) customRow.style.display = 'none';
  }

  // Collisions Box
  const collisionBox = document.getElementById('bp-collision-box');
  const collisionCount = document.getElementById('bp-collision-count');
  if (bp.collisions_count > 0) {
    collisionBox.style.display = 'block';
    collisionCount.textContent = bp.collisions_count;
    playSound('alert');
  } else {
    collisionBox.style.display = 'none';
  }

  // Matching Game Files Banner & Purge Action Button
  const matchingBanner = document.getElementById('bp-matching-banner');
  const matchingText = document.getElementById('bp-matching-banner-text');
  const btnPurge = document.getElementById('btn-purge-action');
  const matchedCount = bp.matching_files_count !== undefined ? bp.matching_files_count : bp.collisions_count;

  if (matchedCount > 0) {
    if (matchingBanner && matchingText) {
      matchingBanner.style.display = 'flex';
      matchingText.textContent = `${matchedCount} of ${bp.total_files} files found in game directory (Installed Manually or Previously).`;
    }
    if (btnPurge) {
      btnPurge.style.display = 'inline-flex';
    }
  } else {
    if (matchingBanner) matchingBanner.style.display = 'none';
    if (btnPurge) btnPurge.style.display = 'none';
  }

  // Planned Files Table
  renderFilesTable(bp.file_plans);

  // Scroll blueprint into view smoothly
  card.scrollIntoView({ behavior: 'smooth' });
}

function onVariantSelectionChanged() {
  const selected = [];
  document.querySelectorAll('#bp-variant-container input:checked').forEach(input => {
    selected.push(input.value);
  });
  recomputeBlueprint(selected);
}

async function recomputeBlueprint(overrideVariants = null) {
  if (!currentArchiveFile || !window.pywebview) return;
  let destOverride = document.getElementById('bp-dest-override').value;
  if (destOverride === 'custom') {
    destOverride = (document.getElementById('bp-custom-dest-input').value.trim()) || 'nativePC';
  }
  const selectedVariants = overrideVariants !== null ? overrideVariants : (currentBlueprint ? currentBlueprint.selected_variants : null);

  try {
    const bp = await window.pywebview.api.inspect_archive(currentArchiveFile, selectedVariants, destOverride);
    renderBlueprint(bp);
    applyCollisionPolicyToPlans();
  } catch (err) {
    console.error('Recompute blueprint failed:', err);
  }
}

function applyCollisionPolicyToPlans() {
  if (!currentBlueprint) return;
  const policy = document.querySelector('input[name="collision-policy"]:checked').value;
  currentBlueprint.file_plans.forEach(plan => {
    if (plan.collision) {
      plan.action = policy; // 'overwrite_backup' or 'skip'
    }
  });
  renderFilesTable(currentBlueprint.file_plans);
}

function renderFilesTable(filePlans) {
  const tbody = document.getElementById('bp-file-table-body');
  document.getElementById('bp-preview-count').textContent = filePlans.length;
  tbody.innerHTML = '';

  filePlans.forEach(plan => {
    const tr = document.createElement('tr');

    let statusHtml = '<span style="color: #38ef7d;">NEW FILE</span>';
    if (plan.collision) {
      const actionBadge = plan.action === 'skip' ? '<span style="color:#aaa;">[SKIPPED]</span>' : '<span style="color:var(--cyan-bright);">[BACKUP & REPLACE]</span>';
      statusHtml = `<span class="collision-tag">⚠️ COLLISION (${plan.existing_owner || 'Base Game'})</span> ${actionBadge}`;
    }

    tr.innerHTML = `
      <td style="max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${plan.archive_path}">${plan.archive_path}</td>
      <td style="max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #fff;" title="${plan.target_rel_path}">${plan.target_rel_path}</td>
      <td>${plan.size_formatted}</td>
      <td>${statusHtml}</td>
    `;
    tbody.appendChild(tr);
  });
}

// Execute All-Out Attack
async function executeDeployment() {
  if (!currentBlueprint || !currentArchiveFile) return;

  const modName = document.getElementById('bp-mod-name-input').value.trim() || currentBlueprint.mod_name;
  const variantName = (currentBlueprint.selected_variants && currentBlueprint.selected_variants.length > 0)
    ? currentBlueprint.selected_variants.join(', ')
    : 'Default';

  // Trigger Persona 3 Reload All-Out Attack Cinematic
  const overlay = document.getElementById('aoa-overlay');
  const progressBar = document.getElementById('aoa-progress-bar');
  const statusText = document.getElementById('aoa-status-text');

  overlay.classList.add('active');
  progressBar.style.width = '15%';
  statusText.textContent = 'DEPLOYING ASSETS & SMART BACKUP...';
  playSound('aoa');

  setTimeout(() => { progressBar.style.width = '55%'; }, 250);

  try {
    const res = await window.pywebview.api.execute_install(
      currentArchiveFile,
      modName,
      currentBlueprint.file_plans,
      variantName
    );

    progressBar.style.width = '100%';
    statusText.textContent = 'MISSION COMPLETE // ASSETS DEPLOYED';

    setTimeout(() => {
      overlay.classList.remove('active');
      logMessage(`[AOA SUCCESS] '${res.mod_name}' deployed successfully! ${res.files_installed} files written, ${res.files_backed_up} files backed up.`, 'success');
      playSound('confirm');

      // Remove deployed archive from queue
      stagedArchives = stagedArchives.filter(p => p !== currentArchiveFile);
      renderStagingQueue();

      if (stagedArchives.length > 0) {
        // Automatically stage and inspect the next archive!
        logMessage(`Advancing to next staged archive (${stagedArchives.length} remaining)...`, 'info');
        processSelectedArchive(stagedArchives[0]);
      } else {
        // Clear blueprint card
        document.getElementById('blueprint-card').style.display = 'none';
        currentBlueprint = null;
        currentArchiveFile = null;

        // Refresh app and switch to Roster tab
        refreshAppStatus();
        document.querySelector('[data-tab="tab-roster"]').click();
      }
    }, 700);

  } catch (err) {
    overlay.classList.remove('active');
    console.error('All-Out Attack deployment failed:', err);
    logMessage(`Deployment failed: ${err}`, 'danger');
    playSound('alert');
  }
}

// Render Installed Roster Cards
function renderRoster(mods) {
  const grid = document.getElementById('roster-grid');
  const emptyState = document.getElementById('roster-empty');

  grid.innerHTML = '';

  if (!mods || mods.length === 0) {
    emptyState.style.display = 'flex';
    return;
  }
  emptyState.style.display = 'none';

  mods.forEach(mod => {
    const card = document.createElement('div');
    card.className = 'mod-card';
    card.innerHTML = `
      <div>
        <div class="mod-card-title">${mod.name}</div>
        <div class="mod-card-meta">
          <div>EDITION: <span>${mod.variant || 'Standard'}</span></div>
          <div>FILES: <span>${mod.file_count} (${mod.total_size_formatted})</span></div>
          <div>DEPLOYED: <span>${mod.install_date || 'Unknown'}</span></div>
          <div style="font-size: 11px; opacity: 0.8; margin-top: 4px;">ARCHIVE: ${mod.archive_name}</div>
        </div>
      </div>
      <div class="mod-card-actions">
        <button class="btn-slanted btn-small btn-inspect" data-id="${mod.id}">
          <span>INSPECT FILES</span>
        </button>
        <button class="btn-slanted btn-small btn-danger btn-uninstall" data-id="${mod.id}" data-name="${mod.name}">
          <span>WITHDRAW / UNINSTALL</span>
        </button>
      </div>
    `;

    card.querySelector('.btn-inspect').addEventListener('click', () => {
      playSound('select');
      openInspectModal(mod);
    });

    card.querySelector('.btn-uninstall').addEventListener('click', () => {
      playSound('alert');
      showConfirm(
        'WITHDRAWAL PROTOCOL',
        `Initiate withdrawal for mod "${mod.name}"? Overwritten previous versions will be automatically restored to the game directory.`,
        async () => {
          playSound('select');
          logMessage(`Withdrawing mod: ${mod.name}...`, 'info');
          const res = await window.pywebview.api.uninstall_mod(mod.id);
          if (res.success) {
            logMessage(`Mod '${res.mod_name}' uninstalled. ${res.files_restored} original files restored, ${res.files_removed} files removed.`, 'success');
            playSound('confirm');
            refreshAppStatus();
          } else {
            logMessage(`Uninstall error: ${res.error}`, 'danger');
          }
        }
      );
    });

    grid.appendChild(card);
  });

  attachButtonSounds();
}

// Inspect Modal
function openInspectModal(mod) {
  const modal = document.getElementById('modal-inspect');
  document.getElementById('inspect-title').textContent = `ASSETS // ${mod.name}`;
  const tbody = document.getElementById('inspect-tbody');
  tbody.innerHTML = '';

  (mod.files || []).forEach(f => {
    const tr = document.createElement('tr');
    const backupText = f.backed_up
      ? `<span style="color:var(--cyan-bright);">RESTORES PREVIOUS (${f.previous_owner || 'Game'})</span>`
      : '<span style="color:#888;">Fresh Addition</span>';
    const szText = f.size ? `${(f.size / 1024).toFixed(1)} KB` : '-';

    tr.innerHTML = `
      <td style="color:#fff;">${f.target_rel_path}</td>
      <td>${szText}</td>
      <td>${backupText}</td>
    `;
    tbody.appendChild(tr);
  });

  modal.classList.add('active');
}

// Generic Confirm Modal
function showConfirm(title, message, onOk) {
  document.getElementById('confirm-title').textContent = title;
  document.getElementById('confirm-message').textContent = message;
  pendingConfirmCallback = onOk;
  document.getElementById('modal-confirm').classList.add('active');
}

// Purge Review Modal Logic
function openPurgeModal(bp) {
  if (!bp || !bp.file_plans) return;
  playSound('alert');

  const modal = document.getElementById('modal-purge');
  const title = document.getElementById('purge-modal-title');
  const subtitle = document.getElementById('purge-modal-subtitle');
  const tbody = document.getElementById('purge-tbody');
  const filterMatchedOnly = document.getElementById('purge-filter-matched-only');

  title.textContent = 'TARGET PURGE PROTOCOL';
  subtitle.textContent = `ARCHIVE: ${bp.archive_filename || 'Target Mod'}`;
  tbody.innerHTML = '';

  // Sort file plans so that matched/found files appear at the top, sorted by path
  const sortedPlans = [...bp.file_plans].sort((a, b) => {
    const aFound = Boolean(a.collision);
    const bFound = Boolean(b.collision);
    if (aFound && !bFound) return -1;
    if (!aFound && bFound) return 1;
    return (a.target_rel_path || '').localeCompare(b.target_rel_path || '');
  });

  sortedPlans.forEach(plan => {
    const isFound = Boolean(plan.collision);
    const matchStatus = plan.match_status || (isFound ? 'FOUND (IDENTICAL)' : 'NOT FOUND');
    let statusClass = 'status-notfound';
    if (matchStatus.includes('IDENTICAL')) {
      statusClass = 'status-identical';
    } else if (matchStatus.includes('MODIFIED')) {
      statusClass = 'status-modified';
    }

    const tr = document.createElement('tr');
    tr.className = isFound ? 'row-matched' : 'row-notfound';
    tr.style.cursor = isFound ? 'pointer' : 'default';

    const diskSizeStr = plan.disk_size_formatted || (plan.disk_size ? `${(plan.disk_size / 1024).toFixed(1)} KB` : '-');

    tr.innerHTML = `
      <td style="text-align: center;">
        <input type="checkbox" class="purge-file-checkbox" data-path="${plan.target_rel_path}" data-size="${plan.disk_size || plan.size || 0}" ${isFound ? 'checked' : 'disabled'}>
      </td>
      <td style="max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #fff;" title="${plan.target_rel_path}">
        ${plan.target_rel_path}
      </td>
      <td>${plan.size_formatted || '-'}</td>
      <td style="color: ${isFound ? '#fff' : '#777'};">${diskSizeStr}</td>
      <td><span class="status-tag ${statusClass}">${matchStatus}</span></td>
    `;

    // Clicking on row toggles checkbox if enabled
    tr.addEventListener('click', (e) => {
      if (e.target.tagName !== 'INPUT' && isFound) {
        const cb = tr.querySelector('.purge-file-checkbox');
        if (cb && !cb.disabled) {
          cb.checked = !cb.checked;
          playSound('select');
          updatePurgeCounter();
        }
      }
    });

    const cb = tr.querySelector('.purge-file-checkbox');
    if (cb) {
      cb.addEventListener('change', () => {
        playSound('select');
        updatePurgeCounter();
      });
    }

    tbody.appendChild(tr);
  });

  // Apply filter state if filter toggle is checked
  if (filterMatchedOnly && filterMatchedOnly.checked) {
    document.querySelectorAll('.row-notfound').forEach(row => row.style.display = 'none');
  }

  updatePurgeCounter();
  modal.classList.add('active');
  attachButtonSounds();
}

function updatePurgeCounter() {
  const allEnabledCheckboxes = document.querySelectorAll('.purge-file-checkbox:not(:disabled)');
  const checkedBoxes = document.querySelectorAll('.purge-file-checkbox:checked');
  const countSpan = document.getElementById('purge-selected-count');
  const totalMatchedSpan = document.getElementById('purge-total-matched-count');
  const sizeSpan = document.getElementById('purge-selected-size');
  const btnExecute = document.getElementById('btn-purge-confirm-execute');

  const totalMatched = allEnabledCheckboxes.length;
  const count = checkedBoxes.length;

  let totalBytes = 0;
  checkedBoxes.forEach(cb => {
    totalBytes += parseInt(cb.getAttribute('data-size') || '0', 10);
  });

  if (countSpan) countSpan.textContent = count;
  if (totalMatchedSpan) totalMatchedSpan.textContent = totalMatched;
  if (sizeSpan) {
    if (totalBytes < 1024) sizeSpan.textContent = `${totalBytes} B`;
    else if (totalBytes < 1024 * 1024) sizeSpan.textContent = `${(totalBytes / 1024).toFixed(1)} KB`;
    else sizeSpan.textContent = `${(totalBytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  if (btnExecute) {
    btnExecute.disabled = count === 0;
    btnExecute.style.opacity = count === 0 ? '0.4' : '1';
    btnExecute.style.pointerEvents = count === 0 ? 'none' : 'auto';
  }
}

function setupPurgeModalListeners() {
  // Purge Action Button on Blueprint Card
  const btnPurge = document.getElementById('btn-purge-action');
  if (btnPurge) {
    btnPurge.addEventListener('click', () => {
      openPurgeModal(currentBlueprint);
    });
  }

  // Filter Matched Only toggle
  const filterMatchedOnly = document.getElementById('purge-filter-matched-only');
  if (filterMatchedOnly) {
    filterMatchedOnly.addEventListener('change', () => {
      playSound('select');
      const hideUnmatched = filterMatchedOnly.checked;
      document.querySelectorAll('.row-notfound').forEach(row => {
        row.style.display = hideUnmatched ? 'none' : '';
      });
    });
  }

  // Select All button
  const btnSelectAll = document.getElementById('btn-purge-select-all');
  if (btnSelectAll) {
    btnSelectAll.addEventListener('click', () => {
      playSound('select');
      document.querySelectorAll('.purge-file-checkbox:not(:disabled)').forEach(cb => {
        cb.checked = true;
      });
      updatePurgeCounter();
    });
  }

  // Deselect All button
  const btnDeselectAll = document.getElementById('btn-purge-deselect-all');
  if (btnDeselectAll) {
    btnDeselectAll.addEventListener('click', () => {
      playSound('select');
      document.querySelectorAll('.purge-file-checkbox:not(:disabled)').forEach(cb => {
        cb.checked = false;
      });
      updatePurgeCounter();
    });
  }

  // Close / Abort Purge Modal buttons
  const closeBtn = document.getElementById('btn-close-purge');
  const cancelBtn = document.getElementById('btn-purge-cancel-action');
  [closeBtn, cancelBtn].forEach(btn => {
    if (btn) {
      btn.addEventListener('click', () => {
        playSound('cancel');
        document.getElementById('modal-purge').classList.remove('active');
      });
    }
  });

  // Execute Purge button
  const btnConfirmExecute = document.getElementById('btn-purge-confirm-execute');
  if (btnConfirmExecute) {
    btnConfirmExecute.addEventListener('click', async () => {
      if (!currentArchiveFile || !window.pywebview || !window.pywebview.api) return;

      const checked = document.querySelectorAll('.purge-file-checkbox:checked');
      const selectedPaths = Array.from(checked).map(cb => cb.getAttribute('data-path')).filter(Boolean);

      if (selectedPaths.length === 0) {
        playSound('alert');
        return;
      }

      const origText = btnConfirmExecute.innerHTML;
      btnConfirmExecute.disabled = true;
      btnConfirmExecute.innerHTML = '<span>PURGING TARGET ASSETS...</span>';
      playSound('alert');

      try {
        const variantName = (currentBlueprint && currentBlueprint.selected_variants && currentBlueprint.selected_variants.length > 0)
          ? currentBlueprint.selected_variants.join(', ')
          : 'Default';

        const res = await window.pywebview.api.purge_matching_files(
          currentArchiveFile,
          selectedPaths,
          variantName
        );

        document.getElementById('modal-purge').classList.remove('active');
        btnConfirmExecute.disabled = false;
        btnConfirmExecute.innerHTML = origText;

        if (res && res.success) {
          playSound('confirm');
          const prunedCount = res.cleaned_dirs ? res.cleaned_dirs.length : 0;
          logMessage(`[MANUAL PURGE] Successfully purged ${res.purged_count} file(s) and pruned ${prunedCount} empty directory(ies). Safety backup saved to: ${res.backup_dir}`, 'success');
          showToast('PURGE COMPLETE', `Removed ${res.purged_count} file(s) from game folder. Pruned ${prunedCount} empty folder(s). Safety backup saved.`, 'success');

          if (res.failed_files && res.failed_files.length > 0) {
            logMessage(`[PURGE WARNING] ${res.failed_files.length} file(s) could not be removed (in use or locked).`, 'warning');
            showToast('PURGE WARNING', `${res.failed_files.length} file(s) could not be removed (in use).`, 'warning');
          }

          // Recompute blueprint to refresh collision state immediately
          await recomputeBlueprint();
          await refreshAppStatus();
        } else {
          playSound('alert');
          const err = (res && res.error) ? res.error : 'Unknown error during purge.';
          logMessage(`[PURGE ERROR] ${err}`, 'danger');
          showToast('PURGE FAILED', err, 'danger');
        }
      } catch (err) {
        btnConfirmExecute.disabled = false;
        btnConfirmExecute.innerHTML = origText;
        playSound('alert');
        console.error('Purge execution failed:', err);
        logMessage(`Purge execution failed: ${err}`, 'danger');
        showToast('PURGE ERROR', `${err}`, 'danger');
      }
    });
  }
}

// Toast notification helper
function showToast(title, message, type = 'info', durationMs = 4500, onClick = null) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  if (onClick) {
    toast.style.cursor = 'pointer';
    toast.title = 'Click to activate';
  }
  toast.innerHTML = `
    <div class="toast-inner">
      <div class="toast-header">
        <span>${title}</span>
      </div>
      <div class="toast-body">${message}</div>
    </div>
  `;

  if (onClick) {
    toast.addEventListener('click', () => {
      onClick();
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    });
  }

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'skewX(var(--skew-angle)) translateX(40px)';
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 350);
  }, durationMs);
}

