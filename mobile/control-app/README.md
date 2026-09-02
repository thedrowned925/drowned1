# Drowned Control

Drowned Control is a read-only Android dashboard for the Drowned distribution repository.

## What it shows

### Catalog tab (v1.0)

- Total game count
- Total published channel/version count
- Total game-data storage from `catalog.json`
- Search and platform filters
- Game cover and hero artwork
- Per-game total storage
- Channel, version, tag and publish date
- Screenshots when present in the catalog
- Offline fallback to the last successfully downloaded catalog

### Release Manager tab (v1.1)

- **Live desktop upload card**: while the Windows Release Manager desktop tool is actively uploading a game/channel or optional package, the phone shows its title, platform/channel/version, phase (preparing/uploading/writing metadata) and live percentage — independent of GitHub Actions, since a desktop upload doesn't necessarily trigger a CI run
- Overview summary: running builds, failed builds, release count, total downloads, latest run status
- GitHub Actions pipeline runs (status, conclusion, event, branch, actor, run number) with filter chips
- Live progress per running CI run: current stage name and completion percentage, computed from the run's job/step list (`GET /actions/runs/{id}/jobs`)
- Auto-refresh: polls every 8s while a CI build or a desktop upload is in progress, every 45s when idle — no manual refresh needed to watch either one land
- Published GitHub Releases with asset list, sizes, download counts and draft/prerelease badges
- Per-component build status read from `.build-status/*.txt` files written by CI workflows
- Tap a run or release to open its GitHub page in the browser
- Offline fallback to the last successfully downloaded dashboard

The Release Manager tab is connected to the whole release pipeline, both halves of it:

- **CI**: it reads the same GitHub Actions runs and Releases that the build workflows produce, and the `.build-status` files those workflows write after every run.
- **Desktop uploads**: the Windows Release Manager app (`windows/release-manager`) writes `.release-status/live.json` every few seconds while a chunked upload is running (via `drowned_shared.upload_status.UploadStatusBroadcaster`, using the same GitHub Contents API call the catalog/manifests already go through — no new server, no new credential). The phone just reads that file back.

Polling uses conditional GET (`If-None-Match` / ETag) against the GitHub Actions/Releases API: an unchanged resource returns HTTP 304, which does not count against GitHub's unauthenticated 60-req/hour rate limit. This is what makes frequent polling safe without a token. The two raw files (`.build-status/*.txt`, `.release-status/live.json`) are served from raw.githubusercontent.com and aren't subject to that quota at all.

## Security model

The app does not contain a GitHub PAT and does not call GitHub write APIs. It only reads the public `catalog.json`, public GitHub Actions/Releases REST API, and artwork/status URLs over HTTPS. It cannot publish, delete or modify releases.

## Data sources

- Catalog: `https://raw.githubusercontent.com/thedrowned925/drowned1/main/catalog.json`
- Pipeline runs: `https://api.github.com/repos/thedrowned925/drowned1/actions/runs`
- Releases: `https://api.github.com/repos/thedrowned925/drowned1/releases`
- Build status: `https://raw.githubusercontent.com/thedrowned925/drowned1/main/.build-status/*.txt`

The catalog storage number is the sum of the `size` field for every published channel in the catalog. Small GitHub metadata/artwork overhead is intentionally not included.
