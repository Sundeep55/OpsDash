/**
 * The organisational siglum tree.
 *
 * Previously assembled as an HTML string and injected with v-html. That had two
 * problems: siglum values come from the GitOps repo and were interpolated into
 * markup unescaped, and the classes inside those strings are invisible to any
 * scanner -- which is why the EGRESS badge here rendered unstyled for so long.
 *
 * As a real component the values are text nodes and the classes sit in a
 * template where `manage.py build_css` can see them.
 */

const NODE_ICON = `<svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>`;
const LEAF_ICON = `<svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"></path></svg>`;

const SiglumTreeRow = {
    name: 'SiglumTreeRow',
    props: {
        prefix: { type: String, required: true },
        node: { type: Object, required: true },
    },
    emits: ['select'],
    computed: {
        stats() { return this.node.stats; },
        isLeaf() { return Object.keys(this.node.children || {}).length === 0; },
        // The analytics endpoint sends a count; older payloads sent a Set.
        tenantCount() {
            const t = this.stats.tenants;
            return t instanceof Set ? t.size : t;
        },
        // Full class strings rather than a computed suffix: `manage.py build_css`
        // finds classes in string literals, so a name assembled at runtime would
        // be invisible to it and silently ship unstyled. There is no
        // `badge-teal` component class -- adding one would need a Tailwind
        // rebuild, which the airgapped build cannot do -- so egress uses
        // utilities the generator can produce from the existing tokens.
        badges() {
            return [
                { key: 'dev', label: 'DEV', count: this.stats.dev, cls: 'badge-blue' },
                { key: 'prod', label: 'PROD', count: this.stats.prod, cls: 'badge-green' },
                { key: 'devspace', label: 'DS', count: this.stats.devspace, cls: 'badge-purple' },
                { key: 'egress', label: 'EGRESS', count: this.stats.egress, cls: '!bg-teal-100 !text-teal-800 !border-teal-200' },
            ].filter(b => b.count > 0);
        },
    },
    template: `
        <div class="flex items-center justify-between gap-3 py-2 px-2 rounded-lg border-l-2 border-transparent hover:bg-slate-50 hover:border-blue-500 transition-colors">
            <div class="flex items-center gap-3 min-w-0">
                <button v-if="isLeaf" type="button" @click.stop="$emit('select', prefix)"
                        class="siglum-link cursor-pointer text-blue-600 hover:underline flex items-center gap-1.5 font-semibold text-sm focus-ring rounded"
                        :aria-label="'View siglum ' + prefix">
                    <span v-html="leafIcon"></span>{{ prefix }}
                </button>
                <span v-else class="font-extrabold text-slate-800 text-sm flex items-center gap-1.5">
                    <span v-html="nodeIcon"></span>{{ prefix }}
                </span>
                <span class="text-[10px] font-semibold text-slate-500 border border-slate-200 px-1.5 py-0.5 rounded shadow-sm whitespace-nowrap">
                    {{ tenantCount }} Tenants &middot; {{ stats.ns_count }} NS
                </span>
            </div>
            <div class="flex gap-1.5 shrink-0">
                <span v-for="b in badges" :key="b.key" :class="['badge', b.cls, '!m-0']" :title="b.count + ' ' + b.label">{{ b.label }}</span>
            </div>
        </div>
    `,
    data() {
        return { leafIcon: LEAF_ICON, nodeIcon: NODE_ICON };
    },
};

export const SiglumTree = {
    name: 'SiglumTree',
    components: { SiglumTreeRow },
    props: {
        tree: { type: Object, default: () => ({}) },
    },
    emits: ['select'],
    computed: {
        entries() { return Object.entries(this.tree || {}); },
    },
    template: `
        <div v-if="entries.length === 0" class="text-[10px] text-slate-400 italic px-2 py-1">
            No organizational data available.
        </div>
        <template v-else>
            <template v-for="[prefix, node] in entries" :key="prefix">
                <details v-if="Object.keys(node.children || {}).length" class="ml-3 mt-1 pl-3 border-l-2 border-slate-100">
                    <summary class="list-none outline-none cursor-pointer focus-ring rounded">
                        <siglum-tree-row :prefix="prefix" :node="node" @select="$emit('select', $event)" />
                    </summary>
                    <div class="mt-1">
                        <siglum-tree :tree="node.children" @select="$emit('select', $event)" />
                    </div>
                </details>
                <div v-else class="ml-3 mt-1 pl-3 border-l-2 border-transparent">
                    <siglum-tree-row :prefix="prefix" :node="node" @select="$emit('select', $event)" />
                </div>
            </template>
        </template>
    `,
};
