# Build binary

[English](../build.md) | Tiếng Việt

Tool là một file Python chỉ dùng stdlib. Binary đóng gói nó cùng Python runtime bằng [PyInstaller](https://pyinstaller.org) (`--onefile`), nên máy chạy không cần cài Python. PyInstaller không cross-compile: **binary của OS nào phải build trên OS đó**. Vì vậy cách dễ nhất là để GitHub Actions build cả 5 bản.

## Cách 1: GitHub Actions (khuyên dùng)

Workflow [`.github/workflows/build.yml`](../../.github/workflows/build.yml):

| Sự kiện | Kết quả |
|---|---|
| push lên `main`, pull request | `--selftest` trên Python 3.9 và 3.12, build 5 binary, mỗi binary tự chạy `--selftest`. Binary nằm trong mục *Artifacts* của lần chạy. |
| push tag `v*` | Như trên, rồi tạo GitHub Release gồm binary, gói Splunk add-on cho từng OS và `SHA256SUMS`. |

Phát hành một version:

```bash
# 1. sửa __version__ trong inventory.py và version trong splunk/TA-container-inventory/default/app.conf
# 2. ghi lại thay đổi vào CHANGELOG.md
git commit -am "release v0.2.5"
git tag v0.2.5
git push origin main v0.2.5
```

| Target | Runner | Ghi chú |
|---|---|---|
| `linux-amd64` | `ubuntu-latest` | build trong container `python:3.11-buster` (glibc 2.28) |
| `linux-arm64` | `ubuntu-24.04-arm` | như trên, bản arm64 |
| `windows-amd64` | `windows-latest` | Python 3.12 |
| `macos-arm64` | `macos-latest` | Apple Silicon |
| `macos-amd64` | `macos-15-intel` | Intel |

**Tại sao Linux build trên Debian 10?** Binary PyInstaller chạy được trên glibc **bằng hoặc mới hơn** glibc của máy build. Nếu build trên Ubuntu 24.04 (glibc 2.39), binary sẽ lỗi `GLIBC_2.xx not found` trên RHEL 8 / Ubuntu 20.04. Build trên glibc 2.28 thì chạy được trên RHEL/Rocky/Alma 8+, Ubuntu 20.04+, Debian 10+. CentOS 7 (glibc 2.17) không hỗ trợ: dùng bản Python, cần Python 3.9+.

## Cách 2: build tay

Cần Python 3.9+ trên máy build.

**Linux** (build trong Docker để có glibc cũ):

```bash
docker run --rm -v "$PWD":/src -w /src python:3.11-buster sh -c \
  "pip install pyinstaller==6.11.1 && pyinstaller --onefile --name container-inventory inventory.py"
./dist/container-inventory --selftest
```

Chạy lệnh này trên máy arm64 (ví dụ Mac Apple Silicon) sẽ ra binary linux-arm64. Muốn bản amd64 thì thêm `--platform linux/amd64` (chạy qua giả lập, chậm).

**macOS / Windows**:

```bash
python3 -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install pyinstaller==6.11.1
pyinstaller --onefile --name container-inventory inventory.py
./dist/container-inventory --selftest                # Windows: dist\container-inventory.exe --selftest
```

## Chạy binary

| OS | Lưu ý |
|---|---|
| Linux | `chmod +x`, user phải gọi được Docker. Binary tự giải nén vào `/tmp` mỗi lần chạy. Nếu `/tmp` mount `noexec`, đặt `TMPDIR` sang thư mục khác. |
| Windows | Chạy được từ PowerShell / cmd. Một số antivirus báo nhầm binary PyInstaller onefile. Khi đó whitelist theo SHA256 trong `SHA256SUMS`. |
| macOS | Binary chưa ký. Lần đầu chạy cần `xattr -d com.apple.quarantine container-inventory-macos-*`. |

Kiểm tra: `container-inventory --version` và `container-inventory --selftest`.

## Kiểm chứng tải về

```bash
sha256sum -c SHA256SUMS --ignore-missing          # macOS: shasum -a 256 -c SHA256SUMS --ignore-missing
```
