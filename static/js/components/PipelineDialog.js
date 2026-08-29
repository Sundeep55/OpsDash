/**
 * The onboarding request form, rendered from request-schema.yaml.
 *
 * Nothing about which fields exist, which are required, or which are shown is
 * written here. All of it comes from the schema the pipeline project publishes,
 * applied by lib/schemaForm.js -- the same engine the GitLab Pages form uses and
 * the same rules pipeline-scripts/load-payload.sh enforces. A field added to the
 * schema appears in this dialog with no change to this file and no OpsDash
 * release.
 *
 * This component therefore only renders and wires. Anything here that decided
 * whether a value were acceptable would be a fourth opinion on that question.
 *
 * Note: this template string compiles with Vue's default {{ }} delimiters. The
 * app configures [[ ]] for the root in-DOM template only.
 */
import { SchemaForm } from '../lib/schemaForm.js';

export const PipelineDialog = {
    props: {
        // { operation, choices: [...], prefill: {...}, title } -- null when closed.
        request: { type: Object, default: null },
        schema: { type: Object, default: null },
        index: { type: Object, default: () => ({ clusters: {} }) },
        loading: { type: Boolean, default: false },
        loadError: { type: String, default: '' },
        result: { type: Object, default: null },
    },
    emits: ['close', 'submit'],

    data() {
        return {
            operation: null,
            input: {},
            sending: false,
            error: '',
            showPayload: false,
            // The dialog opens before the schema has been fetched, so the
            // prefill cannot be applied on the way in -- working out which
            // fields an operation accepts needs the schema. This records
            // whether it has been applied for the request currently open, so
            // the schema watcher can apply it once and then leave the
            // operator's typing alone on any later refresh.
            prefillApplied: false,
            // Errors appear once a field has been touched, so opening the form
            // is not an immediate wall of red on fields nobody has reached yet.
            touched: {},
        };
    },

    watch: {
        request: {
            immediate: true,
            handler(value) {
                if (!value) { this.prefillApplied = false; return; }
                this.operation = value.operation;
                this.error = '';
                this.sending = false;
                this.showPayload = false;
                this.touched = {};
                this.prefillApplied = false;
                this.input = {};
                this.applyPrefill();
            },
        },
        // Applies the prefill when the schema lands, which is normally after
        // the dialog is already on screen.
        schema: {
            handler() { this.applyPrefill(); },
        },
    },

    computed: {
        open() { return !!this.request; },

        operations() {
            if (!this.schema || !this.request) return [];
            return (this.request.choices || []).filter(op => this.schema.operations?.[op]);
        },

        meta() {
            return this.schema?.operations?.[this.operation] || {};
        },

        heading() {
            return this.request?.title || this.meta.title || this.operation || 'New request';
        },

        /* A plain copy of the form values, and the only thing handed to the
         * engine.
         *
         * Two reasons, one of them a bug that took a while to see. The engine
         * asks `Object.prototype.hasOwnProperty.call(input, name)` before
         * reading a value -- and Vue's reactive proxy does not intercept
         * hasOwnProperty. For a key that is absent the engine therefore never
         * reads it either, so the computed registers no dependency on it, and
         * setting that key later never invalidates anything. The symptom was
         * precise and misleading: typing in a text box worked, because the
         * template reads input[name] itself, but choosing "prod" from the
         * lifecycle menu left the ARD field hidden and the resolved value stuck
         * on "dev".
         *
         * Spreading reads ownKeys and every value, so the dependency is
         * complete. It also means the vendored engine is handed an ordinary
         * object rather than a proxy -- it is shared with a page that has no
         * framework at all and should not have to know what Vue is. */
        plainInput() {
            return { ...this.input };
        },

        /* Everything the engine derives: resolved values, what is hidden, and
         * what the operator actually supplied. Recomputed on every keystroke,
         * which is what makes show_if chains resolve as you type. */
        state() {
            if (!this.schema || !this.operation) return { values: {}, hidden: {}, supplied: {} };
            return SchemaForm.resolve(this.schema, this.operation, this.plainInput);
        },

        validation() {
            if (!this.schema || !this.operation) return { errors: {}, ok: false };
            return SchemaForm.validate(this.schema, this.operation, this.plainInput);
        },

        payload() {
            if (!this.schema || !this.operation) return {};
            return SchemaForm.buildPayload(this.schema, this.operation, this.plainInput);
        },

        payloadText() { return JSON.stringify(this.payload, null, 2); },
        payloadBytes() { return JSON.stringify(this.payload).length; },

        /* Fields grouped for display, in the schema's own group order. Hidden
         * fields are dropped here rather than in the template so an emptied
         * group disappears with its heading. */
        groups() {
            if (!this.schema || !this.operation) return [];
            const fields = SchemaForm.operationFields(this.schema, this.operation);
            return (this.schema.groups || []).map(group => ({
                ...group,
                fields: fields.filter(name =>
                    this.schema.fields[name]?.group === group.id && !this.state.hidden[name]),
            })).filter(group => group.fields.length);
        },

        problems() {
            const errors = this.validation.errors || {};
            const out = Object.keys(errors).map(name =>
                `${this.schema?.fields?.[name]?.label || name} ${errors[name]}`);
            if (this.existingTenantNeedsName) {
                out.push(`${this.nameFieldLabel} is required for an existing tenant — `
                    + 'pick one from the list, or type a new name.');
            }
            return out;
        },

        // Which "name" field this operation uses, if any. Namespaces and
        // capsules are the same shape with two different field names.
        nameField() {
            const fields = this.schema && this.operation
                ? SchemaForm.operationFields(this.schema, this.operation) : [];
            if (fields.indexOf('namespace_name') !== -1) return 'namespace_name';
            if (fields.indexOf('sub_tenant_name') !== -1) return 'sub_tenant_name';
            return null;
        },

        nameFieldLabel() {
            return this.schema?.fields?.[this.nameField]?.label || 'Name';
        },

        tenantRecord() {
            const cluster = this.index?.clusters?.[this.state.values.target_cluster];
            return (cluster && cluster[this.state.values.tenant_name]) || null;
        },

        /* The one rule the schema cannot express, because it depends on what is
         * in the repository rather than on the request: an existing tenant must
         * name its namespace. The scaffold script refuses it otherwise, and
         * without the index the operator only finds out from a red pipeline.
         *
         * Only for the create operations -- update and decommission declare the
         * field required in the schema, so the engine already covers them. */
        existingTenantNeedsName() {
            if (!['namespace.create', 'capsule.create'].includes(this.operation)) return false;
            if (!this.state.values.tenant_name || !this.nameField) return false;
            return !!this.tenantRecord && !this.state.values[this.nameField];
        },

        ready() {
            return !this.problems.length && !this.sending && !this.result;
        },
    },

    methods: {
        field(name) { return this.schema?.fields?.[name] || {}; },

        isRequired(name) {
            return SchemaForm.isRequired(this.schema, name, this.state, this.operation);
        },

        /* Picklist values for a field whose schema declares a `source`. Comes
         * from the dashboard's own synced state, so it is minutes behind the
         * repository rather than a merge behind, which is the one thing this
         * surface can do better than the static Pages form. */
        optionsFor(name) {
            const source = this.field(name).source;
            if (!source) return null;
            const cluster = this.index?.clusters?.[this.state.values.target_cluster];
            if (!cluster) return [];
            if (source.index === 'tenants') return Object.keys(cluster).sort();
            const record = cluster[this.state.values.tenant_name];
            if (!record) return [];
            if (source.index === 'namespaces') return record.namespaces || [];
            if (source.index === 'sub_tenants') return record.capsules || [];
            return [];
        },

        errorFor(name) {
            if (!this.touched[name] && !this.state.supplied[name]) return '';
            const message = this.validation.errors?.[name];
            return message ? `${this.field(name).label || name} ${message}` : '';
        },

        applyPrefill() {
            // Needs the schema: which fields an operation accepts is the thing
            // being filtered on. The dialog opens before the fetch returns, so
            // the first call is usually a no-op and the schema watcher makes the
            // real one.
            if (!this.request || !this.schema || !this.operation) return;
            // Once per request. Without this, a schema refresh landing while
            // someone is halfway through the form would reset it under them.
            if (this.prefillApplied) return;
            this.prefillApplied = true;

            const prefill = this.request.prefill || {};
            const fields = SchemaForm.operationFields(this.schema, this.operation);
            const next = {};
            // Only what this operation actually accepts. Switching from
            // "namespace" to "capsule" must not carry namespace_name across as
            // a field the payload check would then reject.
            Object.keys(prefill).forEach(key => {
                if (fields.indexOf(key) !== -1 && prefill[key] !== undefined && prefill[key] !== null) {
                    next[key] = String(prefill[key]);
                }
            });
            this.input = next;
        },

        chooseOperation(operation) {
            if (operation === this.operation) return;
            // Keep what the operator has already typed where the new operation
            // also offers it. Retyping the ITSM id because you switched from
            // "namespace" to "DevSpace" is exactly the kind of friction that
            // sends people back to raising a ticket.
            const previous = { ...this.input };
            this.operation = operation;
            const fields = SchemaForm.operationFields(this.schema, operation);
            const kept = {};
            Object.keys(previous).forEach(key => {
                if (fields.indexOf(key) !== -1) kept[key] = previous[key];
            });
            const prefill = this.request?.prefill || {};
            Object.keys(prefill).forEach(key => {
                if (fields.indexOf(key) !== -1 && kept[key] === undefined) {
                    kept[key] = String(prefill[key]);
                }
            });
            this.input = kept;
            this.error = '';
        },

        setValue(name, value) {
            this.input[name] = value;
            this.touched[name] = true;
        },

        /* Case folding happens on blur, not per keystroke. Rewriting the value
         * under the cursor as someone types fights the caret; but leaving the
         * box showing "acXYme" while the payload carries "acxyme" means the
         * operator has to read the preview to know what they actually sent. */
        normaliseOnBlur(name, value) {
            const rule = this.field(name).normalise;
            if (rule === 'lower') this.input[name] = String(value).toLowerCase();
            else if (rule === 'upper') this.input[name] = String(value).toUpperCase();
            this.touched[name] = true;
        },

        async submit() {
            if (!this.ready) return;
            this.sending = true;
            this.error = '';
            try {
                await this.$emit('submit', { operation: this.operation, payload: this.payload });
            } catch (error) {
                this.error = String(error.message || error);
            } finally {
                this.sending = false;
            }
        },

        copyPayload() {
            navigator.clipboard.writeText(JSON.stringify(this.payload)).then(() => {
                this.error = '';
                this.copied = true;
                setTimeout(() => { this.copied = false; }, 1500);
            }).catch(() => {
                // Clipboard access can be refused. Opening the preview leaves
                // the operator able to select it by hand rather than stuck.
                this.showPayload = true;
            });
        },
    },

    template: `
<div v-if="open" class="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 sm:p-8">
  <div @click="$emit('close')" class="fixed inset-0" aria-hidden="true"></div>

  <div class="relative w-full max-w-3xl bg-white rounded-2xl shadow-xl border border-slate-200 my-4"
       role="dialog" aria-modal="true" aria-labelledby="pipeline-dialog-title">

    <!-- header -->
    <div class="flex items-start justify-between gap-4 px-6 py-4 border-b border-slate-200">
      <div class="min-w-0">
        <h3 id="pipeline-dialog-title" class="text-lg font-extrabold text-slate-900 tracking-tight truncate">
          {{ heading }}
        </h3>
        <p v-if="meta.description" class="text-xs text-slate-500 mt-1">{{ meta.description }}</p>
      </div>
      <button @click="$emit('close')" class="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus-ring" title="Close">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
      </button>
    </div>

    <!-- loading / unavailable -->
    <div v-if="loading" class="px-6 py-10 text-center text-sm font-medium text-slate-500">
      Loading the request schema from GitLab…
    </div>
    <div v-else-if="loadError" class="px-6 py-8">
      <p class="text-sm font-bold text-red-700">{{ loadError }}</p>
      <p class="text-xs text-slate-500 mt-2">
        The dashboard is a shortcut to the pipeline, not the way in. The GitLab onboarding
        form is unaffected by this.
      </p>
    </div>

    <!-- success -->
    <div v-else-if="result" class="px-6 py-8 text-center">
      <div class="mx-auto w-10 h-10 rounded-full bg-green-100 flex items-center justify-center mb-3">
        <svg class="w-5 h-5 text-green-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
      </div>
      <p class="text-sm font-bold text-slate-900">Pipeline #{{ result.id }} started</p>
      <p class="text-xs text-slate-500 mt-1">
        The change is made by the pipeline and reaches this dashboard on the next sync.
      </p>
      <div class="mt-4 flex items-center justify-center gap-2">
        <a v-if="result.web_url" :href="result.web_url" target="_blank" rel="noopener"
           class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg shadow-sm hover:bg-slate-50 hover:text-blue-600 transition-colors">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
          Open in GitLab
        </a>
        <button @click="$emit('close')" class="inline-flex items-center justify-center rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 transition-all focus-ring">
          Done
        </button>
      </div>
    </div>

    <!-- form -->
    <div v-else-if="schema" class="px-6 py-5">

      <!-- operation choice, only when there is one to make -->
      <div v-if="operations.length > 1" class="mb-5">
        <span class="meta-label">Request type</span>
        <div class="flex flex-wrap gap-2 mt-1">
          <button v-for="op in operations" :key="op" @click="chooseOperation(op)" type="button"
                  :class="['px-3 py-1.5 rounded-full text-xs font-bold border transition-all focus-ring',
                           op === operation ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                                            : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50']">
            {{ schema.operations[op].title || op }}
          </button>
        </div>
      </div>

      <!-- what the index knows about this tenant -->
      <div v-if="state.values.tenant_name && nameField"
           :class="['rounded-lg border px-3 py-2 mb-4 text-xs',
                    tenantRecord ? 'bg-slate-50 border-slate-200 text-slate-600'
                                 : 'bg-amber-50 border-amber-200 text-amber-800']">
        <template v-if="tenantRecord">
          <strong class="font-bold">Existing tenant.</strong>
          {{ state.values.tenant_name }} has {{ (tenantRecord.namespaces || []).length }}
          namespace{{ (tenantRecord.namespaces || []).length === 1 ? '' : 's' }}
          and {{ (tenantRecord.capsules || []).length }}
          capsule{{ (tenantRecord.capsules || []).length === 1 ? '' : 's' }}.
          Pick one from the list, or type a new name to add one.
        </template>
        <template v-else>
          <strong class="font-bold">New tenant.</strong>
          {{ state.values.tenant_name }} does not exist yet and will be created.
          A four-character suffix is added by the pipeline.
        </template>
      </div>

      <div class="max-h-[50vh] overflow-y-auto pr-1 -mr-1">
        <fieldset v-for="group in groups" :key="group.id" class="mb-5">
          <legend class="meta-label">{{ group.title }}</legend>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3 mt-2">
            <div v-for="name in group.fields" :key="name"
                 :class="field(name).type === 'boolean' ? 'sm:col-span-1' : 'sm:col-span-2'">

              <!-- boolean -->
              <label v-if="field(name).type === 'boolean'"
                     class="flex items-start gap-2 rounded-lg border border-slate-200 px-3 py-2 hover:bg-slate-50 cursor-pointer">
                <input type="checkbox" class="mt-0.5 shrink-0"
                       :checked="state.values[name] === 'true'"
                       @change="setValue(name, $event.target.checked ? 'true' : 'false')">
                <span class="min-w-0">
                  <span class="block text-xs font-bold text-slate-800">{{ field(name).label || name }}</span>
                  <span v-if="field(name).description" class="block text-[11px] text-slate-500 mt-0.5">{{ field(name).description }}</span>
                </span>
              </label>

              <!-- enum -->
              <template v-else-if="field(name).type === 'enum'">
                <label :for="'pf-' + name" class="block">
                  <span class="text-xs font-bold text-slate-800">{{ field(name).label || name }}<span v-if="isRequired(name)" class="text-red-600"> *</span></span>
                  <span v-if="field(name).description" class="block text-[11px] text-slate-500 mt-0.5">{{ field(name).description }}</span>
                </label>
                <select :id="'pf-' + name" :value="state.values[name]"
                        @change="setValue(name, $event.target.value)"
                        class="mt-1 w-full rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-900 shadow-sm outline-none focus:ring-2 focus:ring-blue-600 h-[38px]">
                  <option v-for="option in (field(name).options || [])" :key="option" :value="option">{{ option }}</option>
                  <option v-if="(field(name).options || []).indexOf(state.values[name]) === -1"
                          :value="state.values[name]">{{ state.values[name] || '(none)' }}</option>
                </select>
              </template>

              <!-- text, email, url, datetime -->
              <template v-else>
                <label :for="'pf-' + name" class="block">
                  <span class="text-xs font-bold text-slate-800">{{ field(name).label || name }}<span v-if="isRequired(name)" class="text-red-600"> *</span></span>
                  <span v-if="field(name).description" class="block text-[11px] text-slate-500 mt-0.5">{{ field(name).description }}</span>
                </label>
                <input :id="'pf-' + name"
                       :type="field(name).type === 'email' ? 'email' : (field(name).type === 'url' ? 'url' : 'text')"
                       :list="optionsFor(name) && optionsFor(name).length ? 'pl-' + name : null"
                       :placeholder="field(name).input_format === 'DD/MM/YYYY HH:mm:ss' ? 'DD/MM/YYYY HH:MM:SS' : ''"
                       :value="input[name] === undefined ? '' : input[name]"
                       @input="setValue(name, $event.target.value)"
                       @change="normaliseOnBlur(name, $event.target.value)"
                       :class="['mt-1 w-full rounded-lg border px-3 text-sm font-medium text-slate-900 shadow-sm outline-none focus:ring-2 focus:ring-blue-600 h-[38px]',
                                errorFor(name) ? 'border-red-300 bg-red-50' : 'border-slate-200']">
                <datalist v-if="optionsFor(name) && optionsFor(name).length" :id="'pl-' + name">
                  <option v-for="option in optionsFor(name)" :key="option" :value="option"></option>
                </datalist>
              </template>

              <p v-if="errorFor(name)" class="text-[11px] font-semibold text-red-700 mt-1">{{ errorFor(name) }}</p>
            </div>
          </div>
        </fieldset>
      </div>

      <!-- problems -->
      <div v-if="problems.length" class="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
        <p class="text-xs font-bold text-amber-800">Not ready to send:</p>
        <ul class="mt-1 space-y-0.5">
          <li v-for="problem in problems" :key="problem" class="text-[11px] text-amber-800">• {{ problem }}</li>
        </ul>
      </div>

      <div v-if="error" class="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
        <p class="text-xs font-bold text-red-800">{{ error }}</p>
      </div>

      <!-- payload preview -->
      <div class="mt-4">
        <button @click="showPayload = !showPayload" type="button"
                class="text-xs font-bold text-slate-500 hover:text-slate-800 underline underline-offset-2 focus-ring rounded">
          {{ showPayload ? 'Hide' : 'Show' }} the request payload ({{ payloadBytes }} bytes)
        </button>
        <pre v-if="showPayload" class="mt-2 max-h-48 overflow-auto rounded-lg bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">{{ payloadText }}</pre>
      </div>
    </div>

    <!-- footer -->
    <div v-if="!loading && !loadError && !result && schema"
         class="flex items-center justify-between gap-3 px-6 py-4 border-t border-slate-200 bg-slate-50 rounded-b-2xl">
      <p class="text-[11px] text-slate-500">
        Runs as the dashboard's service token; recorded against your account.
      </p>
      <div class="flex items-center gap-2">
        <button @click="$emit('close')" type="button"
                class="px-3 py-2 text-sm font-semibold text-slate-600 hover:text-slate-900 focus-ring rounded-lg">
          Cancel
        </button>
        <button @click="submit" :disabled="!ready"
                class="inline-flex items-center justify-center rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 transition-all disabled:opacity-40 disabled:cursor-not-allowed focus-ring">
          <svg v-if="sending" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
          {{ sending ? 'Starting…' : 'Start pipeline' }}
        </button>
      </div>
    </div>
  </div>
</div>`,
};
