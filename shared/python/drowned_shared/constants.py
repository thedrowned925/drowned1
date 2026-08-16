# Central protocol and GitHub release limits
#
# Release assets must remain under GitHub's 2 GiB per-file limit. 1536 MiB
# leaves a comfortable safety margin while still allowing high-throughput
# parallel uploads and keeping the number of assets reasonable.
CHUNK_SIZE_MIB = 1536
CHUNK_SIZE_BYTES = CHUNK_SIZE_MIB * 1024 * 1024

# Legacy fast-start constants kept for manifest/backward compatibility. The
# gigabit uploader now chooses an adaptive chunk size and may use a smaller
# size when necessary to keep all upload workers busy.
STARTER_CHUNK_SIZE_MIB = 256
STARTER_CHUNK_SIZE_BYTES = STARTER_CHUNK_SIZE_MIB * 1024 * 1024

MAX_RELEASE_ASSETS = 1000
RESERVED_RELEASE_ASSETS = 1
MAX_DATA_ASSETS = MAX_RELEASE_ASSETS - RESERVED_RELEASE_ASSETS
MAX_RELEASE_DATA_BYTES = CHUNK_SIZE_BYTES * MAX_DATA_ASSETS
MANIFEST_NAME = "manifest.json"
CATALOG_NAME = "catalog.json"
GITHUB_API = "https://api.github.com"
GITHUB_UPLOADS = "https://uploads.github.com"
GITHUB_API_VERSION = "2026-03-10"
SUPPORTED_CHANNELS = ("stable", "beta", "dev", "nightly", "archive")
