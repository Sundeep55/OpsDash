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

/* Where the operator's GitLab token lives.
 *
 * sessionStorage, not localStorage: this is a credential, and sessionStorage is
 * cleared when the tab closes. The GitLab Pages form uses localStorage and a
 * token put there was still sitting in the browser two days later, which is a
 * long time for a PAT to be lying about on a shared machine.
 *
 * It is never sent to OpsDash except as the header on a trigger, and the server
 * never writes it down -- not to the database, not to the Django session, not to
 * a log line. Nothing else in the app reads this key.
 */
const TOKEN_KEY = 'opsdash-gitlab-token';

function readToken() {
    try { return sessionStorage.getItem(TOKEN_KEY) || ''; }
    catch { return ''; }   // private window, or storage disabled
}

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

    // Mirrors sessionStorage so the UI can react to it; the store is the source.
    const token = ref(readToken());

    const setToken = value => {
        const trimmed = (value || '').trim();
        token.value = trimmed;
        try {
            if (trimmed) sessionStorage.setItem(TOKEN_KEY, trimmed);
            else sessionStorage.removeItem(TOKEN_KEY);
        } catch { /* nothing to do; it simply will not persist */ }
    };

    const hasToken = computed(() => token.value.length > 0);

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
     * `locked` is the subset of that the operator must not change -- see the
     * openers in app.js for why each one is fixed.
     */
    const open = async ({ operation, choices = null, prefill = {}, title = '',
                          locked = [], tenantFromIndex = false }) => {
        result.value = null;
        request.value = {
            operation,
            choices: choices && choices.length ? choices : [operation],
            prefill,
            title,
            // Fields the calling page has already decided. They still travel in
            // the payload; they are simply not the operator's to change here.
            locked,
            // Tenant is chosen from the ones that exist rather than typed.
            tenantFromIndex,
        };
        // Opened first, then loaded: the dialog shows its own loading state,
        // which is far better than a button that appears to do nothing for a
        // second and then produces a dialog.
        await ensureLoaded();
    };

    const close = () => { request.value = null; };

    const send = async (operation, payload) => {
        try {
            // The token goes in a header, per request. It is not in the body,
            // where it would end up in any log or error report that captures
            // request bodies.
            const response = await postJSON(TRIGGER_URL, { operation, payload },
                                            { 'X-GitLab-Token': token.value });
            result.value = response;
            return response;
        } catch (error) {
            // Rethrown so the dialog can await it and show the reason in place.
            // The server's `detail` is the useful half -- it carries GitLab's
            // own refusal text -- so lead with it and keep the status as
            // context rather than as the whole message.
            throw new Error(error.detail || error.message || 'The request could not be sent.');
        }
    };

    return {
        config, schema, index, available, loading, loadError,
        request, result,
        token, hasToken, setToken,
        loadConfig, ensureLoaded, open, close, send,
    };
}
