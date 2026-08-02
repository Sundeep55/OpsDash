import os
import yaml
import tempfile
import zipfile
import shutil
import requests
import urllib3
from django.utils import timezone
from django.core.management.base import BaseCommand
from dashboard.models import (
    Cluster, Tenant, EgressRouter, Namespace, ResourceQuota, LimitRange, 
    GPUAllocation, ServiceMeshControlPlane, NetworkPolicy, RouteException, 
    HarborConfig, Operator, HelmDeployment, RegistryMirror, CustomResource, 
    RobotAccount, NetworkConnection, UserAccess, SystemSyncStatus
)

class Command(BaseCommand):
    help = 'Fetches GitOps YAML files from GitLab (or local fallback) and safely upserts them into the Database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repo-path',
            type=str,
            default='/projects/tools/customer-instances',
            help='Fallback local path to the GitOps cluster/tenant folders if GitLab is not configured',
        )

    def download_gitlab_repo(self, url, token, project_id, branch, ssl_verify=True):
        self.stdout.write(self.style.NOTICE(f"Connecting to GitLab: {url} (Project: {project_id}, Branch: {branch}, SSL Verify: {ssl_verify})..."))
        
        if not ssl_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        api_url = f"{url.rstrip('/')}/api/v4/projects/{project_id}/repository/archive.zip?sha={branch}"
        headers = {"PRIVATE-TOKEN": token}
        
        response = requests.get(api_url, headers=headers, stream=True, verify=ssl_verify)
        response.raise_for_status()
        
        temp_dir = tempfile.mkdtemp(prefix="gitops_sync_")
        zip_path = os.path.join(temp_dir, 'repo.zip')
        
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
            
        os.remove(zip_path)
        
        extracted_dirs = [os.path.join(temp_dir, d) for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
        if extracted_dirs:
            return extracted_dirs[0], temp_dir
            
        return temp_dir, temp_dir

    def handle(self, *args, **options):
        status = SystemSyncStatus.get_state()
        status.is_syncing = True
        status.last_message = "Fetching repository..."
        status.save()

        temp_cleanup_dir = None
        tenant_route_exceptions_found = set()

        try:
            gitlab_url = os.environ.get('GITLAB_URL')
            gitlab_token = os.environ.get('GITLAB_TOKEN')
            gitlab_project_id = os.environ.get('GITLAB_PROJECT_ID')
            gitlab_branch = os.environ.get('GITLAB_BRANCH', 'main')
            gitlab_ssl_verify = os.environ.get('GITLAB_SSL_VERIFY', 'true').lower() == 'true'

            repo_path = options['repo_path']

            if gitlab_url and gitlab_token and gitlab_project_id:
                try:
                    status.last_message = "Downloading GitLab archive..."
                    status.save()
                    repo_path, temp_cleanup_dir = self.download_gitlab_repo(
                        gitlab_url, gitlab_token, gitlab_project_id, gitlab_branch, gitlab_ssl_verify
                    )
                    self.stdout.write(self.style.SUCCESS("Successfully fetched and extracted repository from GitLab."))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"GitLab sync failed: {str(e)}"))
                    self.stdout.write(self.style.WARNING(f"Falling back to local repository path: {repo_path}"))
            else:
                self.stdout.write(self.style.NOTICE(f"GitLab environment variables missing. Using local repository path: {repo_path}"))

            if not os.path.exists(repo_path):
                self.stdout.write(self.style.ERROR(f"Directory not found: {repo_path}. Aborting sync."))
                if temp_cleanup_dir:
                    shutil.rmtree(temp_cleanup_dir)
                status.last_message = f"Directory not found: {repo_path}"
                status.is_syncing = False
                status.save()
                return

            success_count = 0
            
            active_cr_ids = set()
            active_helm_ids = set()
            active_namespace_names = set()
            active_tenant_names = set()
            
            status.last_message = "Parsing configuration files..."
            status.save()
            
            for root, dirs, files in os.walk(repo_path):
                dirs[:] = [d for d in dirs if not d.startswith('.git')]
                for file in files:
                    if file == 'egressip-pool.yaml':
                        continue

                    if not (file.endswith('.yaml') or file.endswith('.yml')):
                        continue
                    
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, repo_path).replace('\\', '/')
                    path_parts = rel_path.split('/')
                    
                    if len(path_parts) < 2:
                        continue
                        
                    cluster_name = path_parts[0]
                    is_tenant_decomm = False
                    
                    if path_parts[1] == '.decommissioned_tenants':
                        is_tenant_decomm = True
                        if len(path_parts) < 3: continue
                        tenant_name = path_parts[2]
                        ns_idx = 3
                    else:
                        tenant_name = path_parts[1]
                        ns_idx = 2

                    cluster_obj, _ = Cluster.objects.get_or_create(name=cluster_name)
                    tenant_obj, _ = Tenant.objects.get_or_create(
                        name=tenant_name,
                        defaults={'cluster': cluster_obj, 'is_decommissioned': is_tenant_decomm}
                    )
                    active_tenant_names.add(tenant_obj.name)
                    
                    if is_tenant_decomm and not tenant_obj.is_decommissioned:
                        tenant_obj.is_decommissioned = True
                        tenant_obj.save()

                    is_ns_decomm = is_tenant_decomm
                    namespace_name = None
                    
                    if '.decommissioned_namespaces' in path_parts:
                        is_ns_decomm = True
                        try:
                            idx = path_parts.index('.decommissioned_namespaces') + 1
                            if idx < len(path_parts) - 1:
                                namespace_name = path_parts[idx].split('_')[0] 
                        except IndexError:
                            pass
                    elif len(path_parts) > ns_idx + 1:
                        namespace_name = path_parts[ns_idx]

                    ns_obj = None
                    if namespace_name:
                        ns_obj, _ = Namespace.objects.get_or_create(
                            name=namespace_name,
                            defaults={
                                'tenant': tenant_obj,
                                'cluster': cluster_obj,
                                'is_decommissioned': is_ns_decomm
                            }
                        )
                        active_namespace_names.add(ns_obj.name)
                        
                        if is_ns_decomm and not ns_obj.is_decommissioned:
                            ns_obj.is_decommissioned = True
                            ns_obj.save()

                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    except Exception:
                        continue

                    if not content:
                        continue

                    try:
                        filename = file
                        
                        if 'templates' in path_parts and ns_obj:
                            for doc in yaml.safe_load_all(content):
                                if doc and 'kind' in doc and 'metadata' in doc:
                                    cr_obj, _ = CustomResource.objects.update_or_create(
                                        namespace=ns_obj,
                                        kind=doc['kind'],
                                        name=doc['metadata'].get('name', 'unknown'),
                                        defaults={'content': yaml.dump(doc, default_flow_style=False)}
                                    )
                                    active_cr_ids.add(cr_obj.id)
                            continue

                        parsed_yaml = yaml.safe_load(content)
                        if not parsed_yaml:
                            continue

                        if filename == 'tenant-metadata.yaml':
                            tenant_obj.siglum = parsed_yaml.get('siglum', tenant_obj.siglum)
                            tenant_obj.cost_center = parsed_yaml.get('billing_code', parsed_yaml.get('wbs', tenant_obj.cost_center))
                            tenant_obj.requester = parsed_yaml.get('requester', tenant_obj.requester)
                            
                            tenant_req = parsed_yaml.get('tenant_request_ticket', parsed_yaml.get('req_id', parsed_yaml.get('request_ticket')))
                            if tenant_req:
                                tenant_obj.request_ticket = tenant_req
                                
                            tenant_obj.save()
                            
                            for ns_dict in parsed_yaml.get('active_namespaces', []):
                                ns_n = ns_dict.get('name')
                                if ns_n:
                                    n_obj, _ = Namespace.objects.get_or_create(name=ns_n, defaults={'tenant': tenant_obj, 'cluster': cluster_obj})
                                    active_namespace_names.add(n_obj.name)
                                    
                                    ns_req = ns_dict.get('namespace_request_ticket', ns_dict.get('req_id', ns_dict.get('request_ticket')))
                                    if ns_req:
                                        n_obj.request_ticket = ns_req
                                        
                                    ns_lc = ns_dict.get('lifecycle')
                                    if ns_lc:
                                        n_obj.lifecycle = str(ns_lc).strip().lower()
                                        
                                    n_obj.is_decommissioned = False
                                    n_obj.save()
                                    
                                    sec_exc = ns_dict.get('security_exception')
                                    if sec_exc:
                                        RouteException.objects.update_or_create(
                                            namespace=n_obj,
                                            defaults={
                                                'is_active': True,
                                                'request_id': sec_exc.get('request_ticket', ''),
                                                'granted_at': sec_exc.get('granted_at')
                                            }
                                        )
                                        tenant_route_exceptions_found.add(n_obj.name)
                            
                            for ns_dict in parsed_yaml.get('decommissioned_namespaces', []):
                                ns_n = ns_dict.get('name')
                                if ns_n:
                                    n_obj, _ = Namespace.objects.get_or_create(name=ns_n, defaults={'tenant': tenant_obj, 'cluster': cluster_obj})
                                    active_namespace_names.add(n_obj.name)
                                    
                                    ns_req = ns_dict.get('namespace_request_ticket', ns_dict.get('req_id', ns_dict.get('request_ticket')))
                                    if ns_req:
                                        n_obj.request_ticket = ns_req
                                        
                                    n_obj.is_decommissioned = True
                                    n_obj.save()

                            active_mirrors = parsed_yaml.get('active_registry_mirrors', [])
                            if active_mirrors:
                                ns_mirrors = {}
                                for m in active_mirrors:
                                    ns_n = m.get('namespace')
                                    if ns_n:
                                        if ns_n not in ns_mirrors: ns_mirrors[ns_n] = []
                                        ns_mirrors[ns_n].append(m)
                                        
                                for ns_n, mirrors_list in ns_mirrors.items():
                                    n_obj, _ = Namespace.objects.get_or_create(name=ns_n, defaults={'tenant': tenant_obj, 'cluster': cluster_obj})
                                    active_namespace_names.add(n_obj.name)
                                    RegistryMirror.objects.filter(namespace=n_obj).delete() 
                                    for mirror in mirrors_list:
                                        RegistryMirror.objects.create(
                                            namespace=n_obj,
                                            name=mirror.get('name', 'mirror'),
                                            image=mirror.get('image', ''),
                                            endpoint_url=mirror.get('url', mirror.get('endpoint_url', ''))
                                        )

                        elif filename == 'Chart.yaml' and ns_obj:
                            for dep in parsed_yaml.get('dependencies', []):
                                hd_obj, _ = HelmDeployment.objects.update_or_create(
                                    namespace=ns_obj,
                                    chart_name=dep.get('name', 'Unknown'),
                                    defaults={'version': dep.get('version', 'Unknown')}
                                )
                                active_helm_ids.add(hd_obj.id)
                                
                        elif ns_obj:
                            prov = parsed_yaml.get('namespace-provisioner') or {}
                            
                            cso = parsed_yaml.get('egress') or {}
                            if cso:
                                ns_obj.is_cso = True
                                req_labels = cso.get('requiredLabels') or {}
                                add_labels = cso.get('additionalLabels') or {}
                                
                                extracted_lc = (
                                    req_labels.get('lifecycle') or
                                    req_labels.get('env') or
                                    add_labels.get('lifecycle') or
                                    add_labels.get('env')
                                )
                                if extracted_lc:
                                    ns_obj.lifecycle = str(extracted_lc).strip().lower()

                                ns_siglum = req_labels.get('siglum')
                                if ns_siglum:
                                    ns_obj.siglum = ns_siglum

                                for res in cso.get('egressIPResources', []):
                                    egress_name = res.get('name')
                                    egress_ips = res.get('egressIPs', [])
                                    if egress_name:
                                        router_obj, _ = EgressRouter.objects.get_or_create(name=egress_name, defaults={'cluster': cluster_obj})
                                        router_obj.egress_ips = egress_ips
                                        router_obj.provider_namespace = ns_obj 
                                        router_obj.save()
                                        
                                ns_obj.save()
                                success_count += 1
                                
                            else:
                                # FIX: The "Ghost State" CSO Reset
                                if getattr(ns_obj, 'is_cso', False):
                                    ns_obj.is_cso = False
                                    EgressRouter.objects.filter(provider_namespace=ns_obj).delete()
                                    ns_obj.save()

                            if prov:
                                req_labels = prov.get('requiredLabels') or {}
                                add_labels = prov.get('additionalLabels') or {}
                                devspace = prov.get('devspaceConfig') or {}
                                
                                extracted_lc = (
                                    req_labels.get('lifecycle') or
                                    req_labels.get('env') or
                                    add_labels.get('lifecycle') or
                                    add_labels.get('env')
                                )
                                if extracted_lc:
                                    ns_obj.lifecycle = str(extracted_lc).strip().lower()
                                
                                ns_obj.is_devspace = devspace.get('isDevspace', ns_obj.is_devspace)
                                ns_obj.devspace_user = devspace.get('devspaceUser', ns_obj.devspace_user)
                                
                                ns_siglum = req_labels.get('siglum')
                                if ns_siglum:
                                    ns_obj.siglum = ns_siglum
                                
                                egress_name = add_labels.get('egressip_name')
                                if egress_name:
                                    router_obj, _ = EgressRouter.objects.get_or_create(name=egress_name, defaults={'cluster': cluster_obj})
                                    ns_obj.egress_router = router_obj
                                    
                                ns_obj.save()
                                
                                if ns_siglum and not tenant_obj.siglum:
                                    tenant_obj.siglum = ns_siglum
                                    tenant_obj.save()

                                flows = prov.get('allowedFlows') or {}
                                NetworkPolicy.objects.update_or_create(
                                    namespace=ns_obj,
                                    defaults={
                                        'flows_enabled': flows.get('enabled', flows.get('enable', False)),
                                        'dns_resolution_enabled': flows.get('dnsResolutionEnabled', False),
                                        'proxy_enabled': flows.get('proxyEnabled', False),
                                        's3_connection_enabled': flows.get('s3ConnectionEnabled', False)
                                    }
                                )
                                
                                conns = flows.get('connections') or []
                                if conns:
                                    NetworkConnection.objects.filter(namespace=ns_obj).delete() 
                                    for conn in conns:
                                        to_dst = conn.get('to', [])
                                        NetworkConnection.objects.create(
                                            namespace=ns_obj,
                                            from_pod=conn.get('from', ''),
                                            to_destinations=to_dst if isinstance(to_dst, list) else [to_dst],
                                            flows=conn.get('flows', [])
                                        )
                                else:
                                    NetworkConnection.objects.filter(namespace=ns_obj).delete()

                                if ns_obj.name not in tenant_route_exceptions_found:
                                    route_exc = prov.get('routeException') or {}
                                    if route_exc.get('enabled'):
                                        RouteException.objects.update_or_create(
                                            namespace=ns_obj,
                                            defaults={
                                                'is_active': True,
                                                'request_id': route_exc.get('requestId', ''),
                                                'granted_at': route_exc.get('grantedAt')
                                            }
                                        )
                                    else:
                                        RouteException.objects.filter(namespace=ns_obj).delete()

                                ops = prov.get('managedServices') or {}
                                for op_name, op_val in ops.items():
                                    if isinstance(op_val, dict):
                                        Operator.objects.update_or_create(
                                            namespace=ns_obj,
                                            name=op_name,
                                            defaults={'is_enabled': op_val.get('enabled', False)}
                                        )

                                rq = prov.get('resourceQuota') or {}
                                if rq.get('enabled'):
                                    ResourceQuota.objects.update_or_create(
                                        namespace=ns_obj,
                                        defaults={
                                            'requests_cpu': rq.get('requestsCpu'),
                                            'limits_cpu': rq.get('limitsCpu'),
                                            'requests_memory': rq.get('requestsMemory'),
                                            'limits_memory': rq.get('limitsMemory'),
                                            'requests_storage': rq.get('requestsStorage'),
                                            'requests_ephemeral_storage': rq.get('requestsEphemeralStorage')
                                        }
                                    )
                                else:
                                    ResourceQuota.objects.filter(namespace=ns_obj).delete()

                                lr = prov.get('limitRange') or {}
                                if lr:
                                    LimitRange.objects.update_or_create(
                                        namespace=ns_obj,
                                        defaults={
                                            'storage_max': lr.get('storageMax'),
                                            'storage_min': lr.get('storageMin'),
                                            'container_cpu': lr.get('containerCPU'),
                                            'container_request_cpu': lr.get('containerRequestCPU'),
                                            'container_ram': lr.get('containerRAM'),
                                            'container_request_ram': lr.get('containerRequestRAM'),
                                        }
                                    )
                                else:
                                    LimitRange.objects.filter(namespace=ns_obj).delete()

                                harbor = prov.get('harborOnboardingConfig') or {}
                                if harbor.get('enable'):
                                    HarborConfig.objects.update_or_create(
                                        namespace=ns_obj,
                                        defaults={
                                            'is_enabled': True,
                                            'storage_quota_gb': harbor.get('storageQuota', 0),
                                            'vulnerability_scanning': harbor.get('vulnerabilityScanning', False),
                                            'auto_sbom_generation': harbor.get('autoSbomGeneration', False),
                                            'cve_allowlist': harbor.get('cveAllowlist', [])
                                        }
                                    )
                                else:
                                    HarborConfig.objects.filter(namespace=ns_obj).delete()

                                ra_cfg = prov.get('harborRobotAccounts') or {}
                                if ra_cfg.get('enabled'):
                                    RobotAccount.objects.filter(namespace=ns_obj).delete()
                                    for acc in ra_cfg.get('robotAccounts') or []:
                                        RobotAccount.objects.create(
                                            namespace=ns_obj,
                                            name_suffix=acc.get('nameSuffix', ''),
                                            is_default=acc.get('default', False),
                                            permissions=acc.get('permissions', [])
                                        )
                                else:
                                    RobotAccount.objects.filter(namespace=ns_obj).delete()

                                owner_conf = prov.get('project_owner_config') or {}
                                owner_proj = owner_conf.get('project_owner') or {}
                                owners = owner_proj.get('initialUsers') or []
                                
                                user_conf = prov.get('project_user_config') or {}
                                user_proj = user_conf.get('project_users') or {}
                                users = user_proj.get('initialUsers') or []
                                
                                UserAccess.objects.filter(namespace=ns_obj).delete()
                                for owner in owners:
                                    if owner: UserAccess.objects.create(namespace=ns_obj, email=owner, role='Owner')
                                for user in users:
                                    if user: UserAccess.objects.create(namespace=ns_obj, email=user, role='User')
                                
                                success_count += 1

                            mesh = parsed_yaml.get('service-mesh') or {}
                            if mesh:
                                cluster_cfg = mesh.get('cluster') or {}
                                cp_cfg = mesh.get('cp') or {}
                                kiali_cfg = cp_cfg.get('kiali') or {}
                                gw_cfg = cp_cfg.get('gw') or {}
                                dp_cfg = mesh.get('dataplane') or {}
                                dp_namespaces = dp_cfg.get('namespaces') or []
                                
                                sm_cp, _ = ServiceMeshControlPlane.objects.update_or_create(
                                    namespace=ns_obj,
                                    defaults={
                                        'domain': cluster_cfg.get('domain', ''),
                                        'kiali_name': kiali_cfg.get('name', ''),
                                        'gateway_namespaces': gw_cfg.get('namespaces', []),
                                        'cp_tenant': cp_cfg.get('tenant', ''),
                                        'dataplane_namespaces': dp_namespaces if isinstance(dp_namespaces, list) else []
                                    }
                                )
                                
                                for dp_ns_item in dp_namespaces:
                                    dp_ns_name = dp_ns_item.get('name') if isinstance(dp_ns_item, dict) else str(dp_ns_item)
                                    if dp_ns_name and dp_ns_name != 'None':
                                        dp_ns_obj, _ = Namespace.objects.get_or_create(
                                            name=dp_ns_name, 
                                            defaults={'tenant': tenant_obj, 'cluster': cluster_obj}
                                        )
                                        active_namespace_names.add(dp_ns_obj.name)
                                        dp_ns_obj.service_mesh_cp = sm_cp
                                        dp_ns_obj.save()
                                        
                                if not prov:
                                    success_count += 1
                            elif prov:
                                ServiceMeshControlPlane.objects.filter(namespace=ns_obj).delete()

                            reg_cfg = parsed_yaml.get('registry-config') or {}
                            if reg_cfg:
                                registries = { r.get('name'): r for r in reg_cfg.get('registries', []) }
                                replications = reg_cfg.get('dockerRegistryReplications', [])
                                
                                if replications or registries:
                                    RegistryMirror.objects.filter(namespace=ns_obj).delete()
                                    for rep in replications:
                                        reg_name = rep.get('registry')
                                        reg_info = registries.get(reg_name) or {}
                                        
                                        image_filter = ""
                                        tag_filter = ""
                                        for f in rep.get('filters', []):
                                            if 'name' in f: image_filter = f['name']
                                            if 'tag' in f: tag_filter = f['tag']
                                            
                                        RegistryMirror.objects.create(
                                            namespace=ns_obj,
                                            name=reg_name or rep.get('name', 'mirror'),
                                            endpoint_url=reg_info.get('endpointUrl', ''),
                                            provider_name=reg_info.get('providerName', ''),
                                            image=image_filter,
                                            tag=tag_filter,
                                            schedule=rep.get('schedule', '')
                                        )
                                if not prov and not mesh and not cso:
                                    success_count += 1
                            else:
                                RegistryMirror.objects.filter(namespace=ns_obj).delete()

                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"Failed to process content of {full_path}: {e}"))

            deleted_crs = CustomResource.objects.exclude(id__in=active_cr_ids).delete()
            deleted_helms = HelmDeployment.objects.exclude(id__in=active_helm_ids).delete()
            deleted_namespaces = Namespace.objects.exclude(name__in=active_namespace_names).delete()
            deleted_tenants = Tenant.objects.exclude(name__in=active_tenant_names).delete()
            
            if deleted_crs[0] > 0 or deleted_helms[0] > 0 or deleted_namespaces[0] > 0 or deleted_tenants[0] > 0:
                self.stdout.write(self.style.NOTICE(f"Pruned stale records: {deleted_crs[0]} CRs, {deleted_helms[0]} Charts, {deleted_namespaces[0]} Namespaces, {deleted_tenants[0]} Tenants."))

            if temp_cleanup_dir and os.path.exists(temp_cleanup_dir):
                shutil.rmtree(temp_cleanup_dir)
                self.stdout.write(self.style.NOTICE("Cleaned up temporary GitLab repository files."))

            status.last_sync_time = timezone.now()
            status.last_message = "Ready"
            status.is_syncing = False
            status.save()

            self.stdout.write(self.style.SUCCESS(f"✅ GitOps Sync Complete! Safely updated database with configurations from {success_count} namespaces."))

        except Exception as e:
            status.last_message = f"Sync Error: {str(e)}"
            status.is_syncing = False
            status.save()
            
            if 'temp_cleanup_dir' in locals() and temp_cleanup_dir and os.path.exists(temp_cleanup_dir):
                shutil.rmtree(temp_cleanup_dir)
                
            self.stdout.write(self.style.ERROR(f'Failed to sync: {str(e)}'))
            raise e
