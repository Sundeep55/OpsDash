/**
 * The request-schema rule engine, as an ES module.
 *
 * static/js/vendor/schema-form.js is a byte-for-byte copy of
 * pages/schema-form.js in the pipeline repository -- the same rules the GitLab
 * Pages form applies, and the same rules pipeline-scripts/load-payload.sh
 * enforces on the other side. It is deliberately not edited here:
 * tools/check_schema_form_drift.py fails the build if the two copies differ, so
 * the two surfaces cannot start disagreeing about what a valid request is.
 *
 * It is an IIFE that assigns to globalThis rather than a module, because it also
 * has to run from a plain <script> tag in an airgapped static site with no build
 * step. Importing it for its side effect and re-exporting is the whole adaptor.
 *
 * Why vendored at all, when the *schema* is fetched live: the schema is data and
 * changes when someone merges a field, so it must not be baked into the image.
 * The engine is code, ships with the image like every other module here, and a
 * page that downloaded its own validation logic from another project at runtime
 * would be a considerably worse idea.
 */
import '../vendor/schema-form.js';

export const SchemaForm = globalThis.SchemaForm;
