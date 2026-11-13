# Building binaries

English | [Tiếng Việt](vi/build.md)

The tool is a single standard-library Python file. Binaries bundle it with a Python runtime using [PyInstaller](https://pyinstaller.org) (`--onefile`), so target hosts need no Python. PyInstaller does not cross-compile: **each OS binary must be built on that OS**, which is why GitHub Actions builds all five.

## GitHub Actions (recommended)

Workflow: [`.github/workflows/build.yml`](../.github/workflows/build.yml)

| Event | Result |
|---|---|
| push to `main`, pull request | `--selftest` on Python 3.9 and 3.13, then 5 binaries, each running its own `--selftest`. Binaries are kept as run artifacts. |
| tag `v*` | Same, then a GitHub Release with the binaries, one Splunk add-on package per platform, and `SHA256SUMS`. |

Cutting a release:

```bash
# 1. bump __version__ in inventory.py and version in splunk/TA-container-inventory/default/app.conf
# 2. add the changes to CHANGELOG.md
git commit -am "release v0.2.5"
git tag v0.2.5
git push origin main v0.2.5
```

| Target | Runner | Notes |
|---|---|---|
| `linux-amd64` | `ubuntu-latest` | built inside `python:3.11-buster` (glibc 2.28) |
| `linux-arm64` | `ubuntu-24.04-arm` | same, arm64 |
| `windows-amd64` | `windows-latest` | Python 3.12 |
| `macos-arm64` | `macos-latest` | Apple Silicon |
| `macos-amd64` | `macos-15-intel` | Intel |

**Why build Linux on Debian 10?** A PyInstaller binary runs on a glibc **equal to or newer than** the build host's. Built on Ubuntu 24.04 (glibc 2.39), it fails with `GLIBC_2.xx not found` on RHEL 8 or Ubuntu 20.04. Built on glibc 2.28, it runs on RHEL / Rocky / Alma 8+, Ubuntu 20.04+ and Debian 10+. CentOS 7 (glibc 2.17) is not supported by the binary; run `inventory.py` with Python 3.9+ there.

## Building by hand

Requires Python 3.9+ on the build machine.

**Linux** (inside Docker, for an old glibc):

```bash
docker run --rm -v "$PWD":/src -w /src python:3.11-buster sh -c \
  "pip install pyinstaller==6.11.1 && pyinstaller --onefile --name container-inventory inventory.py"
./dist/container-inventory --selftest
```

On an arm64 machine (e.g. Apple Silicon) this produces a linux-arm64 binary. Add `--platform linux/amd64` for amd64 (emulated, slow).

**macOS / Windows**:

```bash
python3 -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install pyinstaller==6.11.1
pyinstaller --onefile --name container-inventory inventory.py
./dist/container-inventory --selftest                # Windows: dist\container-inventory.exe --selftest
```

## Running the binary

| OS | Notes |
|---|---|
| Linux | `chmod +x`; the user must be able to reach Docker. The binary unpacks itself to `/tmp` on every run; if `/tmp` is mounted `noexec`, set `TMPDIR` to another directory. |
| Windows | Runs from PowerShell or cmd. Some antivirus products flag PyInstaller onefile binaries; allow-list by the hash in `SHA256SUMS`. |
| macOS | The binary is not signed. Before the first run: `xattr -d com.apple.quarantine container-inventory-macos-*`. |

Check with `container-inventory --version` and `container-inventory --selftest`.

## Verifying downloads

```bash
sha256sum -c SHA256SUMS --ignore-missing          # macOS: shasum -a 256 -c SHA256SUMS --ignore-missing
```
