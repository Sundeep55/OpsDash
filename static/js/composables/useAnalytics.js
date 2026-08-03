import { getJSON } from '../lib/api.js';
import { clusterParam } from '../lib/util.js';

const { ref, computed } = Vue;

/** Dashboard aggregates: KPIs, lifecycle counts, per-cluster totals, siglum tree. */
export function useAnalytics({ cluster, onError }) {
    const analytics = ref(null);
    const isLoading = ref(false);

    const fetchAnalytics = async () => {
        isLoading.value = true;
        try {
            analytics.value = await getJSON('/api/v2/analytics/', { cluster: clusterParam(cluster.value) });
        } catch (error) {
            if (onError) onError(error);
        } finally {
            isLoading.value = false;
        }
    };

    const clusters = computed(() =>
        Object.keys(analytics.value?.cluster_resources ?? {}).sort()
    );

    const operators = computed(() =>
        Object.keys(analytics.value?.operators ?? {}).sort()
    );

    const kpis = computed(() => {
        const k = analytics.value?.global_kpis;
        if (!k) return { tenants: 0, namespaces: 0, cpu: '0', mem: '0' };
        return {
            tenants: k.tenants || 0,
            namespaces: k.namespaces || 0,
            cpu: (k.cpu_req || 0).toFixed(0),
            mem: (k.mem_req || 0).toFixed(0),
        };
    });

    const lifecycles = computed(() =>
        analytics.value?.lifecycles ?? { dev: 0, prod: 0, devspace: 0, egress: 0, unassigned: 0 }
    );

    // Derives a new object rather than writing back into `analytics`: a computed
    // that mutates its own dependency re-triggers itself on every read.
    const perCluster = computed(() => {
        const source = analytics.value?.cluster_resources;
        if (!source) return {};
        return Object.fromEntries(Object.entries(source).map(([name, data]) => [name, {
            ...data,
            cpu_req: data.cpu_req || 0,
            cpu_limit: data.cpu_limit || 0,
            mem_req: data.mem_req || 0,
            mem_limit: data.mem_limit || 0,
        }]));
    });

    const siglumTree = computed(() => analytics.value?.siglum_tree ?? {});

    return { analytics, isLoading, fetchAnalytics, clusters, operators, kpis, lifecycles, perCluster, siglumTree };
}
