import { getJSON } from '../lib/api.js';
import { clusterParam } from '../lib/util.js';

const { ref } = Vue;

// Which detail endpoint backs each entity, and which tab shows it.
const DETAIL_ENDPOINTS = {
    tenant: id => [`/api/v2/tenants/${encodeURIComponent(id)}/`, null],
    namespace: id => [`/api/v2/namespaces/${encodeURIComponent(id)}/`, null],
    user: (id, cluster) => [`/api/v2/users/${encodeURIComponent(id)}/`, { cluster: clusterParam(cluster) }],
    capsule: id => [`/api/v2/capsules/${encodeURIComponent(id)}/`, null],
};

/** Tab -> the `selected` key it owns, so switching tabs can clear it. */
export const TAB_ENTITY = { tenants: 'tenant', namespaces: 'namespace', users: 'user', capsules: 'capsule' };

/**
 * The currently opened detail record per entity.
 *
 * Cleared before each fetch so the previous record is not left on screen while
 * the next one loads -- which previously made a slow detail look like a
 * mis-click on the wrong row.
 */
export function useSelection({ cluster, onError }) {
    const selected = ref({ tenant: null, namespace: null, user: null, capsule: null });
    const isLoading = ref(false);

    const select = async (type, id) => {
        const build = DETAIL_ENDPOINTS[type];
        if (!build) return;

        selected.value[type] = null;
        isLoading.value = true;
        try {
            const [url, params] = build(id, cluster.value);
            selected.value[type] = await getJSON(url, params);
        } catch (error) {
            if (onError) onError(error);
        } finally {
            isLoading.value = false;
        }
    };

    const clear = type => { selected.value[type] = null; };

    return { selected, isLoading, select, clear };
}
