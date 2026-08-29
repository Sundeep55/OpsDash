/**
 * Pipeline triggering: availability, the schema, and the request itself.
 *
 * The dashboard is read-only everywhere else, so this composable is deliberately
 * conservative about announcing itself. It asks once, on mount, whether
 * triggering is configured and permitted; until that answers yes, no trigger
 * control renders anywhere. A dashboard pointed at an estate with no pipeline
 * configured looks exactly as it did before this feature existed.
 *
 * The schema and the tenant index are fetched lazily, the first time a form is
 * opened. Both are round trips to GitLab or the database that most page loads
 * would never use, and paying for them on every load to save a few hundred
 * milliseconds on the rare one is the wrong trade.
 */
import { getJSON, postJSON } from '../lib/api.js';

const { ref, computed } = Vue;

const CONFIG_URL = '/api/v2/pipeline/config/';
const SCHEMA_URL = '/api/v2/pipeline/schema/';
const INDEX_URL = '/api/v2/pipeline/index/';
const TRIGGER_URL = '/api/v2/pipeline/trigger/';

export function usePipeline({ onError } = {}) {
    const config = ref({ enabled: false, reason: '' });
    const schema = ref(null);
    const index = ref({ clusters: {} });
    const loading = ref(false);
    const loadError = ref('');

    // What the dialog is currently showing. Null means closed.
    const request = ref(null);
    const result = ref(null);

    const available = computed(() => config.value.enabled === true);

    const loadConfig = async () => {
        try {
            config.value = await getJSON(CONFIG_URL);
        } catch (error) {
            // Never surfaced as an error: a dashboard whose pipeline project is
            // unreachable is a dashboard without trigger buttons, not a broken
            // one. The GitLab Pages form is the primary route regardless.
            config.value = { enabled: false, reason: '' };
            if (onError && error.name === 'SessionExpired') onError(error);
        }
    };

    /** Schema and index, fetched once and reused. */
    const ensureLoaded = async ({ refresh = false } = {}) => {
        if (schema.value && index.value && !refresh) return true;
        loading.value = true;
        loadError.value = '';
        try {
            const [loadedSchema, loadedIndex] = await Promise.all([
                getJSON(SCHEMA_URL, refresh ? { refresh: 'true' } : undefined),
                getJSON(INDEX_URL),
            ]);
            schema.value = loadedSchema;
            index.value = loadedIndex || { clusters: {} };
            return true;
        } catch (error) {
            if (error.name === 'SessionExpired') { if (onError) onError(error); return false; }
            loadError.value = 'The request schema could not be loaded from GitLab. '
                + 'Use the GitLab onboarding form instead.';
            return false;
        } finally {
            loading.value = false;
        }
    };

    /**
     * Open the form.
     *
     * `choices` is the set of operations offered at this point in the UI --
     * "Add namespace" inside a tenant offers the standard, DevSpace and egress
     * variants, because they are the same decision made three ways. `prefill`
     * is what the surrounding page already knows: cluster, tenant, namespace.
     */
    const open = async ({ operation, choices = null, prefill = {}, title = '' }) => {
        result.value = null;
        request.value = {
            operation,
            choices: choices && choices.length ? choices : [operation],
            prefill,
            title,
        };
        // Opened first, then loaded: the dialog shows its own loading state,
        // which is far better than a button that appears to do nothing for a
        // second and then produces a dialog.
        await ensureLoaded();
    };

    const close = () => { request.value = null; };

    const send = async (operation, payload) => {
        const response = await postJSON(TRIGGER_URL, { operation, payload });
        result.value = response;
        return response;
    };

    return {
        config, schema, index, available, loading, loadError,
        request, result,
        loadConfig, ensureLoaded, open, close, send,
    };
}
