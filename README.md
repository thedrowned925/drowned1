# Drowned Distribution Suite

Drowned Distribution Suite is a monorepo for distributing large game, software, homebrew and dataset builds through GitHub Releases without creating a second full archive copy on disk.

## Applications

- **Drowned Release Manager (Windows)** — creates draft releases, streams the source directory into ~1900 MiB chunks, hashes them, uploads release assets, publishes raw repository metadata, and includes a careful release/game deletion manager.
- **Drowned Launcher (Windows)** — browses the shared raw catalog, downloads release chunks, reconstructs final files directly at their target offsets, resumes completed chunks, and verifies SHA-256.
- **Drowned Mobile (Android)** — native Kotlin/Jetpack Compose catalog client with platform/channel filters and manager connection settings using the same catalog/manifest protocol.

> Use this project only for content you have the right to distribute.

## GitHub release model

The suite currently uses 1900 MiB data chunks. GitHub documents a maximum of 1000 assets per release and requires each release asset to be under 2 GiB. One asset is reserved for a redundant `manifest.json`, leaving 999 data chunks. Limits live in one shared constants module so they can be changed centrally if GitHub changes its policy.

Large payloads live in **GitHub Releases**, not Git history. Small metadata lives in the repository and is read through `raw.githubusercontent.com` whenever possible:

- `catalog.json`
- `manifests/<platform>/<game>/<channel>/<version>.json`
- `artwork/<platform>/<game>/...`

The REST API is reserved for operations that actually require authenticated GitHub management, such as creating/updating repository content and creating/deleting Releases. Binary chunk downloads use direct `github.com/.../releases/download/...` URLs and do not enumerate assets through the REST API.

## Safe deletion model

Release Manager has a **Yayınları Yönet** tab with two destructive operations:

- delete one selected channel/version
- delete an entire game across every channel

Deletion is deliberately ordered so the catalog is the last mutation:

```text
GitHub Release + its chunk assets
        -> raw manifest
        -> artwork (only when the whole game disappears)
        -> catalog.json entry
```

A whole-game deletion requires typing the exact game title. A channel/version deletion requires typing `SİL`.

The deletion backend is idempotent. If a network/API error interrupts the operation, `catalog.json` is not intentionally mutated before the remote cleanup completes. Re-running the same deletion treats already-missing Releases/manifests/artwork as already deleted and continues toward the final catalog cleanup.

## Repository layout

```text
shared/
  python/drowned_shared/   shared Windows backend
  schemas/                 JSON Schemas
  examples/                protocol examples
windows/
  release-manager/         publisher + deletion manager
  launcher/                end-user launcher
android/                    native Android app
.github/workflows/          CI and build pipelines
```

## Windows development

Python 3.12+ is recommended.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e shared/python
pip install -r windows/release-manager/requirements.txt
python windows/release-manager/app.py
```

Launcher:

```powershell
pip install -r windows/launcher/requirements.txt
python windows/launcher/app.py
```

### GitHub token

Release Manager supports a fine-grained GitHub PAT. Restrict the token to the distribution repository and grant the minimum repository permission needed by GitHub for Releases/Contents writes. The app stores the token through the OS keyring; it is never written into source control.

## Android development

The Android project uses Kotlin, Jetpack Compose, Material 3, AGP 9.3.0 and Gradle 9.5.0. CI installs the required Gradle/Android SDK toolchain.

```bash
cd android
gradle :app:assembleDebug
```

## Protocol

### `catalog.json`

The catalog is the launcher index. Games are grouped by stable IDs and platform, with independent release channels such as `stable`, `beta`, `dev`, `nightly`, and `archive`. Clients read it directly from the repository raw URL.

### Raw release manifests

Each channel points to a repository raw manifest. Each manifest contains:

- file relative path, size and SHA-256
- chunk name, size and SHA-256
- segment map (`file`, `file_offset`, `chunk_offset`, `length`)
- owner/repo/tag metadata

Downloaders reject unsafe paths, invalid offsets, overlaps and sizes before writing files. The manifest tells clients which direct Release download URLs to use for the large chunks; clients do not need to list Release assets through the REST API.

## Streaming behavior

Uploader:

```text
source files -> one temporary ~1900 MiB chunk -> hash -> upload -> delete chunk
```

Downloader:

```text
raw manifest -> direct GitHub Release HTTP stream -> small RAM buffer -> segment map -> final file offset
```

No RAR/ZIP extraction stage is required.

## Tests

```bash
pip install -e shared/python
python -m unittest discover -s tests -v
```

Tests cover chunk reconstruction, unsafe paths, invalid segment maps, catalog parsing, safe deletion ordering, full game cleanup, retry behavior, and protection against catalog mutation after a simulated deletion failure.

## Builds

GitHub Actions produce:

- `Drowned-Release-Manager-Windows`
- `Drowned-Launcher-Windows`
- `Drowned-Mobile-debug.apk`

A `suite-vX.Y.Z` tag triggers the release workflow and attaches packaged builds plus SHA256 sums when all build jobs succeed.
