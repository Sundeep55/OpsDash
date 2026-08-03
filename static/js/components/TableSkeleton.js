/**
 * Placeholder rows shown while a list request is in flight.
 *
 * Filter changes used to leave the previous results on screen with no
 * indication anything was happening, so a slow change looked like a no-op and
 * invited a second click. Rows keep the table's height stable, which avoids the
 * page jumping as results arrive.
 */
export const TableSkeleton = {
    name: 'TableSkeleton',
    props: {
        rows: { type: Number, default: 8 },
        cols: { type: Number, default: 4 },
    },
    computed: {
        // Varied widths read as content rather than as a progress bar.
        widths() {
            return ['w-3/4', 'w-1/2', 'w-2/3', 'w-1/3', 'w-5/6', 'w-1/2'];
        },
    },
    template: `
        <tr v-for="r in rows" :key="r" aria-hidden="true">
            <td v-for="c in cols" :key="c" class="px-6 py-4">
                <div :class="['skeleton h-4', widths[(r + c) % widths.length]]"></div>
            </td>
        </tr>
    `,
};
