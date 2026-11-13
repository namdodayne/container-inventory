# Spec

[English](../spec.md) | Tiếng Việt

**Mốc là image, không phải container.** Công nghệ, git và registry là thuộc tính của image. Nhiều container (replica, compose scale) dùng chung một image. Vì vậy mỗi bản ghi là một image ID, container nằm trong danh sách `containers` của image đó.

**Fallback mốc container.** Nếu image đã bị xoá hoặc build lại trùng tag, host chỉ còn container. Khi đó mỗi container là một bản ghi (`anchor: "container"`), dữ liệu lấy từ bản config image mà container còn giữ.

**Không cần đệ quy theo tầng image.** Docker gộp ENV và LABEL của mọi tầng FROM vào config của image ngoài cùng. Process và file đọc từ container đang chạy là kết quả cuối của mọi tầng. Chuỗi base (`base`) chỉ dùng để truy nguồn gốc, không cần cho việc nhận diện tech.

**Môi trường**: Linux, macOS, Windows (Docker Desktop). Đã test: macOS; Ubuntu 22.04 / Python 3.10 (có `--deep`); Ubuntu 24.04 / Python 3.12; Windows. Cần Python 3.9+ (hoặc dùng binary đã build sẵn, không cần Python), chỉ dùng stdlib, và `docker` CLI. User chạy script phải gọi được Docker: thuộc group `docker` hoặc dùng `sudo`. File `--apps` dạng TOML cần Python 3.11+ hoặc `pip install tomli`; dạng JSON (`{"app": [...]}`) chạy được mọi bản.

**Đầu vào**
- Docker daemon lấy theo `DOCKER_HOST` / `DOCKER_CONTEXT`, chạy được với host remote.
- Mặc định chỉ lấy image có container đang chạy. Cờ `-a` lấy thêm container đã dừng.
- `--deep`: đọc thêm bên trong container đang chạy, xem bảng dưới.
- `--apps <file.toml|file.json>`: mapping thủ công, xem [apps.example.toml](../../apps.example.toml).

## Chế độ mặc định: chỉ đọc metadata, không exec vào container

| Trường | Lấy từ |
|---|---|
| `registry`, `repo`, `tag` | Ref mà container dùng khi chạy (`Config.Image`). Image không có registry thì là `docker.io`, không có namespace thì thêm `library/`. Image build trên host này có `registry: local` và không thêm `library/`. Một image được tính là build local khi có một trong ba dấu hiệu: (1) không có `RepoDigests` (chỉ đúng với classic image store); (2) ID image nằm trong output của `docker buildx history` (BuildKit, buildx 0.12+); (3) có label `com.docker.compose.service`, label này compose chỉ gắn vào image do nó build. Nếu container đang chạy image cũ đã mất, script dùng image mà tag hiện trỏ tới để quyết định. |
| `digest` | Digest trong ref, nếu không có thì lấy `RepoDigests[0]` |
| `base` | Chuỗi base image, gần nhất đứng trước. Một image local được tính là base nếu danh sách layer (`RootFS.Layers`) của nó là tiền tố thực sự của image này. |
| `product`, `product_version`, `version_source` | Tên + version của app trong image, ví dụ `bunkerweb v1.6.16`, `kibana 9.3.8`. Tên lấy từ label `org.opencontainers.image.title` / `org.label-schema.name`. Version lấy từ label `org.opencontainers.image.version` / `org.label-schema.version` (`version_source: label`); nếu không có label thì lấy từ tag có dạng semver như `9.3.8`, `v2.45.1`, `1.30.4-alpine` (`version_source: tag`), khi đó tên lấy từ tên repo. Tag `latest`, `15`, `16-alpine` hay tag ngày tháng không được tính là version. Label có thể kế thừa từ base image (ví dụ wolfi-base). |
| `tech` | 3 nguồn: env `<X>_VERSION` / `<X>_MAJOR` (bảng `ENV_TECH`); tên process trong entrypoint/cmd, tên image và `docker top` (bảng `NAME_TECH`) |
| `connects` | URI kết nối trong env của container (`postgresql://`, `redis://`, `mongodb+srv://`, `sqlite:///`...) và các biến `<X>_HOST`. Chỉ giữ host:port, **luôn bỏ user/password**. |
| `git`, `revision` | Label `org.opencontainers.image.source` / `.revision`, hoặc `org.label-schema.vcs-*` |
| `containers[]` | Tên, id, trạng thái, compose project, port. `stale: true` nghĩa là tag đã được build lại hoặc pull lại, nhưng container vẫn chạy image cũ (container chưa được tạo lại). `tag_image_id` là ID image mà tag đang trỏ tới. |
| `app` | Mapping thủ công. `[[app]]` đầu tiên có glob `match` khớp `<registry>/<repo>` hoặc tên container sẽ được dùng. `git` khai báo tay ghi đè `git` lấy từ label. |

## `--deep`: đọc bên trong container đang chạy

Chế độ này chạy `docker exec -u 0 <ctr> sh -c <script>`. Script chỉ đọc: `cat`, `find`, `readlink`, và lệnh `--version` của các runtime đã biết. Ngoài ra dùng `docker cp` để copy binary của process ra host đọc. Mỗi image chỉ quét một container, ưu tiên container đang chạy. Container đã dừng hoặc đang `restarting` (cần `-a`) được đọc bằng `docker export` thay cho `exec` (`deep_source: "export"`): không có version runtime, không có dữ liệu trong volume.

| Trường | Lấy từ |
|---|---|
| `os` | `PRETTY_NAME` trong `/etc/os-release` |
| `tech` (version) | Lệnh `<bin> --version` (hoặc `-v`). Chỉ điền version cho tech đã xác định là đang chạy, không thêm runtime chỉ được cài sẵn. |
| `tech` (lib nhúng) | File `libmodsecurity*` → ModSecurity; `libluajit*` → LuaJIT; `liblua*` → Lua |
| `frameworks` | 3 nguồn, đối chiếu với bảng `FRAMEWORKS`: (1) Python `*.dist-info` cho version đúng bản đang cài; (2) manifest trong WorkingDir, `/app`, `/srv`, `/opt`...: `package.json`, `requirements*.txt`, `pyproject.toml`, `go.mod`, `composer.json`, `pom.xml`, `build.gradle*`, `Gemfile`, `Cargo.toml`, `*.csproj`; (3) dependency của binary Go |
| `packages` | Mọi dependency tìm được, không lọc theo bảng `FRAMEWORKS`: `npm:<name>` lấy từ `dependencies` trong `package.json`, version là bản cài thật trong `node_modules` (nếu không có thì lấy range trong manifest); `pypi:<name>` lấy từ dist-info (gồm cả transitive); `go:<module>` lấy từ go.mod hoặc binary; `composer:<name>`. Bảng chỉ hiện số lượng, chi tiết xem ở `--json`. |
| `data_files`, `tech.SQLite` | File `*.sqlite`, `*.sqlite3`, `*.db` có header là `SQLite format 3` |
| `product_version` (`version_source: binary`) | Chỉ dùng khi label và tag không cho ra version. Lấy từ Go build info của binary: `-ldflags -X ...Version=` (ví dụ cloudflared `main.Version=2026.10.7`), nếu không có thì lấy tag thật của module chính. Pseudo-version `v0.0.0-…` và `(devel)` bị bỏ qua. |
| `binaries[]` | Binary của mọi process trong container (`/proc/*/exe`, fallback sang `cmdline` khi bị rosetta/qemu hoặc khác uid), copy ra bằng `docker cp` để đọc Go build info: version Go, module chính, dependency. Image distroless không có `sh` thì dùng binary trong entrypoint. |

**Đầu ra**: bảng (mặc định), `--json` (mảng JSON có thụt dòng) hoặc `--ndjson` (mỗi dòng một bản ghi JSON, dùng cho log agent). Mỗi image là một bản ghi.

**Giới hạn đã biết**
- `base` chỉ tìm được khi image gốc có sẵn trên host **và cùng kiến trúc**. Ví dụ `custom_waf26` là amd64, còn bunkerweb local là arm64, nên layer khác nhau và không ra base.
- Containerd store (Docker Desktop): image build bằng `docker build` mà build history đã bị xoá, lại không qua compose, sẽ bị tính là `docker.io`. Trường hợp này dùng `--apps` để gán đúng.
- Framework Node chỉ lấy từ `package.json` của app. Nếu app đã bundle thành `dist/` mà không giữ `package.json` thì sẽ miss. Chưa quét `node_modules`.
- Binary Rust, C/C++ chưa đọc được dependency. Binary Go build trước Go 1.18 không có build info dạng inline.
- `FRAMEWORKS` là danh sách chọn lọc, nên package không có trong bảng sẽ không hiện. Muốn bắt thêm thì thêm một dòng vào bảng.
- Không có `--deep` thì container đã dừng chỉ có tech lấy từ env/cmd.
