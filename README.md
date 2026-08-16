# Drowned Distribution Suite

Drowned Distribution Suite is a monorepo for distributing large game, software, homebrew and dataset builds through GitHub Releases without creating a second full archive copy on disk.

## Applications

- **Drowned Release Manager (Windows)** — creates draft releases, streams the source directory into ~1900 MiB chunks, hashes them, uploads release assets, publishes artwork/catalog metadata, then publishes the release.
- **Drowned Launcher (Windows)** — browses the shared catalog, downloads release chunks, reconstructs final files directly at their target offsets, resumes completed chunks, verifies SHA-256, and launches configured PC executables.
- **Drowned Mobile (Android)** — native Kotlin/Jetpack Compose catalog client with platform/channel filters and manager connection settings using the same catalog/manifest protocol.

> Use this project only for content you have the right to distribute.

## GitHub release model

The suite currently uses 1900 MiB data chunks. GitHub documents a maximum of 1000 assets per release and requires each release asset to be under 2 GiB. One asset is reserved for `manifest.json`, leaving 999 data chunks. Limits live in one shared constants module so they can be changed centrally if GitHub changes its policy.

Large payloads live in **GitHub Releases**, not Git history. Small artwork and `catalog.json` live in the repository.

## Repository layout

```text
shared/
  python/drowned_shared/   shared Windows backend
  schemas/                 JSON Schemas
  examples/                protocol examples
windows/
  release-manager/         publisher application
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

The catalog is the launcher index. Games are grouped by stable IDs and platform, with independent release channels such as `stable`, `beta`, `dev`, `nightly`, and `archive`.

### `manifest.json`

Each release manifest contains:

- file relative path, size and SHA-256
- chunk name, size and SHA-256
- segment map (`file`, `file_offset`, `chunk_offset`, `length`)
- owner/repo/tag metadata

Downloaders reject unsafe paths, invalid offsets, overlaps and sizes before writing files.

## Streaming behavior

Uploader:

```text
source files -> one temporary ~1900 MiB chunk -> hash -> upload -> delete chunk
```

Downloader:

```text
GitHub HTTP stream -> small RAM buffer -> manifest segment map -> final file offset
```

No RAR/ZIP extraction stage is required.

## Tests

```bash
pip install -e shared/python
python -m unittest discover -s tests -v
```

Tests cover chunk reconstruction, unsafe paths, invalid segment maps and catalog parsing.

## Builds

GitHub Actions produce:

- `Drowned-Release-Manager-Windows`
- `Drowned-Launcher-Windows`
- `Drowned-Mobile-debug.apk`

A `suite-vX.Y.Z` tag triggers the release workflow and attaches packaged builds plus SHA256 sums when all build jobs succeed.
