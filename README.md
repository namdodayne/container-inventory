# container-inventory

[![build](https://github.com/namdodayne/container-inventory/actions/workflows/build.yml/badge.svg)](https://github.com/namdodayne/container-inventory/actions/workflows/build.yml)
[![release](https://img.shields.io/github/v/release/namdodayne/container-inventory?sort=semver)](https://github.com/namdodayne/container-inventory/releases/latest)
![python](https://img.shields.io/badge/python-3.9%2B-blue)

English | [Tiếng Việt](README.vi.md)

Inventory of what runs on a Docker host: where each image comes from, which application and version it ships, which runtimes and libraries it contains, what it connects to, and which containers still run an outdated image.

It is a single Python file with no dependencies, also published as a standalone binary for Linux, Windows and macOS, with a Splunk Universal Forwarder add-on for fleet-wide collection.

## What it reports

For every image behind a container on the host:

- **Origin**: registry, repository, tag, digest, base image chain. Images built on the host are reported as `local`, including on Docker Desktop's containerd image store.
- **Application version**: `product` and `product_version`, taken from OCI / label-schema labels, a semver tag, or Go build info (`--deep`). `version_source` records which one was used.
- **Tech stack**: runtimes with versions (Node.js, Python, Java, Go, nginx, PostgreSQL, Redis, ...). With `--deep`: frameworks, every package, SQLite files, ModSecurity / LuaJIT.
- **Connections**: databases and services the app talks to, read from environment variables. Credentials are always stripped.
- **Containers**: name, status, compose project, ports, and `stale` when the tag now points to a newer image than the one the container runs.
- **Source**: git repository and revision from image labels, optional manual mapping to app / owner / environment.

By default the tool only reads Docker metadata (`docker inspect`, `docker top`). `--deep` additionally runs read-only commands inside containers (`docker exec`, `docker cp`, `docker export`).

## Install

Download a binary from [Releases](https://github.com/namdodayne/container-inventory/releases/latest):

| Platform | Asset |
|---|---|
| Linux x86_64, arm64 (glibc 2.28+) | `container-inventory-linux-amd64`, `container-inventory-linux-arm64` |
| Windows x64 | `container-inventory-windows-amd64.exe` |
| macOS Apple Silicon, Intel | `container-inventory-macos-arm64`, `container-inventory-macos-amd64` |

Or run `inventory.py` directly with Python 3.9+.

The user running it must be able to reach the Docker API: member of the `docker` group, `sudo`, or `DOCKER_HOST` pointing to a read-only socket proxy.

## Usage

```bash
container-inventory                      # table, running containers
container-inventory -a                   # include stopped containers
container-inventory -a --json            # full records
container-inventory -a --ndjson          # one record per line, for log agents
container-inventory -a --deep            # frameworks, packages, Go build info
container-inventory --apps apps.toml     # join manual app / owner / git mapping
DOCKER_CONTEXT=prod container-inventory  # remote Docker host
container-inventory --selftest
```

Example (table output, trimmed):

```text
IMAGE                          REGISTRY   PRODUCT                TECH                            CONTAINERS
custom_waf26:latest            ghcr.io    bunkerweb v1.6.16      nginx 1.30.5, Python, Redis     team1_fuap_bunkerweb
louislam/uptime-kuma:2.5.6     docker.io  uptime-kuma 2.5.6      Node.js 22.22.3, Yarn 1.22.22   uptime-kuma
cloudflare/cloudflared:latest  docker.io  cloudflared 2026.10.7  Go 1.27.3                       tunnel
fhacker2026-backend:latest     local                             Node.js 22.23.4, Yarn 1.22.22   backend-1 (stale)
```

## Splunk

Release assets include a Splunk add-on:

- `TA-container-inventory.tgz` for indexers and search heads (event breaking, JSON field extraction)
- `TA-container-inventory-<os>-<arch>.tgz` for Universal Forwarders (binary and scripted input, hourly, sourcetype `container:inventory`)

Other agents (Filebeat / Elastic Agent, Fluent Bit, Wazuh) can read the `--ndjson` output from a file. See [docs/splunk.md](docs/splunk.md).

## Documentation

Detailed documentation is currently in Vietnamese.

- [docs/spec.md](docs/spec.md): design, data source of every field, known limitations
- [docs/build.md](docs/build.md): building binaries for each platform, release workflow
- [docs/splunk.md](docs/splunk.md): Splunk Universal Forwarder and other agents
- [CHANGELOG.md](CHANGELOG.md): version history and roadmap
