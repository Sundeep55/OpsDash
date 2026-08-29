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
import { usePipeline } from './composables/usePipeline.js';
import { SiglumTree } from './components/SiglumTree.js';
import { CopyButton } from './components/CopyButton.js';
import { DetailSection } from './components/DetailSection.js';
import { TableSkeleton } from './components/TableSkeleton.js';
import { ExpiryBanner } from './components/ExpiryBanner.js';
import { PipelineDialog } from './components/PipelineDialog.js';
import { UI_CONFIG } from './ui_config.js';

const { createApp, ref, computed, onMounted, onUnmounted, watch } = Vue;

const NO_FEATURES = {
    dev: false, prod: false, devspace: false, cso: false, flows: false,
    dns: false, proxy: false, templates: false, routeException: false,
    cveException: false, mirror: false,
};

createApp({
    delimiters: ['[[', ']]'],
    components: { SiglumTree, CopyButton, DetailSection, TableSkeleton, ExpiryBanner, PipelineDialog },

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
            user: '', siglum: '', request: '', capsule: '',
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

        // A flat list, not paginated: capsules are counted in dozens, not
        // hundreds -- a tenant has one or two, where it can have many namespaces.
        const capsules = useSearchList({
            endpoint: '/api/v2/capsules/',
            initial: [],
            onError,
            buildParams: () => ({
                search: search.value.capsule,
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

        /* Pipeline triggering.
         *
         * The one place the dashboard causes anything to happen. Every control
         * it adds is hidden unless the backend says triggering is configured
         * and this user may use it, so an estate without a pipeline configured
         * looks exactly as it did before the feature existed.
         *
         * Nothing is refreshed on success on purpose: the pipeline opens a
         * merge request, and the estate only changes once that is merged and
         * the next sync picks it up. Refetching immediately would suggest
         * otherwise. */
        const pipeline = usePipeline({ onError });

        const submitPipeline = async ({ operation, payload }) => {
            await pipeline.send(operation, payload);
        };

        /* Context-aware openers.
         *
         * Each one passes what the surrounding page already knows. The point of
         * triggering from here rather than from the standalone form is that the
         * operator is already looking at the tenant they mean, so re-typing its
         * name is both friction and a chance to typo it. */
        // Only prefill the cluster when the operator has actually chosen one.
        // 'All' is a filter, not a target, and sending it would be a value the
        // schema's enum does not offer.
        const clusterPrefill = cluster => (cluster && cluster !== ALL ? { target_cluster: cluster } : {});

        const addTenant = () => pipeline.open({
            operation: 'namespace.create',
            // A tenant is created by requesting its first namespace; there is no
            // separate "create tenant" operation, and inventing one in the UI
            // would imply a pipeline path that does not exist.
            choices: ['namespace.create', 'devspace.create', 'capsule.create', 'cso.create'],
            title: 'New tenant',
            prefill: clusterPrefill(globalCluster.value),
        });

        // From the Capsules tab, where the operator has already said which kind
        // of thing they want. The tenant is still theirs to pick or invent.
        const newCapsule = () => pipeline.open({
            operation: 'capsule.create',
            title: 'New capsule',
            prefill: clusterPrefill(globalCluster.value),
        });

        const addNamespace = tenant => pipeline.open({
            operation: 'namespace.create',
            choices: ['namespace.create', 'devspace.create', 'cso.create'],
            title: `Add to ${tenant.tenant_name || tenant.name}`,
            prefill: {
                target_cluster: tenant.cluster,
                tenant_name: tenant.tenant_name || tenant.name,
                siglum: tenant.siglum,
            },
        });

        const addCapsule = tenant => pipeline.open({
            operation: 'capsule.create',
            title: `Add capsule to ${tenant.tenant_name || tenant.name}`,
            prefill: {
                target_cluster: tenant.cluster,
                tenant_name: tenant.tenant_name || tenant.name,
                siglum: tenant.siglum,
            },
        });

        const updateNamespace = namespace => pipeline.open({
            operation: 'namespace.update',
            choices: ['namespace.update', 'mirror.create', 'namespace.decommission'],
            title: `Change ${namespace.name}`,
            prefill: {
                target_cluster: namespace.cluster,
                tenant_name: namespace.tenant,
                namespace_name: namespace.name,
                harbor_project: namespace.name,
                lifecycle: namespace.lifecycle,
                siglum: namespace.siglum,
            },
        });

        const updateCapsule = capsule => pipeline.open({
            operation: 'capsule.update',
            choices: ['capsule.update', 'capsule.decommission'],
            title: `Change ${capsule.name}`,
            prefill: {
                target_cluster: capsule.cluster,
                tenant_name: capsule.tenant,
                sub_tenant_name: capsule.name,
                lifecycle: capsule.lifecycle,
                siglum: capsule.siglum,
            },
        });

        // ---------------------------------------------------------- reactions

        watch(() => [search.value.namespace, search.value.namespaceCluster, search.value.namespaceStatus],
            namespaces.refresh);
        watch(() => search.value.nsFeatures, namespaces.refresh, { deep: true });
        watch(() => [search.value.tenant, search.value.tenantCluster, search.value.tenantStatus],
            tenants.refresh);
        watch(() => search.value.user, users.refresh);
        watch(() => search.value.capsule, capsules.refresh);
        watch(() => search.value.siglum, siglums.refresh);
        watch(() => search.value.request, requests.refresh);

        watch(globalCluster, () => {
            analytics.fetchAnalytics();
            users.fetchPage(1);
            capsules.fetchData();
            siglums.fetchData();
        });

        /* The capsule's remaining provisioner blocks, ready to render.
         *
         * Formatted here rather than in the template because the shape is not
         * known ahead of time: it is whatever the capsule chart carries. A short
         * summary is derived per block so the page is scannable without opening
         * every one. */
        const capsuleConfigBlocks = computed(() => {
            const cfg = selection.selected.value.capsule?.config;
            if (!cfg) return [];
            return Object.keys(cfg).sort().map(key => {
                const value = cfg[key];
                let summary = '';
                if (Array.isArray(value)) {
                    summary = value.length ? `${value.length} entr${value.length === 1 ? 'y' : 'ies'}` : 'empty';
                } else if (value && typeof value === 'object') {
                    const enabled = value.enabled ?? value.enable;
                    const n = Object.keys(value).length;
                    summary = enabled === undefined ? `${n} setting${n === 1 ? '' : 's'}`
                                                    : (enabled ? 'enabled' : 'disabled');
                } else {
                    summary = String(value);
                }
                return { key, summary, pretty: JSON.stringify(value, null, 2) };
            });
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
            pipeline.loadConfig();
            analytics.fetchAnalytics();
            namespaces.fetchPage(1);
            tenants.fetchPage(1);
            users.fetchPage(1);
            capsules.fetchData();
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
            capsulesList: capsules.data, capsulesLoading: capsules.isLoading, capsuleConfigBlocks,
            capsuleLifecycles: analytics.capsuleLifecycles,
            capsuleTotal: computed(() => {
                const c = analytics.capsuleLifecycles.value;
                return (c.dev || 0) + (c.prod || 0) + (c.unassigned || 0);
            }),
            usersList: users.items, userPagination: users.pagination,
            fetchUsersList: users.fetchPage, usersLoading: users.isLoading,
            filteredSiglumResults: siglums.data, allSiglumsList: computed(() => siglums.data.value?.siglums ?? []),
            filteredRequests: requests.data,
            // selection + drilldown
            selected: selection.selected, selectItem: selection.select, detailLoading: selection.isLoading,
            jumpTo, dashboardDetail, drilldownNamespaces, showDashboardDetail,
            getOperatorIcon,
            // pipeline triggering
            pipelineAvailable: pipeline.available,
            pipelineRequest: pipeline.request, pipelineSchema: pipeline.schema,
            pipelineIndex: pipeline.index, pipelineLoading: pipeline.loading,
            pipelineLoadError: pipeline.loadError, pipelineResult: pipeline.result,
            closePipeline: pipeline.close, submitPipeline,
            addTenant, addNamespace, addCapsule, newCapsule, updateNamespace, updateCapsule,
        };
    },
}).mount('#app');
