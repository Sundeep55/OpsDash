/**
 * Renders a namespace section straight from its API descriptor.
 *
 * The backend registry (dashboard/gitops/sections.py) already carries the
 * title and the field labels, so this needs no matching frontend registry --
 * there is one list to edit, in Python, not two that can drift apart.
 *
 * A section added to that registry appears here automatically: no serializer
 * field, no template block, no entry in any JS file.
 *
 * Sections with bespoke markup on the detail page (compute limits, GPU, Harbor,
 * networking) set auto_render=False and are not routed through this.
 */
const EMPTY = '—';

export const DetailSection = {
    name: 'DetailSection',
    props: {
        section: { type: Object, required: true },
    },
    computed: {
        rows() {
            return (this.section.fields || []).map(f => ({
                ...f,
                display: this.format(f.value),
                isEmpty: this.format(f.value) === EMPTY,
            }));
        },
    },
    methods: {
        format(value) {
            if (value === null || value === undefined || value === '') return EMPTY;
            if (typeof value === 'boolean') return value ? 'Yes' : 'No';
            // JSON columns (CVE allowlists, permission lists) arrive as arrays.
            if (Array.isArray(value)) return value.length ? value.join(', ') : EMPTY;
            return String(value);
        },
    },
    template: `
        <div class="bento-card">
            <div class="bento-header"><h4 class="bento-title">{{ section.title }}</h4></div>
            <div class="bento-body">
                <dl class="grid grid-cols-2 gap-y-5 gap-x-8">
                    <div v-for="row in rows" :key="row.name">
                        <dt class="meta-label">{{ row.label }}</dt>
                        <dd :class="['text-sm font-medium', row.isEmpty ? 'text-slate-400 italic' : 'text-slate-800']">
                            {{ row.display }}
                        </dd>
                    </div>
                </dl>
            </div>
        </div>
    `,
};
