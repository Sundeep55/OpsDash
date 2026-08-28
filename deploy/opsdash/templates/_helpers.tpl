{{/*
Name helpers. Standard Helm shapes, with one deliberate difference: see
opsdash.selectorLabels.
*/}}

{{- define "opsdash.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "opsdash.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "opsdash.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Selector labels.

Only `app`, and only ever `app`. The flat manifest selected on `app: ops-portal`
and a Deployment's spec.selector is immutable, so emitting the conventional
app.kubernetes.io/name pair here would make `helm upgrade` over the existing
Deployment fail with "field is immutable" -- and ArgoCD would sit permanently
OutOfSync on an object it cannot patch.

The recommended labels still go on metadata via opsdash.labels, where they are
free to change.
*/}}
{{- define "opsdash.selectorLabels" -}}
app: {{ include "opsdash.fullname" . }}
{{- end -}}

{{- define "opsdash.labels" -}}
{{ include "opsdash.selectorLabels" . }}
app.kubernetes.io/name: {{ include "opsdash.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ include "opsdash.chart" . }}
{{- end -}}

{{- define "opsdash.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "opsdash.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "opsdash.secretName" -}}
{{- default (printf "%s-secret" (include "opsdash.fullname" .)) .Values.secret.name -}}
{{- end -}}

{{- define "opsdash.pvcName" -}}
{{- default (printf "%s-data" (include "opsdash.fullname" .)) .Values.persistence.existingClaim -}}
{{- end -}}

{{/*
The hostname, resolved once.

Fails the render rather than producing a Deployment whose probes cannot pass.
An empty hostname would put an empty Host header on every probe, which Django
rejects the same way it rejects a pod IP.
*/}}
{{- define "opsdash.hostname" -}}
{{- required "hostname is required: it sets ALLOWED_HOSTS, the CSRF origin, the Route host and the Host header on every HTTP probe" .Values.hostname -}}
{{- end -}}

{{/*
The SQLite path, checked against the volume it is supposed to sit on.

These are two separate values that have to agree, and when they do not the
failure is quiet and expensive: Django creates a fresh database on the
container's ephemeral filesystem, the dashboard comes up looking empty but
healthy, the sync repopulates it, and every local user and session disappears on
the next restart. Nothing logs an error at any point.

So it is a render-time failure instead.
*/}}
{{- define "opsdash.databasePath" -}}
{{- $path := required "django.databasePath is required" .Values.django.databasePath -}}
{{- $mount := required "persistence.mountPath is required" .Values.persistence.mountPath -}}
{{- if not (hasPrefix (printf "%s/" (trimSuffix "/" $mount)) $path) -}}
{{- fail (printf "django.databasePath (%s) must live under persistence.mountPath (%s), or the database is written to the container filesystem and lost on every restart" $path $mount) -}}
{{- end -}}
{{- $path -}}
{{- end -}}

{{- define "opsdash.allowedHosts" -}}
{{- default (include "opsdash.hostname" .) .Values.django.allowedHosts -}}
{{- end -}}

{{- define "opsdash.csrfTrustedOrigins" -}}
{{- default (printf "https://%s" (include "opsdash.hostname" .)) .Values.django.csrfTrustedOrigins -}}
{{- end -}}

{{/*
The HTTP probe block, shared by all three web probes.

Emitting it once is not just deduplication: the Host header has to match
ALLOWED_HOSTS on every one of them, and the flat manifest repeated the literal
hostname three times for the kubelet to get wrong independently.

Call as: include "opsdash.httpProbe" (dict "ctx" $ "path" "/healthz")
*/}}
{{- define "opsdash.httpProbe" -}}
httpGet:
  path: {{ .path }}
  port: http
  httpHeaders:
    - name: Host
      value: {{ include "opsdash.hostname" .ctx | quote }}
{{- end -}}

{{/*
envFrom, identical for both containers -- they run the same image and read the
same settings module, so a variable set for one and not the other is a bug
waiting for someone to wonder why the sidecar walks a different repo.
*/}}
{{- define "opsdash.envFrom" -}}
- configMapRef:
    name: {{ include "opsdash.fullname" . }}-config
- secretRef:
    name: {{ include "opsdash.secretName" . }}
    optional: {{ .Values.secret.optional }}
{{- end -}}
