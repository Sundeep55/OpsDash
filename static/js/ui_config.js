/**
 * Static UI configuration.
 *
 * Tabs and operator icon mappings live here so they can be changed without
 * touching application logic. Imported as a module -- it no longer defines a
 * global, so nothing can read it by accident.
 */
export const UI_CONFIG = {
    // 1. Navigation Tabs Definition
    tabs: [
        { id: 'dashboard', label: 'Dashboard' },
        { id: 'tenants', label: 'Tenants' },
        { id: 'namespaces', label: 'Namespaces' },
        { id: 'users', label: 'Users' },
        { id: 'siglums', label: 'Siglums' },
        { id: 'requests', label: 'Requests' }
    ],

    // 2. Operator UI Mappings
    // To add a new operator icon, simply add a new object to this array!
    operators: {
        iconMappings: [
            { match: ['argo'], path: '/static/images/argo-cd.png', label: 'ArgoCD' },
            { match: ['cert'], path: '/static/images/cert-manager.png', label: 'Cert-Manager' },
            { match: ['pg', 'postgres', 'cloudnative'], path: '/static/images/postgres.png', label: 'PostgreSQL' },
            { match: ['gitlab'], path: '/static/images/gitlab.png', label: 'GitLab' },
            { match: ['loki'], path: '/static/images/loki.png', label: 'Loki' }
        ],
        // The fallback icon if no match is found
        defaultSvg: `<svg class="w-4 h-4 text-slate-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path></svg>`
    }
};