/* =============================================================================
 * schema-form.js — the browser half of request-schema.yaml.
 *
 * This is the same rule set as pipeline-scripts/load-payload.sh, in JavaScript:
 * resolve values, apply show_if to a fixed point, decide what is required,
 * validate, and build the payload.
 *
 * WHY IT IS A SEPARATE FILE WITH NO DOM IN IT
 * -------------------------------------------
 * Two things load it: the GitLab Pages form (app.js), and later OpsDash. Both
 * must agree with each other and with the shim. Keeping the rules in one
 * dependency-free module means there is one place to change them and one place
 * to test them, rather than a copy per surface that drifts.
 *
 * The shim remains the gate. Nothing here is a security control — a browser
 * cannot be one. This exists so an operator finds out about a mistake while
 * filling the form instead of from a red pipeline five minutes later.
 * tools/cases.json is run through both; tools/test-cases.sh is the shell side.
 *
 * No imports, no build step, no framework. It runs from a <script> tag in an
 * airgapped environment.
 * ============================================================================= */
(function (root) {
  'use strict';

  // --- helpers --------------------------------------------------------------

  function prop(schema, name, key) {
    var f = schema.fields[name];
    if (!f || f[key] === undefined || f[key] === null) return '';
    return String(f[key]);
  }

  function list(schema, name, key) {
    var f = schema.fields[name];
    if (!f || !f[key]) return [];
    return f[key];
  }

  function conditions(schema, name, key) {
    var f = schema.fields[name];
    if (!f || !f[key]) return null;
    return f[key];
  }

  function normalise(schema, name, value) {
    switch (prop(schema, name, 'normalise')) {
      case 'lower': return String(value).toLowerCase();
      case 'upper': return String(value).toUpperCase();
      default:      return value;
    }
  }

  function operationFields(schema, op) {
    var o = schema.operations[op];
    return o && o.fields ? o.fields : [];
  }

  // --- resolution -----------------------------------------------------------

  /* Resolve every field of an operation against what the operator has entered
   * so far, then hide what show_if excludes.
   *
   * Returns { values, hidden, supplied } where `values` is what would reach the
   * scripts, `hidden` marks fields the form should not show, and `supplied`
   * records what the operator actually gave — the distinction `required` turns
   * on, since a required field ignores its own default.
   *
   * The hiding loop iterates because conditions chain: registry_username is
   * shown only when registry_needs_credentials is true, and that field is
   * itself hidden for the internal replication types. */
  function resolve(schema, op, input) {
    var fields = operationFields(schema, op);
    var values = {}, hidden = {}, supplied = {};

    fields.forEach(function (name) {
      var has = Object.prototype.hasOwnProperty.call(input, name) && input[name] !== undefined;
      supplied[name] = has;
      values[name] = normalise(schema, name, has ? input[name] : prop(schema, name, 'default'));
      hidden[name] = false;
    });

    var changed = true, rounds = 0;
    while (changed && rounds < 10) {
      changed = false;
      rounds += 1;
      fields.forEach(function (name) {
        if (hidden[name]) return;
        var cond = conditions(schema, name, 'show_if');
        if (!cond) return;
        var holds = Object.keys(cond).every(function (k) {
          return String(values[k]) === String(cond[k]);
        });
        if (holds) return;
        var absent = prop(schema, name, 'absent_value');
        values[name] = absent !== '' ? absent : prop(schema, name, 'default');
        hidden[name] = true;
        changed = true;
      });
    }

    return { values: values, hidden: hidden, supplied: supplied };
  }

  function isRequired(schema, name, state) {
    if (prop(schema, name, 'required') === 'true') return true;
    var cond = conditions(schema, name, 'required_if');
    if (!cond) return false;
    return Object.keys(cond).every(function (k) {
      return String(state.values[k]) === String(cond[k]);
    });
  }

  // --- validation -----------------------------------------------------------

  var DATE_DDMM = /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2}):(\d{2})$/;
  var DATE_ISO  = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/;

  function datetimeFormat(schema, name) {
    return prop(schema, name, 'input_format') || 'YYYY-MM-DDTHH:mm:ss';
  }

  function checkDatetime(schema, name, value) {
    var fmt = datetimeFormat(schema, name), m, d, mo, h, mi, s;
    if (fmt === 'DD/MM/YYYY HH:mm:ss') {
      m = DATE_DDMM.exec(value);
      if (!m) return 'must be DD/MM/YYYY HH:MM:SS exactly as MyITSM shows it';
      d = +m[1]; mo = +m[2]; h = +m[4]; mi = +m[5]; s = +m[6];
    } else {
      m = DATE_ISO.exec(value);
      if (!m) return 'must be ISO 8601 (YYYY-MM-DDTHH:MM:SS)';
      mo = +m[2]; d = +m[3]; h = +m[4]; mi = +m[5]; s = +m[6];
    }
    if (mo < 1 || mo > 12) return 'has an invalid month: ' + mo;
    if (d < 1 || d > 31)   return 'has an invalid day: ' + d;
    if (h > 23)            return 'has an invalid hour: ' + h;
    if (mi > 59)           return 'has an invalid minute: ' + mi;
    if (s > 59)            return 'has an invalid second: ' + s;
    return null;
  }

  /* Render a datetime into the ISO 8601 the pipeline stores. The payload
   * carries what the operator pasted; the shim does this same conversion. */
  function toIso(schema, name, value) {
    if (!value) return value;
    if (datetimeFormat(schema, name) !== 'DD/MM/YYYY HH:mm:ss') return value;
    var m = DATE_DDMM.exec(value);
    if (!m) return value;
    return m[3] + '-' + m[2] + '-' + m[1] + 'T' + m[4] + ':' + m[5] + ':' + m[6];
  }

  function validateField(schema, name, state) {
    var value = state.values[name];
    var required = isRequired(schema, name, state);
    var allowEmpty = prop(schema, name, 'allow_empty') === 'true';

    if (required) {
      if (!state.supplied[name]) {
        return allowEmpty
          ? 'must be supplied — send an empty value if that is intentional'
          : 'is required';
      }
      if (!allowEmpty && value === '') return 'is required and must not be empty';
    }
    if (value === '' || value === undefined || value === null) return null;

    switch (prop(schema, name, 'type')) {
      case 'boolean':
        if (value !== 'true' && value !== 'false') return 'must be true or false';
        break;
      case 'integer':
        if (!/^-?\d+$/.test(value)) return 'must be an integer';
        break;
      case 'datetime': {
        var e = checkDatetime(schema, name, value);
        if (e) return e;
        break;
      }
      case 'email':
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) return 'is not a valid email address';
        break;
      case 'url':
        if (!/^https?:\/\//.test(value)) return 'must be a URL';
        break;
      case 'enum': {
        var opts = list(schema, name, 'options');
        if (opts.indexOf(value) === -1 &&
            value !== prop(schema, name, 'absent_value') &&
            value !== prop(schema, name, 'default')) {
          return 'must be one of: ' + opts.join(', ');
        }
        break;
      }
    }

    var pattern = prop(schema, name, 'pattern');
    if (pattern) {
      // The schema's patterns are POSIX ERE; the subset in use is also valid
      // JavaScript. A pattern JS cannot compile is reported rather than
      // silently skipped, so the two engines cannot quietly disagree.
      try {
        if (!new RegExp(pattern).test(value)) return 'does not match the required format';
      } catch (err) {
        return 'has a pattern this browser cannot evaluate (' + pattern + ')';
      }
    }

    var deny = list(schema, name, 'deny_prefix');
    for (var i = 0; i < deny.length; i++) {
      if (value.indexOf(deny[i]) === 0) {
        return 'may not start with "' + deny[i] + '" — that prefix is reserved';
      }
    }
    return null;
  }

  /* Every visible field's error, keyed by field name. Hidden fields are never
   * validated and never required — same as the shim.
   *
   * The two structural checks below exist because the shim has them. The form
   * itself cannot produce an unknown field — it builds the payload from the
   * schema — but this function is a public entry point that OpsDash and the
   * parity suite also call, and an engine that quietly accepts what the pipeline
   * will reject is worse than no engine at all. The merged case file caught all
   * three of these on its first run. */
  function validate(schema, op, input) {
    var errors = {};

    if (!schema.operations || !schema.operations[op]) {
      return {
        errors: { _operation: 'Unknown operation "' + op + '"' },
        state: { values: {}, hidden: {}, supplied: {} },
        ok: false
      };
    }

    var fields = operationFields(schema, op);
    Object.keys(input || {}).forEach(function (key) {
      if (fields.indexOf(key) !== -1) return;
      errors[key] = schema.fields && schema.fields[key]
        ? 'is not accepted by operation "' + op + '"'
        : 'is not a field declared in the schema';
    });

    var state = resolve(schema, op, input);
    fields.forEach(function (name) {
      if (state.hidden[name]) return;
      var e = validateField(schema, name, state);
      if (e) errors[name] = e;
    });
    return { errors: errors, state: state, ok: Object.keys(errors).length === 0 };
  }

  // --- payload --------------------------------------------------------------

  /* Only visible fields, and only those worth sending.
   *
   * An empty value is omitted so the schema's default applies — sending
   * lifecycle:"" would override "dev" with nothing and hand the script an empty
   * INPUT_LIFECYCLE. The exception is a required allow_empty field like
   * cost_center, where empty is a real answer meaning non-billable and its
   * absence is what the shim rejects. */
  function buildPayload(schema, op, input) {
    var state = resolve(schema, op, input);
    var payload = {};
    operationFields(schema, op).forEach(function (name) {
      if (state.hidden[name]) return;
      var value = state.values[name];
      var mustSend = isRequired(schema, name, state) &&
                     prop(schema, name, 'allow_empty') === 'true';
      if (value === '' && !mustSend) return;
      payload[name] = value;
    });
    return payload;
  }

  root.SchemaForm = {
    resolve: resolve,
    isRequired: isRequired,
    validate: validate,
    buildPayload: buildPayload,
    toIso: toIso,
    operationFields: operationFields
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
