/* =============================================================================
 * app.js — DOM wiring for the onboarding form.
 *
 * All the rules live in schema-form.js. This file only renders them and talks
 * to GitLab. Anything that decides whether a value is acceptable belongs there,
 * not here, so the browser and the pipeline shim stay in step.
 *
 * Two data files, both generated at build time by tools/build-pages.sh:
 *   schema.json  — request-schema.yaml, converted
 *   index.json   — the tenants and namespaces that exist as of the last merge
 * ============================================================================= */
(function () {
  'use strict';

  var SCHEMA = null, INDEX = null, CONFIG = {};
  var operation = null;
  var input = {};                                   // what the operator has typed
  var CFG_KEY = 'onboarding-form-config';

  var $ = function (id) { return document.getElementById(id); };

  // --- boot -----------------------------------------------------------------

  Promise.all([
    fetch('schema.json').then(function (r) { return r.json(); }),
    fetch('index.json').then(function (r) { return r.json(); }).catch(function () { return null; }),
    fetch('config.json').then(function (r) { return r.json(); }).catch(function () { return {}; })
  ]).then(function (res) {
    SCHEMA = res[0];
    INDEX = res[1] || { clusters: {} };
    CONFIG = res[2] || {};
    renderOperations();
    renderFreshness();
    loadConfig();
  }).catch(function (e) {
    document.querySelector('main').innerHTML =
      '<div class="card"><p class="err">Could not load schema.json — ' + esc(String(e)) + '</p></div>';
  });

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function renderFreshness() {
    if (!INDEX.generated_at) return;
    // Shown because the index is only as current as the last merge to main.
    // A namespace created by a pipeline that has not been merged yet is not here.
    $('freshness').textContent =
      'Tenant and namespace lists are as of ' + INDEX.generated_at +
      (INDEX.commit ? ' (' + INDEX.commit + ')' : '') + '.';
  }

  // --- step 1 ---------------------------------------------------------------

  function renderOperations() {
    var box = $('operations');
    box.innerHTML = '';
    Object.keys(SCHEMA.operations).forEach(function (op) {
      var meta = SCHEMA.operations[op];
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'op';
      b.setAttribute('aria-pressed', 'false');
      b.innerHTML = '<b>' + esc(meta.title || op) + '</b>' +
                    (meta.description ? '<span>' + esc(meta.description) + '</span>' : '');
      b.addEventListener('click', function () { chooseOperation(op); });
      b.dataset.op = op;
      box.appendChild(b);
    });
  }

  function chooseOperation(op) {
    operation = op;
    input = {};
    Array.prototype.forEach.call($('operations').children, function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.op === op));
    });
    $('form-card').hidden = false;
    $('submit-card').hidden = false;
    render();
  }

  // --- index lookups --------------------------------------------------------

  function tenantsIn(cluster) {
    var c = INDEX.clusters && INDEX.clusters[cluster];
    return c ? Object.keys(c).sort() : [];
  }

  function tenantRecord(cluster, tenant) {
    var c = INDEX.clusters && INDEX.clusters[cluster];
    return (c && c[tenant]) || null;
  }

  function namespacesIn(cluster, tenant) {
    var t = tenantRecord(cluster, tenant);
    return t && t.namespaces ? t.namespaces.slice().sort() : [];
  }

  function optionsFor(name, state) {
    var src = SCHEMA.fields[name].source;
    if (!src) return null;
    if (src.index === 'tenants')    return tenantsIn(state.values.target_cluster);
    if (src.index === 'namespaces') return namespacesIn(state.values.target_cluster, state.values.tenant_name);
    return null;
  }

  // --- step 2 ---------------------------------------------------------------

  function render() {
    var state = SchemaForm.resolve(SCHEMA, operation, input);
    renderContext(state);
    renderForm(state);
    renderSubmit(state);
  }

  /* The one rule the schema cannot express, because it depends on what is in the
   * repository rather than on the request: an existing tenant must name its
   * namespace. scaffold-namespace.sh refuses the request otherwise, and without
   * the index the operator only finds out from a failed pipeline. */
  function existingTenantNeedsNamespace(state) {
    // Only namespace.create. Update and decommission declare namespace_name as
    // required in the schema, so the engine already covers them; DevSpace does
    // not offer the field at all.
    if (operation !== 'namespace.create') return false;
    var t = state.values.tenant_name;
    if (!t) return false;
    return !!tenantRecord(state.values.target_cluster, t) && !state.values.namespace_name;
  }

  function renderContext(state) {
    var el = $('context');
    var fields = SchemaForm.operationFields(SCHEMA, operation);
    if (fields.indexOf('tenant_name') === -1 || !state.values.tenant_name) { el.hidden = true; return; }

    var rec = tenantRecord(state.values.target_cluster, state.values.tenant_name);
    el.hidden = false;
    if (rec) {
      el.className = 'context';
      el.innerHTML = '<strong>Existing tenant.</strong> ' +
        esc(state.values.tenant_name) + ' has ' + rec.namespaces.length +
        ' namespace' + (rec.namespaces.length === 1 ? '' : 's') + '. ' +
        (fields.indexOf('namespace_name') !== -1
          ? 'Pick one to update, or type a new name to add one.'
          : '');
    } else {
      el.className = 'context is-new';
      el.innerHTML = '<strong>New tenant.</strong> ' + esc(state.values.tenant_name) +
        ' does not exist yet and will be created. A four-character suffix is added by the pipeline.';
    }
  }

  function renderForm(state) {
    var form = $('request-form');
    var focused = document.activeElement ? document.activeElement.dataset : null;
    var focusName = focused ? focused.field : null;
    var selStart = null;
    if (focusName && document.activeElement.setSelectionRange) {
      try { selStart = document.activeElement.selectionStart; } catch (e) { /* not a text input */ }
    }

    form.innerHTML = '';
    var fields = SchemaForm.operationFields(SCHEMA, operation);
    var groups = SCHEMA.groups || [];

    groups.forEach(function (g) {
      var mine = fields.filter(function (n) {
        return SCHEMA.fields[n].group === g.id && !state.hidden[n];
      });
      if (!mine.length) return;

      var fs = document.createElement('fieldset');
      fs.className = 'group';
      var lg = document.createElement('legend');
      lg.textContent = g.title;
      fs.appendChild(lg);
      mine.forEach(function (n) { fs.appendChild(renderField(n, state)); });
      form.appendChild(fs);
    });

    if (focusName) {
      var again = form.querySelector('[data-field="' + focusName + '"]');
      if (again) {
        again.focus();
        if (selStart !== null && again.setSelectionRange) {
          try { again.setSelectionRange(selStart, selStart); } catch (e) { /* ignore */ }
        }
      }
    }
  }

  function renderField(name, state) {
    var f = SCHEMA.fields[name];
    var wrap = document.createElement('div');
    wrap.className = 'field' + (f.type === 'boolean' ? ' bool' : '');

    var required = SchemaForm.isRequired(SCHEMA, name, state, operation);
    var value = state.values[name];
    var control;

    if (f.type === 'boolean') {
      control = document.createElement('input');
      control.type = 'checkbox';
      control.checked = value === 'true';
      control.addEventListener('change', function () {
        input[name] = control.checked ? 'true' : 'false';
        render();
      });
    } else if (f.type === 'enum') {
      control = document.createElement('select');
      (f.options || []).forEach(function (o) {
        var opt = document.createElement('option');
        opt.value = o; opt.textContent = o;
        if (o === value) opt.selected = true;
        control.appendChild(opt);
      });
      if ((f.options || []).indexOf(value) === -1) {
        var cur = document.createElement('option');
        cur.value = value; cur.textContent = value || '(none)';
        cur.selected = true;
        control.insertBefore(cur, control.firstChild);
      }
      control.addEventListener('change', function () { input[name] = control.value; render(); });
    } else {
      control = document.createElement('input');
      control.type = f.type === 'email' ? 'email' : (f.type === 'url' ? 'url' : 'text');
      control.value = state.supplied[name] ? (input[name] || '') : '';
      if (f.type === 'datetime') control.placeholder = 'DD/MM/YYYY HH:MM:SS';

      // A picklist that still accepts free text: an existing tenant is chosen,
      // a new one is typed. This is what stops operators writing names down
      // before triggering.
      var opts = optionsFor(name, state);
      if (opts && opts.length) {
        var listId = 'list-' + name;
        var dl = document.createElement('datalist');
        dl.id = listId;
        opts.forEach(function (o) {
          var opt = document.createElement('option');
          opt.value = o;
          dl.appendChild(opt);
        });
        control.setAttribute('list', listId);
        wrap.appendChild(dl);
      }
      control.addEventListener('input', function () { input[name] = control.value; render(); });

      // Case folding happens on blur, not per keystroke. Rewriting the value
      // under the cursor as someone types is jarring and fights the caret; but
      // leaving the box showing "acXYme" while the pipeline receives "acxyme"
      // means the operator has to cross-check the payload preview to know what
      // they actually sent. `change` fires on blur, and only if the value moved.
      control.addEventListener('change', function () {
        var rule = SCHEMA.fields[name].normalise;
        if (rule === 'lower')      input[name] = control.value.toLowerCase();
        else if (rule === 'upper') input[name] = control.value.toUpperCase();
        else return;
        render();
      });
    }

    control.dataset.field = name;
    control.id = 'f-' + name;

    var label = document.createElement('label');
    label.setAttribute('for', control.id);
    label.innerHTML = esc(f.label || name) + (required ? '<span class="req" title="required">*</span>' : '') +
      (f.description ? '<span class="desc">' + esc(f.description) + '</span>' : '');

    if (f.type === 'boolean') { wrap.appendChild(control); wrap.appendChild(label); }
    else { wrap.appendChild(label); wrap.appendChild(control); }

    // Errors are shown once the operator has touched the field, so a fresh form
    // is not a wall of red.
    if (state.supplied[name]) {
      var res = SchemaForm.validate(SCHEMA, operation, input);
      if (res.errors[name]) {
        wrap.className += ' bad';
        var e = document.createElement('div');
        e.className = 'err';
        e.textContent = (f.label || name) + ' ' + res.errors[name];
        wrap.appendChild(e);
      }
    }
    return wrap;
  }

  // --- step 3 ---------------------------------------------------------------

  function problems(state) {
    var res = SchemaForm.validate(SCHEMA, operation, input);
    var out = Object.keys(res.errors).map(function (n) {
      return (SCHEMA.fields[n].label || n) + ' ' + res.errors[n];
    });
    if (existingTenantNeedsNamespace(state)) {
      out.push('Namespace is required for an existing tenant — pick one to update, or type a new name.');
    }
    return out;
  }

  function renderSubmit(state) {
    var payload = SchemaForm.buildPayload(SCHEMA, operation, input);
    var compact = JSON.stringify(payload);
    $('payload').textContent = JSON.stringify(payload, null, 2);

    // The payload travels as a single CI input value, so its size is worth
    // showing rather than leaving anyone to wonder. Every fixed-size request is
    // under 800 bytes; only a registry mirror grows, because the image list is
    // comma-separated and unbounded.
    var bytes = compact.length;
    $('payload-size').textContent = bytes + ' bytes';
    $('payload-size').className = bytes > 8000 ? 'hint bad' : 'hint';

    var probs = problems(state);
    var box = $('problems');
    if (probs.length) {
      box.hidden = false;
      box.innerHTML = '<strong>Not ready to send:</strong><ul>' +
        probs.map(function (p) { return '<li>' + esc(p) + '</li>'; }).join('') + '</ul>';
    } else {
      box.hidden = true;
    }
    $('trigger').disabled = probs.length > 0;
  }

  $('copy').addEventListener('click', function () {
    var text = JSON.stringify(SchemaForm.buildPayload(SCHEMA, operation, input));
    navigator.clipboard.writeText(text).then(function () {
      say('Copied. Paste as REQUEST_PAYLOAD, and set OPERATION to "' + operation + '".', 'ok');
    }).catch(function () {
      // Clipboard access can be refused; falling back to selection means the
      // operator is never stuck.
      var pre = $('payload');
      pre.parentElement.open = true;
      var r = document.createRange();
      r.selectNodeContents(pre);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
      say('Select-and-copy the payload above (clipboard access was refused).', 'bad');
    });
  });

  function say(msg, kind) {
    var s = $('status');
    s.textContent = msg;
    s.className = 'status' + (kind ? ' ' + kind : '');
  }

  // --- trigger --------------------------------------------------------------

  /* Where to send the request comes from config.json, which the pages job wrote
   * from GitLab's own predefined variables. The operator is never asked for it.
   * Only the token is theirs, and only because a published static file is not a
   * place to keep one. */
  function config() {
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(CFG_KEY) || '{}'); } catch (e) { /* ignore */ }
    return {
      host:    CONFIG.gitlab_url || saved.host || '',
      project: CONFIG.project_id || CONFIG.project_path || saved.project || '',
      ref:     CONFIG.ref || saved.ref || 'main',
      token:   saved.token || ''
    };
  }

  function loadConfig() {
    var c = config();
    var baked = !!(CONFIG.gitlab_url && (CONFIG.project_id || CONFIG.project_path));

    $('cfg-token').value = c.token || '';
    $('cfg-host').value = c.host || '';
    $('cfg-project').value = c.project || '';
    $('cfg-ref').value = c.ref || 'main';

    // When the build supplied them, show them as read-only facts rather than
    // as questions. They are only editable at all so the form still works when
    // opened from a local directory during development.
    $('cfg-target').hidden = !baked;
    $('cfg-manual').hidden = baked;
    if (baked) {
      // The path reads better than the numeric id; the id is what the API call
      // uses, since it needs no encoding.
      $('cfg-target').textContent =
        'Requests go to ' + (CONFIG.project_path || c.project) + ' on ' + c.host + ', branch ' + c.ref + '.';
    }
  }

  $('cfg-save').addEventListener('click', function () {
    // Only ever the token and any manual overrides; config.json wins when present.
    localStorage.setItem(CFG_KEY, JSON.stringify({
      host: $('cfg-host').value.trim().replace(/\/+$/, ''),
      project: $('cfg-project').value.trim(),
      ref: $('cfg-ref').value.trim() || 'main',
      token: $('cfg-token').value
    }));
    say('Saved to this browser.', 'ok');
  });

  $('cfg-clear').addEventListener('click', function () {
    var c = config();
    delete c.token;
    localStorage.setItem(CFG_KEY, JSON.stringify(c));
    $('cfg-token').value = '';
    say('Token cleared.', 'ok');
  });

  $('trigger').addEventListener('click', function () {
    var c = config();
    if (!c.host || !c.project) {
      say('This site was not built by the pipeline, so it does not know which GitLab to talk to. Fill in the settings below, or use Copy.', 'bad');
      return;
    }
    if (!c.token) {
      say('Add your personal access token under Trigger settings, or use Copy instead — Copy needs nothing.', 'bad');
      return;
    }
    var url = c.host + '/api/v4/projects/' + encodeURIComponent(c.project) + '/pipeline';
    var body = {
      ref: c.ref || 'main',
      inputs: {
        OPERATION: operation,
        REQUEST_PAYLOAD: JSON.stringify(SchemaForm.buildPayload(SCHEMA, operation, input))
      }
    };
    say('Triggering…');
    $('trigger').disabled = true;

    fetch(url, {
      method: 'POST',
      headers: { 'PRIVATE-TOKEN': c.token, 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; });
    }).then(function (r) {
      $('trigger').disabled = false;
      if (r.ok && r.body && r.body.web_url) {
        var s = $('status');
        s.className = 'status ok';
        s.textContent = 'Pipeline #' + r.body.id + ' started — ';
        var a = document.createElement('a');
        a.href = r.body.web_url;
        a.target = '_blank';
        a.rel = 'noopener';
        a.textContent = 'open it';
        s.appendChild(a);
      } else {
        say('GitLab refused it (' + r.status + '): ' +
            ((r.body && (r.body.message || r.body.error)) || 'unknown') +
            ' — use Copy instead.', 'bad');
      }
    }).catch(function (e) {
      $('trigger').disabled = false;
      // The likely cause is the browser blocking a cross-origin POST to the API.
      // Copy still works, so this is a degraded path rather than a dead end.
      say('Could not reach the API from this page (' + e.message +
          '). This is usually a cross-origin restriction — use Copy instead.', 'bad');
    });
  });

})();
