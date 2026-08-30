#!/usr/bin/env bash
set +x
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$script_directory/.." && pwd)"
fixture_source="$repository_root/examples/gradle-kotlin-pilot"
installer="$script_directory/install-release-assets.py"
provenance_validator="$script_directory/validate-gradle-kotlin-pilot-provenance.py"
expected_jar_sha256="d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
expected_pom_sha256="05570bfa238ef77db255a46efdd5bbb25e994ae0137db86491a46a25e28deac9"

usage() {
    cat <<'EOF'
Usage: ./scripts/verify-gradle-kotlin-pilot.sh --release-assets-dir /absolute/path \
  [--provenance-output /absolute/absent/file.json]

The directory must contain the exact immutable v0.1.0 GitHub Release asset
inventory. The verifier installs it into an absent temporary Maven repository,
runs the profile-off fixture, verifies the Kotlin DSL graph, verifies the
missing-baseline failure, and proves a separate synthetic candidate match.

Requires Java 17, Python 3.10+, Docker, and network access for uncached Gradle
dependencies and the digest-pinned MySQL image. The synthetic copy is test
scaffolding, not human approval or external adoption.
EOF
}

die() {
    printf 'ROUTECONTRACT_GRADLE_KOTLIN_VERIFY_ERROR %s\n' "$1" >&2
    exit 2
}

sha256_file() {
    python3 -I -c \
        'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
        "$1"
}

lstat_identity() {
    python3 -I - "$1" <<'PY'
import hashlib
import pathlib
import stat
import sys

path = pathlib.Path(sys.argv[1])
try:
    metadata = path.lstat()
except FileNotFoundError:
    print("ABSENT")
    raise SystemExit(0)
if not stat.S_ISREG(metadata.st_mode):
    raise SystemExit(f"expected a regular non-symlink file: {path}")
if metadata.st_nlink != 1:
    raise SystemExit(f"expected a singly linked regular file: {path}")
digest = hashlib.sha256(path.read_bytes()).hexdigest()
print("|".join(str(value) for value in (
    "REGULAR",
    metadata.st_dev,
    metadata.st_ino,
    metadata.st_mode,
    metadata.st_nlink,
    metadata.st_uid,
    metadata.st_gid,
    metadata.st_size,
    metadata.st_mtime_ns,
    metadata.st_ctime_ns,
    digest,
)))
PY
}

exclusive_regular_copy() {
    python3 -I - "$1" "$2" "$3" <<'PY'
import os
import pathlib
import stat
import sys

source, destination, allowed_root = map(pathlib.Path, sys.argv[1:])
root = allowed_root.resolve(strict=True)
if root.is_symlink() or not root.is_dir():
    raise SystemExit(f"allowed root must be a real directory: {root}")
destination = destination.absolute()
try:
    relative_parent = destination.parent.relative_to(root)
except ValueError as error:
    raise SystemExit(f"destination escapes allowed root: {destination}") from error
cursor = root
for component in relative_parent.parts:
    cursor = cursor / component
    try:
        os.mkdir(cursor, 0o700)
    except FileExistsError:
        pass
    metadata = os.lstat(cursor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise SystemExit(f"destination ancestor must be a real directory: {cursor}")
try:
    os.lstat(destination)
except FileNotFoundError:
    pass
else:
    raise SystemExit(f"destination must be absent immediately before copy: {destination}")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
descriptor = os.open(destination, flags, 0o600)
try:
    with os.fdopen(descriptor, "wb", closefd=True) as stream:
        stream.write(source.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
except BaseException:
    try:
        destination.unlink()
    except FileNotFoundError:
        pass
    raise
metadata = os.lstat(destination)
if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
    raise SystemExit(f"exclusive copy did not create one regular file: {destination}")
PY
}

assert_one_fixed_line() {
    expected="$1"
    log="$2"
    count="$(python3 -I - "$expected" "$log" <<'PY'
import pathlib
import sys

expected, log_text = sys.argv[1:]
lines = pathlib.Path(log_text).read_text(
    encoding="utf-8", errors="strict"
).splitlines()
print(sum(line.strip() == expected for line in lines))
PY
)"
    test "$count" = 1 || die "expected exactly one marker in $log: $expected"
}

assert_no_fixed_line() {
    expected="$1"
    log="$2"
    count="$(python3 -I - "$expected" "$log" <<'PY'
import pathlib
import sys

expected, log_text = sys.argv[1:]
lines = pathlib.Path(log_text).read_text(
    encoding="utf-8", errors="strict"
).splitlines()
print(sum(line.strip() == expected for line in lines))
PY
)"
    test "$count" = 0 || die "unexpected success marker in $log: $expected"
}

parse_junit_report() {
    expected_outcome="$1"
    report="$2"
    expected_candidate="$3"
    expected_approved="$4"
    python3 -I - "$expected_outcome" "$report" \
        "$expected_candidate" "$expected_approved" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

outcome, report_text, candidate, approved = sys.argv[1:]
report = pathlib.Path(report_text)
if not report.is_file() or report.is_symlink():
    raise SystemExit(f"expected one regular non-symlink JUnit report: {report}")
root = ET.parse(report).getroot()
counts = tuple(int(root.attrib.get(key, "-1")) for key in (
    "tests", "failures", "errors", "skipped"
))
cases = root.findall("testcase")
expected_class = (
    "io.github.ym0506.routecontract.examples.gradle.kotlin."
    "GradleKotlinRouteContractPilotTest"
)
if len(cases) != 1 or cases[0].attrib.get("classname") != expected_class \
        or cases[0].attrib.get("name") != "keepsTheApprovedExecutionStructure()":
    raise SystemExit("the exact selected Gradle Kotlin pilot testcase did not run once")
if outcome == "missing":
    if counts != (1, 1, 0, 0):
        raise SystemExit(f"unexpected missing-baseline JUnit counts: {root.attrib}")
    failures = cases[0].findall("failure")
    expected_message = (
        "org.opentest4j.AssertionFailedError: No approved baseline. Review "
        f"{candidate} and copy it to {approved} only after human approval."
    )
    if len(failures) != 1 or failures[0].attrib.get("message") != expected_message:
        raise SystemExit("missing-baseline run did not have the exact sole failure")
elif outcome == "matched":
    if counts != (1, 0, 0, 0):
        raise SystemExit(f"unexpected matched JUnit counts: {root.attrib}")
    if any(cases[0].findall(name) for name in ("failure", "error", "skipped")):
        raise SystemExit("matched Gradle Kotlin pilot testcase did not pass")
else:
    raise SystemExit(f"unknown expected outcome: {outcome}")
PY
}

if [[ ("$#" -ne 2 && "$#" -ne 4) || "$1" != "--release-assets-dir" ]]; then
    usage >&2
    exit 64
fi
release_assets_directory="$2"
provenance_output=""
if [[ "$#" -eq 4 ]]; then
    [[ "$3" == "--provenance-output" ]] || {
        usage >&2
        exit 64
    }
    provenance_output="$4"
    [[ "$provenance_output" == /* ]] \
        || die "provenance output path must be absolute"
    test ! -e "$provenance_output" && test ! -L "$provenance_output" \
        || die "provenance output path must start absent"
    test -d "$(dirname -- "$provenance_output")" \
        || die "provenance output parent directory must exist"
    test ! -L "$(dirname -- "$provenance_output")" \
        || die "provenance output parent directory must not be a symbolic link"
fi
[[ "$release_assets_directory" == /* ]] \
    || die "Release assets directory must be absolute"
test -d "$release_assets_directory" \
    || die "Release assets directory does not exist"
test ! -L "$release_assets_directory" \
    || die "Release assets directory must not be a symbolic link"

for command in docker java ln python3 tar; do
    command -v "$command" >/dev/null 2>&1 \
        || die "required command is missing: $command"
done
for path in "$repository_root/gradlew" "$installer" "$provenance_validator" \
    "$fixture_source/build.gradle.kts"; do
    test -f "$path" || die "required regular file is missing: $path"
    test ! -L "$path" || die "required file must not be a symbolic link: $path"
done
test ! -e "$fixture_source/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json" \
    || die "source fixture must not contain an approved or synthetic baseline"
test ! -L "$fixture_source/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json" \
    || die "source fixture baseline path must not be a symbolic link"

python3 -I - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required")
PY
java_version="$(java -version 2>&1)"
printf '%s\n' "$java_version" | grep -Eq '^(openjdk|java) version "17\.' \
    || die "the Gradle Kotlin pilot must run on Java 17"
docker info >/dev/null

temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/routecontract-gradle-kotlin-pilot.XXXXXX")"
temporary_root="$(cd -- "$temporary_root" && pwd -P)"
cleanup() {
    case "$temporary_root" in
        */routecontract-gradle-kotlin-pilot.*)
            rm -rf -- "$temporary_root"
            ;;
        *)
            printf 'Refusing to remove unexpected temporary path: %s\n' \
                "$temporary_root" >&2
            ;;
    esac
}
trap cleanup EXIT

bootstrap_gradle_home="$temporary_root/bootstrap-gradle-home"
test ! -e "$bootstrap_gradle_home" && test ! -L "$bootstrap_gradle_home" \
    || die "Gradle wrapper bootstrap cache must start absent"
env \
    -u GRADLE_RO_DEP_CACHE \
    -u GRADLE_OPTS \
    -u JAVA_TOOL_OPTIONS \
    -u _JAVA_OPTIONS \
    GRADLE_USER_HOME="$bootstrap_gradle_home" \
    "$repository_root/gradlew" --no-daemon --version \
    >"$temporary_root/gradle-bootstrap.log" 2>&1
gradle_command="$(python3 -I - "$bootstrap_gradle_home" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
matches = sorted(
    path for path in root.glob(
        "wrapper/dists/gradle-8.14.4-bin/*/gradle-8.14.4/bin/gradle"
    )
    if path.is_file() and not path.is_symlink()
)
if len(matches) != 1:
    raise SystemExit(f"expected one bootstrapped Gradle 8.14.4 executable, got {matches}")
print(matches[0].resolve(strict=True))
PY
)"
test -x "$gradle_command" && test ! -L "$gradle_command" \
    || die "bootstrapped Gradle 8.14.4 executable is not a real executable file"

fixture="$temporary_root/fixture"
repository="$temporary_root/maven-repository"
marker_fixture="$temporary_root/marker-copy"
cache_record="$temporary_root/case-caches.txt"
: >"$cache_record"

prepare_case_caches() {
    local case_name="$1"
    local case_root="$temporary_root/case-cache-$case_name"
    case "$case_name" in
        missing-repository-property|relative-repository|nonexistent-repository|symlink-repository|wrong-gav|missing-gav|tampered-pom|tampered-gav|marker-copy|profile-off|gav-origin|graph|missing-baseline|matched) ;;
        *) die "unexpected Gradle verification case name: $case_name" ;;
    esac
    test ! -e "$case_root" && test ! -L "$case_root" \
        || die "Gradle verification case cache root must start absent: $case_name"
    mkdir "$case_root"
    case_gradle_home="$case_root/gradle-user-home"
    case_project_cache="$case_root/project-cache"
    test ! -e "$case_gradle_home" && test ! -L "$case_gradle_home" \
        || die "Gradle user cache must start absent: $case_name"
    test ! -e "$case_project_cache" && test ! -L "$case_project_cache" \
        || die "Gradle project cache must start absent: $case_name"
    if grep -Fqx "$case_gradle_home|$case_project_cache" "$cache_record"; then
        die "Gradle verification case cache pair was reused: $case_name"
    fi
    printf '%s|%s\n' "$case_gradle_home" "$case_project_cache" >>"$cache_record"
}

run_gradle_case() {
    env \
        -u ROUTECONTRACT_REPOSITORY \
        -u ORG_GRADLE_PROJECT_routecontractRepository \
        -u ORG_GRADLE_PROJECT_routecontractPilot \
        -u GRADLE_RO_DEP_CACHE \
        -u GRADLE_OPTS \
        -u JAVA_TOOL_OPTIONS \
        -u _JAVA_OPTIONS \
        GRADLE_USER_HOME="$case_gradle_home" \
        "$gradle_command" \
        --no-daemon \
        --no-build-cache \
        --no-configuration-cache \
        --no-watch-fs \
        --project-cache-dir "$case_project_cache" \
        "$@"
}

mkdir "$fixture"
tar -C "$fixture_source" --exclude .gradle --exclude build -cf - . \
    | tar -C "$fixture" -xf -
test ! -e "$fixture/.gradle" && test ! -L "$fixture/.gradle" \
    || die "copied fixture must start without a project .gradle directory"
test ! -e "$fixture/build" && test ! -L "$fixture/build" \
    || die "copied fixture must start without a project build directory"
test ! -e "$repository"
python3 -I "$installer" \
    --release-assets-dir "$release_assets_directory" \
    --repository "$repository" >"$temporary_root/install.log"
cached_jar="$repository/io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.0/routecontract-shardingsphere-5.5-0.1.0.jar"
cached_pom="$repository/io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.0/routecontract-shardingsphere-5.5-0.1.0.pom"
gav_marker="ROUTECONTRACT_GRADLE_GAV coordinate=io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0 jarSha256=$expected_jar_sha256 pomSha256=$expected_pom_sha256 resolved=VERIFIED"
provenance_marker="ROUTECONTRACT_GRADLE_PROVENANCE coordinate=io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0 jarSha256=$expected_jar_sha256 pomSha256=$expected_pom_sha256 origins=EXACT claim=SELECTED_INVARIANTS_ONLY"
runtime_origin_marker="ROUTECONTRACT_GRADLE_RUNTIME_ORIGIN coordinate=io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0 jarSha256=$expected_jar_sha256 pomSha256=$expected_pom_sha256 apiOrigin=EXACT providerOrigin=EXACT serviceDescriptorCount=1"
test "$(sha256_file "$cached_jar")" = "$expected_jar_sha256" \
    || die "installed RouteContract JAR hash changed"
test "$(sha256_file "$cached_pom")" = "$expected_pom_sha256" \
    || die "installed RouteContract POM hash changed"

wrong_gav_repository="$temporary_root/wrong-gav-repository"
missing_gav_repository="$temporary_root/missing-gav-repository"
tampered_pom_repository="$temporary_root/tampered-pom-repository"
tampered_gav_repository="$temporary_root/tampered-gav-repository"
python3 -I - "$repository" "$wrong_gav_repository" \
    "$missing_gav_repository" "$tampered_pom_repository" \
    "$tampered_gav_repository" <<'PY'
import pathlib
import shutil
import sys

source, wrong, missing, tampered_pom, tampered_jar = map(
    pathlib.Path, sys.argv[1:]
)
coordinate = pathlib.Path(
    "io/github/ym0506/routecontract/routecontract-shardingsphere-5.5"
)
source_version = source / coordinate / "0.1.0"

wrong_version = wrong / coordinate / "0.1.1"
wrong_version.mkdir(parents=True)
shutil.copyfile(
    source_version / "routecontract-shardingsphere-5.5-0.1.0.jar",
    wrong_version / "routecontract-shardingsphere-5.5-0.1.1.jar",
)
shutil.copyfile(
    source_version / "routecontract-shardingsphere-5.5-0.1.0.pom",
    wrong_version / "routecontract-shardingsphere-5.5-0.1.1.pom",
)

missing_version = missing / coordinate / "0.1.0"
missing_version.mkdir(parents=True)
shutil.copyfile(
    source_version / "routecontract-shardingsphere-5.5-0.1.0.jar",
    missing_version / "routecontract-shardingsphere-5.5-0.1.0.jar",
)

shutil.copytree(source, tampered_pom)
tampered_pom_file = (
    tampered_pom
    / coordinate
    / "0.1.0"
    / "routecontract-shardingsphere-5.5-0.1.0.pom"
)
with tampered_pom_file.open("ab") as stream:
    stream.write(b"<!-- ROUTECONTRACT_TAMPERED_POM -->\n")

shutil.copytree(source, tampered_jar)
tampered_jar = (
    tampered_jar
    / coordinate
    / "0.1.0"
    / "routecontract-shardingsphere-5.5-0.1.0.jar"
)
with tampered_jar.open("ab") as stream:
    stream.write(b"ROUTECONTRACT_TAMPERED_GAV\n")
PY

missing_repository_property_log="$temporary_root/missing-repository-property.log"
prepare_case_caches missing-repository-property
set +e
run_gradle_case \
    -p "$fixture" -ProutecontractPilot=true help \
    >"$missing_repository_property_log" 2>&1
missing_repository_property_status="$?"
set -e
test "$missing_repository_property_status" = 1 \
    || die "enabled pilot without a RouteContract repository must exit exactly 1"
grep -Fq \
    'Set -ProutecontractRepository or ROUTECONTRACT_REPOSITORY for the pilot' \
    "$missing_repository_property_log" \
    || die "enabled pilot without a repository did not fail at the required input boundary"

relative_repository_log="$temporary_root/relative-repository.log"
prepare_case_caches relative-repository
set +e
run_gradle_case \
    -p "$fixture" -ProutecontractPilot=true \
    -ProutecontractRepository=relative-repository help \
    >"$relative_repository_log" 2>&1
relative_repository_status="$?"
set -e
test "$relative_repository_status" = 1 \
    || die "relative RouteContract repository must exit exactly 1"
grep -Fq \
    'RouteContract repository must be an absolute local filesystem directory' \
    "$relative_repository_log" \
    || die "relative RouteContract repository did not fail at the path boundary"

nonexistent_repository="$temporary_root/nonexistent-repository"
test ! -e "$nonexistent_repository" && test ! -L "$nonexistent_repository" \
    || die "nonexistent RouteContract repository test path must start absent"
nonexistent_repository_log="$temporary_root/nonexistent-repository.log"
prepare_case_caches nonexistent-repository
set +e
run_gradle_case \
    -p "$fixture" -ProutecontractPilot=true \
    "-ProutecontractRepository=$nonexistent_repository" help \
    >"$nonexistent_repository_log" 2>&1
nonexistent_repository_status="$?"
set -e
test "$nonexistent_repository_status" = 1 \
    || die "nonexistent RouteContract repository must exit exactly 1"
grep -Fq 'RouteContract repository must be a real local directory' \
    "$nonexistent_repository_log" \
    || die "nonexistent RouteContract repository did not fail at the path boundary"

repository_link="$temporary_root/repository-link"
ln -s "$repository" "$repository_link"
symlink_repository_log="$temporary_root/symlink-repository.log"
prepare_case_caches symlink-repository
set +e
run_gradle_case \
    -p "$fixture" -ProutecontractPilot=true \
    "-ProutecontractRepository=$repository_link" help \
    >"$symlink_repository_log" 2>&1
symlink_repository_status="$?"
set -e
test "$symlink_repository_status" = 1 \
    || die "symlink-backed RouteContract repository must exit exactly 1"
grep -Fq 'RouteContract repository must be a real local directory' \
    "$symlink_repository_log" \
    || die "symlink-backed RouteContract repository did not fail at the path boundary"

wrong_gav_log="$temporary_root/wrong-gav.log"
prepare_case_caches wrong-gav
set +e
run_gradle_case \
    --offline \
    -p "$fixture" -ProutecontractPilot=true \
    "-ProutecontractRepository=$wrong_gav_repository" \
    routeContractPilotArtifactProvenance \
    >"$wrong_gav_log" 2>&1
wrong_gav_status="$?"
set -e
test "$wrong_gav_status" = 1 \
    || die "wrong RouteContract GAV must exit exactly 1"
grep -Fq \
    'io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0' \
    "$wrong_gav_log" \
    || die "wrong RouteContract GAV did not fail while resolving the exact coordinate"
assert_no_fixed_line "$gav_marker" "$wrong_gav_log"

missing_gav_log="$temporary_root/missing-gav.log"
prepare_case_caches missing-gav
set +e
run_gradle_case \
    --offline \
    -p "$fixture" -ProutecontractPilot=true \
    "-ProutecontractRepository=$missing_gav_repository" \
    routeContractPilotArtifactProvenance >"$missing_gav_log" 2>&1
missing_gav_status="$?"
set -e
test "$missing_gav_status" = 1 \
    || die "missing RouteContract GAV metadata must exit exactly 1"
grep -Fq \
    'io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0' \
    "$missing_gav_log" \
    || die "missing RouteContract GAV metadata did not fail during exact resolution"
assert_no_fixed_line "$gav_marker" "$missing_gav_log"

tampered_pom_log="$temporary_root/tampered-pom.log"
prepare_case_caches tampered-pom
set +e
run_gradle_case \
    --offline \
    -p "$fixture" -ProutecontractPilot=true \
    "-ProutecontractRepository=$tampered_pom_repository" \
    routeContractPilotArtifactProvenance >"$tampered_pom_log" 2>&1
tampered_pom_status="$?"
set -e
test "$tampered_pom_status" = 1 \
    || die "tampered RouteContract GAV POM must exit exactly 1"
grep -Fq 'RouteContract repository POM SHA-256 mismatch:' \
    "$tampered_pom_log" \
    || die "tampered RouteContract GAV POM did not fail at the SHA-256 boundary"
assert_no_fixed_line "$gav_marker" "$tampered_pom_log"

tampered_gav_log="$temporary_root/tampered-gav.log"
prepare_case_caches tampered-gav
set +e
run_gradle_case \
    --offline \
    -p "$fixture" -ProutecontractPilot=true \
    "-ProutecontractRepository=$tampered_gav_repository" \
    routeContractPilotArtifactProvenance >"$tampered_gav_log" 2>&1
tampered_gav_status="$?"
set -e
test "$tampered_gav_status" = 1 \
    || die "tampered RouteContract GAV must exit exactly 1"
grep -Fq 'RouteContract runtime JAR SHA-256 mismatch:' \
    "$tampered_gav_log" \
    || die "tampered RouteContract GAV did not fail at the SHA-256 boundary"
assert_no_fixed_line "$gav_marker" "$tampered_gav_log"

mkdir "$marker_fixture"
python3 -I - "$fixture_source/build.gradle.kts" \
    "$marker_fixture/build.gradle.kts" "$marker_fixture/settings.gradle.kts" <<'PY'
import pathlib
import sys

source_path, build_path, settings_path = map(pathlib.Path, sys.argv[1:])
source = source_path.read_text(encoding="utf-8")
start_marker = "// ROUTECONTRACT_KOTLIN_DSL_START"
end_marker = "// ROUTECONTRACT_KOTLIN_DSL_END"
if source.count(start_marker) != 1 or source.count(end_marker) != 1:
    raise SystemExit("expected exactly one Kotlin DSL marker pair")
start = source.index(start_marker)
end = source.index(end_marker, start) + len(end_marker)
block = source[start:end]
prelude = """import java.nio.file.Files as JFiles
import java.nio.file.LinkOption as JLinkOption
import java.nio.file.Path as JPath
import java.security.MessageDigest as JMessageDigest
import java.util.HexFormat as JHexFormat

plugins { java }

repositories { mavenCentral() }

"""
build_path.write_text(prelude + block + "\n", encoding="utf-8", newline="\n")
settings_path.write_text(
    'rootProject.name = "routecontract-marker-copy"\n',
    encoding="utf-8",
    newline="\n",
)
PY
test ! -e "$marker_fixture/.gradle" && test ! -L "$marker_fixture/.gradle" \
    || die "marker-only fixture must start without a project .gradle directory"
marker_compile_log="$temporary_root/marker-compile.log"
prepare_case_caches marker-copy
run_gradle_case \
    -p "$marker_fixture" help \
    >"$marker_compile_log" 2>&1

profile_off_log="$temporary_root/profile-off.log"
prepare_case_caches profile-off
run_gradle_case \
    -p "$fixture" clean test \
    >"$profile_off_log" 2>&1
assert_one_fixed_line \
    'ROUTECONTRACT_GRADLE_KOTLIN_PROFILE_OFF businessResult=PASS routecontractDependency=ABSENT mysql=8.4.11 shardingsphere=5.5.3' \
    "$profile_off_log"
candidate="$fixture/build/routecontract/orders.find-by-user-id.candidate.json"
approved="$fixture/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"
test ! -e "$candidate" || die "profile-off run created a pilot candidate"

gav_origin_log="$temporary_root/gav-origin.log"
prepare_case_caches gav-origin
run_gradle_case \
    --offline \
    -p "$fixture" \
    -ProutecontractPilot=true "-ProutecontractRepository=$repository" \
    routeContractPilotArtifactProvenance >"$gav_origin_log" 2>&1
assert_one_fixed_line "$gav_marker" "$gav_origin_log"

graph_log="$temporary_root/graph.log"
prepare_case_caches graph
run_gradle_case \
    -p "$fixture" \
    -ProutecontractPilot=true "-ProutecontractRepository=$repository" \
    routeContractPilotGraph >"$graph_log" 2>&1
assert_one_fixed_line 'ROUTECONTRACT_GRADLE_GRAPH VERIFIED' "$graph_log"

missing_log="$temporary_root/missing-baseline.log"
prepare_case_caches missing-baseline
set +e
run_gradle_case \
    -p "$fixture" \
    -ProutecontractPilot=true "-ProutecontractRepository=$repository" \
    routeContractPilot >"$missing_log" 2>&1
missing_status="$?"
set -e
test "$missing_status" = 1 \
    || die "missing-baseline pilot must exit exactly 1, got $missing_status"
assert_one_fixed_line \
    "ROUTECONTRACT_GRADLE_KOTLIN_PILOT businessResult=PASS capture=COMPLETE observedPhysicalAttempts=1 observedDataSourceNames=[ds_0] candidate=$candidate" \
    "$missing_log"
assert_one_fixed_line "$runtime_origin_marker" "$missing_log"
test -f "$candidate" && test ! -L "$candidate" \
    || die "missing-baseline run did not create a regular candidate"
candidate_sha256="$(sha256_file "$candidate")"
report="$fixture/build/test-results/routeContractPilot/TEST-io.github.ym0506.routecontract.examples.gradle.kotlin.GradleKotlinRouteContractPilotTest.xml"
parse_junit_report missing "$report" "$candidate" "$approved"
provenance="$fixture/build/routecontract/gradle-kotlin-pilot-provenance.json"
test -f "$provenance" && test ! -L "$provenance" \
    || die "missing-baseline run did not create a regular provenance artifact"
python3 -I "$provenance_validator" "$provenance" \
    >"$temporary_root/missing-provenance-validation.log"
assert_one_fixed_line "$provenance_marker" \
    "$temporary_root/missing-provenance-validation.log"

approved_absent_identity="$(lstat_identity "$approved")"
test "$approved_absent_identity" = "ABSENT" \
    || die "approved baseline must be absent immediately before synthetic copy"
exclusive_regular_copy "$candidate" "$approved" "$fixture"
test "$(sha256_file "$approved")" = "$candidate_sha256" \
    || die "synthetic baseline copy changed candidate bytes"
approved_identity_before_match="$(lstat_identity "$approved")"
case "$approved_identity_before_match" in
    REGULAR\|*) ;;
    *) die "synthetic baseline must have one regular-file lstat identity" ;;
esac

matched_log="$temporary_root/matched.log"
prepare_case_caches matched
run_gradle_case \
    -p "$fixture" \
    -ProutecontractPilot=true "-ProutecontractRepository=$repository" \
    routeContractPilot >"$matched_log" 2>&1
assert_one_fixed_line 'ROUTECONTRACT_GRADLE_KOTLIN_PILOT candidateCheck=MATCHED' \
    "$matched_log"
assert_one_fixed_line "$runtime_origin_marker" "$matched_log"
test "$(sha256_file "$candidate")" = "$candidate_sha256" \
    || die "matched run changed deterministic candidate bytes"
test "$(sha256_file "$approved")" = "$candidate_sha256" \
    || die "matched run changed the synthetic baseline"
approved_identity_after_match="$(lstat_identity "$approved")"
test "$approved_identity_after_match" = "$approved_identity_before_match" \
    || die "matched run changed the synthetic baseline lstat identity"
parse_junit_report matched "$report" "$candidate" "$approved"
test -f "$provenance" && test ! -L "$provenance" \
    || die "matched run did not create a regular provenance artifact"
python3 -I "$provenance_validator" "$provenance" \
    >"$temporary_root/matched-provenance-validation.log"
assert_one_fixed_line "$provenance_marker" \
    "$temporary_root/matched-provenance-validation.log"
provenance_sha256="$(sha256_file "$provenance")"
if [[ -n "$provenance_output" ]]; then
    exclusive_regular_copy \
        "$provenance" "$provenance_output" "$(dirname -- "$provenance_output")"
    test "$(sha256_file "$provenance_output")" = "$provenance_sha256" \
        || die "preserved provenance output changed during exclusive copy"
fi

test ! -e "$fixture_source/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json" \
    || die "verifier mutated the source fixture baseline"
test ! -e "$fixture/.gradle" && test ! -L "$fixture/.gradle" \
    || die "verifier created a project-local .gradle cache"
test "$(wc -l <"$cache_record" | tr -d ' ')" = 14 \
    || die "verifier did not use exactly fourteen independent Gradle cache pairs"
test "$(sort -u "$cache_record" | wc -l | tr -d ' ')" = 14 \
    || die "verifier reused a Gradle user/project cache pair"
printf 'ROUTECONTRACT_GRADLE_KOTLIN_VERIFY markerCopy=PASS repositoryBoundary=PASS profileOff=PASS graph=VERIFIED '\
'gavResolution=PASS gavNoRemoteFallback=OFFLINE_FRESH_CACHE gavNegativeCases=PASS cacheIsolation=PASS artifactOrigin=EXACT_COORDINATE_JAR '\
'provenance=VALIDATED missingBaseline=EXPECTED matched=PASS mysql=8.4.11 shardingsphere=5.5.3 jarSha256=%s pomSha256=%s candidateSha256=%s provenanceSha256=%s\n' \
    "$expected_jar_sha256" "$expected_pom_sha256" "$candidate_sha256" \
    "$provenance_sha256"
