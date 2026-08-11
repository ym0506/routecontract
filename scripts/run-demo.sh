#!/usr/bin/env bash
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$script_directory/.." && pwd)"
test_name='io.github.ym0506.routecontract.example.OperationCorrelationMySqlTest.functionallyEquivalentRangeQueryFailsCanonicalManifestContractWithActionableCiEvidence'
result_file="$repository_root/examples/mysql/build/test-results/test/TEST-io.github.ym0506.routecontract.example.OperationCorrelationMySqlTest.xml"

"$repository_root/gradlew" \
    --no-daemon \
    --no-build-cache \
    -p "$repository_root" \
    :mysql-example:test \
    --rerun-tasks \
    --tests "$test_name"

if [[ ! -f "$result_file" ]]; then
    echo "Demo test passed but its machine-readable result was not found: $result_file" >&2
    exit 1
fi

demo_line="$(grep -F 'ROUTECONTRACT_MANIFEST_DEMO' "$result_file" \
    | sed -E 's/.*(ROUTECONTRACT_MANIFEST_DEMO[^<]*).*/\1/' \
    | head -n 1 || true)"
if [[ -z "$demo_line" ]]; then
    echo "Demo marker is missing from $result_file" >&2
    exit 1
fi

printf '%s\n' "$demo_line"
