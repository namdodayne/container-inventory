#!/usr/bin/env python3
"""Inventory of images behind running containers: registry, tech stack, git, and who runs them.

Default: reads `docker inspect` metadata (env, labels, cmd, layers) and `docker top`;
never execs into a container. Base images are found by matching layer prefixes of local images.
--deep: also `docker exec -u 0` read-only commands (manifests, installed packages, SQLite files,
process binaries) and `docker cp` of process binaries to read Go build info.
Respects DOCKER_HOST / DOCKER_CONTEXT, so it works against remote hosts too.
Python 3.9+, stdlib only (TOML apps file needs 3.11+ or `tomli`; JSON works everywhere).

    ./inventory.py                       # table
    ./inventory.py --json                # full records
    ./inventory.py --ndjson -a           # one record per line, for log agents (Splunk UF...)
    ./inventory.py --deep                # + frameworks, packages, SQLite, Go modules
    ./inventory.py --apps apps.toml      # join manual app / git / registry info (.json also works)
    ./inventory.py --selftest
"""
import argparse
import fnmatch
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile

__version__ = "0.2.4"
# <PREFIX>_VERSION / <PREFIX>_MAJOR env vars set by official base images.
ENV_TECH = {
    "NODE": "Node.js", "YARN": "Yarn", "PYTHON": "Python", "JAVA": "Java", "JDK": "Java",
    "PHP": "PHP", "COMPOSER": "Composer", "GOLANG": "Go", "RUBY": "Ruby", "RUST": "Rust",
    "DOTNET": ".NET", "ASPNET": "ASP.NET Core", "NGINX": "nginx", "HTTPD": "Apache httpd",
    "TOMCAT": "Tomcat", "PG": "PostgreSQL", "MYSQL": "MySQL", "MARIADB": "MariaDB",
    "REDIS": "Redis", "MONGO": "MongoDB", "RABBITMQ": "RabbitMQ", "ELASTIC": "Elasticsearch",
    "KAFKA": "Kafka", "TRAEFIK": "Traefik", "CADDY": "Caddy", "HAPROXY": "HAProxy",
}
# Process names in entrypoint/cmd, and well-known image names.
NAME_TECH = {
    "node": "Node.js", "npm": "Node.js", "pnpm": "Node.js", "bun": "Bun", "deno": "Deno",
    "python": "Python", "python3": "Python", "gunicorn": "Python", "uvicorn": "Python",
    "java": "Java", "php": "PHP", "php-fpm": "PHP", "ruby": "Ruby", "rails": "Ruby",
    "dotnet": ".NET", "nginx": "nginx", "httpd": "Apache httpd", "postgres": "PostgreSQL",
    "mysql": "MySQL", "mysqld": "MySQL", "mariadb": "MariaDB", "redis": "Redis",
    "redis-server": "Redis", "mongo": "MongoDB", "mongod": "MongoDB", "rabbitmq": "RabbitMQ",
    "elasticsearch": "Elasticsearch", "traefik": "Traefik", "caddy": "Caddy",
    "haproxy": "HAProxy", "tomcat": "Tomcat", "golang": "Go", "supervisord": "Supervisor",
    "memcached": "Memcached", "php-fpm8": "PHP", "sqlite3": "SQLite",
}
# Package / module name -> label, across ecosystems. Go modules also match by path prefix (…/v4).
FRAMEWORKS = {
    # Python
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "starlette": "Starlette",
    "gunicorn": "Gunicorn", "uvicorn": "Uvicorn", "celery": "Celery", "tornado": "Tornado",
    "aiohttp": "aiohttp", "sqlalchemy": "SQLAlchemy", "alembic": "Alembic", "pydantic": "Pydantic",
    "aiogram": "aiogram", "python-telegram-bot": "python-telegram-bot", "telethon": "Telethon",
    "pyrogram": "Pyrogram", "jira": "jira", "scrapy": "Scrapy", "streamlit": "Streamlit",
    "gradio": "Gradio", "pandas": "pandas", "torch": "PyTorch", "transformers": "Transformers",
    "langchain": "LangChain", "openai": "OpenAI SDK", "anthropic": "Anthropic SDK", "boto3": "AWS SDK",
    "psycopg2": "PostgreSQL client", "psycopg2-binary": "PostgreSQL client", "psycopg": "PostgreSQL client",
    "asyncpg": "PostgreSQL client", "pymysql": "MySQL client", "mysqlclient": "MySQL client",
    "pymongo": "MongoDB client", "motor": "MongoDB client", "redis": "Redis client",
    "aiosqlite": "SQLite", "selenium": "Selenium", "playwright": "Playwright",
    # Node.js
    "express": "Express", "next": "Next.js", "react": "React", "vue": "Vue", "nuxt": "Nuxt",
    "@nestjs/core": "NestJS", "fastify": "Fastify", "koa": "Koa", "@angular/core": "Angular",
    "svelte": "Svelte", "@sveltejs/kit": "SvelteKit", "vite": "Vite", "telegraf": "Telegraf",
    "node-telegram-bot-api": "node-telegram-bot-api", "grammy": "grammY", "@prisma/client": "Prisma",
    "prisma": "Prisma", "mongoose": "Mongoose", "sequelize": "Sequelize", "typeorm": "TypeORM",
    "pg": "PostgreSQL client", "mysql2": "MySQL client", "ioredis": "Redis client",
    "better-sqlite3": "SQLite", "sqlite3": "SQLite", "socket.io": "Socket.IO", "puppeteer": "Puppeteer",
    "jira-client": "jira", "jira.js": "jira",
    # PHP
    "laravel/framework": "Laravel", "symfony/framework-bundle": "Symfony",
    "codeigniter4/framework": "CodeIgniter", "slim/slim": "Slim",
    # Go
    "github.com/gin-gonic/gin": "Gin", "github.com/labstack/echo": "Echo", "github.com/gofiber/fiber": "Fiber",
    "github.com/gorilla/mux": "Gorilla mux", "github.com/go-chi/chi": "chi", "gorm.io/gorm": "GORM",
    "github.com/jackc/pgx": "PostgreSQL client", "github.com/lib/pq": "PostgreSQL client",
    "github.com/go-sql-driver/mysql": "MySQL client", "github.com/redis/go-redis": "Redis client",
    "github.com/go-redis/redis": "Redis client", "github.com/mattn/go-sqlite3": "SQLite",
    "modernc.org/sqlite": "SQLite", "go.mongodb.org/mongo-driver": "MongoDB client",
    "google.golang.org/grpc": "gRPC", "github.com/quic-go/quic-go": "QUIC",
    "github.com/golang-jwt/jwt": "JWT", "github.com/prometheus/client_golang": "Prometheus client",
    "github.com/go-telegram-bot-api/telegram-bot-api": "telegram-bot-api",
    # Java / Ruby / Rust
    "spring-boot": "Spring Boot", "quarkus": "Quarkus", "rails": "Rails", "sinatra": "Sinatra",
    "actix-web": "Actix Web", "axum": "Axum", "rocket": "Rocket",
}
# Connection URIs and *_HOST vars in container env: what the app talks to (credentials dropped).
SCHEME_TECH = {
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB",
    "mongodb": "MongoDB", "mongodb+srv": "MongoDB", "redis": "Redis", "rediss": "Redis",
    "amqp": "RabbitMQ", "amqps": "RabbitMQ", "mssql": "SQL Server", "sqlserver": "SQL Server",
    "sqlite": "SQLite", "kafka": "Kafka", "nats": "NATS", "memcached": "Memcached",
}
HOST_TECH = {"POSTGRES": "PostgreSQL", "PG": "PostgreSQL", "MYSQL": "MySQL", "MARIADB": "MariaDB",
             "MONGO": "MongoDB", "MONGODB": "MongoDB", "REDIS": "Redis", "RABBITMQ": "RabbitMQ",
             "AMQP": "RabbitMQ", "KAFKA": "Kafka", "ELASTICSEARCH": "Elasticsearch", "DB": "DB"}
LIB_TECH = {"libmodsecurity": "ModSecurity", "libluajit": "LuaJIT", "liblua": "Lua"}  # soname must equal release version: true for these
# Interpreters and coreutils: their binaries say nothing beyond the process name.
NOT_APP_BINARIES = {"sh", "bash", "ash", "dash", "busybox", "sleep", "tail", "sed", "tr", "cat", "tini",
                    "dumb-init", "rosetta", "python", "python3", "node", "java", "php", "php-fpm", "ruby",
                    "nginx", "redis-server", "postgres", "mysqld", "mongod", "httpd", "supervisord", "logrotate"}
GIT_LABELS = ("org.opencontainers.image.source", "org.label-schema.vcs-url")
REV_LABELS = ("org.opencontainers.image.revision", "org.label-schema.vcs-ref")
TITLE_LABELS = ("org.opencontainers.image.title", "org.label-schema.name")
VERSION_LABELS = ("org.opencontainers.image.version", "org.label-schema.version")
TAG_VERSION = re.compile(r"v?(\d+(?:\.\d+)+)")  # 9.3.8, v2.45.1, 1.30.4-alpine-stable; not 15 / 16-alpine / dates


def parse_ref(ref):
    """'reg.io:5000/ns/app:1.2@sha256:..' -> {registry, repo, tag, digest}."""
    ref, _, digest = ref.partition("@")
    head, _, last = ref.rpartition("/")
    name, _, tag = last.partition(":")
    path = f"{head}/{name}" if head else name
    first, _, rest = path.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        registry, repo = first, rest
    else:
        registry, repo = "docker.io", path if "/" in path else f"library/{path}"
    return {"registry": registry, "repo": repo, "tag": tag or ("" if digest else "latest"), "digest": digest}


def detect_tech(env, cmd, repo, procs=()):
    """procs: CMD lines from `docker top`; first few tokens are matched, so wrappers like
    `python3 -m gunicorn` or `/run/rosetta/rosetta /usr/sbin/nginx` still hit."""
    tech = {}
    for suffix in ("_VERSION", "_MAJOR"):  # full version wins over major
        for item in env:
            key, _, val = item.partition("=")
            prefix = key.removesuffix(suffix)
            if prefix != key and prefix in ENV_TECH:
                tech.setdefault(ENV_TECH[prefix], val)
    words = [repo, *cmd[:3], *(w for line in procs for w in line.split()[:5])]
    for word in (w.rsplit("/", 1)[-1] for w in words):
        if word in NAME_TECH:
            tech.setdefault(NAME_TECH[word], "")
    return tech


def connections(env):
    """['PostgreSQL postgres:5432', ...] from URIs and <X>_HOST vars; userinfo is never kept."""
    found = []
    for item in env:
        key, _, val = item.partition("=")
        m = re.match(r"([a-z][a-z0-9+.\-]*)://(?:[^@/]*@)?([^/?#,]*)(/[^?#]*)?", val.strip())
        label = m and (SCHEME_TECH.get(m.group(1)) or SCHEME_TECH.get(m.group(1).split("+")[0]))
        if m and not label and m.group(1) in ("http", "https", "ws", "wss", "grpc") \
                and key.endswith(("_URL", "_URI", "_ENDPOINT")):  # service-to-service calls
            label = m.group(1).upper()
        if label:
            target = m.group(2) or (m.group(3) or "")  # sqlite:///path has no host
        elif key.endswith("_HOST") and key[:-5] in HOST_TECH and val:
            label, target = HOST_TECH[key[:-5]], val
        else:
            continue
        if f"{label} {target}" not in found:
            found.append(f"{label} {target}")
    return found


def first(labels, keys):
    return next((labels[k] for k in keys if labels.get(k)), "")


def product(labels, ref):
    """(name, version, source): OCI / label-schema labels first, then a semver-looking tag.
    ponytail: labels can be inherited from a base image (e.g. wolfi-base); no guard, base chain is often missing."""
    name, version = first(labels, TITLE_LABELS), first(labels, VERSION_LABELS)
    source = "label" if version else ""
    m = not version and TAG_VERSION.match(ref["tag"])
    if m:
        version, source = m.group(1), "tag"
    if version and not name:
        name = ref["repo"].rsplit("/", 1)[-1]
    return name, version, source


def ancestors(img, all_imgs):
    """Local images whose layer list is a proper prefix of img's: its base chain, nearest first."""
    layers = (img.get("RootFS") or {}).get("Layers") or []
    found = {}
    for other in all_imgs:
        ol = (other.get("RootFS") or {}).get("Layers") or []
        if 0 < len(ol) < len(layers) and layers[:len(ol)] == ol:
            name = (other.get("RepoTags") or other.get("RepoDigests") or [other["Id"][7:19]])[0]
            found.setdefault(len(ol), name)  # retags of one base: keep the first name
    return [found[n] for n in sorted(found, reverse=True)]


def built_here(img, built=frozenset()):
    """Image was built on this host, not pulled. Three signals, any one is enough:
    no RepoDigests (classic image store only: containerd store gives every image one);
    its ID is the output of a BuildKit build in `docker buildx history`;
    a `docker compose build` label (compose only adds it to images it builds)."""
    if "Config" not in img:
        return False
    labels = img["Config"].get("Labels") or {}
    return not img.get("RepoDigests") or img["Id"] in built or "com.docker.compose.service" in labels


def build_record(img, ctrs, procs=(), built=frozenset(), tag_img=None):
    """Anchor is the image: tech/git come from its config, containers are what runs it.
    Image deleted or rebuilt under the same tag: anchor is the container (one record each),
    using the container's copy of the image config. tag_img: what the container's ref points to now,
    used to tell local from pulled when the container's own image is gone."""
    cfg = img.get("Config") or (ctrs[0]["Config"] if ctrs else {})
    labels = cfg.get("Labels") or {}
    digests = img.get("RepoDigests") or []
    name = ctrs[0]["Config"]["Image"] if ctrs else (img.get("RepoTags") or digests or [img["Id"]])[0]
    ref = parse_ref(name)
    # Built on this host: no registry, whatever the name says; `library/` is Docker Hub only.
    if ref["registry"] == "docker.io" and built_here(img if "Config" in img else tag_img or {}, built):
        ref["registry"], ref["repo"] = "local", ref["repo"].removeprefix("library/")
    prod_name, prod_version, version_source = product(labels, ref)
    return {
        "image": name,
        "image_id": img["Id"].removeprefix("sha256:")[:12],
        "anchor": "image" if "Config" in img else "container",
        **ref,
        "digest": ref["digest"] or (digests[0].partition("@")[2] if digests else ""),
        "platform": f"{img.get('Os', '')}/{img.get('Architecture', '')}".strip("/"),
        "created": img.get("Created", "")[:10],
        "base": [],
        "os": "",
        "git": first(labels, GIT_LABELS),
        "revision": first(labels, REV_LABELS),
        # What the image is, e.g. bunkerweb v1.6.16 / kibana 9.3.8; version_source: label | tag | "".
        "product": " ".join(filter(None, (prod_name, prod_version))),
        "product_version": prod_version,
        "version_source": version_source,
        "tech": detect_tech(cfg.get("Env") or [], (cfg.get("Entrypoint") or []) + (cfg.get("Cmd") or []),
                            ref["repo"], procs),
        "frameworks": {},
        "packages": {},
        "connects": [c for ctr in ctrs for c in connections(ctr["Config"].get("Env") or [])],
        "data_files": [],
        "binaries": [],
        "containers": [{
            "name": c["Name"].lstrip("/"),
            "id": c["Id"][:12],
            "status": c["State"]["Status"],
            "compose_project": (c["Config"].get("Labels") or {}).get("com.docker.compose.project", ""),
            "ports": sorted((c.get("NetworkSettings") or {}).get("Ports") or {}),
        } for c in ctrs],
        "app": {},
    }


def apply_apps(rec, apps):
    """First [[app]] whose `match` glob hits registry/repo or a container name wins; manual values override labels."""
    names = [f"{rec['registry']}/{rec['repo']}", *(c["name"] for c in rec["containers"])]
    for app in apps:
        if any(fnmatch.fnmatch(n, app["match"]) for n in names):
            rec["app"] = {k: v for k, v in app.items() if k != "match"}
            rec["git"] = app.get("git", rec["git"])
            return


def docker_json(*args, allow_missing=False):
    out = subprocess.run(["docker", *args], capture_output=True, encoding="utf-8", errors="replace")
    if out.returncode and not (allow_missing and "No such" in out.stderr):
        sys.exit(f"docker {' '.join(args[:2])} failed: {out.stderr.strip()}")
    return json.loads(out.stdout) if out.stdout.strip() else []


def buildx_outputs(limit=200):
    """Image IDs produced by BuildKit builds on this daemon (`docker buildx history`, buildx 0.12+).
    In the containerd store an image ID is its index digest, which is what the build attaches.
    Empty set when buildx/history is missing or pruned. ponytail: one inspect per build, newest `limit`."""
    run = lambda *a: subprocess.run(["docker", "buildx", "history", *a, "--format", "json"],
                                    capture_output=True, encoding="utf-8", errors="replace")
    out, ids = run("ls"), set()
    if out.returncode:
        return ids
    for line in out.stdout.splitlines()[:limit]:
        try:
            build = json.loads(line)
            if build.get("status") != "Completed":
                continue
            detail = run("inspect", build["ref"].rsplit("/", 1)[-1])
            ids.update(a["Digest"] for a in json.loads(detail.stdout).get("Attachments") or []
                       if "image.index" in a.get("Type", "") or "manifest" in a.get("Type", ""))
        except (ValueError, KeyError):
            continue
    return ids


def tag_ids(ctrs):
    """{container ref: image ID that ref points to now}; a container whose ID differs runs a stale image."""
    found = {}
    for ref in {c["Config"]["Image"] for c in ctrs}:
        out = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", ref],
                             capture_output=True, encoding="utf-8", errors="replace")
        if out.returncode == 0:
            found[ref] = out.stdout.strip()
    return found


def processes(ctr):
    """CMD column of `docker top` (last column of the default ps format); empty unless running."""
    if ctr["State"]["Status"] != "running":
        return []
    out = subprocess.run(["docker", "top", ctr["Id"]], capture_output=True, encoding="utf-8", errors="replace")
    lines = out.stdout.splitlines()
    if out.returncode or not lines:
        return []
    col = lines[0].find("CMD")
    return [line[col:] for line in lines[1:]] if col >= 0 else []


DEEP_SCRIPT = r'''
grep -s '^PRETTY_NAME=' /etc/os-release | sed 's/^PRETTY_NAME=/@os /; s/"//g'
for p in /proc/[0-9]*; do
  e=$(readlink "$p/exe" 2>/dev/null)
  case "$e" in ""|*rosetta*|*qemu*) e=$(tr '\0' '\n' < "$p/cmdline" 2>/dev/null | head -n1);; esac
  case "$e" in /*) echo "@exe $e";; esac
done | sort -u
for b in nginx node python3 php java ruby redis-server postgres mysqld mongod httpd dotnet go supervisord; do
  command -v $b >/dev/null 2>&1 || continue
  case $b in nginx|httpd) v=$($b -v 2>&1);; java) v=$($b -version 2>&1);; go) v=$($b version 2>&1);;
    *) v=$($b --version 2>&1);; esac
  echo "@ver $b $(echo "$v" | head -n1)"
done
find / -maxdepth 8 \( -path /proc -o -path /sys -o -path /dev -o -path /usr/share/doc -o -path /usr/share/man \
    -o -path /usr/share/locale -o -path /usr/share/zoneinfo -o -path /var/cache \
    -o -path /var/lib/rpm -o -path /usr/lib/sysimage -o -name node_modules -o -name .git \) -prune -o \
  \( -name '*.dist-info' -o -name 'libmodsecurity*' -o -name 'libluajit*' -o -name 'liblua*' \
     -o -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.db' \) -print 2>/dev/null | head -n 5000 |
while read -r f; do
  case "$f" in
    *.dist-info) echo "@py $f";;
    *.sqlite|*.sqlite3|*.db) [ "$(head -c 15 "$f" 2>/dev/null)" = "SQLite format 3" ] && echo "@sqlite $f";;
    *) echo "@lib $f";;
  esac
done
for d in "$WD" /app /usr/src/app /srv /var/www /opt /code /workspace /home; do
  [ -n "$d" ] && [ -d "$d" ] && find "$d" -maxdepth 3 \( -name node_modules -o -name .git -o -name vendor \
    -o -name site-packages -o -name .venv \) -prune -o -type f \( -name package.json -o -name 'requirements*.txt' \
    -o -name pyproject.toml -o -name Pipfile -o -name go.mod -o -name composer.json -o -name pom.xml \
    -o -name 'build.gradle*' -o -name Gemfile -o -name Cargo.toml -o -name '*.csproj' \) -print 2>/dev/null
done | sort -u | head -n 30 | while read -r f; do
  echo "@file $f"; head -c 65536 "$f"; echo; echo "@end"
  case "$f" in */package.json)  # installed versions beat the ranges written in package.json
    for m in "${f%/*}"/node_modules/*/package.json "${f%/*}"/node_modules/@*/*/package.json; do
      [ -f "$m" ] && echo "@npm $m $(grep -m1 '"version"' "$m" | cut -d'"' -f4)"
    done;; esac
done
'''


def match_framework(name):
    name = name.lower().strip()
    for key, label in FRAMEWORKS.items():
        if name == key or (key.count("/") >= 2 and name.startswith(key + "/")):
            return label
    return None


def add_framework(fw, name, version=""):
    label = match_framework(name)
    if label and not fw.get(label):
        fw[label] = version


def add_package(rec, eco, name, version):
    """Every direct dependency goes to `packages`; the known ones also to `frameworks`."""
    rec["packages"].setdefault(f"{eco}:{name}", version)
    add_framework(rec["frameworks"], name, version)


def parse_manifest(path, text, rec, installed=None):
    """installed: {(manifest dir, npm name): version} from node_modules, preferred over ranges."""
    folder, _, base = path.rpartition("/")
    fw = rec["frameworks"]
    if base in ("package.json", "composer.json"):
        try:
            data = json.loads(text)
        except ValueError:
            return
        eco = "npm" if base == "package.json" else "composer"
        for key in ("dependencies", "require"):
            for name, ver in (data.get(key) or {}).items():
                ver = (installed or {}).get((folder, name)) or str(ver).lstrip("^~>=v ")
                add_package(rec, eco, name, ver)
    elif base == "go.mod":
        for name, ver in re.findall(r"^\s*(?:require\s+)?([\w.\-]+/[\w./\-]+)\s+(v[\w.+\-]+)", text, re.M):
            add_package(rec, "go", name, ver)
    else:  # requirements, pyproject, Gemfile, pom, gradle, Cargo, csproj: look for known names
        for name, ver in re.findall(r"([A-Za-z0-9_.\-@/]+)(?:\s*[=~><!]=*\s*([\w.]+))?", text):
            add_framework(fw, name, ver or "")


def parse_deep(out, rec):
    """Fold the DEEP_SCRIPT output into rec; returns the executable paths seen in /proc."""
    exes, lines, i = [], out.splitlines(), 0
    installed = {}
    for line in lines:
        if line.startswith("@npm "):
            path, _, ver = line[5:].rpartition(" ")
            folder, _, name = path.removesuffix("/package.json").partition("/node_modules/")
            installed[(folder, name)] = ver
    while i < len(lines):
        tag, _, val = lines[i].partition(" ")
        if tag == "@os":
            rec["os"] = val
        elif tag == "@exe":
            exes.append(val)
        elif tag == "@ver":
            binary, _, text = val.partition(" ")
            label, m = NAME_TECH.get(binary), re.search(r"\d+\.\d+(?:\.\d+)?", text)
            if label in rec["tech"] and not rec["tech"][label] and m:  # versions only for what runs
                rec["tech"][label] = m.group()
        elif tag == "@py":
            name, _, ver = val.rsplit("/", 1)[-1].removesuffix(".dist-info").rpartition("-")
            add_package(rec, "pypi", name.replace("_", "-").lower(), ver)
        elif tag == "@sqlite":
            rec["data_files"].append(val)
            rec["tech"].setdefault("SQLite", "")
        elif tag == "@lib":
            lib = val.rsplit("/", 1)[-1]
            if ".so" not in lib:  # .a/.la are build leftovers, not what the process loads
                pass
            else:
                for prefix, label in LIB_TECH.items():  # libluajit is listed before liblua
                    if lib.startswith(prefix):
                        m = re.search(r"\.so\.(\d+(?:\.\w+)+)$", lib)  # libmodsecurity.so.3.0.17
                        if m and len(m.group(1)) > len(rec["tech"].get(label, "")):
                            rec["tech"][label] = m.group(1)
                        rec["tech"].setdefault(label, "")
                        break
        elif tag == "@file":
            j = i + 1
            while j < len(lines) and lines[j] != "@end":
                j += 1
            parse_manifest(val, "\n".join(lines[i + 1:j]), rec, installed)
            i = j
        i += 1
    return exes


def read_varint(data, i):
    n = shift = 0
    while True:
        b = data[i]
        n |= (b & 0x7F) << shift
        i += 1
        if b < 0x80:
            return n, i
        shift += 7


def go_buildinfo(data):
    """Go version + main module + deps embedded by the Go 1.18+ linker; None if not a Go binary."""
    at = data.find(b"\xff Go buildinf:")
    if at < 0 or not data[at + 15] & 2:  # flag 2: inline strings (Go 1.18+)
        return None
    n, i = read_varint(data, at + 32)
    version = data[i:i + n].decode(errors="replace")
    n, i = read_varint(data, i + n)
    mod = data[i:i + n].decode(errors="replace")
    info = {"go": version.removeprefix("go"), "module": "", "version": "", "deps": {}}
    for line in mod.splitlines():
        parts = line.split("\t")
        if parts[0] == "mod" and len(parts) > 1:
            info["module"] = parts[1]
            # Real tag only: (devel) and pseudo-versions (v0.0.0-2026…-872b241f9487) say nothing.
            if len(parts) > 2 and re.fullmatch(r"v\d+\.\d+\.\d+", parts[2]):
                info["version"] = parts[2]
        elif parts[0] == "dep" and len(parts) > 2:
            info["deps"][parts[1]] = parts[2]
        elif parts[0] == "build" and len(parts) > 1 and parts[1].startswith("-ldflags="):
            # -X "main.Version=2026.10.7" (cloudflared), -X github.com/x/y/version.Version=v1.2 ...
            m = re.search(r'-X[ =]\\?"?[\w./\-]*\.(?:[Vv]ersion|VERSION)=v?(\d[\w.+\-]*)', parts[1])
            if m:
                info["version"] = m.group(1)  # ldflags beat the module tag: it is what --version prints
    return info


def copy_out(ctr_id, path, limit=200 << 20):
    """File bytes via `docker cp` (works on distroless images, no shell needed)."""
    out = subprocess.run(["docker", "cp", "-L", f"{ctr_id}:{path}", "-"], capture_output=True)
    if out.returncode:
        return None
    with tarfile.open(fileobj=io.BytesIO(out.stdout)) as tar:
        member = next((m for m in tar if m.isfile() and m.size <= limit), None)
        return tar.extractfile(member).read() if member else None


MANIFEST_RE = re.compile(r"(package\.json|requirements.*\.txt|pyproject\.toml|Pipfile|go\.mod|composer\.json"
                         r"|pom\.xml|build\.gradle.*|Gemfile|Cargo\.toml|.*\.csproj)")
APP_ROOTS = ("/app", "/usr/src/app", "/srv", "/var/www", "/opt", "/code", "/workspace", "/home")
SKIP_PARTS = {"node_modules", ".git", "vendor", "site-packages", ".venv"}
SKIP_ROOTS = ("/proc/", "/sys/", "/dev/", "/usr/share/doc/", "/usr/share/man/", "/usr/share/locale/",
              "/usr/share/zoneinfo/", "/var/cache/", "/var/lib/rpm/", "/usr/lib/sysimage/")


def export_scan(ctr, binaries):
    """DEEP_SCRIPT-style lines from `docker export` (stopped / restarting containers: no exec possible).
    Reads the container filesystem only; data in volumes is not part of an export.
    binaries: paths whose bytes are wanted (Go build info); returned as {path: bytes}."""
    wd = (ctr["Config"].get("WorkingDir") or "").rstrip("/")
    roots = [r for r in (wd, *APP_ROOTS) if r]
    lines, found, manifests = [], {}, 0
    proc = subprocess.Popen(["docker", "export", ctr["Id"]], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for m in tar:
                path = "/" + m.name.lstrip("./").rstrip("/")
                base = path.rsplit("/", 1)[-1]
                if path.startswith(SKIP_ROOTS):
                    continue
                if m.isdir():
                    if base.endswith(".dist-info") and path.count("/") <= 9:
                        lines.append(f"@py {path}")
                    continue
                if not m.isfile():
                    continue
                read = lambda n=-1: tar.extractfile(m).read(n)
                if path in ("/etc/os-release", "/usr/lib/os-release"):
                    pretty = re.search(r'^PRETTY_NAME="?([^"\n]*)', read().decode(errors="replace"), re.M)
                    if pretty:
                        lines.append(f"@os {pretty.group(1)}")
                elif base.endswith((".sqlite", ".sqlite3", ".db")):
                    if read(15) == b"SQLite format 3":
                        lines.append(f"@sqlite {path}")
                elif base.startswith(tuple(LIB_TECH)):
                    lines.append(f"@lib {path}")
                elif re.fullmatch(r"(.*?)/node_modules/((?:@[^/]+/)?[^/]+)/package\.json", path) \
                        and path.count("/node_modules/") == 1:
                    ver = re.search(rb'"version"\s*:\s*"([^"]+)"', read(65536))
                    lines.append(f"@npm {path} {ver.group(1).decode() if ver else ''}")
                elif MANIFEST_RE.fullmatch(base) and manifests < 30 and not SKIP_PARTS & set(path.split("/")) \
                        and any(path.startswith(r + "/") and path.count("/") - r.count("/") <= 3 for r in roots):
                    manifests += 1
                    lines += [f"@file {path}", read(65536).decode(errors="replace"), "@end"]
                elif path in binaries and m.size <= 200 << 20:
                    found[path] = read()
    finally:
        proc.stdout.close()
        proc.wait()
    return "\n".join(lines), found


def deep_scan(rec, ctr):
    cfg = ctr["Config"]
    first_cmd = ((cfg.get("Entrypoint") or []) + (cfg.get("Cmd") or []) or [""])[0]
    dirs = [cfg.get("WorkingDir") or "/", "/usr/local/bin", "/usr/bin", "/bin", "/"]
    entry = [first_cmd] if first_cmd.startswith("/") else [f"{d.rstrip('/')}/{first_cmd}" for d in dirs] if first_cmd else []
    if ctr["State"]["Status"] != "running":
        out, blobs = export_scan(ctr, set(entry))
        parse_deep(out, rec)
        rec["deep_source"] = "export"
        for exe, data in blobs.items():
            add_go_binary(rec, exe, data)
        return
    rec["deep_source"] = "exec"
    out = subprocess.run(["docker", "exec", "-u", "0", "-e", f"WD={cfg.get('WorkingDir') or ''}", ctr["Id"],
                          "sh", "-c", DEEP_SCRIPT], capture_output=True, encoding="utf-8", errors="replace", timeout=180)
    exes = parse_deep(out.stdout, rec) if out.returncode == 0 or out.stdout else []
    for exe in sorted(set(exes or entry))[:8]:  # no shell (distroless): the entrypoint binary
        if exe.rsplit("/", 1)[-1] in NOT_APP_BINARIES or exe.endswith((".sh", ".py", ".js")):
            continue
        data = copy_out(ctr["Id"], exe)
        if data:
            add_go_binary(rec, exe, data)


def add_go_binary(rec, exe, data):
    info = go_buildinfo(data)
    if info:
        rec["binaries"].append({"path": exe, **info})
        rec["tech"]["Go"] = info["go"]
        if info["version"] and not rec["product_version"]:
            name = rec["product"] or info["module"].rsplit("/", 1)[-1] or exe.rsplit("/", 1)[-1]
            rec["product"], rec["product_version"], rec["version_source"] = f"{name} {info['version']}", info["version"], "binary"
        for dep, ver in info["deps"].items():
            add_package(rec, "go", dep, ver)


def collect(all_containers, deep=False):
    ids = subprocess.run(["docker", "ps", "-q", *(["-a"] if all_containers else [])],
                         capture_output=True, encoding="utf-8", errors="replace")
    if ids.returncode:
        sys.exit(f"docker ps failed: {ids.stderr.strip()}")
    if not ids.stdout.split():
        return []
    by_image = {}
    for c in docker_json("inspect", *ids.stdout.split()):
        by_image.setdefault(c["Image"], []).append(c)
    imgs = {i["Id"]: i for i in docker_json("image", "inspect", *by_image, allow_missing=True)}
    local = subprocess.run(["docker", "image", "ls", "-q", "--no-trunc"], capture_output=True, encoding="utf-8", errors="replace").stdout.split()
    all_imgs = docker_json("image", "inspect", *dict.fromkeys(local), allow_missing=True) if local else []
    by_id = {i["Id"]: i for i in all_imgs}
    built = buildx_outputs()
    now = tag_ids([c for ctrs in by_image.values() for c in ctrs])
    recs = []
    for i, ctrs in by_image.items():
        if i in imgs:
            rec = build_record(imgs[i], ctrs, [p for c in ctrs for p in processes(c)], built)
            rec["base"] = ancestors(imgs[i], all_imgs)
            recs.append((rec, next((c for c in ctrs if c["State"]["Status"] == "running"), ctrs[0])))
        else:
            recs.extend((build_record({"Id": i}, [c], processes(c), built,
                                      by_id.get(now.get(c["Config"]["Image"]))), c) for c in ctrs)
    by_ctr = {c["Id"][:12]: c for ctrs in by_image.values() for c in ctrs}
    for rec, _ in recs:
        for entry in rec["containers"]:
            ctr = by_ctr[entry["id"]]
            current = now.get(ctr["Config"]["Image"], "")
            # Ref was rebuilt or re-pulled since this container started: it runs an older image.
            entry["stale"] = bool(current) and current != ctr["Image"]
            entry["tag_image_id"] = current.removeprefix("sha256:")[:12]
    if deep:
        for rec, ctr in recs:
            try:
                deep_scan(rec, ctr)
            except (subprocess.TimeoutExpired, tarfile.TarError, IndexError) as e:
                print(f"deep scan {rec['containers'][0]['name']}: {e}", file=sys.stderr)
    return [rec for rec, _ in recs]


def print_table(recs):
    rows = [("IMAGE", "REGISTRY", "BASE", "PRODUCT", "TECH", "FRAMEWORKS", "CONNECTS", "CONTAINERS", "APP", "GIT")]
    for r in recs:
        tech = ", ".join(f"{k} {v}".strip() for k, v in r["tech"].items()) or "?"
        fw = ", ".join(f"{k} {v}".strip() for k, v in r["frameworks"].items())
        if len(r["packages"]) > len(r["frameworks"]):
            fw += f" (+{len(r['packages']) - len(r['frameworks'])} pkg in --json)"
        image = f"{r['repo']}:{r['tag']}" + (" (container)" if r["anchor"] == "container" else "")
        rows.append((image, r["registry"], (r["base"] or [""])[0], r["product"], tech, fw, ", ".join(dict.fromkeys(r["connects"])),
                     ", ".join(c["name"] + (" (stale)" if c.get("stale") else "") for c in r["containers"]),
                     r["app"].get("name", ""), r["git"]))
    widths = [min(max(len(row[i]) for row in rows), 60 if rows[0][i] in ("TECH", "FRAMEWORKS", "CONNECTS") else 40)
              for i in range(len(rows[0]))]
    for row in rows:
        print("  ".join(c[:w].ljust(w) for c, w in zip(row, widths)).rstrip())


def selftest():
    assert parse_ref("nginx") == {"registry": "docker.io", "repo": "library/nginx", "tag": "latest", "digest": ""}
    assert parse_ref("ghcr.io/acme/api:1.2") == {"registry": "ghcr.io", "repo": "acme/api", "tag": "1.2", "digest": ""}
    assert parse_ref("localhost:5000/app")["registry"] == "localhost:5000"
    assert parse_ref("acme/api@sha256:ab") == {"registry": "docker.io", "repo": "acme/api", "tag": "", "digest": "sha256:ab"}
    img = {
        "Id": "sha256:0123456789abcdef", "RepoDigests": ["registry.acme.vn/shop/api@sha256:dd"],
        "Os": "linux", "Architecture": "amd64", "Created": "2026-10-01T00:00:00Z",
        "Config": {
            "Env": ["PATH=/usr/bin", "NODE_VERSION=20.11.1", "YARN_VERSION=1.22.19"],
            "Entrypoint": ["docker-entrypoint.sh"], "Cmd": ["node", "server.js"],
            "Labels": {"org.opencontainers.image.source": "https://github.com/acme/shop-api"},
        },
    }
    ctrs = [{"Name": f"/shop-api-{n}", "Id": f"abcdef12345{n}", "State": {"Status": "running"},
             "NetworkSettings": {"Ports": {"3000/tcp": None}},
             "Config": {"Image": "registry.acme.vn/shop/api:2.0", "Labels": {"com.docker.compose.project": "shop"}}}
            for n in (1, 2)]
    rec = build_record(img, ctrs)
    assert [c["name"] for c in rec["containers"]] == ["shop-api-1", "shop-api-2"]
    assert rec["image_id"] == "0123456789ab" and rec["tag"] == "2.0"
    assert rec["tech"] == {"Node.js": "20.11.1", "Yarn": "1.22.19"}, rec["tech"]
    assert (rec["registry"], rec["digest"], rec["platform"]) == ("registry.acme.vn", "sha256:dd", "linux/amd64")
    assert rec["git"] == "https://github.com/acme/shop-api"
    apply_apps(rec, [{"match": "other/*", "name": "x"},
                     {"match": "registry.acme.vn/shop/*", "name": "shop-api", "git": "https://git.acme.vn/shop/api"}])
    assert rec["app"] == {"name": "shop-api", "git": "https://git.acme.vn/shop/api"}
    assert rec["git"] == "https://git.acme.vn/shop/api"
    assert detect_tech([], ["/usr/sbin/nginx", "-g"], "library/nginx") == {"nginx": ""}
    assert build_record({"Id": "sha256:ff", "RepoTags": ["redis:7"], "Config": {}}, [])["image"] == "redis:7"
    gone = build_record({"Id": "sha256:0123456789abcdef"}, [{**ctrs[0], "Config": {**ctrs[0]["Config"], "Env": ["PYTHON_VERSION=3.12.1"]}}])
    assert detect_tech(["PG_MAJOR=16", "PG_VERSION=16.15"], [], "library/postgres") == {"PostgreSQL": "16.15"}
    assert build_record({"Id": "sha256:ee", "RepoTags": ["app:dev"], "Config": {}}, [])["registry"] == "local"
    assert gone["anchor"] == "container" and gone["tech"] == {"Python": "3.12.1"}
    procs = ["/run/rosetta/rosetta /usr/bin/python3 python3 -m gunicorn --config x",
             "/usr/bin/redis-server redis-server /var/lib/x.conf", "/usr/bin/python3 /usr/bin/supervisord -c y"]
    assert detect_tech(["NGINX_VERSION=1.30.5"], ["/usr/local/bin/fhacker-entrypoint"], "acme/waf", procs) == {
        "nginx": "1.30.5", "Python": "", "Redis": "", "Supervisor": ""}
    waf = build_record({"Id": "sha256:aa", "RepoTags": ["waf:1"], "Config": {"Labels": {
        "org.opencontainers.image.title": "bunkerweb", "org.opencontainers.image.version": "v1.6.16"}}}, [])
    assert waf["product"] == "bunkerweb v1.6.16" and waf["version_source"] == "label"
    ref = lambda tag, repo="acme/elk/kibana": {"repo": repo, "tag": tag}
    assert product({"org.label-schema.name": "kibana", "org.label-schema.version": "9.3.8"}, ref("latest")) == ("kibana", "9.3.8", "label")
    assert product({}, ref("9.3.8")) == ("kibana", "9.3.8", "tag")
    assert product({}, ref("v2.45.1", "x/portainer-ce")) == ("portainer-ce", "2.45.1", "tag")
    assert product({}, ref("1.30.4-alpine-stable", "x/nginx")) == ("nginx", "1.30.4", "tag")
    assert product({"org.opencontainers.image.title": "elastic-agent"}, ref("latest")) == ("elastic-agent", "", "")
    assert all(product({}, ref(t)) == ("", "", "") for t in ("latest", "15", "16-alpine", "2026-10-05e", ""))
    local = build_record({"Id": "sha256:ab", "Config": {}}, [{**ctrs[0], "Config": {**ctrs[0]["Config"], "Image": "ai-guardrail:latest"}}])
    assert (local["registry"], local["repo"]) == ("local", "ai-guardrail")
    # containerd store: every image has RepoDigests; buildx output or compose build label marks it local.
    hub = {"Id": "sha256:p", "RepoDigests": ["postgres@sha256:p"], "Config": {}}
    composed = {"Id": "sha256:f", "RepoDigests": ["fe@sha256:f"], "Config": {"Labels": {"com.docker.compose.service": "frontend"}}}
    assert not built_here(hub) and built_here(hub, {"sha256:p"}) and built_here(composed) and not built_here({"Id": "x"})
    fe = {**ctrs[0], "Config": {**ctrs[0]["Config"], "Image": "fhacker2026-backend:latest"}}
    assert build_record({"Id": "sha256:old"}, [fe], tag_img=composed)["registry"] == "local"
    assert build_record({"Id": "sha256:old"}, [fe])["repo"] == "library/fhacker2026-backend"  # no evidence: stays Hub
    assert connections(["DATABASE_URI=postgresql+psycopg://bw:S3cret@postgres:5432/bw", "REDIS_HOST=redis",
                        "DB=sqlite:////data/db.sqlite3", "URL=https://u:p@api.x", "API_URL=http://backend:3000", "MONGO_URL=mongodb+srv://a:b@c.net/x",
                        "CACHE=redis://:pw@cache:6379/0"]) == [
        "PostgreSQL postgres:5432", "Redis redis", "SQLite //data/db.sqlite3", "HTTP backend:3000", "MongoDB c.net", "Redis cache:6379"]
    L = lambda *ids: {"RootFS": {"Layers": list(ids)}}
    chain = [{"Id": "sha256:" + "a" * 12, "RepoTags": ["alpine:3"], **L("a")},
             {"Id": "sha256:" + "b" * 12, "RepoTags": ["nginx:alpine"], **L("a", "b")},
             {"Id": "sha256:" + "c" * 12, "RepoTags": ["other:1"], **L("a", "x")}]
    assert ancestors({"Id": "t", **L("a", "b", "c")}, chain) == ["nginx:alpine", "alpine:3"]
    rec = build_record({"Id": "sha256:aa", "Config": {}}, [], ["/usr/bin/python3 python3 bot.py"])
    exes = parse_deep("\n".join([
        "@os Debian GNU/Linux 12 (bookworm)", "@exe /usr/local/bin/python3.12", "@exe /app/server",
        "@ver python3 Python 3.12.4", "@ver node v22.1.0",
        "@py /usr/local/lib/python3.12/site-packages/python_telegram_bot-21.3.dist-info",
        "@py /usr/local/lib/python3.12/site-packages/SQLAlchemy-2.0.30.dist-info",
        "@py /usr/local/lib/python3.12/site-packages/six-1.16.0.dist-info",
        "@sqlite /data/bot.db", "@lib /usr/lib/libmodsecurity.so.3", "@lib /usr/lib/libmodsecurity.so.3.0.17",
        "@lib /x/liblua.a", "@lib /x/libluajit-5.1.so.2.1.ROLLING",
        "@file /app/package.json", '{"dependencies": {"express": "^4.19.2", "left-pad": "1"}}', "@end",
        "@npm /app/node_modules/express/package.json 4.22.3", "@npm /app/node_modules/@scope/x/package.json 2.0.0",
        "@file /app/go.mod", "module x", "require (", "\tgithub.com/gin-gonic/gin v1.10.0", ")", "@end",
        "@file /app/requirements.txt", "fastapi==0.111.0", "uvicorn", "@end",
    ]), rec)
    assert exes == ["/usr/local/bin/python3.12", "/app/server"]
    assert rec["os"] == "Debian GNU/Linux 12 (bookworm)"
    assert rec["tech"] == {"Python": "3.12.4", "SQLite": "", "ModSecurity": "3.0.17", "LuaJIT": "2.1.ROLLING"}, rec["tech"]
    assert rec["frameworks"] == {"python-telegram-bot": "21.3", "SQLAlchemy": "2.0.30", "Express": "4.22.3",
                                 "Gin": "v1.10.0", "FastAPI": "0.111.0", "Uvicorn": ""}, rec["frameworks"]
    assert rec["data_files"] == ["/data/bot.db"]
    assert rec["packages"]["npm:left-pad"] == "1" and rec["packages"]["pypi:six"] == "1.16.0"
    assert match_framework("github.com/labstack/echo/v4") == "Echo" and match_framework("nextjs") is None
    mod = b"0123456789abcdef" + b"path\tgithub.com/acme/svc\nmod\tgithub.com/acme/svc\t(devel)\t\n" \
          b"dep\tgithub.com/gin-gonic/gin\tv1.10.0\th1:x\n" + b"0123456789abcdef"
    blob = b"junk" + b"\xff Go buildinf:" + bytes([8, 2]) + b"\0" * 16 + bytes([8]) + b"go1.22.5" \
           + bytes([len(mod) & 0x7F | 0x80, len(mod) >> 7]) + mod  # varint, mod is > 127 bytes
    assert go_buildinfo(blob) == {"go": "1.22.5", "module": "github.com/acme/svc", "version": "",
                                  "deps": {"github.com/gin-gonic/gin": "v1.10.0"}}
    cf = b"0123456789abcdef" + b"mod\tgithub.com/cloudflare/cloudflared\tv0.0.0-20261030164329-872b241f9487+dirty\t\n" \
         b'build\t-ldflags="-X \\"main.Version=2026.10.7\\" -X \\"main.BuildTime=2026-10-30\\" "\n' + b"0123456789abcdef"
    cf_blob = b"\xff Go buildinf:" + bytes([8, 2]) + b"\0" * 16 + bytes([8]) + b"go1.27.3" \
        + bytes([len(cf) & 0x7F | 0x80, len(cf) >> 7]) + cf
    assert go_buildinfo(cf_blob)["version"] == "2026.10.7"
    rec = build_record({"Id": "sha256:cf", "RepoTags": ["cloudflare/cloudflared:latest"], "RepoDigests": ["x@sha256:1"], "Config": {}}, [])
    add_go_binary(rec, "/usr/local/bin/cloudflared", cf_blob)
    assert (rec["product"], rec["version_source"]) == ("cloudflared 2026.10.7", "binary"), rec["product"]
    assert go_buildinfo(b"\x7fELF not go") is None
    if shutil.which("sh"):  # escaping slips in DEEP_SCRIPT only show up as sh syntax errors
        check = subprocess.run(["sh", "-n", "-c", DEEP_SCRIPT], capture_output=True, encoding="utf-8", errors="replace")
        assert check.returncode == 0, check.stderr
    print("selftest ok")


def load_apps(path):
    with open(path, "rb") as f:
        if path.endswith(".json"):
            return json.load(f)
        try:
            import tomllib
        except ImportError:  # Python < 3.11, e.g. Ubuntu 22.04
            try:
                import tomli as tomllib
            except ImportError:
                sys.exit("TOML needs Python 3.11+ or `pip install tomli`; or pass a .json apps file")
        return tomllib.load(f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apps", help="TOML or JSON file with app mappings (see apps.example.toml)")
    ap.add_argument("--json", action="store_true", help="print full records as JSON")
    ap.add_argument("--ndjson", action="store_true",
                    help="one compact JSON record per line (log agents: Splunk UF, Filebeat, Fluent Bit...)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("-a", "--all", action="store_true", help="include stopped containers")
    ap.add_argument("--deep", action="store_true",
                    help="docker exec/cp into running containers: frameworks, packages, SQLite, Go modules")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    # Windows consoles default to cp1252: never crash on an emoji in a label or a manifest.
    sys.stdout.reconfigure(errors="replace")
    if args.selftest:
        return selftest()
    recs = collect(args.all, args.deep)
    if args.apps:
        apps = load_apps(args.apps).get("app", [])
        for r in recs:
            apply_apps(r, apps)
    if args.ndjson:
        for r in recs:
            print(json.dumps(r, separators=(",", ":")))
    elif args.json:
        json.dump(recs, sys.stdout, indent=2)  # \u escapes: lossless on any console encoding
        print()
    else:
        print_table(recs)


if __name__ == "__main__":
    main()
