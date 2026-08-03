/**
 * Ops Control Plane -- application entry point.
 *
 * Composition only: state and data access live in composables/, HTTP in lib/,
 * reusable markup in components/. Anything that grows past a few lines here
 * belongs in one of those.
 */
import { getJSON, readPortalConfig, SessionExpired } from './lib/api.js';
import { ALL, clusterParam, decommissionedParam } from './lib/util.js';
import { usePaginatedList, useSearchList } from './composables/usePaginatedList.js';
import { useAnalytics } from './composables/useAnalytics.js';
import { useSelection, TAB_ENTITY } from './composables/useSelection.js';
import { useSync } from './composables/useSync.js';
import { SiglumTree } from './components/SiglumTree.js';
import { CopyButton } from './components/CopyButton.js';
import { DetailSection } from './components/DetailSection.js';
import { TableSkeleton } from './components/TableSkeleton.js';
import { UI_CONFIG } from './ui_config.js';

const { createApp, ref, computed, onMounted, onUnmounted, watch } = Vue;

const NO_FEATURES = {
    dev: false, prod: false, devspace: false, cso: false, flows: false,
    dns: false, proxy: false, templates: false, routeException: false,
    cveException: false, mirror: false,
};

createApp({
    delimiters: ['[[', ']]'],
    components: { SiglumTree, CopyButton, DetailSection, TableSkeleton },

    setup() {
        const portal = readPortalConfig();
        const activeTab = ref('dashboard');
        const globalCluster = ref(ALL);
        const dashboardDetail = ref(null);
        const drilldownNamespaces = ref([]);
        const uiState = ref({ tenantClusterOpen: false, nsClusterOpen: false, globalClusterOpen: false });

        const search = ref({
            tenant: '', tenantStatus: 'active', tenantCluster: ALL,
            namespace: '', namespaceStatus: 'active', namespaceCluster: ALL,
            nsFeatures: { ...NO_FEATURES },
            user: '', siglum: '', request: '',
        });

        const reloadOnExpiry = error => {
            if (error instanceof SessionExpired) window.location.reload();
            else console.error(error);
        };
        const onError = reloadOnExpiry;

        // ---------------------------------------------------------- data

        const analytics = useAnalytics({ cluster: globalCluster, onError });
        const selection = useSelection({ cluster: globalCluster, onError });

        const namespaces = usePaginatedList({
            endpoint: '/api/v2/namespaces/',
            onError,
            buildParams: () => {
                const f = search.value.nsFeatures;
                return {
                    search: search.value.namespace,
                    cluster: clusterParam(search.value.namespaceCluster),
                    is_decommissioned: decommissionedParam(search.value.namespaceStatus),
                    has_flows: f.flows, has_dns: f.dns, has_proxy: f.proxy,
                    has_route_exception: f.routeException, has_cve_exception: f.cveException,
                    is_cso: f.cso, has_mirror: f.mirror, has_templates: f.templates,
                    // devspace wins over the lifecycle pills; the two are exclusive
                    // in the API because a devspace has no meaningful lifecycle.
                    ...(f.devspace
                        ? { is_devspace: true }
                        : f.dev ? { lifecycle: 'dev', is_devspace: 'false' }
                        : f.prod ? { lifecycle: 'prod', is_devspace: 'false' }
                        : {}),
                };
            },
        });

        const tenants = usePaginatedList({
            endpoint: '/api/v2/tenants/',
            onError,
            buildParams: () => ({
                search: search.value.tenant,
                cluster: clusterParam(search.value.tenantCluster),
                is_decommissioned: decommissionedParam(search.value.tenantStatus),
            }),
        });

        const users = usePaginatedList({
            endpoint: '/api/v2/users/',
            onError,
            buildParams: () => ({
                search: search.value.user,
                cluster: clusterParam(globalCluster.value),
            }),
        });

        const siglums = useSearchList({
            endpoint: '/api/v2/siglums/',
            initial: { siglums: [], namespaces: [], tenants: [] },
            onError,
            buildParams: () => ({
                search: search.value.siglum,
                cluster: clusterParam(globalCluster.value),
            }),
        });

        const requests = useSearchList({
            endpoint: '/api/v2/requests/',
            initial: [],
            onError,
            buildParams: () => ({ search: search.value.request }),
        });

        const refreshAll = () => Promise.all([
            analytics.fetchAnalytics(),
            namespaces.fetchPage(namespaces.pagination.value.page),
            tenants.fetchPage(tenants.pagination.value.page),
            users.fetchPage(users.pagination.value.page),
            siglums.fetchData(),
            requests.fetchData(),
        ]);

        const sync = useSync({
            onDataChanged: refreshAll,
            onSessionExpired: () => window.location.reload(),
        });

        // ---------------------------------------------------------- reactions

        watch(() => [search.value.namespace, search.value.namespaceCluster, search.value.namespaceStatus],
            namespaces.refresh);
        watch(() => search.value.nsFeatures, namespaces.refresh, { deep: true });
        watch(() => [search.value.tenant, search.value.tenantCluster, search.value.tenantStatus],
            tenants.refresh);
        watch(() => search.value.user, users.refresh);
        watch(() => search.value.siglum, siglums.refresh);
        watch(() => search.value.request, requests.refresh);

        watch(globalCluster, () => {
            analytics.fetchAnalytics();
            users.fetchPage(1);
            siglums.fetchData();
        });

        // ---------------------------------------------------------- navigation

        const resetTab = tabId => {
            const entity = TAB_ENTITY[tabId];
            if (entity) selection.clear(entity);
            if (tabId === 'tenants') Object.assign(search.value, { tenant: '', tenantStatus: 'active', tenantCluster: ALL });
            if (tabId === 'namespaces') Object.assign(search.value, { namespace: '', namespaceStatus: 'active', namespaceCluster: ALL, nsFeatures: { ...NO_FEATURES } });
            if (tabId === 'users') search.value.user = '';
            if (tabId === 'siglums') search.value.siglum = '';
            if (tabId === 'requests') search.value.request = '';
            if (tabId === 'dashboard') dashboardDetail.value = null;
        };

        const handleTabClick = tabId => {
            uiState.value = { tenantClusterOpen: false, nsClusterOpen: false, globalClusterOpen: false };
            // Clicking the tab you are already on clears its filters; clicking a
            // different one just leaves the detail view behind.
            if (activeTab.value === tabId) {
                resetTab(tabId);
            } else {
                activeTab.value = tabId;
                const entity = TAB_ENTITY[tabId];
                if (entity) selection.clear(entity);
            }
        };

        const jumpTo = async (tabName, id) => {
            activeTab.value = tabName;
            if (tabName === 'tenants') { search.value.tenantStatus = 'all'; await selection.select('tenant', id); }
            if (tabName === 'namespaces') { search.value.namespaceStatus = 'all'; await selection.select('namespace', id); }
            if (tabName === 'users') await selection.select('user', id);
            if (tabName === 'siglums') search.value.siglum = id;
            if (tabName === 'requests') search.value.request = id;
        };

        const showDashboardDetail = async (type, rawValue, cluster = ALL) => {
            dashboardDetail.value = { type, raw: rawValue, cluster };
            drilldownNamespaces.value = [];
            const params = {
                page_size: 500,
                is_decommissioned: 'false',
                cluster: clusterParam(cluster),
                ...(type === 'lifecycle'
                    ? (rawValue === 'devspace' ? { is_devspace: true } : { lifecycle: rawValue, is_devspace: 'false' })
                    : type === 'operator' ? { operator: rawValue }
                    : type === 'chart' ? { chart: rawValue }
                    : {}),
            };
            try {
                const data = await getJSON('/api/v2/namespaces/', params);
                drilldownNamespaces.value = data.results || [];
            } catch (error) { onError(error); }
        };

        // ---------------------------------------------------------- lifecycle

        onMounted(() => {
            analytics.fetchAnalytics();
            namespaces.fetchPage(1);
            tenants.fetchPage(1);
            users.fetchPage(1);
            siglums.fetchData();
            requests.fetchData();
            sync.start();
        });

        onUnmounted(sync.stop);

        const hasData = computed(() =>
            namespaces.items.value.length > 0 || tenants.items.value.length > 0 || analytics.analytics.value !== null
        );

        // An icon mapping supplies either a vendored image path or inline svg;
        // see the notes in ui_config.js for why both exist.
        const getOperatorIcon = name => {
            const lower = String(name).toLowerCase();
            const match = UI_CONFIG.operators.iconMappings.find(m => m.match.some(t => lower.includes(t)));
            if (!match) return UI_CONFIG.operators.defaultSvg;
            if (match.svg) return match.svg;
            return `<img src="${match.path}" alt="${match.label}" class="w-4 h-4 shrink-0 object-contain" />`;
        };

        return {
            // shell
            tabs: UI_CONFIG.tabs, activeTab, handleTabClick, uiState, hasData,
            gitBrowserUrl: portal.gitBrowserUrl || '',
            // filters
            search, globalClusterFilter: globalCluster,
            // sync
            isSyncing: sync.isSyncing, syncStatus: sync.statusMessage, syncData: sync.trigger,
            // analytics
            globalAnalytics: analytics.analytics, clustersList: analytics.clusters,
            allOperatorsList: analytics.operators, dashboardKpis: analytics.kpis,
            activeLifecycles: analytics.lifecycles, perClusterMetrics: analytics.perCluster,
            siglumTree: analytics.siglumTree,
            // directories
            namespacesList: namespaces.items, nsPagination: namespaces.pagination,
            fetchNamespacesList: namespaces.fetchPage, namespacesLoading: namespaces.isLoading,
            tenantsList: tenants.items, tenantPagination: tenants.pagination,
            fetchTenantsList: tenants.fetchPage, tenantsLoading: tenants.isLoading,
            usersList: users.items, userPagination: users.pagination,
            fetchUsersList: users.fetchPage, usersLoading: users.isLoading,
            filteredSiglumResults: siglums.data, allSiglumsList: computed(() => siglums.data.value?.siglums ?? []),
            filteredRequests: requests.data,
            // selection + drilldown
            selected: selection.selected, selectItem: selection.select, detailLoading: selection.isLoading,
            jumpTo, dashboardDetail, drilldownNamespaces, showDashboardDetail,
            getOperatorIcon,
        };
    },
}).mount('#app');
