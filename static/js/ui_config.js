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
        { id: 'capsules', label: 'Capsules' },
        { id: 'users', label: 'Users' },
        { id: 'siglums', label: 'Siglums' },
        { id: 'requests', label: 'Requests' }
    ],

    // 2. Operator UI Mappings
    //
    // Matched against the lowercased operator name by substring, first entry
    // wins -- so put more specific patterns above more general ones.
    //
    // An entry supplies either:
    //   path: '/static/images/<file>.png'   a vendored image, or
    //   svg:  '<svg ...>'                   inline markup
    //
    // Prefer `path` with the vendor's official asset. `svg` exists for
    // operators whose logo we do not have a licensed copy of: the build is
    // airgapped, so nothing can be fetched from a CDN at runtime, and drawing
    // an approximation of someone's brand mark is worse than a neutral glyph.
    // To upgrade one, drop the PNG into static/images/ and swap svg -> path.
    operators: {
        iconMappings: [
            { match: ['argo'], path: '/static/images/argo-cd.png', label: 'ArgoCD' },
            { match: ['cert'], path: '/static/images/cert-manager.png', label: 'Cert-Manager' },
            // Ahead of the PostgreSQL entry: a name like `perconaPGOperator`
            // would otherwise match its 'pg' pattern first.
            {
                match: ['percona', 'mongo'],
                label: 'Percona MongoDB',
                svg: `<svg class="w-4 h-4 shrink-0 text-emerald-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><ellipse cx="12" cy="6" rx="7" ry="3"/><path stroke-linecap="round" d="M5 6v6c0 1.657 3.134 3 7 3s7-1.343 7-3V6"/><path stroke-linecap="round" d="M5 12v6c0 1.657 3.134 3 7 3s7-1.343 7-3v-6"/></svg>`,
            },
            { match: ['pg', 'postgres', 'cloudnative'], path: '/static/images/postgres.png', label: 'PostgreSQL' },
            { match: ['gitlab'], path: '/static/images/gitlab.png', label: 'GitLab' },
            { match: ['loki'], path: '/static/images/loki.png', label: 'Loki' }
        ],
        // The fallback icon if no match is found
        defaultSvg: `<svg class="w-4 h-4 text-slate-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path></svg>`
    }
};