Here are the issues i see

1. portal page is blank with this issue in web console

```
Uncaught SyntaxError: https://vuejs.org/error-reference/#compiler-30
    s6 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    ae https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    ae https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    Vue https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    o0 https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    <anonymous> https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:8
    <anonymous> https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:13
    az https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:13
    iP https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    iO https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    q https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    q https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    q https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    U https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    x https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    ea https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    mount https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    mount https://ops-portal-xxxx.corp/static/js/vue.global.prod.70247c205655.js:7
    <anonymous> https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js:258
vue.global.prod.70247c205655.js:7:59381

```

2. pod logs
```
Applying database migrations...
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, dashboard, sessions
Running migrations:
  Applying dashboard.0002_systemsyncstatus_sync_started_at... OK
  Applying dashboard.0003_remove_registrymirror_provider_name_and_more... OK
  Applying dashboard.0004_remove_gpuallocation_gpu_tier_and_more... OK
Ensuring Admin Superuser exists...
Superuser already exists. Skipping creation.
Starting Gunicorn Web Server with custom access logging...
[2026-08-06 08:58:08 +0000] [1] [INFO] Starting gunicorn 23.0.0
[2026-08-06 08:58:08 +0000] [1] [INFO] Listening at: http://0.0.0.0:8000 (1)
[2026-08-06 08:58:08 +0000] [1] [INFO] Using worker: gthread
[2026-08-06 08:58:08 +0000] [9] [INFO] Booting worker with pid: 9
[2026-08-06 08:58:08 +0000] [10] [INFO] Booting worker with pid: 10
[2026-08-06 08:58:08 +0000] [11] [INFO] Booting worker with pid: 11
100.120.0.2 - - [06/Aug/2026:08:58:35 +0000] "GET /accounts/login/?next=/ HTTP/1.1" 200 2605 "https://ops-portal-xxxx.corp/accounts/login/?next=/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:35 +0000] "GET /static/css/tailwind.25f430a7caab.css HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/accounts/login/?next=/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:35 +0000] "GET /favicon.ico HTTP/1.1" 404 179 "https://ops-portal-xxxx.corp/accounts/login/?next=/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "POST /accounts/login/ HTTP/1.1" 302 0 "https://ops-portal-xxxx.corp/accounts/login/?next=/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET / HTTP/1.1" 200 120282 "https://ops-portal-xxxx.corp/accounts/login/?next=/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/css/utilities.generated.0b49f37663ec.css HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/css/components.564c3d44ca2e.css HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/app.727fe253c116.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/vue.global.prod.70247c205655.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/lib/api.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/lib/util.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/composables/useAnalytics.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/composables/usePaginatedList.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/components/SiglumTree.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/composables/useSelection.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/composables/useSync.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/components/TableSkeleton.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/components/DetailSection.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/components/CopyButton.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/ui_config.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /static/js/lib/clipboard.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/components/CopyButton.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:37 +0000] "GET /favicon.ico HTTP/1.1" 404 179 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:44 +0000] "GET / HTTP/1.1" 200 120282 "https://ops-portal-xxxx.corp/accounts/login/?next=/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:44 +0000] "GET /favicon.ico HTTP/1.1" 404 179 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:58:48 +0000] "GET /static/css/tailwind.25f430a7caab.css HTTP/1.1" 200 0 "-" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET / HTTP/1.1" 200 120282 "https://ops-portal-xxxx.corp/accounts/login/?next=/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/css/tailwind.25f430a7caab.css HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/css/utilities.generated.0b49f37663ec.css HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/css/components.564c3d44ca2e.css HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/vue.global.prod.70247c205655.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/app.727fe253c116.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/lib/api.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/lib/util.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/composables/usePaginatedList.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/composables/useAnalytics.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/composables/useSelection.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/composables/useSync.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/components/SiglumTree.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/components/CopyButton.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/components/DetailSection.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/components/TableSkeleton.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/ui_config.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/app.727fe253c116.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /static/js/lib/clipboard.js HTTP/1.1" 200 0 "https://ops-portal-xxxx.corp/static/js/components/CopyButton.js" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
100.120.0.2 - - [06/Aug/2026:08:59:03 +0000] "GET /favicon.ico HTTP/1.1" 404 179 "https://ops-portal-xxxx.corp/" "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
```

3. the chart names i provided like namesapce-provisioner, egress, service-mesh, etc are all masked chart names, so i would also say to bring all these things to settings so it is easy for my to update and run it in actual env. the values/tenant metadata files content within though is not masked so only file anames needs to be brought to a common place.
