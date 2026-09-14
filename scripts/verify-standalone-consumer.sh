#!/usr/bin/env bash
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$script_directory/.." && pwd)"
consumer_directory="$repository_root/examples/standalone-consumer"
temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/routecontract-standalone.XXXXXX")"
temporary_maven_repository="$temporary_root/maven-repository"

cleanup() {
    case "$temporary_root" in
        */routecontract-standalone.*)
            rm -rf -- "$temporary_root"
            ;;
        *)
            echo "Refusing to remove unexpected temporary path: $temporary_root" >&2
            ;;
    esac
}
trap cleanup EXIT

mkdir -p "$temporary_maven_repository"

routecontract_group="$(sed -nE "s/^group = '([^']+)'$/\1/p" "$repository_root/build.gradle")"
routecontract_version="$(sed -nE "s/^version = '([^']+)'$/\1/p" "$repository_root/build.gradle")"
if [[ "$routecontract_group" != 'io.github.ym0506.routecontract' \
    || ! "$routecontract_version" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "Could not read the canonical RouteContract group and a safe version from build.gradle" >&2
    exit 1
fi
routecontract_group_path="${routecontract_group//./\/}"

"$repository_root/gradlew" \
    --no-daemon \
    --no-build-cache \
    --stacktrace \
    "-Dmaven.repo.local=$temporary_maven_repository" \
    :routecontract-core:publishToMavenLocal \
    :routecontract-shardingsphere-5.5:publishToMavenLocal

published_core_artifact="$temporary_maven_repository/$routecontract_group_path/routecontract-core/$routecontract_version/routecontract-core-$routecontract_version.jar"
published_core_pom="$temporary_maven_repository/$routecontract_group_path/routecontract-core/$routecontract_version/routecontract-core-$routecontract_version.pom"
published_artifact="$temporary_maven_repository/$routecontract_group_path/routecontract-shardingsphere-5.5/$routecontract_version/routecontract-shardingsphere-5.5-$routecontract_version.jar"
published_pom="$temporary_maven_repository/$routecontract_group_path/routecontract-shardingsphere-5.5/$routecontract_version/routecontract-shardingsphere-5.5-$routecontract_version.pom"

if [[ ! -f "$published_core_artifact" || ! -f "$published_core_pom" \
    || ! -f "$published_artifact" || ! -f "$published_pom" ]]; then
    echo "Published RouteContract core and adapter coordinates are incomplete in $temporary_maven_repository" >&2
    exit 1
fi

if grep -Fq "project(" "$consumer_directory/build.gradle"; then
    echo "Standalone consumer must not declare a Gradle project dependency" >&2
    exit 1
fi

ROUTECONTRACT_REPOSITORY="$temporary_maven_repository" \
ROUTECONTRACT_GROUP="$routecontract_group" \
ROUTECONTRACT_VERSION="$routecontract_version" \
    "$repository_root/gradlew" \
    --no-daemon \
    --no-build-cache \
    --stacktrace \
    --refresh-dependencies \
    -p "$consumer_directory" \
    clean test

echo "Standalone consumer verified published coordinate, SPI discovery, and real MySQL capture."
