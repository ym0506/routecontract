#!/usr/bin/env bash
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$script_directory/.." && pwd)"

exec "$repository_root/gradlew" \
    --no-daemon \
    --no-build-cache \
    -p "$repository_root" \
    :routecontract-shardingsphere-5.5:manifestCiFailureDemo \
    --rerun-tasks
