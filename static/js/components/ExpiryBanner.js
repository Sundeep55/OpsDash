/**
 * Route exceptions that are expiring or already expired, as a banner across the
 * top of every tab.
 *
 * Why a banner rather than something on the security tab: a route exception is
 * a time-limited waiver of a control, and the failure mode is nobody noticing it
 * lapsed. Putting it where you have to go looking is the same as not showing it.
 * This appears wherever the operator already is.
 *
 * It reads /api/v2/route-exceptions/, which is the same view an SMTP job reads
 * at /api/v2/security/route-exceptions/ -- subclassed only to take the browser
 * session instead of a token. Same queryset, so the screen and the mail cannot
 * disagree about what is expiring.
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

/* How far back a lapse is still worth raising.
 *
 * The grant is never edited or removed to quiet this -- it is in Git as the
 * audit record and stays there. What is bounded is the alerting: a waiver that
 * lapsed a fortnight ago needs chasing; one that lapsed three years ago is
 * history, and a banner still counting it is noise that buries the one that
 * lapsed yesterday. Anything older is on the Security tab, in full.
 */
const EXPIRED_WITHIN_DAYS = 14;


export const ExpiryBanner = {
    props: {
        // Narrows with the global cluster selector, so the banner agrees with
        // whatever the rest of the page is showing.
        cluster: { type: String, default: 'All' },
    },
    // Rows are clickable. The banner is on every tab precisely because a lapsed
    // waiver has to be noticed from wherever you are -- so it should also be
    // actionable from wherever you are, rather than telling you a name to go
    // and search for.
    emits: ['select'],
    data() {
        return { rows: [], dismissed: false, open: false, failed: false };
    },
    computed: {
        expired()  { return this.rows.filter(r => r.status === 'expired'); },
        expiring() { return this.rows.filter(r => r.status === 'expiring'); },
        visible()  { return !this.dismissed && this.rows.length > 0; },
        windowDays() { return EXPIRED_WITHIN_DAYS; },
        headline() {
            const parts = [];
            if (this.expired.length)  parts.push(`${this.expired.length} lapsed recently`);
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
                // expired_within: a grant that lapsed in March should not still
                // be shouting in September. It stays expired and stays listed
                // on the security tab -- this banner just stops repeating it,
                // because one that never changes is one nobody reads, and then
                // it is not warning about yesterday's lapse either.
                const q = new URLSearchParams({
                    status: 'expiring,expired',
                    expired_within: String(EXPIRED_WITHIN_DAYS),
                });
                if (this.cluster && this.cluster !== 'All') q.set('cluster', this.cluster);
                // The internal copy of the endpoint, not /security/…, which is
                // token-only. Same view and therefore the same answer -- a
                // notifier reading the product API cannot disagree with what is
                // on screen here.
                const res = await fetch(`/api/v2/route-exceptions/?${q}`, {
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
        A route exception lets a dev namespace expose Routes, for a fixed term. When it lapses the
        waiver stops applying — renew it through ITSM, or the namespace should give the Routes up.
        <span v-if="expired.length" class="opacity-80">Lapses older than {{ windowDays }} days have had their notice period and are on the Security tab; the record stays in Git either way.</span>
      </p>

      <button @click="open = !open"
              :class="['mt-2 text-xs font-bold underline underline-offset-2 focus-ring rounded',
                       severity === 'expired' ? 'text-red-800' : 'text-amber-800']">
        {{ open ? 'Hide' : 'Show' }} the {{ rows.length }} namespace{{ rows.length === 1 ? '' : 's' }}
      </button>

      <!--
        Scrolls rather than truncates. Everything matching is here -- nothing is
        hidden behind an "and N more" -- but a list of a few hundred should not
        push the whole page down, so it gets its own scroll box.
      -->
      <ul v-if="open" class="mt-2 space-y-1 max-h-72 overflow-y-auto pr-1">
        <li v-for="r in rows" :key="r.namespace"
            @click="$emit('select', r.namespace)"
            :class="['text-xs flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded px-1 py-0.5 -mx-1 cursor-pointer',
                     severity === 'expired' ? 'hover:bg-red-100' : 'hover:bg-amber-100']"
            :title="'Open ' + r.namespace">
          <span :class="['badge !m-0 !px-1.5 !py-0.5 text-white font-bold',
                         r.status === 'expired' ? 'bg-red-600' : 'bg-amber-500']">
            {{ r.status === 'expired' ? 'LAPSED' : r.days_remaining + 'd' }}
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
