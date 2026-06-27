import base64
import json
import time
from http.client import RemoteDisconnected
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.parse import urljoin

from sqlalchemy.exc import SQLAlchemyError

from app.branches.models.model import Branch
from app.modules.models import Module
from app.product.models import Product
from app.relasionship.models.model import ModuleBranch, ProductModule
from extensions import db


class GitLabSyncError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def normalize_gitlab_project(project):
    path_with_namespace = project.get("path_with_namespace") or project.get("path") or project.get("name")
    parts = [part for part in path_with_namespace.split("/") if part]
    product_name = parts[0] if parts else project.get("namespace", {}).get("name") or "default"

    repo_url = project.get("http_url_to_repo") or project.get("ssh_url_to_repo")
    if not repo_url and project.get("web_url"):
        repo_url = f"{project['web_url'].rstrip('/')}.git"

    return {
        "product_name": product_name,
        "module_name": project.get("name") or parts[-1],
        "repo_url": repo_url,
        "default_branch": project.get("default_branch"),
        "project_id": project.get("id"),
        "path_with_namespace": path_with_namespace,
    }


def build_gitlab_project_query(page, membership_only=False):
    params = {
        "simple": "true",
        "per_page": 100,
        "page": page,
        "order_by": "path",
        "sort": "asc",
    }
    if membership_only:
        params["membership"] = "true"
    return params


def fetch_gitlab_projects(
    base_url,
    username=None,
    password=None,
    private_token=None,
    timeout=30,
    membership_only=False,
    max_retries=3,
    retry_delay=1,
):
    api_url = urljoin(base_url.rstrip("/") + "/", "api/v4/projects")
    page = 1
    projects = []

    while True:
        params = build_gitlab_project_query(page, membership_only=membership_only)
        headers = {}
        auth = None
        if private_token:
            headers["PRIVATE-TOKEN"] = private_token
        elif username or password:
            raw_token = f"{username or ''}:{password or ''}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(raw_token).decode('ascii')}"

        batch, response_headers = _get_json_with_retry(
            api_url,
            params,
            headers,
            timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        if not batch:
            break

        projects.extend(batch)
        next_page = response_headers.get("X-Next-Page")
        if not next_page:
            break
        page = int(next_page)

    return projects


def _get_json_with_retry(api_url, params, headers, timeout, max_retries, retry_delay):
    attempt = 0
    while True:
        attempt += 1
        try:
            return _get_json(api_url, params, headers, timeout)
        except (TimeoutError, RemoteDisconnected, GitLabSyncError) as exc:
            if isinstance(exc, GitLabSyncError) and exc.status_code:
                raise
            if attempt > max_retries:
                raise GitLabSyncError("GitLab API 请求超时或连接失败，请稍后重试") from exc
            if retry_delay:
                time.sleep(retry_delay)


def _get_json(api_url, params, headers, timeout):
    url = f"{api_url}?{urlencode(params)}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload), response.headers
    except HTTPError as exc:
        raise GitLabSyncError("GitLab API 返回错误", status_code=exc.code) from exc
    except URLError as exc:
        raise GitLabSyncError("无法连接 GitLab API") from exc


def sync_gitlab_projects(projects, db_max_retries=2):
    stats = {
        "scanned_projects": 0,
        "synced_projects": 0,
        "skipped_projects": 0,
        "created_products": 0,
        "created_modules": 0,
        "created_branches": 0,
        "created_product_modules": 0,
        "created_module_branches": 0,
    }

    for project in projects:
        stats["scanned_projects"] += 1
        item = normalize_gitlab_project(project)
        if not item["product_name"] or not item["module_name"] or not item["repo_url"]:
            stats["skipped_projects"] += 1
            continue

        project_stats = _sync_project_with_retry(item, db_max_retries)
        for key, value in project_stats.items():
            stats[key] += value

    return stats


def _sync_project_with_retry(item, db_max_retries):
    attempt = 0
    while True:
        attempt += 1
        try:
            project_stats = _sync_normalized_project(item)
            db.session.commit()
            return project_stats
        except SQLAlchemyError:
            db.session.rollback()
            _dispose_current_engine()
            if attempt > db_max_retries:
                raise


def _sync_normalized_project(item):
    stats = {
        "synced_projects": 0,
        "created_products": 0,
        "created_modules": 0,
        "created_branches": 0,
        "created_product_modules": 0,
        "created_module_branches": 0,
    }

    product, created = _get_or_create_product(item["product_name"])
    stats["created_products"] += int(created)

    module, created = _get_or_create_module_for_product(product.id, item["module_name"])
    stats["created_modules"] += int(created)

    branch, created = _get_or_create_branch(item["repo_url"], item["default_branch"])
    stats["created_branches"] += int(created)

    created = _ensure_product_module(product.id, module.id)
    stats["created_product_modules"] += int(created)

    created = _ensure_module_branch(module.id, branch.id)
    stats["created_module_branches"] += int(created)
    stats["synced_projects"] += 1

    return stats


def _dispose_current_engine():
    try:
        bind = db.session.get_bind()
        if hasattr(bind, "dispose"):
            bind.dispose()
    except Exception:
        pass


def sync_gitlab_projects_from_config(config):
    projects = fetch_gitlab_projects(
        config["GIT_BASE_URL"],
        username=config.get("GIT_USER"),
        password=config.get("GIT_PASSWORD"),
        private_token=config.get("GITLAB_PRIVATE_TOKEN"),
        timeout=config.get("GITLAB_API_TIMEOUT", 30),
        membership_only=config.get("GITLAB_PROJECT_MEMBERSHIP_ONLY", False),
        max_retries=config.get("GITLAB_API_MAX_RETRIES", 3),
        retry_delay=config.get("GITLAB_API_RETRY_DELAY", 1),
    )
    fetched_count = len(projects)
    skipped_existing = 0
    if config.get("GITLAB_SYNC_SKIP_EXISTING_REPOS", True):
        projects, skipped_existing = filter_projects_missing_repositories(projects)

    stats = sync_gitlab_projects(projects, db_max_retries=config.get("GITLAB_DB_MAX_RETRIES", 2))
    stats["fetched_projects"] = fetched_count
    stats["existing_repositories_skipped"] = skipped_existing
    return stats


def filter_projects_missing_repositories(projects):
    repo_urls = [project.get("http_url_to_repo") for project in projects if project.get("http_url_to_repo")]
    if not repo_urls:
        return projects, 0

    existing_urls = {
        row[0]
        for row in Branch.query.with_entities(Branch.address)
        .filter(Branch.address.in_(repo_urls))
        .all()
    }
    missing = [project for project in projects if project.get("http_url_to_repo") not in existing_urls]
    return missing, len(projects) - len(missing)


def _get_or_create_product(name):
    product = Product.query.filter_by(name=name).first()
    if product:
        return product, False

    product = Product(name=name, description=f"GitLab 同步产品: {name}")
    db.session.add(product)
    db.session.flush()
    return product, True


def _get_or_create_module_for_product(product_id, name):
    module = (
        db.session.query(Module)
        .join(ProductModule, ProductModule.module_id == Module.id)
        .filter(ProductModule.product_id == product_id, Module.name == name)
        .first()
    )
    if module:
        return module, False

    module = Module(name=name)
    db.session.add(module)
    db.session.flush()
    return module, True


def _get_or_create_branch(repo_url, default_branch):
    branch = Branch.query.filter_by(address=repo_url).first()
    if branch:
        if default_branch and not branch.tag_version:
            branch.tag_version = default_branch
        return branch, False

    branch = Branch(address=repo_url, tag_version=default_branch)
    db.session.add(branch)
    db.session.flush()
    return branch, True


def _ensure_product_module(product_id, module_id):
    relation = ProductModule.query.filter_by(product_id=product_id, module_id=module_id).first()
    if relation:
        return False

    db.session.add(ProductModule(product_id=product_id, module_id=module_id))
    db.session.flush()
    return True


def _ensure_module_branch(module_id, branch_id):
    relation = ModuleBranch.query.filter_by(module_id=module_id, branch_id=branch_id).first()
    if relation:
        return False

    db.session.add(ModuleBranch(module_id=module_id, branch_id=branch_id))
    db.session.flush()
    return True
