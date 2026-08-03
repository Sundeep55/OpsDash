import { getJSON, postJSON } from '../lib/api.js';

const { ref } = Vue;

const STATUS_URL = '/api/v2/sync/status/';
const TRIGGER_URL = '/api/v2/sync/';

// How often to ask whether the sidecar has resynced behind our back.
const WATCH_INTERVAL_MS = 5000;
// Faster cadence while a sync this tab started is still running.
const ACTIVE_INTERVAL_MS = 2000;

/**
 * Sync status polling and manual trigger.
 *
 * Two loops with different jobs: a slow one that notices the polling sidecar
 * resyncing and refreshes the screen, and a fast one that tracks a sync this
 * tab started until it finishes.
 *
 * `onDataChanged` fires when last_sync_time moves -- never on the first poll,
 * which only establishes the baseline, or every page load would refetch
 * everything a second time.
 */
export function useSync({ onDataChanged, onSessionExpired }) {
    const isSyncing = ref(false);
    const statusMessage = ref('Ready');
    const lastSyncTime = ref(null);

    let watchTimer = null;
    let activeTimer = null;
    let baselineEstablished = false;

    const check = async ({ tracking = false } = {}) => {
        let status;
        try {
            status = await getJSON(STATUS_URL);
        } catch (error) {
            if (error.name === 'SessionExpired') {
                stop();
                if (onSessionExpired) onSessionExpired();
                return;
            }
            isSyncing.value = false;
            statusMessage.value = 'Status offline';
            if (tracking) stopTracking();
            return;
        }

        isSyncing.value = status.is_syncing;
        statusMessage.value = status.last_message || 'Ready';

        if (status.last_sync_time && status.last_sync_time !== lastSyncTime.value) {
            const isFirstPoll = !baselineEstablished;
            lastSyncTime.value = status.last_sync_time;
            baselineEstablished = true;

            if (!isFirstPoll && onDataChanged) {
                statusMessage.value = 'Refreshing…';
                await onDataChanged();
                statusMessage.value = 'Ready';
            }
        } else {
            baselineEstablished = true;
        }

        if (tracking && !status.is_syncing) stopTracking();
    };

    const stopTracking = () => {
        clearInterval(activeTimer);
        activeTimer = null;
    };

    const trigger = async () => {
        if (isSyncing.value) return;
        isSyncing.value = true;
        statusMessage.value = 'Triggering sync…';
        try {
            await postJSON(TRIGGER_URL);
            if (!activeTimer) {
                activeTimer = setInterval(() => check({ tracking: true }), ACTIVE_INTERVAL_MS);
            }
        } catch (error) {
            isSyncing.value = false;
            // 409 means someone else's sync is already running -- not an error
            // for this user, and its progress shows up on the next poll.
            statusMessage.value = String(error.message).includes('409')
                ? 'A sync is already running'
                : 'Sync failed to start';
        }
    };

    const start = () => {
        check();
        watchTimer = setInterval(() => check(), WATCH_INTERVAL_MS);
    };

    const stop = () => {
        clearInterval(watchTimer);
        stopTracking();
        watchTimer = null;
    };

    return { isSyncing, statusMessage, lastSyncTime, trigger, start, stop };
}
