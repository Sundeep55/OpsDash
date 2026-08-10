Genrate a gitlab ci file with 100 inputs. use something like this script for reference but evetually give me a script

```
#!/usr/bin/env python3
"""Generate a .gitlab-ci.yml with N inputs, to find where your instance stops accepting them.

The public docs say "a pipeline can take up to 20 inputs", but a real file with 25
defined inputs runs fine today -- so it is unclear whether the cap applies to inputs
*defined* in spec:inputs or inputs *supplied* at trigger time. Limits also move
between GitLab versions, so your instance at your version is the only authority.

    python3 generate.py 100 > .gitlab-ci.yml

Then work through TESTPLAN.md.
"""
import sys

n = int(sys.argv[1]) if len(sys.argv) > 1 else 100

print("# GENERATED probe file -- commit to a scratch project, not a real one.")
print("spec:")
print("  inputs:")
# One realistic mix: strings, booleans, enums -- same shapes as the real pipeline.
for i in range(n):
    name = f"PROBE_{i:03d}"
    if i % 5 == 0:
        print(f"    {name}:")
        print(f'      description: "Probe input {i} (boolean)."')
        print(f"      type: boolean")
        print(f"      default: false")
    elif i % 5 == 1:
        print(f"    {name}:")
        print(f'      description: "Probe input {i} (enum)."')
        print(f'      options: ["alpha", "beta", "gamma"]')
        print(f'      default: "alpha"')
    else:
        print(f"    {name}:")
        print(f'      description: "Probe input {i} (string)."')
        print(f'      default: "default-{i}"')

# The dual-path input the real design would use.
print("    REQUEST_JSON:")
print('      description: "Full request document as JSON. Overrides the fields above when set."')
print('      default: ""')
print("---")
print("""
stages: [probe]

show-inputs:
  stage: probe
  image: busybox
  script:
    - echo "pipeline created successfully with the inputs below"
    - echo "REQUEST_JSON=$INPUT_REQUEST_JSON"
    - echo "PROBE_000=$INPUT_PROBE_000  PROBE_001=$INPUT_PROBE_001"
  variables:
    INPUT_REQUEST_JSON: $[[ inputs.REQUEST_JSON ]]""")
for i in range(min(n, 3)):
    print(f"    INPUT_PROBE_{i:03d}: $[[ inputs.PROBE_{i:03d} ]]")
```




# Does your GitLab accept 100 inputs?

The docs say **"a pipeline can take up to 20 inputs"**, but repo 1 defines 25 and
runs fine today. So it is unclear whether the cap applies to inputs *defined* in
`spec:inputs` or inputs *supplied* at trigger time — and the answer decides
whether "one CI file for everything" is viable.

Limits also move between GitLab versions. Your instance at your version is the
only authority. This takes about fifteen minutes.

Use a throwaway project. Record your GitLab version first (`/help`), because the
answer is only valid for that version.

---

## 1. Can 100 inputs even be *defined*?

Commit `gitlab-ci-100-inputs.yml` as `.gitlab-ci.yml`, then open
**Build → Pipeline editor**.

- **Validates** → the cap is not on definitions. Go to step 2.
- **"exceeds the maximum" / lint error** → the cap *is* on definitions. Skip to
  step 5 and bisect with the 21- and 25-input files.

## 2. Does the web form render them?

Open **Build → Pipelines → Run pipeline**.

- Do all 100 fields appear, or does it truncate?
- How usable is it? (This is the question that matters even if it *works* —
  see the note at the bottom.)
- Click **Run pipeline** without changing anything. Does it start?

That last click is the important one: the form submits values for every field,
so if the 20 cap applies to *supplied* inputs, this is where it fails.

## 3. Trigger via API with only a few inputs set

```bash
curl -X POST \
  -H "PRIVATE-TOKEN: $TOKEN" \
  "https://gitlab.local/api/v4/projects/$PROJECT_ID/pipeline?ref=main" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"PROBE_002": "set-by-api", "PROBE_003": "also-set"}}'
```

Expect success. If this fails, the cap is on definitions and step 1 should have
caught it.

## 4. Trigger via API with more than 20 inputs set

```bash
python3 - <<'EOF' > /tmp/payload.json
import json
print(json.dumps({"inputs": {f"PROBE_{i:03d}": f"v{i}" for i in range(2, 40)}}))
EOF

curl -X POST -H "PRIVATE-TOKEN: $TOKEN" \
  "https://gitlab.local/api/v4/projects/$PROJECT_ID/pipeline?ref=main" \
  -H "Content-Type: application/json" -d @/tmp/payload.json
```

- **Succeeds** → no practical cap on supplied inputs either.
- **Fails** → the cap is on supplied values. Note the exact number in the error;
  that is your real ceiling.

## 5. Bisect, if anything failed

Try `gitlab-ci-21-inputs.yml` then `gitlab-ci-25-inputs.yml`. Since the real
repo runs 25 today, 25 should pass — if 21 fails but the real repo works, the
difference is somewhere other than the count, and worth understanding before
designing around it.

## 6. Confirm the JSON escape hatch

Every generated file carries a `REQUEST_JSON` input. Trigger with it alone:

```bash
curl -X POST -H "PRIVATE-TOKEN: $TOKEN" \
  "https://gitlab.local/api/v4/projects/$PROJECT_ID/pipeline?ref=main" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"REQUEST_JSON": "{\"type\":\"add-namespace\",\"tenant\":\"acme\",\"operators\":[\"argocd\",\"loki\"]}"}}'
```

Check the job log echoes it back intact. A string input must be under 1 MB and
"a string inside an input" under 1 KB, so confirm a realistic full request fits —
that is the constraint that actually binds this path, not the input count.

---

## What to report back

| | |
|---|---|
| GitLab version | |
| 100 inputs defined — lint | pass / fail + message |
| Web form renders 100 | yes / truncated / unusable |
| Run pipeline, all defaults | pass / fail |
| API, 2 inputs | pass / fail |
| API, 38 inputs | pass / fail + message |
| REQUEST_JSON round-trip | intact / truncated |

---

## The question the test does not answer

Even if 100 inputs is permitted, **do you want a 100-field web form?** That form
is the fallback for when the dashboard is down — the path that has to work when
someone is under pressure. A hundred fields is arguably worse than today's
twenty-five.

Worth considering regardless of the result: keep the web form to the ~19
genuinely common fields, and let `REQUEST_JSON` carry the full surface for the
dashboard and for automation. One file, one pipeline, a usable fallback, and no
input ceiling on the rich path.