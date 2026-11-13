# Tích hợp Splunk Universal Forwarder

```text
 Docker host                                 Splunk
┌──────────────────────────────────┐     ┌──────────────────────────────────────┐
│ Splunk UF                        │     │ Indexer / HF   TA-container-inventory │
│  TA-container-inventory-<target> │────▶│   1 dòng = 1 event (props.conf)      │
│   mỗi giờ: container-inventory   │     │ Search head    TA-container-inventory │
│            --ndjson -a           │     │   KV_MODE = json → field tự tách     │
└──────────────────────────────────┘     └──────────────────────────────────────┘
```

Mỗi lần chạy, tool in ra **một dòng JSON cho mỗi image** (`--ndjson`), gồm cả container đã dừng (`-a`). Sourcetype là `container:inventory`.

## Gói phát hành

Có trên trang [Releases](https://github.com/namdodayne/container-inventory/releases/latest):

| Gói | Cài ở đâu | Bên trong |
|---|---|---|
| `TA-container-inventory.tgz` | Indexer, heavy forwarder, search head | `props.conf` (tách event, field JSON). Không có input. |
| `TA-container-inventory-linux-amd64.tgz` | UF trên Linux x86_64 | props + `inputs.conf` + binary + `container_inventory.path` |
| `TA-container-inventory-linux-arm64.tgz` | UF trên Linux arm64 | như trên |
| `TA-container-inventory-windows-amd64.tgz` | UF trên Windows x64 | như trên, binary `.exe` |
| `TA-container-inventory-macos-arm64.tgz`, `-macos-amd64.tgz` | UF trên macOS | như trên |

Mỗi target có một tên app riêng. Lý do: file `.path` phải ghi đường dẫn tuyệt đối tới binary, mà đường dẫn này chứa tên app. Nhờ tên riêng, deployment server giữ được tất cả các bản cùng lúc.

## 1. Indexer và search head

```bash
tar -xzf TA-container-inventory.tgz -C $SPLUNK_HOME/etc/apps/
$SPLUNK_HOME/bin/splunk restart
```

Indexer cluster: đặt vào `manager-apps/` rồi apply bundle. Search head cluster: đặt vào `shcluster/apps/` của deployer.

Nếu muốn dữ liệu vào index riêng, tạo index trước, ví dụ `container_inventory`, rồi đổi `index` ở bước 2.

## 2. Universal Forwarder

### Linux

```bash
tar -xzf TA-container-inventory-linux-amd64.tgz -C /opt/splunkforwarder/etc/apps/
sudo -u splunkfwd /opt/splunkforwarder/etc/apps/TA-container-inventory-linux-amd64/bin/container-inventory --version
```

**Quyền gọi Docker.** Từ bản 9.1, UF chạy bằng user `splunkfwd` (bản cũ hơn là `splunk`). User này phải đọc được Docker API. Chọn một trong hai cách:

| Cách | Làm | Đánh đổi |
|---|---|---|
| A. group `docker` | `sudo usermod -aG docker splunkfwd`, rồi restart UF | ⚠️ Vào được `docker.sock` là có quyền tương đương root trên host. Chạy được `--deep`. |
| B. socket proxy chỉ đọc (khuyên dùng) | Chạy [docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy) với `CONTAINERS=1 IMAGES=1 INFO=1`, bind `127.0.0.1:2375`. Thêm `DOCKER_HOST=tcp://127.0.0.1:2375` vào `$SPLUNK_HOME/etc/splunk-launch.conf`, rồi restart UF. | Chỉ cho phép GET, nên không dùng được `--deep` (cần exec). `buildx history` cũng không chạy được, nên nhận diện image local chỉ còn dựa vào `RepoDigests` và label compose. |

Ví dụ chạy proxy cho cách B:

```bash
docker run -d --name docker-ro-proxy --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -e CONTAINERS=1 -e IMAGES=1 -e INFO=1 -e POST=0 \
  -p 127.0.0.1:2375:2375 tecnativa/docker-socket-proxy:v0.5.0
```

### Windows

Giải nén `TA-container-inventory-windows-amd64.tgz` vào `C:\Program Files\SplunkUniversalForwarder\etc\apps\`, rồi restart service `SplunkForwarder`. Mặc định service chạy bằng `LocalSystem`, tài khoản này gọi được named pipe của Docker. Nếu đổi sang tài khoản dịch vụ khác, thêm tài khoản đó vào group `docker-users` (Docker Desktop) hoặc cấp quyền trên pipe `\\.\pipe\docker_engine`.

### macOS

Như Linux, nhưng trước khi chạy phải gỡ quarantine:

```bash
xattr -dr com.apple.quarantine /Applications/SplunkForwarder/etc/apps/TA-container-inventory-macos-*
```

### Deployment server

Đặt các gói forwarder vào `$SPLUNK_HOME/etc/deployment-apps/`, rồi tạo serverclass theo `machineTypesFilter`:

```ini
# serverclass.conf
[serverClass:container_inventory_linux_amd64]
whitelist.0 = *
machineTypesFilter = linux-x86_64
[serverClass:container_inventory_linux_amd64:app:TA-container-inventory-linux-amd64]
restartSplunkd = true

[serverClass:container_inventory_linux_arm64]
whitelist.0 = *
machineTypesFilter = linux-aarch64
[serverClass:container_inventory_linux_arm64:app:TA-container-inventory-linux-arm64]
restartSplunkd = true

[serverClass:container_inventory_windows]
whitelist.0 = *
machineTypesFilter = windows-x64
[serverClass:container_inventory_windows:app:TA-container-inventory-windows-amd64]
restartSplunkd = true
```

Đổi `whitelist.0` để chỉ chọn các host có chạy Docker.

## 3. Tuỳ chỉnh

Tạo `local/inputs.conf` trong app của forwarder. Không sửa `default/`, vì lần nâng cấp sau sẽ ghi đè.

```ini
[script://./bin/container_inventory.path]
index = container_inventory
interval = 1800            # giây, hoặc cron: 0 */6 * * *
```

Muốn đổi tham số (thêm `--deep`, thêm `--apps`), sửa dòng duy nhất trong `bin/container_inventory.path`. File này nằm ngoài `local/`, nên phải sửa lại sau mỗi lần nâng cấp gói:

```text
$SPLUNK_HOME/etc/apps/TA-container-inventory-linux-amd64/bin/container-inventory --ndjson -a --deep --apps /etc/container-inventory/apps.toml
```

`--deep` chạy `docker exec -u 0` vào từng container, vì vậy cần cách A ở trên và mất vài phút mỗi host. Nên dùng interval dài, ví dụ 6–24 giờ.

## 4. Kiểm tra

```spl
index=main sourcetype=container:inventory earliest=-2h
| stats latest(product) as product latest(registry) as registry by host image
```

Không thấy dữ liệu thì xem log của UF:

```bash
grep -i "container_inventory\|ExecProcessor" /opt/splunkforwarder/var/log/splunk/splunkd.log | tail
```

| Lỗi trong splunkd.log | Nguyên nhân |
|---|---|
| `permission denied ... docker.sock` | User UF chưa vào được Docker, xem mục Quyền gọi Docker. |
| `failed to connect to the docker API` | Docker không chạy, hoặc `DOCKER_HOST` sai. |
| `GLIBC_2.xx not found` | OS quá cũ (glibc < 2.28), dùng bản Python thay binary. |
| `cannot execute ... noexec` | `/tmp` mount `noexec`: thêm `TMPDIR=/opt/splunkforwarder/var/run` vào `splunk-launch.conf`. |

## 5. Search mẫu

Mỗi event là một image. Container nằm trong mảng `containers{}`.

Version app và nguồn của version:

```spl
index=main sourcetype=container:inventory
| dedup host image_id
| table host image registry product product_version version_source
```

Container đang chạy image cũ (chưa được tạo lại sau khi build hoặc pull image mới):

```spl
index=main sourcetype=container:inventory
| dedup host image_id
| spath path=containers{} output=c | mvexpand c
| spath input=c | where stale="true"
| table host name image tag_image_id status
```

Image không rõ version (tag `latest`, không có label):

```spl
index=main sourcetype=container:inventory
| dedup host image_id
| where tag="latest" AND product_version=""
| stats values(host) as hosts by image
```

## Agent khác

Agent nào đọc được file log cũng dùng được (Elastic Agent / Filebeat, Fluent Bit, Wazuh, Vector...). Cách làm: cho tool ghi NDJSON ra file theo lịch, rồi để agent tail file đó.

Mỗi lần chạy ghi ra **một file mới**. Không ghi đè một file cố định: nội dung đầu file giữa hai lần chạy gần như giống nhau, nên agent nhận diện file theo checksum đầu file (Splunk `monitor`, Filebeat `fingerprint`) sẽ coi là file đã đọc rồi và bỏ qua.

```bash
# /etc/cron.d/container-inventory: mỗi giờ một file, giữ 2 ngày. Trong crontab, % phải escape thành \%.
0 * * * * root d=/var/log/container-inventory; mkdir -p $d && /usr/local/bin/container-inventory --ndjson -a > $d/.tmp && mv $d/.tmp $d/inventory-$(date +\%Y\%m\%d\%H).ndjson && find $d -name '*.ndjson' -mtime +2 -delete
```

Windows: dùng Task Scheduler chạy lệnh tương tự, ghi vào `C:\ProgramData\container-inventory\inventory-<giờ>.ndjson`.

| Agent | Cấu hình đọc file |
|---|---|
| Filebeat / Elastic Agent | input `filestream`, `paths: [/var/log/container-inventory/*.ndjson]`, `parsers: - ndjson: {target: ""}` |
| Fluent Bit | `[INPUT] Name tail`, `Path /var/log/container-inventory/*.ndjson`, `Parser json` |
| Wazuh | `<localfile><log_format>json</log_format><location>/var/log/container-inventory/*.ndjson</location></localfile>` |
| Splunk UF (thay cho scripted input) | `[monitor:///var/log/container-inventory/*.ndjson]`, `sourcetype = container:inventory` |
