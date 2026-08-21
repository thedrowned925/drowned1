# Drowned Control

Drowned Control is a read-only Android dashboard for the Drowned distribution repository.

## What it shows

- Total game count
- Total published channel/version count
- Total game-data storage from `catalog.json`
- Search and platform filters
- Game cover and hero artwork
- Per-game total storage
- Channel, version, tag and publish date
- Screenshots when present in the catalog
- Offline fallback to the last successfully downloaded catalog

## Security model

The app does not contain a GitHub PAT and does not call GitHub write APIs. It only reads the public `catalog.json` and artwork URLs over HTTPS. It cannot publish, delete or modify releases.

## Data source

`https://raw.githubusercontent.com/thedrowned925/drowned1/main/catalog.json`

The storage number is the sum of the `size` field for every published channel in the catalog. Small GitHub metadata/artwork overhead is intentionally not included.
