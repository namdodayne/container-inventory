# container-inventory

[![build](https://github.com/namdodayne/container-inventory/actions/workflows/build.yml/badge.svg)](https://github.com/namdodayne/container-inventory/actions/workflows/build.yml)
[![release](https://img.shields.io/github/v/release/namdodayne/container-inventory?sort=semver)](https://github.com/namdodayne/container-inventory/releases/latest)
![python](https://img.shields.io/badge/python-3.9%2B-blue)

[English](README.md) | Tiếng Việt

Kiểm kê những gì đang chạy trên một Docker host: image lấy từ đâu, bên trong là ứng dụng nào và version bao nhiêu, dùng runtime và thư viện gì, kết nối tới dịch vụ nào, container nào vẫn đang chạy image cũ.

Tool là một file Python, không cần dependency. Có sẵn binary cho Linux, Windows và macOS, kèm add-on cho Splunk Universal Forwarder để thu thập trên nhiều host.

## Thông tin thu được

Với mỗi image có container trên host:

- **Nguồn gốc**: registry, repository, tag, digest, chuỗi base image. Image build ngay trên host được ghi là `local`, kể cả trên containerd image store của Docker Desktop.
- **Version ứng dụng**: `product` và `product_version`, lấy từ label OCI / label-schema, tag dạng semver, hoặc Go build info (`--deep`). Trường `version_source` cho biết version lấy từ nguồn nào.
- **Tech stack**: runtime kèm version (Node.js, Python, Java, Go, nginx, PostgreSQL, Redis...). Với `--deep`: framework, toàn bộ package, file SQLite, ModSecurity / LuaJIT.
- **Kết nối**: database và dịch vụ mà app gọi tới, đọc từ biến môi trường. Thông tin đăng nhập luôn bị loại bỏ.
- **Container**: tên, trạng thái, compose project, port. `stale` bằng `true` khi tag đã trỏ sang image mới hơn image container đang chạy.
- **Mã nguồn**: git repository và revision lấy từ label của image. Có thể map thủ công sang app / owner / môi trường.

Mặc định tool chỉ đọc metadata của Docker (`docker inspect`, `docker top`). `--deep` chạy thêm các lệnh chỉ đọc bên trong container (`docker exec`, `docker cp`, `docker export`).

## Cài đặt

Tải binary ở trang [Releases](https://github.com/namdodayne/container-inventory/releases/latest):

| Nền tảng | File |
|---|---|
| Linux x86_64, arm64 (glibc 2.28 trở lên) | `container-inventory-linux-amd64`, `container-inventory-linux-arm64` |
| Windows x64 | `container-inventory-windows-amd64.exe` |
| macOS Apple Silicon, Intel | `container-inventory-macos-arm64`, `container-inventory-macos-amd64` |

Hoặc chạy trực tiếp `inventory.py` bằng Python 3.9 trở lên.

User chạy tool phải gọi được Docker API: thuộc group `docker`, dùng `sudo`, hoặc đặt `DOCKER_HOST` trỏ tới một socket proxy chỉ đọc.

## Sử dụng

```bash
container-inventory                      # dạng bảng, chỉ container đang chạy
container-inventory -a                   # thêm container đã dừng
container-inventory -a --json            # bản ghi đầy đủ
container-inventory -a --ndjson          # mỗi dòng một bản ghi, dùng cho log agent
container-inventory -a --deep            # framework, package, Go build info
container-inventory --apps apps.toml     # ghép mapping app / owner / git khai báo tay
DOCKER_CONTEXT=prod container-inventory  # Docker host remote
container-inventory --selftest
```

Ví dụ (dạng bảng, đã lược bớt cột):

```text
IMAGE                          REGISTRY   PRODUCT                TECH                            CONTAINERS
custom_waf26:latest            ghcr.io    bunkerweb v1.6.16      nginx 1.30.5, Python, Redis     team1_fuap_bunkerweb
louislam/uptime-kuma:2.5.6     docker.io  uptime-kuma 2.5.6      Node.js 22.22.3, Yarn 1.22.22   uptime-kuma
cloudflare/cloudflared:latest  docker.io  cloudflared 2026.10.7  Go 1.27.3                       tunnel
fhacker2026-backend:latest     local                             Node.js 22.23.4, Yarn 1.22.22   backend-1 (stale)
```

## Splunk

Mỗi bản phát hành có kèm add-on cho Splunk:

- `TA-container-inventory.tgz`: cài trên indexer và search head (tách event, trích field JSON)
- `TA-container-inventory-<os>-<arch>.tgz`: cài trên Universal Forwarder (binary và scripted input chạy mỗi giờ, sourcetype `container:inventory`)

Các agent khác (Filebeat / Elastic Agent, Fluent Bit, Wazuh) đọc output `--ndjson` từ file. Xem [docs/splunk.md](docs/splunk.md).

## Tài liệu

- [docs/spec.md](docs/spec.md): thiết kế, nguồn dữ liệu của từng trường, giới hạn đã biết
- [docs/build.md](docs/build.md): build binary cho từng nền tảng, quy trình phát hành
- [docs/splunk.md](docs/splunk.md): Splunk Universal Forwarder và các agent khác
- [CHANGELOG.md](CHANGELOG.md): lịch sử phiên bản và roadmap
