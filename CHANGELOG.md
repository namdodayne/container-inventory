# Changelog

## v0.2.4

- `--deep` reads the application version from Go binaries: `-ldflags -X ...Version=` (cloudflared 2026.10.7) or a real module tag.
- Local-build detection on the containerd image store (Docker Desktop) through `docker buildx history` and compose build labels.
- `containers[].stale` and `tag_image_id`: containers still running an image their tag no longer points to.
- `--ndjson` output for log agents, `--version`.
- Prebuilt binaries for Linux amd64 / arm64 (glibc 2.28), Windows x64, macOS arm64 / x64, built and released by GitHub Actions.
- Splunk add-on: `TA-container-inventory` for indexers and search heads, `TA-container-inventory-<os>-<arch>` for Universal Forwarders.
- Documentation moved to `docs/`, in English and Vietnamese.

## v0.2.3

- Application version, not only runtimes: `product_version` and `version_source` from OCI / label-schema labels, falling back to semver-looking tags.
- Local images no longer get a `library/` prefix.

## v0.2.2

- Stopped and restarting containers are scanned with `docker export` (`deep_source: "export"`, needs `-a`). No runtime versions there, and no volume data.
- Versions from `.so` file names: ModSecurity 3.0.17, LuaJIT 2.1. `.a` / `.la` files ignored (previously reported "Lua" from `liblua.a`).
- Supervisor version. `connects` also picks up HTTP / WS / gRPC URLs in `*_URL`, `*_URI`, `*_ENDPOINT` variables.

## v0.2.1

- Windows console encoding fixed (`--deep` verified on Windows).
- npm versions taken from `node_modules` instead of manifest ranges; new `packages` field.
- Checked against the source of the 7 F-Hacker 2026 services (Dockerfile, package.json, go.mod): runtimes 7/7, direct dependencies 36/36, no false positives. Misses: frontend JS loaded from a CDN (runs in the browser, not in the container), and base images not present on the host.

## v0.2 (2026-11-04)

- Base image chain from layer prefixes; `connects` from the environment.
- `--deep`: OS, runtime versions, frameworks (dist-info, manifests), SQLite, ModSecurity / Lua, Go build info (distroless included).
- Verified on macOS and Ubuntu 22.04: bunkerweb (FastAPI, SQLAlchemy, ModSecurity, PostgreSQL), fuap_go (Go 1.23.12, lib/pq), cloudflared (Go 1.27.3, quic-go, gRPC, chi).

## v0.1.1

- Container fallback when the image is gone; processes from `docker top`; `product` from OCI labels; Python 3.10 support; JSON apps files.

## v0.1

- Images of running containers with registry / tag / digest; tech from env, cmd and names; git from OCI labels; manual app mapping in TOML.

## Roadmap

- v0.3: scan `node_modules` for bundled Node apps; read `cargo auditable` data from Rust binaries; identify JARs (`META-INF/MANIFEST.MF`, `BOOT-INF/lib`).
- v0.4: compare against the registry: current tag versus latest tag, local digest versus registry digest (outdated or re-tagged images).
- v0.5: multi-host collection, CSV export, CMDB push.
- Later: SBOM and CVE matching with `syft` / `grype` per image.
