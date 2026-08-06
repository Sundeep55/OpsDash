Here are the issues i see

1. our end has below reuirements allowed

```
# Direct dependencies
Django==4.2.30
djangorestframework==3.16.1
django-filter==25.1
drf-spectacular==0.30.0
drf-spectacular-sidecar==2026.8.1
gunicorn==23.0.0
whitenoise==6.11.0
PyYAML==6.0.3
requests==2.32.5

# Transitive -- pinned for reproducible image builds
asgiref==3.11.1
attrs==26.1.0
certifi==2026.7.22
charset-normalizer==3.4.9
idna==3.18
inflection==0.5.1
jsonschema==4.25.1
jsonschema-specifications==2025.9.1
packaging==26.2
referencing==0.36.2
rpds-py==0.27.1
sqlparse==0.5.5
uritemplate==4.2.0
urllib3==2.6.3
```

2. error when i start the process
```
python manage.py runserver
Watching for file changes with StatReloader
Performing system checks...

Exception in thread django-main-thread:
Traceback (most recent call last):
  File "/usr/lib64/python3.9/threading.py", line 980, in _bootstrap_inner
    self.run()
  File "/usr/lib64/python3.9/threading.py", line 917, in run
    self._target(*self._args, **self._kwargs)
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/utils/autoreload.py", line 64, in wrapper
    fn(*args, **kwargs)
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/core/management/commands/runserver.py", line 133, in inner_run
    self.check(display_num_errors=True)
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/core/management/base.py", line 485, in check
    all_issues = checks.run_checks(
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/core/checks/registry.py", line 88, in run_checks
    new_errors = check(app_configs=app_configs, databases=databases)
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/core/checks/urls.py", line 42, in check_url_namespaces_unique
    all_namespaces = _load_all_namespaces(resolver)
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/core/checks/urls.py", line 61, in _load_all_namespaces
    url_patterns = getattr(resolver, "url_patterns", [])
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/utils/functional.py", line 57, in __get__
    res = instance.__dict__[self.name] = self.func(instance)
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/urls/resolvers.py", line 715, in url_patterns
    patterns = getattr(self.urlconf_module, "urlpatterns", self.urlconf_module)
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/utils/functional.py", line 57, in __get__
    res = instance.__dict__[self.name] = self.func(instance)
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/urls/resolvers.py", line 708, in urlconf_module
    return import_module(self.urlconf_name)
  File "/usr/lib64/python3.9/importlib/__init__.py", line 127, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
  File "<frozen importlib._bootstrap>", line 1030, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1007, in _find_and_load
  File "<frozen importlib._bootstrap>", line 986, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 680, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 850, in exec_module
  File "<frozen importlib._bootstrap>", line 228, in _call_with_frames_removed
  File "/projects/ops-dashboard/ops_portal/urls.py", line 15, in <module>
    path('api/v2/', include('dashboard.api.urls')),
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/urls/conf.py", line 38, in include
    urlconf_module = import_module(urlconf_module)
  File "/usr/lib64/python3.9/importlib/__init__.py", line 127, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
  File "<frozen importlib._bootstrap>", line 1030, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1007, in _find_and_load
  File "<frozen importlib._bootstrap>", line 986, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 680, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 850, in exec_module
  File "<frozen importlib._bootstrap>", line 228, in _call_with_frames_removed
  File "/projects/ops-dashboard/dashboard/api/urls.py", line 9, in <module>
    path('', include('dashboard.api.internal.urls')),
  File "/projects/ops-dashboard/venv/lib64/python3.9/site-packages/django/urls/conf.py", line 38, in include
    urlconf_module = import_module(urlconf_module)
  File "/usr/lib64/python3.9/importlib/__init__.py", line 127, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
  File "<frozen importlib._bootstrap>", line 1030, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1007, in _find_and_load
  File "<frozen importlib._bootstrap>", line 986, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 680, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 850, in exec_module
  File "<frozen importlib._bootstrap>", line 228, in _call_with_frames_removed
  File "/projects/ops-dashboard/dashboard/api/internal/urls.py", line 5, in <module>
    from . import analytics, namespaces, requests, siglums, sync, tenants, users
  File "/projects/ops-dashboard/dashboard/api/internal/namespaces.py", line 9, in <module>
    from dashboard.serializers import NamespaceDetailSerializer, NamespaceListSerializer
  File "/projects/ops-dashboard/dashboard/serializers/__init__.py", line 9, in <module>
    from .core import (
  File "/projects/ops-dashboard/dashboard/serializers/core.py", line 14, in <module>
    from dashboard.gitops.sections import auto_rendered_sections, describe
  File "/projects/ops-dashboard/dashboard/gitops/__init__.py", line 16, in <module>
    from . import walker
  File "/projects/ops-dashboard/dashboard/gitops/walker.py", line 34, in <module>
    class FileLocation:
  File "/projects/ops-dashboard/dashboard/gitops/walker.py", line 42, in FileLocation
    namespace_name: str | None
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```

3. the chart names i provided like namesapce-provisioner, egress, service-mesh, etc are all masked chart names, so i would also say to bring all these things to settings so it is easy for my to update and run it in actual env. the values/tenant metadata files content within though is not masked so only file anames needs to be brought to a common place.
