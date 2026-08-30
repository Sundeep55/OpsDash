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
            user: '', siglum: '', request: '',
            capsule: '', capsuleStatus: 'active',
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
                is_decommissioned: decommissionedParam(search.value.capsuleStatus),
            }),
        });

        const siglums = useSearchList({
            endpoint: '/api/v2/siglums/',
            initial: { siglums: [], namespaces: [], tenants: [], capsules: [] },
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

        /* From a directory, which is not scoped to a tenant.
         *
         * The tenant is chosen from the ones that exist rather than typed: from
         * here the operator is adding to a tenant, never inventing one, and a
         * free-text box would accept a typo and quietly create a second tenant
         * one character different. Choosing it fills in the cluster, siglum and
         * cost centre, which are properties of the tenant the dashboard already
         * knows -- retyping them is friction and a chance to disagree with Git.
         *
         * Creating a *new* tenant is still possible; it is the "New Tenant"
         * button on the Tenants directory, where typing a new name is the
         * point. */
        const addNamespaceStandalone = () => pipeline.open({
            operation: 'namespace.create',
            choices: ['namespace.create', 'devspace.create', 'cso.create'],
            title: 'New namespace',
            tenantFromIndex: true,
            prefill: {},
        });

        const newCapsule = () => pipeline.open({
            operation: 'capsule.create',
            title: 'New capsule',
            tenantFromIndex: true,
            prefill: {},
        });

        /* From inside one tenant.
         *
         * Opening the form from a tenant page answers the tenant question by
         * the act of opening it, so the tenant and its cluster are fixed --
         * leaving them changeable invites filing the request against a tenant
         * nobody is looking at.
         *
         * The siglum and cost centre are filled in from that tenant but stay
         * editable. They are the tenant's defaults for this request rather than
         * facts about it: a namespace can legitimately carry its own siglum
         * (the parser has a whole fallback chain for exactly that), and a
         * cost centre can differ per request. Locking them would have made the
         * form refuse a case the estate already supports. */
        const tenantContext = tenant => ({
            prefill: {
                target_cluster: tenant.cluster,
                tenant_name: tenant.tenant_name || tenant.name,
                siglum: tenant.siglum,
                cost_center: tenant.cost_center,
            },
            locked: ['target_cluster', 'tenant_name'],
        });

        const addNamespace = tenant => pipeline.open({
            operation: 'namespace.create',
            choices: ['namespace.create', 'devspace.create', 'cso.create'],
            title: `Add to ${tenant.tenant_name || tenant.name}`,
            ...tenantContext(tenant),
        });

        const addCapsule = tenant => pipeline.open({
            operation: 'capsule.create',
            title: `Add capsule to ${tenant.tenant_name || tenant.name}`,
            ...tenantContext(tenant),
        });

        /* From inside one namespace or capsule.
         *
         * Which object this acts on was settled by opening it, so its identity
         * -- cluster, tenant, and its own name -- is fixed. A decommission form
         * that let you edit the namespace name is a form that can retire the
         * wrong namespace.
         *
         * The lifecycle is deliberately NOT locked: changing it is one of the
         * things an update is for. */
        const updateNamespace = namespace => pipeline.open({
            operation: 'namespace.update',
            choices: ['namespace.update', 'mirror.create', 'namespace.decommission'],
            title: `Change ${namespace.name}`,
            locked: ['target_cluster', 'tenant_name', 'namespace_name'],
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
            locked: ['target_cluster', 'tenant_name', 'sub_tenant_name'],
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
        watch(() => [search.value.capsule, search.value.capsuleStatus], capsules.refresh);
        watch(() => search.value.siglum, siglums.refresh);
        watch(() => search.value.request, requests.refresh);

        watch(globalCluster, () => {
            analytics.fetchAnalytics();
            users.fetchPage(1);
            capsules.fetchData();
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
            if (tabId === 'capsules') Object.assign(search.value, { capsule: '', capsuleStatus: 'active' });
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

        /* A CSV export URL carrying the filters currently on screen.
         *
         * The export should be what the person is looking at. Handing back the
         * whole estate when they had narrowed to one cluster is the kind of
         * thing that gets noticed only after the spreadsheet has been sent on.
         *
         * A plain href rather than a fetch: the browser saves the file, the
         * session cookie authenticates it, and there is no blob to build or
         * revoke. `All` and empty values are dropped so the URL stays readable.
         */
        const exportUrl = (kind, params = {}) => {
            const query = new URLSearchParams();
            Object.entries(params).forEach(([key, value]) => {
                if (value === undefined || value === null || value === '' || value === ALL) return;
                // The status pill's own vocabulary: only 'all' means anything
                // to the API, since active-only is the default.
                if (key === 'status' && value !== 'all') return;
                query.set(key, value);
            });
            const suffix = query.toString();
            return `/api/v2/${kind}/export/${suffix ? '?' + suffix : ''}`;
        };

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
            capsulesList: capsules.data, capsulesLoading: capsules.isLoading,
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
            getOperatorIcon, exportUrl,
            // pipeline triggering
            pipelineAvailable: pipeline.available,
            pipelineRequest: pipeline.request, pipelineSchema: pipeline.schema,
            pipelineIndex: pipeline.index, pipelineLoading: pipeline.loading,
            pipelineLoadError: pipeline.loadError, pipelineResult: pipeline.result,
            pipelineDryRun: computed(() => pipeline.config.value.dry_run === true),
            pipelineHasToken: pipeline.hasToken,
            pipelineGitlabUrl: computed(() => pipeline.config.value.gitlab_url || ''),
            setPipelineToken: pipeline.setToken,
            closePipeline: pipeline.close, submitPipeline,
            addTenant, addNamespace, addNamespaceStandalone, addCapsule, newCapsule,
            updateNamespace, updateCapsule,
        };
    },
}).mount('#app');
