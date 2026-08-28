/**
 * Route exceptions that are expiring or already expired, as a banner across the
 * top of every tab.
 *
 * Why a banner rather than something on the security tab: a route exception is
 * a time-limited waiver of a control, and the failure mode is nobody noticing it
 * lapsed. Putting it where you have to go looking is the same as not showing it.
 * This appears wherever the operator already is.
 *
 * It reads the same product endpoint an SMTP job would
 * (/api/v2/security/route-exceptions/?status=expiring,expired), so the screen
 * and the mail cannot disagree about what is expiring.
 *
 * Note: this component's template string compiles with Vue's default {{ }}
 * delimiters. The app configures [[ ]] for the root in-DOM template only, which
 * is why every component here uses {{ }} inside its own template.
 *
 * Dismissal is per-browser and per-day: dismissing gets the rest of the day back
 * without silencing it permanently, because a waiver that expired last week
 * should keep asking.
 */
const DISMISS_KEY = 'opsdash-expiry-banner-dismissed';

export const ExpiryBanner = {
    props: {
        // Narrows with the global cluster selector, so the banner agrees with
        // whatever the rest of the page is showing.
        cluster: { type: String, default: 'All' },
    },
    data() {
        return { rows: [], dismissed: false, open: false, failed: false };
    },
    computed: {
        expired()  { return this.rows.filter(r => r.status === 'expired'); },
        expiring() { return this.rows.filter(r => r.status === 'expiring'); },
        visible()  { return !this.dismissed && this.rows.length > 0; },
        headline() {
            const parts = [];
            if (this.expired.length)  parts.push(`${this.expired.length} expired`);
            if (this.expiring.length) parts.push(`${this.expiring.length} expiring within 30 days`);
            return parts.join(' · ');
        },
        severity() { return this.expired.length ? 'expired' : 'expiring'; },
    },
    watch: {
        cluster: 'load',
    },
    mounted() {
        try {
            this.dismissed = localStorage.getItem(DISMISS_KEY) === new Date().toDateString();
        } catch (e) { /* private window: just show it */ }
        this.load();
    },
    methods: {
        async load() {
            try {
                const q = new URLSearchParams({ status: 'expiring,expired' });
                if (this.cluster && this.cluster !== 'All') q.set('cluster', this.cluster);
                const res = await fetch(`/api/v2/security/route-exceptions/?${q}`, {
                    headers: { 'Accept': 'application/json' },
                });
                if (!res.ok) throw new Error(res.status);
                this.rows = await res.json();
                this.failed = false;
            } catch (e) {
                // A banner that cannot load is not worth an error state of its
                // own; the security tab is still there. Stay quiet.
                this.rows = [];
                this.failed = true;
            }
        },
        dismiss() {
            this.dismissed = true;
            try { localStorage.setItem(DISMISS_KEY, new Date().toDateString()); } catch (e) { /* ignore */ }
        },
    },
    template: `
<div v-if="visible"
     :class="['mb-6 rounded-xl border shadow-sm overflow-hidden',
              severity === 'expired' ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200']">
  <div class="flex items-start gap-3 px-4 py-3">
    <svg :class="['w-5 h-5 shrink-0 mt-0.5', severity === 'expired' ? 'text-red-600' : 'text-amber-600']"
         fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
    </svg>

    <div class="flex-1 min-w-0">
      <p :class="['text-sm font-bold', severity === 'expired' ? 'text-red-800' : 'text-amber-800']">
        Route exceptions need attention — {{ headline }}
      </p>
      <p :class="['text-xs mt-0.5', severity === 'expired' ? 'text-red-700' : 'text-amber-700']">
        A route exception is a time-limited waiver. Renew it through ITSM or let the namespace revert.
      </p>

      <button @click="open = !open"
              :class="['mt-2 text-xs font-bold underline underline-offset-2 focus-ring rounded',
                       severity === 'expired' ? 'text-red-800' : 'text-amber-800']">
        {{ open ? 'Hide' : 'Show' }} the {{ rows.length }} namespace{{ rows.length === 1 ? '' : 's' }}
      </button>

      <ul v-if="open" class="mt-2 space-y-1">
        <li v-for="r in rows" :key="r.namespace"
            class="text-xs flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span :class="['badge !m-0 !px-1.5 !py-0.5 text-white font-bold',
                         r.status === 'expired' ? 'bg-red-600' : 'bg-amber-500']">
            {{ r.status === 'expired' ? 'EXPIRED' : r.days_remaining + 'd' }}
          </span>
          <span class="font-bold text-slate-800">{{ r.namespace }}</span>
          <span class="text-slate-500">{{ r.tenant }} · {{ r.cluster }}</span>
          <span class="text-slate-500">expires {{ r.expires_at }}</span>
          <span v-if="r.request_id" class="text-slate-400">{{ r.request_id }}</span>
        </li>
      </ul>
    </div>

    <button @click="dismiss" title="Hide until tomorrow"
            :class="['shrink-0 rounded p-1 focus-ring', severity === 'expired' ? 'text-red-500 hover:bg-red-100' : 'text-amber-600 hover:bg-amber-100']">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
      </svg>
    </button>
  </div>
</div>`,
};
