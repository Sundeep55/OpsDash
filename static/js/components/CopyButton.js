import { copyText } from '../lib/clipboard.js';

const { ref } = Vue;

/**
 * Copy a value to the clipboard, with inline confirmation.
 *
 * Confirmation is on the button itself rather than a toast: the button is where
 * the user is looking, and a toast in the corner is easy to miss.
 */
export const CopyButton = {
    name: 'CopyButton',
    props: {
        value: { type: String, required: true },
        label: { type: String, default: 'Copy' },
        // 'md' sits beside a page heading, 'sm' inside a table row.
        size: { type: String, default: 'md' },
    },
    setup(props) {
        const state = ref('idle'); // idle | copied | failed
        let resetTimer = null;

        const copy = async () => {
            clearTimeout(resetTimer);
            state.value = (await copyText(props.value)) ? 'copied' : 'failed';
            resetTimer = setTimeout(() => { state.value = 'idle'; }, 1600);
        };

        return { state, copy };
    },
    computed: {
        title() {
            if (this.state === 'copied') return 'Copied';
            if (this.state === 'failed') return 'Copy failed — select and copy manually';
            return `${this.label} “${this.value}”`;
        },
        buttonClass() {
            const base = this.size === 'sm'
                ? 'h-6 w-6 rounded-md'
                : 'h-8 w-8 rounded-lg';
            const tone = {
                copied: 'text-green-600 bg-green-50 border-green-200',
                failed: 'text-red-600 bg-red-50 border-red-200',
                idle: 'text-slate-400 bg-white border-slate-200 hover:text-blue-600 hover:border-blue-300 hover:bg-blue-50',
            }[this.state];
            return `${base} ${tone} inline-flex items-center justify-center border shadow-sm transition-colors focus-ring shrink-0`;
        },
        iconClass() {
            return this.size === 'sm' ? 'w-3 h-3' : 'w-4 h-4';
        },
    },
    template: `
        <button type="button" @click.stop="copy" :title="title" :aria-label="title" :class="buttonClass">
            <svg v-if="state === 'copied'" :class="iconClass" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <svg v-else-if="state === 'failed'" :class="iconClass" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
            <svg v-else :class="iconClass" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <span class="sr-only">{{ title }}</span>
        </button>
    `,
};
