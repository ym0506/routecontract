#!/usr/bin/env bash
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

"$script_directory/run-demo.sh"
exec "$script_directory/demo-manifest-ci-failure.sh"
