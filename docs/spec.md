# Specification

English | [Tiếng Việt](vi/spec.md)

## Design

**The image is the anchor, not the container.** Tech stack, git source and registry are properties of an image, and several containers (replicas, compose scale) can share one. Each record is therefore one image ID, with the containers that run it listed under `containers`.

**Container fallback.** When an image was deleted or rebuilt under the same tag, only the container is left on the host. Each such container becomes its own record (`anchor: "container"`), built from the copy of the image config that the container keeps.

**No walking through image layers.** Docker merges the `ENV` and `LABEL` of every `FROM` stage into the config of the final image, and processes and files read from a running container are the end result of all layers. The base chain (`base`) is reported for provenance only; detection does not need it.

**Platforms.** Linux, macOS, Windows (Docker Desktop). Tested on macOS, Ubuntu 22.04 / Python 3.10 (including `--deep`), Ubuntu 24.04 / Python 3.12, and Windows. Requirements: Python 3.9+ (or a prebuilt binary, which needs no Python), standard library only, and the `docker` CLI. The user running the tool must be able to reach Docker: member of the `docker` group, or `sudo`. A TOML `--apps` file needs Python 3.11+ or `pip install tomli`; a JSON file (`{"app": [...]}`) works everywhere.

## Inputs

- The Docker daemon is taken from `DOCKER_HOST` / `DOCKER_CONTEXT`, so remote hosts work.
- By default only images with a running container are reported. `-a` adds stopped containers.
- `--deep` also reads inside containers, see below.
- `--apps <file.toml|file.json>` joins a manual mapping, see [apps.example.toml](../apps.example.toml).

## Default mode: Docker metadata only, no exec

| Field | Source |
|---|---|
| `registry`, `repo`, `tag` | The reference the container was started with (`Config.Image`). No registry means `docker.io`, and no namespace means `library/`. Images built on this host get `registry: local` and no `library/` prefix. An image counts as built locally when any of these holds: (1) it has no `RepoDigests` (classic image store only); (2) its ID is an output of `docker buildx history` (BuildKit, buildx 0.12+); (3) it carries the `com.docker.compose.service` label, which compose only adds to images it builds. When the container's own image is gone, the image its tag points to now is used for this decision. |
| `digest` | Digest in the reference, otherwise `RepoDigests[0]` |
| `base` | Base image chain, nearest first. A local image is a base when its layer list (`RootFS.Layers`) is a proper prefix of this image's. |
| `product`, `product_version`, `version_source` | Name and version of the application in the image, e.g. `bunkerweb v1.6.16`, `kibana 9.3.8`. The name comes from `org.opencontainers.image.title` / `org.label-schema.name`. The version comes from `org.opencontainers.image.version` / `org.label-schema.version` (`version_source: label`); without such a label, from a semver-looking tag such as `9.3.8`, `v2.45.1`, `1.30.4-alpine` (`version_source: tag`), with the name taken from the repository. Tags like `latest`, `15`, `16-alpine` or dates are never treated as versions. Labels can be inherited from a base image (e.g. wolfi-base). |
| `tech` | Three sources: `<X>_VERSION` / `<X>_MAJOR` environment variables (`ENV_TECH` table); process names in entrypoint / cmd, the image name, and `docker top` (`NAME_TECH` table) |
| `connects` | Connection URIs in the container environment (`postgresql://`, `redis://`, `mongodb+srv://`, `sqlite:///`, ...) and `<X>_HOST` variables. Only host:port is kept; **user and password are always dropped**. |
| `git`, `revision` | Labels `org.opencontainers.image.source` / `.revision`, or `org.label-schema.vcs-*` |
| `containers[]` | Name, id, status, compose project, ports. `stale: true` means the tag was rebuilt or re-pulled but the container still runs the older image (it was not recreated). `tag_image_id` is the image the tag points to now. |
| `app` | Manual mapping. The first `[[app]]` whose `match` glob matches `<registry>/<repo>` or a container name is used. A `git` value set there overrides the label. |

## `--deep`: reading inside containers

This mode runs `docker exec -u 0 <ctr> sh -c <script>`. The script only reads: `cat`, `find`, `readlink`, and `--version` of known runtimes. Process binaries are copied out with `docker cp` and parsed on the host. One container is scanned per image, a running one when available. Stopped or restarting containers (needs `-a`) are read with `docker export` instead of `exec` (`deep_source: "export"`): no runtime versions, and no data from volumes.

| Field | Source |
|---|---|
| `os` | `PRETTY_NAME` in `/etc/os-release` |
| `tech` (version) | `<bin> --version` (or `-v`). Versions are only filled in for tech already known to be running, not for runtimes that are merely installed. |
| `tech` (embedded libraries) | `libmodsecurity*` → ModSecurity; `libluajit*` → LuaJIT; `liblua*` → Lua |
| `frameworks` | Three sources, matched against the `FRAMEWORKS` table: (1) Python `*.dist-info`, for the exact installed version; (2) manifests in the working directory, `/app`, `/srv`, `/opt`, ...: `package.json`, `requirements*.txt`, `pyproject.toml`, `go.mod`, `composer.json`, `pom.xml`, `build.gradle*`, `Gemfile`, `Cargo.toml`, `*.csproj`; (3) dependencies of Go binaries |
| `packages` | Every dependency found, not filtered by `FRAMEWORKS`: `npm:<name>` from `dependencies` in `package.json`, with the version actually installed in `node_modules` (or the manifest range); `pypi:<name>` from dist-info (transitive included); `go:<module>` from go.mod or binaries; `composer:<name>`. The table shows a count only; see `--json`. |
| `data_files`, `tech.SQLite` | `*.sqlite`, `*.sqlite3`, `*.db` files starting with `SQLite format 3` |
| `product_version` (`version_source: binary`) | Only when labels and tag give no version. Taken from the Go build info of the binary: `-ldflags -X ...Version=` (e.g. cloudflared `main.Version=2026.10.7`), otherwise a real tag of the main module. Pseudo-versions `v0.0.0-…` and `(devel)` are ignored. |
| `binaries[]` | Binaries of every process in the container (`/proc/*/exe`, falling back to `cmdline` under rosetta / qemu or a different uid), copied out with `docker cp` to read Go build info: Go version, main module, dependencies. Distroless images without `sh` use the entrypoint binary. |

## Output

Table (default), `--json` (indented JSON array) or `--ndjson` (one compact JSON record per line, for log agents). One record per image.

## Known limitations

- `base` is only found when the base image is present on the host **with the same architecture**. For example `custom_waf26` is amd64 while the local bunkerweb is arm64, so the layers differ and no base is reported.
- Containerd image store (Docker Desktop): an image built with plain `docker build`, whose build history was pruned and that did not go through compose, is reported as `docker.io`. Use `--apps` to correct it.
- Node frameworks are read from the app's `package.json` only. Apps bundled into `dist/` without their `package.json` are missed; `node_modules` is not scanned yet.
- Rust and C/C++ binaries: dependencies are not read. Go binaries built before Go 1.18 have no inline build info.
- `FRAMEWORKS` is a curated list; packages not in it do not appear under `frameworks` (they are still in `packages`). Add a line to the table to track more.
- Without `--deep`, stopped containers only get tech from env / cmd.
