const { createApp, ref, computed, onMounted, watch } = Vue;

createApp({
    delimiters: ['[[', ']]'], 
    
    setup() {
        const globalAnalytics = ref(null);
        const isSyncing = ref(false);
        const syncStatus = ref('Ready');
        let pollInterval = null;
        
        let nsDebounceTimer = null;
        let tenantDebounceTimer = null;
        let userDebounceTimer = null;
        let siglumDebounceTimer = null;
        let reqDebounceTimer = null;
        
        const tabs = UI_CONFIG.tabs;
        const activeTab = ref('dashboard');
        const selected = ref({ tenant: null, namespace: null, user: null });
        const dashboardDetail = ref(null);

        const uiState = ref({
            tenantClusterOpen: false,
            nsClusterOpen: false,
            globalClusterOpen: false
        });

        const globalClusterFilter = ref('All');

        // FIX: Replaced 'sandbox' with 'routeException' in the default search state
        const search = ref({ 
            tenant: '', tenantStatus: 'active', tenantCluster: 'All',
            namespace: '', namespaceStatus: 'active', namespaceCluster: 'All',
            nsFeatures: { dev: false, prod: false, devspace: false, cso: false, flows: false, dns: false, proxy: false, templates: false, routeException: false, cveException: false, mirror: false },
            user: '', siglum: '', request: '' 
        });

        const namespacesList = ref([]);
        const nsPagination = ref({ page: 1, total: 0, totalPages: 1 });
        
        const tenantsList = ref([]);
        const tenantPagination = ref({ page: 1, total: 0, totalPages: 1 });
        
        const usersList = ref([]);
        const userPagination = ref({ page: 1, total: 0, totalPages: 1 });
        
        const filteredSiglumResults = ref({ namespaces: [], tenants: [] });
        const filteredRequests = ref([]);
        const drilldownNamespaces = ref([]);

        const hasData = computed(() => (namespacesList.value.length > 0 || tenantsList.value.length > 0 || globalAnalytics.value !== null));
        
        const clustersList = computed(() => {
            if (!globalAnalytics.value?.cluster_resources) return [];
            return Object.keys(globalAnalytics.value.cluster_resources).sort();
        });

        const allOperatorsList = computed(() => {
            if (!globalAnalytics.value?.operators) return [];
            return Object.keys(globalAnalytics.value.operators).sort();
        });

        const fetchAnalytics = async () => {
            try {
                const url = globalClusterFilter.value === 'All' ? '/api/v2/analytics/' : `/api/v2/analytics/?cluster=${encodeURIComponent(globalClusterFilter.value)}`;
                const res = await fetch(url);
                globalAnalytics.value = await res.json();
            } catch (e) { console.error("Failed Analytics", e); }
        };

        const fetchNamespacesList = async (page = 1) => {
            let url = `/api/v2/namespaces/?page=${page}`;
            if (search.value.namespace) url += `&search=${encodeURIComponent(search.value.namespace)}`;
            if (search.value.namespaceCluster !== 'All') url += `&cluster=${encodeURIComponent(search.value.namespaceCluster)}`;
            if (search.value.namespaceStatus === 'active') url += `&is_decommissioned=false`;
            else if (search.value.namespaceStatus === 'decomm') url += `&is_decommissioned=true`;
            
            const f = search.value.nsFeatures;
            if (f.flows) url += `&has_flows=true`; 
            if (f.dns) url += `&has_dns=true`; 
            if (f.proxy) url += `&has_proxy=true`;
            
            // FIX: Map the UI checkbox to the new API query parameter
            if (f.routeException) url += `&has_route_exception=true`; 
            if (f.cveException) url += `&has_cve_exception=true`;
            if (f.cso) url += `&is_cso=true`; 
            
            if (f.mirror) url += `&has_mirror=true`; 
            if (f.templates) url += `&has_templates=true`;
            if (f.devspace) url += `&is_devspace=true`; 
            else if (f.dev) url += `&lifecycle=dev&is_devspace=false`; 
            else if (f.prod) url += `&lifecycle=prod&is_devspace=false`;
            
            try {
                const res = await fetch(url); 
                const data = await res.json();
                nsPagination.value = { page: data.current_page || page, total: data.count, totalPages: data.total_pages || 1 };
                namespacesList.value = data.results || [];
            } catch(e) { console.error("NS Error", e); }
        };

        const fetchTenantsList = async (page = 1) => {
            let url = `/api/v2/tenants/?page=${page}`;
            if (search.value.tenant) url += `&search=${encodeURIComponent(search.value.tenant)}`;
            if (search.value.tenantCluster !== 'All') url += `&cluster=${encodeURIComponent(search.value.tenantCluster)}`;
            if (search.value.tenantStatus === 'active') url += `&is_decommissioned=false`;
            else if (search.value.tenantStatus === 'decomm') url += `&is_decommissioned=true`;
            
            try {
                const res = await fetch(url); 
                const data = await res.json();
                tenantPagination.value = { page: data.current_page || page, total: data.count, totalPages: data.total_pages || 1 };
                tenantsList.value = data.results || [];
            } catch(e) { console.error("Tenant Error", e); }
        };

        const fetchUsersList = async (page = 1) => {
            let url = `/api/v2/users/?page=${page}`;
            if (search.value.user) url += `&search=${encodeURIComponent(search.value.user)}`;
            if (globalClusterFilter.value !== 'All') url += `&cluster=${encodeURIComponent(globalClusterFilter.value)}`;
            
            try {
                const res = await fetch(url); 
                const data = await res.json();
                userPagination.value = { page: data.current_page || page, total: data.count, totalPages: data.total_pages || 1 };
                usersList.value = data.results || [];
            } catch(e) { console.error("User Error", e); }
        };

        const fetchSiglumsList = async () => {
            let url = `/api/v2/siglums/?search=${encodeURIComponent(search.value.siglum)}`;
            if (globalClusterFilter.value !== 'All') url += `&cluster=${encodeURIComponent(globalClusterFilter.value)}`;
            try {
                const res = await fetch(url);
                filteredSiglumResults.value = await res.json();
            } catch(e) { console.error("Siglum Error", e); }
        };

        const fetchRequestsList = async () => {
            let url = `/api/v2/requests/?search=${encodeURIComponent(search.value.request)}`;
            try {
                const res = await fetch(url);
                filteredRequests.value = await res.json();
            } catch(e) { console.error("Request Error", e); }
        };

        const debouncedFetchNamespaces = () => { clearTimeout(nsDebounceTimer); nsDebounceTimer = setTimeout(() => { fetchNamespacesList(1); }, 300); };
        const debouncedFetchTenants = () => { clearTimeout(tenantDebounceTimer); tenantDebounceTimer = setTimeout(() => { fetchTenantsList(1); }, 300); };
        const debouncedFetchUsers = () => { clearTimeout(userDebounceTimer); userDebounceTimer = setTimeout(() => { fetchUsersList(1); }, 300); };
        const debouncedFetchSiglums = () => { clearTimeout(siglumDebounceTimer); siglumDebounceTimer = setTimeout(() => { fetchSiglumsList(); }, 300); };
        const debouncedFetchRequests = () => { clearTimeout(reqDebounceTimer); reqDebounceTimer = setTimeout(() => { fetchRequestsList(); }, 300); };

        watch(() => search.value.namespace, debouncedFetchNamespaces);
        watch(() => search.value.namespaceCluster, debouncedFetchNamespaces);
        watch(() => search.value.namespaceStatus, debouncedFetchNamespaces);
        watch(() => search.value.nsFeatures, debouncedFetchNamespaces, { deep: true });
        
        watch(() => search.value.tenant, debouncedFetchTenants);
        watch(() => search.value.tenantCluster, debouncedFetchTenants);
        watch(() => search.value.tenantStatus, debouncedFetchTenants);
        
        watch(() => search.value.user, debouncedFetchUsers);
        watch(() => search.value.siglum, debouncedFetchSiglums);
        watch(() => search.value.request, debouncedFetchRequests);
        
        watch(globalClusterFilter, () => {
            fetchAnalytics(); fetchUsersList(1); fetchSiglumsList();
        });

        // --- NEW: Smart Ping & Polling Variables ---
        let lastKnownSyncTime = null;
        let silentPollInterval = null;

        const checkSyncStatus = async (isManualTrigger = false) => {
            try {
                const res = await fetch('/api/v2/sync/status/');

                if (res.status === 401 || res.status === 403) {
                    console.warn("Session expired. Redirecting to login...");
                    clearInterval(silentPollInterval);
                    if (pollInterval) clearInterval(pollInterval);
                    window.location.reload(); // Reloading will force Django to bounce the user to the login screen
                    return;
                }

                const data = await res.json();
                
                isSyncing.value = data.is_syncing;
                syncStatus.value = data.last_message || "Ready";

                // SMART PING LOGIC: Has the sidecar updated the DB since our last check?
                if (data.last_sync_time && lastKnownSyncTime !== data.last_sync_time) {
                    if (lastKnownSyncTime !== null) {
                        // It changed! Silently reload the data without refreshing the page
                        syncStatus.value = "Hot-swapping UI data...";
                        await Promise.all([
                            fetchAnalytics(), fetchNamespacesList(nsPagination.value.page), 
                            fetchTenantsList(tenantPagination.value.page), fetchUsersList(userPagination.value.page), 
                            fetchSiglumsList(), fetchRequestsList()
                        ]);
                        syncStatus.value = "Ready";
                    }
                    lastKnownSyncTime = data.last_sync_time;
                }
                
                if (isManualTrigger && !data.is_syncing) {
                    clearInterval(pollInterval); pollInterval = null;
                }
            } catch (err) {
                if (isManualTrigger) { clearInterval(pollInterval); pollInterval = null; }
                isSyncing.value = false; syncStatus.value = "Status offline";
            }
        };

        const syncData = async () => {
            if (isSyncing.value) return; 
            isSyncing.value = true; syncStatus.value = "Triggering manual sync...";
            try {
                const res = await fetch('/api/v2/sync/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') } });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                if (!pollInterval) pollInterval = setInterval(() => checkSyncStatus(true), 2000);
            } catch (err) {
                isSyncing.value = false; syncStatus.value = `Error`; 
            }
        };

        const getCookie = (name) => {
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1)); break;
                    }
                }
            }
            return cookieValue;
        };

        onMounted(() => {
            fetchAnalytics();
            fetchNamespacesList(1);
            fetchTenantsList(1);
            fetchUsersList(1);
            fetchSiglumsList();
            fetchRequestsList();
            
            // --- NEW: Start the silent UI ping loop ---
            checkSyncStatus(); // Get the initial timestamp baseline
            silentPollInterval = setInterval(() => checkSyncStatus(false), 5000); // Check every 5s
        });

        const getOperatorIcon = (opName) => {
            const name = opName.toLowerCase();
            for (const mapping of UI_CONFIG.operators.iconMappings) {
                if (mapping.match.some(m => name.includes(m))) return `<img src="${mapping.path}" alt="${mapping.label}" class="w-4 h-4 shrink-0 object-contain" />`;
            }
            return UI_CONFIG.operators.defaultSvg;
        };

        const buildSiglumTreeHtml = (treeObj) => {
            if (!treeObj || Object.keys(treeObj).length === 0) return '<div class="text-[10px] text-slate-400 italic">No organizational data available.</div>';
            let html = '';
            for (const [prefix, node] of Object.entries(treeObj)) {
                const s = node.stats; const tenantsCount = s.tenants instanceof Set ? s.tenants.size : s.tenants; const hasChildren = Object.keys(node.children).length > 0;
                const titleHtml = !hasChildren 
                    ? `<span class="siglum-link cursor-pointer text-blue-600 hover:underline flex items-center gap-1.5" data-siglum="${prefix}"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"></path></svg>${prefix}</span>`
                    : `<span class="font-extrabold text-slate-800 text-sm flex items-center gap-1.5"><svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>${prefix}</span>`;
                let content = `
                    <div class="flex items-center justify-between py-2 hover:bg-slate-50 rounded-lg px-2 border-l-2 border-transparent hover:border-blue-500">
                        <div class="flex items-center gap-3">${titleHtml}<span class="text-[10px] font-semibold text-slate-400 border px-1.5 py-0.5 rounded shadow-sm">${tenantsCount} Tenants &middot; ${s.ns_count} NS</span></div>
                        <div class="flex gap-2 ml-2">
                            ${s.dev > 0 ? `<span class="badge badge-blue !m-0">DEV</span>` : ''}${s.prod > 0 ? `<span class="badge badge-green !m-0">PROD</span>` : ''}${s.devspace > 0 ? `<span class="badge badge-purple !m-0">DS</span>` : ''}${s.egress > 0 ? `<span class="badge !bg-teal-100 !text-teal-800 !border-teal-200 !m-0">EGRESS</span>` : ''}
                        </div>
                    </div>
                `;
                if (hasChildren) html += `<details class="ml-3 mt-1 pl-3 border-l-2 border-slate-100 group"><summary class="list-none outline-none cursor-pointer">${content}</summary><div class="mt-1">${buildSiglumTreeHtml(node.children)}</div></details>`;
                else html += `<div class="ml-3 mt-1 pl-3 border-l-2 border-transparent">${content}</div>`;
            }
            return html;
        };

        const dashboardKpis = computed(() => {
            if (!globalAnalytics.value || !globalAnalytics.value.global_kpis) return { tenants: 0, namespaces: 0, cpu: '0', mem: '0' };
            const k = globalAnalytics.value.global_kpis;
            return { tenants: k.tenants || 0, namespaces: k.namespaces || 0, cpu: (k.cpu_req || 0).toFixed(0), mem: (k.mem_req || 0).toFixed(0) };
        });

        const activeLifecycles = computed(() => {
            return globalAnalytics.value?.lifecycles
                ?? { dev: 0, prod: 0, devspace: 0, egress: 0, unassigned: 0 };
        });

        const renderedSiglumTree = computed(() => {
            if (!globalAnalytics.value?.siglum_tree) return '';
            return buildSiglumTreeHtml(globalAnalytics.value.siglum_tree);
        });

        // Derives a new object rather than writing back into globalAnalytics.
        // It used to assign data.renderedTree onto the reactive source, so a
        // computed getter mutated the state it depended on -- which schedules
        // another evaluation of itself on every read.
        const perClusterMetrics = computed(() => {
            const source = globalAnalytics.value?.cluster_resources;
            if (!source) return {};

            return Object.fromEntries(Object.entries(source).map(([name, data]) => [name, {
                ...data,
                cpu_req: data.cpu_req || 0,
                cpu_limit: data.cpu_limit || 0,
                mem_req: data.mem_req || 0,
                mem_limit: data.mem_limit || 0,
                renderedTree: data.siglum_tree ? buildSiglumTreeHtml(data.siglum_tree) : '',
            }]));
        });

        const allSiglumsList = computed(() => {
            return filteredSiglumResults.value?.siglums || [];
        });

        const showDashboardDetail = async (type, rawValue, cluster = 'All') => {
            dashboardDetail.value = { type, raw: rawValue, cluster };
            drilldownNamespaces.value = []; 

            try {
                let url = `/api/v2/namespaces/?page_size=500&is_decommissioned=false`;
                if (cluster !== 'All') url += `&cluster=${encodeURIComponent(cluster)}`;

                if (type === 'lifecycle') {
                    if (rawValue === 'devspace') url += `&is_devspace=true`;
                    else url += `&lifecycle=${encodeURIComponent(rawValue)}&is_devspace=false`;
                } else if (type === 'operator') {
                    url += `&operator=${encodeURIComponent(rawValue)}`;
                } else if (type === 'chart') {
                    url += `&chart=${encodeURIComponent(rawValue)}`;
                }

                const response = await fetch(url);
                const data = await response.json();
                drilldownNamespaces.value = data.results || [];
            } catch (e) {
                console.error("Failed to fetch drilldown namespaces", e);
            }
        };

        const handleTreeClick = (event) => {
            const link = event.target.closest('.siglum-link');
            if (link) jumpTo('siglums', link.getAttribute('data-siglum'));
        };

        const handleTabClick = (tabId) => {
            uiState.value = { tenantClusterOpen: false, nsClusterOpen: false, globalClusterOpen: false };
            if (activeTab.value === tabId) {
                if (tabId === 'tenants') { selected.value.tenant = null; search.value.tenant = ''; search.value.tenantStatus = 'active'; search.value.tenantCluster = 'All'; }
                
                if (tabId === 'namespaces') { 
                    selected.value.namespace = null; 
                    search.value.namespace = ''; 
                    search.value.namespaceStatus = 'active'; 
                    search.value.namespaceCluster = 'All'; 
                    search.value.nsFeatures = { dev: false, prod: false, devspace: false, cso: false, flows: false, dns: false, proxy: false, templates: false, routeException: false, cveException: false, mirror: false }; 
                }
                
                if (tabId === 'users') { selected.value.user = null; search.value.user = ''; }
                if (tabId === 'siglums') { search.value.siglum = ''; }
                if (tabId === 'requests') { search.value.request = ''; }
                if (tabId === 'dashboard') { dashboardDetail.value = null; }
            } else {
                activeTab.value = tabId;
                // Show the tab's list, not whatever detail was open last time.
                // Without this, leaving a namespace and coming back re-opened
                // the previous namespace -- with data that may since be stale.
                selected.value[tabId.replace(/s$/, '')] = null;
            }
        };

        const selectItem = async (type, id) => {
            if (type === 'tenant') {
                try {
                    selected.value.tenant = null;
                    const res = await fetch(`/api/v2/tenants/${encodeURIComponent(id)}/`);
                    selected.value.tenant = await res.json();
                } catch(e) { console.error("Tenant Fetch failed", e); }
            }
            if (type === 'namespace') {
                try {
                    selected.value.namespace = null; 
                    const res = await fetch(`/api/v2/namespaces/${encodeURIComponent(id)}/`);
                    selected.value.namespace = await res.json();
                } catch (err) { console.error("Namespace Fetch failed", err); }
            }
            if (type === 'user') {
                try {
                    selected.value.user = null;
                    let url = `/api/v2/users/${encodeURIComponent(id)}/`;
                    if (globalClusterFilter.value !== 'All') url += `?cluster=${encodeURIComponent(globalClusterFilter.value)}`;
                    const res = await fetch(url);
                    selected.value.user = await res.json();
                } catch (err) { console.error("User Fetch failed", err); }
            }
        };

        const jumpTo = async (tabName, id) => {
            activeTab.value = tabName;
            if (tabName === 'tenants') { search.value.tenantStatus = 'all'; await selectItem('tenant', id); }
            if (tabName === 'namespaces') { search.value.namespaceStatus = 'all'; await selectItem('namespace', id); }
            if (tabName === 'users') await selectItem('user', id);
            if (tabName === 'siglums') search.value.siglum = id;
            if (tabName === 'requests') search.value.request = id;
        };

        return {
            globalAnalytics, isSyncing, syncStatus, hasData, tabs, activeTab, search, selected, uiState,
            globalClusterFilter, clustersList, getOperatorIcon, 
            namespacesList, nsPagination, fetchNamespacesList,
            tenantsList, tenantPagination, fetchTenantsList,
            usersList, userPagination, fetchUsersList, 
            filteredSiglumResults, filteredRequests, 
            dashboardKpis, perClusterMetrics, activeLifecycles, dashboardDetail, drilldownNamespaces, allSiglumsList, allOperatorsList,
            renderedSiglumTree, handleTreeClick, showDashboardDetail, syncData, selectItem, jumpTo, handleTabClick,
            gitBrowserUrl: typeof GIT_BROWSER_URL !== 'undefined' ? GIT_BROWSER_URL : ''
        };
    }
}).mount('#app');