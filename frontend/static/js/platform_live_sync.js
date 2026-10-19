/**
 * DirectHarvest AI - Real-time Platform State & Feature Synchronizer
 * Automatically synchronizes admin configuration changes (AI status, feature toggles, etc.)
 * across all active consumer, farmer, delivery, and public panels without manual refresh.
 */
(function() {
    if (window.__platformSyncLoaded) return;
    window.__platformSyncLoaded = true;

    let currentVersion = null;
    let currentAiStatus = null;

    function updatePills(aiStatus) {
        currentAiStatus = aiStatus;
        const isConnected = (aiStatus === 'connected');

        // Update all navbar & sidebar pills
        const pills = document.querySelectorAll('#global-ai-status-pill, .sidebar-ai-status-pill');
        pills.forEach(pill => {
            if (isConnected) {
                pill.classList.remove('text-danger');
                pill.classList.add('text-success');
            } else {
                pill.classList.remove('text-success');
                pill.classList.add('text-danger');
            }
        });

        const dots = document.querySelectorAll('#global-ai-status-dot, .sidebar-ai-status-dot');
        dots.forEach(dot => {
            if (isConnected) {
                dot.style.backgroundColor = '#28a745';
                dot.style.boxShadow = '0 0 6px rgba(40,167,69,0.8)';
            } else {
                dot.style.backgroundColor = '#dc3545';
                dot.style.boxShadow = '0 0 6px rgba(220,53,69,0.8)';
            }
        });

        const texts = document.querySelectorAll('#global-ai-status-text, .sidebar-ai-status-text');
        texts.forEach(txt => {
            txt.textContent = isConnected ? 'AI Connected' : 'AI Disconnected';
        });
    }

    async function checkPlatformSync() {
        try {
            const resp = await fetch('/api/platform/sync-state', {
                headers: { 'Accept': 'application/json' },
                cache: 'no-store'
            });
            if (!resp.ok) return;
            const data = await resp.json();

            // First run: record initial values
            if (currentVersion === null) {
                currentVersion = data.version;
                currentAiStatus = data.ai_status;
                updatePills(data.ai_status);
                return;
            }

            const statusChanged = (data.ai_status !== currentAiStatus);
            const versionChanged = (data.version !== currentVersion);

            if (statusChanged || versionChanged) {
                updatePills(data.ai_status);
                currentVersion = data.version;
                currentAiStatus = data.ai_status;

                // Don't interrupt user typing in input fields
                const activeEl = document.activeElement;
                const isUserTyping = activeEl && (
                    activeEl.tagName === 'INPUT' || 
                    activeEl.tagName === 'TEXTAREA' || 
                    activeEl.isContentEditable
                );

                if (!isUserTyping) {
                    console.log("[DirectHarvest Sync] Platform configuration changed by admin. Synchronizing view...");
                    setTimeout(() => {
                        window.location.reload();
                    }, 250);
                }
            }
        } catch (err) {
            // Silent retry on next poll tick
        }
    }

    // Start background sync poll every 1.5 seconds
    setInterval(checkPlatformSync, 1500);

    // Initial trigger
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkPlatformSync);
    } else {
        checkPlatformSync();
    }
})();
