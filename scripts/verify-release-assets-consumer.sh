#!/usr/bin/env bash
set +x
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$script_directory/.." && pwd)"
consumer_directory="$repository_root/examples/standalone-consumer"
installer="$script_directory/install-release-assets.py"

usage() {
    cat <<'EOF'
Usage: ./scripts/verify-release-assets-consumer.sh \
  /absolute/path/to/downloaded-release-assets \
  /absolute/path/to/empty-target-maven-repository

The installer first verifies the exact public Release allowlist, SHA256SUMS,
non-SNAPSHOT Maven coordinate (stable or strict -rcN), RouteContract JAR
structure, and the source ZIP's versioned root, required source paths, and
canonical package namespace. The
standalone consumer then resolves RouteContract exclusively from the explicit
repository and runs one real ShardingSphere-JDBC 5.5.3/MySQL 8.4.11 test.

The target coordinate must not already exist. Installation itself is offline;
the consumer build can download the Gradle distribution and third-party Maven
Central dependencies and requires Java 17 plus a running Docker daemon.
EOF
}

if [[ "$#" -ne 2 ]]; then
    usage >&2
    exit 64
fi

release_assets_directory="$1"
target_maven_repository="$2"
if [[ "$release_assets_directory" != /* || "$target_maven_repository" != /* ]]; then
    echo "Both paths must be explicit absolute paths." >&2
    exit 64
fi
if [[ -d "$target_maven_repository" \
    && -n "$(find "$target_maven_repository" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "Verification target Maven repository must be empty." >&2
    exit 2
fi
if [[ ! -f "$installer" ]]; then
    echo "Release installer is missing: $installer" >&2
    exit 2
fi
if [[ ! -x "$repository_root/gradlew" ]]; then
    echo "Gradle Wrapper is not executable: $repository_root/gradlew" >&2
    exit 2
fi

install_output="$(python3 "$installer" \
    --release-assets-dir "$release_assets_directory" \
    --repository "$target_maven_repository")"
printf '%s\n' "$install_output"

coordinate="$(printf '%s\n' "$install_output" \
    | sed -n 's/^Installed coordinate: //p')"
if [[ "$(printf '%s\n' "$coordinate" | wc -l | tr -d ' ')" != 1 ]]; then
    echo "Installer did not report exactly one Maven coordinate." >&2
    exit 2
fi
IFS=':' read -r routecontract_group routecontract_artifact routecontract_version extra \
    <<< "$coordinate"
if [[ "$routecontract_group" != 'io.github.ym0506.routecontract' \
    || "$routecontract_artifact" != 'routecontract-shardingsphere-5.5' \
    || -n "${extra:-}" \
    || ! "$routecontract_version" =~ ^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})(-rc[1-9][0-9]{0,5})?$ ]]; then
    echo "Installer reported an unsafe or unexpected Maven coordinate." >&2
    exit 2
fi

if grep -Fq "project(" "$consumer_directory/build.gradle"; then
    echo "Standalone consumer must not declare a Gradle project dependency." >&2
    exit 2
fi

temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/routecontract-release-consumer.XXXXXX")"
cleanup() {
    case "$temporary_root" in
        */routecontract-release-consumer.*)
            rm -rf -- "$temporary_root"
            ;;
        *)
            echo "Refusing to remove unexpected temporary path: $temporary_root" >&2
            ;;
    esac
}
trap cleanup EXIT

GRADLE_USER_HOME="$temporary_root/gradle-user-home" \
ROUTECONTRACT_REPOSITORY="$target_maven_repository" \
ROUTECONTRACT_GROUP="$routecontract_group" \
ROUTECONTRACT_VERSION="$routecontract_version" \
    "$repository_root/gradlew" \
    --no-daemon \
    --no-build-cache \
    --stacktrace \
    --refresh-dependencies \
    "-Dmaven.repo.local=$temporary_root/unused-maven-local" \
    -p "$consumer_directory" \
    clean test

printf 'ROUTECONTRACT_RELEASE_ASSET_CONSUMER coordinate=%s result=VERIFIED_MYSQL\n' \
    "$coordinate"
printf '%s\n' \
    'The consumer used the explicit file Maven repository for RouteContract; this is same-checkout release packaging evidence, not external adoption.'
