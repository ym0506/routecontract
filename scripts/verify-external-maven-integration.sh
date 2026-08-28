#!/usr/bin/env bash
set +x
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
routecontract_root="$(cd -- "${script_directory}/.." && pwd)"
installer="${script_directory}/install-release-assets.py"
checksum_preparer="${script_directory}/prepare_maven_v0_1_0_checksums.py"

expected_installer_sha256="d21a7c71eb725e8d5f0675cfb88815b26be130d63711dc025a06347317652d33"
expected_checksum_preparer_sha256="546f801ae6056ae82dc6cbf8c3852056e7ec7ca9acfc7c077d06fc8d20247b89"
expected_index_sha256="820ed33eb8bfe8d47f3ec8782d2aa99f2879227c4ee066ecafc467e61abb8684"
expected_jar_sha256="d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
expected_pom_sha256="05570bfa238ef77db255a46efdd5bbb25e994ae0137db86491a46a25e28deac9"
release_base="https://github.com/ym0506/routecontract/releases/download/v0.1.0"
repository_id="routecontract-verified-file-repository"
group_path="io/github/ym0506/routecontract"
artifact_id="routecontract-shardingsphere-5.5"
version="0.1.0"
checksum_algorithm_property="-Daether.checksums.algorithms.${repository_id}=SHA-256"

assets=(
    SHA256SUMS
    routecontract-0.1.0-source.zip
    routecontract-shardingsphere-5.5-0.1.0.jar
    routecontract-shardingsphere-5.5-0.1.0-sources.jar
    routecontract-shardingsphere-5.5-0.1.0-javadoc.jar
    routecontract-shardingsphere-5.5.pom
    routecontract-shardingsphere-5.5-cyclonedx.json
    routecontract-shardingsphere-5.5-cyclonedx.xml
    routecontract-aggregate-cyclonedx.json
    routecontract-aggregate-cyclonedx.xml
    supply-chain-evidence.json
    test-summary.txt
)

die() {
    printf 'ROUTECONTRACT_EXTERNAL_MAVEN_ERROR %s\n' "$1" >&2
    exit 2
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command is missing: $1"
}

require_env() {
    variable_name="$1"
    if [[ -z "${!variable_name:-}" ]]; then
        die "required environment variable is missing: ${variable_name}"
    fi
}

sha256_file() {
    python3 -I -c \
        'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
        "$1"
}

assert_regular_file() {
    path="$1"
    label="$2"
    test -f "$path" || die "${label} is not a regular file: ${path}"
    test ! -L "$path" || die "${label} must not be a symbolic link: ${path}"
}

assert_absent_path() {
    path="$1"
    label="$2"
    test ! -e "$path" || die "${label} must start absent"
    test ! -L "$path" || die "${label} must not be a symbolic link"
}

validate_confined_path() {
    candidate_path="$1"
    confinement_root="$2"
    label="$3"
    required_state="$4"
    python3 -I - "$candidate_path" "$confinement_root" "$label" "$required_state" <<'PY'
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[2])
label = sys.argv[3]
required_state = sys.argv[4]
normalized = pathlib.Path(os.path.normpath(os.fspath(path)))
normalized_root = pathlib.Path(os.path.normpath(os.fspath(root)))
if not path.is_absolute() or path != normalized:
    raise SystemExit(f"{label} must be an absolute normalized path")
if not root.is_absolute() or root != normalized_root:
    raise SystemExit(f"{label} confinement root is not absolute and normalized")
if path == root or not path.is_relative_to(root):
    raise SystemExit(f"{label} must stay below its confinement root")
ancestor = path.parent
while True:
    if ancestor.is_symlink():
        raise SystemExit(f"{label} has a symbolic-link ancestor")
    if ancestor.exists() and not ancestor.is_dir():
        raise SystemExit(f"{label} has a non-directory ancestor")
    if ancestor == root:
        break
    if not ancestor.is_relative_to(root):
        raise SystemExit(f"{label} escaped its confinement root")
    ancestor = ancestor.parent
if path.is_symlink():
    raise SystemExit(f"{label} must not be a symbolic link")
if path.exists() and not path.is_file():
    raise SystemExit(f"{label} must be a regular file when it exists")
if required_state == "regular":
    if not path.is_file():
        raise SystemExit(f"{label} is not a regular file")
    if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise SystemExit(f"{label} resolved outside its confinement root")
elif required_state != "allow-missing":
    raise SystemExit("invalid path-validation state")
PY
}

file_identity() {
    python3 -I - "$1" <<'PY'
import hashlib
import os
import pathlib
import stat
import sys

path = pathlib.Path(sys.argv[1])
metadata = os.lstat(path)
if not stat.S_ISREG(metadata.st_mode):
    raise SystemExit("approved manifest is not a regular file")
digest = hashlib.sha256(path.read_bytes()).hexdigest()
print(":".join(map(str, (
    metadata.st_dev,
    metadata.st_ino,
    metadata.st_mode,
    metadata.st_size,
    metadata.st_mtime_ns,
    digest,
))))
PY
}

assert_no_integrity_warning() {
    log="$1"
    if grep -Eiq \
        'Could not validate integrity|Checksum validation failed|no checksums available' \
        "$log"; then
        die "successful Maven log contains an integrity warning: ${log}"
    fi
}

report_suppressed_log() {
    printf '%s\n' \
        'ROUTECONTRACT_EXTERNAL_MAVEN_DIAGNOSTIC Maven output was not echoed because application logs can contain sensitive data; reproduce locally only after reviewing its output handling.' \
        >&2
}

for variable in \
    ROUTECONTRACT_EXPECTED_OUTCOME \
    ROUTECONTRACT_REACTOR_POM \
    ROUTECONTRACT_OWNING_POM \
    ROUTECONTRACT_REACTOR_SELECTOR \
    ROUTECONTRACT_PROFILE_OFF_REPORT \
    ROUTECONTRACT_PROFILE_OFF_CLASS \
    ROUTECONTRACT_PROFILE_OFF_METHOD \
    ROUTECONTRACT_TEST_CLASS \
    ROUTECONTRACT_TEST_METHOD \
    ROUTECONTRACT_CANDIDATE_PATH \
    ROUTECONTRACT_APPROVED_PATH \
    ROUTECONTRACT_SUREFIRE_REPORT; do
    require_env "$variable"
done

case "$ROUTECONTRACT_EXPECTED_OUTCOME" in
    review|matched) ;;
    *) die "ROUTECONTRACT_EXPECTED_OUTCOME must be review or matched" ;;
esac

for required in curl java mvn python3; do
    require_command "$required"
done
for required_file in "$installer" "$checksum_preparer"; do
    assert_regular_file "$required_file" "RouteContract helper"
done
test "$(sha256_file "$installer")" = "$expected_installer_sha256" \
    || die "release installer does not match the immutable v0.1.0 hash"
test "$(sha256_file "$checksum_preparer")" = "$expected_checksum_preparer_sha256" \
    || die "checksum preparer does not match the reviewed hash"

python3 -I - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required")
PY

maven_version="$(mvn -version 2>&1)"
printf '%s\n' "$maven_version" | grep -Fqx \
    'Apache Maven 3.9.14 (996c630dbc656c76214ce58821dcc58be960875b)' \
    || die "Apache Maven must be exact version 3.9.14"
printf '%s\n' "$maven_version" | grep -Eq '^Java version: 17\.' \
    || die "Maven must run on Java 17"

assert_regular_file "$ROUTECONTRACT_REACTOR_POM" "reactor POM"
assert_regular_file "$ROUTECONTRACT_OWNING_POM" "owning POM"
routecontract_owning_directory="$(python3 -I - \
    "$ROUTECONTRACT_OWNING_POM" <<'PY'
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
normalized = pathlib.Path(os.path.normpath(os.fspath(path)))
if not path.is_absolute() or path != normalized:
    raise SystemExit("owning POM must use an absolute normalized path")
print(path.parent)
PY
)"
routecontract_owning_target="${routecontract_owning_directory}/target"
validate_confined_path \
    "$ROUTECONTRACT_PROFILE_OFF_REPORT" "$routecontract_owning_target" \
    "profile-off report" allow-missing
validate_confined_path \
    "$ROUTECONTRACT_CANDIDATE_PATH" "$routecontract_owning_target" \
    "candidate" allow-missing
validate_confined_path \
    "$ROUTECONTRACT_SUREFIRE_REPORT" "$routecontract_owning_target" \
    "Surefire report" allow-missing
validate_confined_path \
    "$ROUTECONTRACT_APPROVED_PATH" "$routecontract_owning_directory" \
    "approved manifest" allow-missing
case "$ROUTECONTRACT_APPROVED_PATH" in
    "$routecontract_owning_target"|"$routecontract_owning_target"/*)
        die "approved manifest must stay outside Maven target"
        ;;
esac
python3 -I - \
    "$ROUTECONTRACT_PROFILE_OFF_REPORT" \
    "$ROUTECONTRACT_CANDIDATE_PATH" \
    "$ROUTECONTRACT_SUREFIRE_REPORT" <<'PY'
import pathlib
import sys

paths = list(map(pathlib.Path, sys.argv[1:]))
if len(set(paths)) != len(paths):
    raise SystemExit("profile-off report, candidate, and selected-test report must be distinct")
PY
assert_absent_path "$ROUTECONTRACT_PROFILE_OFF_REPORT" "profile-off report"
assert_absent_path "$ROUTECONTRACT_CANDIDATE_PATH" "candidate"
assert_absent_path "$ROUTECONTRACT_SUREFIRE_REPORT" "selected-test report"
approved_identity=""
if [[ "$ROUTECONTRACT_EXPECTED_OUTCOME" == "review" ]]; then
    test ! -e "$ROUTECONTRACT_APPROVED_PATH" \
        || die "review outcome requires an absent approved manifest"
    test ! -L "$ROUTECONTRACT_APPROVED_PATH" \
        || die "approved manifest path must not be a symbolic link"
else
    validate_confined_path \
        "$ROUTECONTRACT_APPROVED_PATH" "$routecontract_owning_directory" \
        "approved manifest" regular
    approved_identity="$(file_identity "$ROUTECONTRACT_APPROVED_PATH")"
fi

temporary_parent="${TMPDIR:-/tmp}"
temporary_parent="${temporary_parent%/}"
temporary_root="$(mktemp -d "${temporary_parent}/routecontract-external-maven.XXXXXX")"
cleanup() {
    case "$temporary_root" in
        */routecontract-external-maven.*) rm -rf -- "$temporary_root" ;;
        *) printf 'Refusing to remove unexpected temporary path: %s\n' "$temporary_root" >&2 ;;
    esac
}
trap cleanup EXIT

if [[ -n "${ROUTECONTRACT_RELEASE_ASSETS_DIR:-}" ]]; then
    [[ "$ROUTECONTRACT_RELEASE_ASSETS_DIR" == /* ]] \
        || die "ROUTECONTRACT_RELEASE_ASSETS_DIR must be absolute"
    test -d "$ROUTECONTRACT_RELEASE_ASSETS_DIR" \
        || die "Release assets directory does not exist"
    test ! -L "$ROUTECONTRACT_RELEASE_ASSETS_DIR" \
        || die "Release assets directory must not be a symbolic link"
    release_assets_directory="$ROUTECONTRACT_RELEASE_ASSETS_DIR"
else
    release_assets_directory="${temporary_root}/release-assets"
    mkdir "$release_assets_directory"
    for asset in "${assets[@]}"; do
        curl --disable --proto '=https' --tlsv1.2 --fail --location \
            --silent --show-error --retry 3 --connect-timeout 15 --max-time 300 \
            --remove-on-error --max-filesize 5242880 \
            --output "${release_assets_directory}/${asset}" \
            "${release_base}/${asset}"
    done
fi

assert_regular_file "${release_assets_directory}/SHA256SUMS" "checksum index"
test "$(sha256_file "${release_assets_directory}/SHA256SUMS")" = "$expected_index_sha256" \
    || die "Release checksum index does not match the immutable v0.1.0 hash"

repository_directory="${temporary_root}/routecontract-maven"
consumer_cache="${temporary_root}/consumer-cache"
graph_log="${temporary_root}/dependency-tree.log"
profile_log="${temporary_root}/profile-off.log"
test_log="${temporary_root}/candidate-test.log"
python3 -I "$installer" \
    --release-assets-dir "$release_assets_directory" \
    --repository "$repository_directory"
python3 -I "$checksum_preparer" --repository "$repository_directory"

repository_uri="$(python3 -I -c \
    'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True).as_uri())' \
    "$repository_directory")"
coordinate_directory="${consumer_cache}/${group_path}/${artifact_id}/${version}"
cached_jar="${coordinate_directory}/${artifact_id}-${version}.jar"
cached_pom="${coordinate_directory}/${artifact_id}-${version}.pom"
test ! -e "$consumer_cache" || die "consumer cache must start absent"

mvn -B -ntp -Dstyle.color=never \
    -f "$ROUTECONTRACT_REACTOR_POM" \
    "-Dmaven.repo.local=${consumer_cache}" \
    -P=-routecontract-pilot \
    -DskipTests=false \
    -Dmaven.test.skip=false \
    -Dmaven.test.failure.ignore=false \
    -pl "$ROUTECONTRACT_REACTOR_SELECTOR" -am clean install >"$profile_log" 2>&1 \
    || { report_suppressed_log; die "profile-off reactor build failed"; }
assert_no_integrity_warning "$profile_log"
validate_confined_path \
    "$ROUTECONTRACT_PROFILE_OFF_REPORT" "$routecontract_owning_target" \
    "profile-off Surefire report" regular
python3 -I - \
    "$ROUTECONTRACT_PROFILE_OFF_REPORT" \
    "$ROUTECONTRACT_PROFILE_OFF_CLASS" \
    "$ROUTECONTRACT_PROFILE_OFF_METHOD" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

root = ET.fromstring(pathlib.Path(sys.argv[1]).read_bytes())
if int(root.attrib.get("failures", "-1")) != 0 \
        or int(root.attrib.get("errors", "-1")) != 0:
    raise SystemExit("profile-off Surefire suite contains a failure or error")
matches = [
    case for case in root.findall("testcase")
    if case.attrib.get("classname") == sys.argv[2]
    and case.attrib.get("name") == sys.argv[3]
]
if len(matches) != 1:
    raise SystemExit(f"expected exactly one profile-off testcase, found {len(matches)}")
if any(matches[0].findall(name) for name in ("failure", "error", "skipped")):
    raise SystemExit("profile-off testcase did not pass")
PY
test ! -e "${consumer_cache}/${group_path}/${artifact_id}" \
    || die "profile-off build unexpectedly resolved RouteContract"
assert_absent_path "$ROUTECONTRACT_CANDIDATE_PATH" "profile-off candidate"
assert_absent_path "$ROUTECONTRACT_SUREFIRE_REPORT" "profile-off selected-test report"

mvn -B -ntp -Dstyle.color=never \
    -f "$ROUTECONTRACT_OWNING_POM" \
    "-Dmaven.repo.local=${consumer_cache}" \
    -DroutecontractPilot=true \
    "-DroutecontractRepositoryUrl=${repository_uri}" \
    "-Droutecontract.artifactJarPath=${cached_jar}" \
    "$checksum_algorithm_property" \
    -DskipTests=false \
    -Dmaven.test.skip=false \
    "-Dtest=${ROUTECONTRACT_TEST_CLASS}#${ROUTECONTRACT_TEST_METHOD}" \
    org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree >"$graph_log" 2>&1 \
    || { report_suppressed_log; die "dependency graph resolution failed"; }
assert_no_integrity_warning "$graph_log"

python3 -I - "$graph_log" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
pattern = re.compile(
    r"^(?P<prefix>(?:(?:\|  | {3})*(?:\+- |\\- )))"
    r"(?P<group>[A-Za-z0-9_.-]+):(?P<artifact>[A-Za-z0-9_.-]+):"
    r"(?P<type>[A-Za-z0-9_.-]+):(?:(?P<classifier>[^:\s]+):)?"
    r"(?P<version>[^:\s]+):(?P<scope>[^:\s]+)(?:\s.*)?$"
)
root_pattern = re.compile(
    r"(?P<group>[A-Za-z0-9_.-]+):(?P<artifact>[A-Za-z0-9_.-]+):"
    r"(?P<type>[A-Za-z0-9_.-]+):(?P<version>[^:\s]+)"
)
section_pattern = re.compile(
    r"^\[INFO\] --- (?:dependency|maven-dependency-plugin):3\.11\.0:tree "
    r"\([^)]*\) @ [^ ]+ ---$"
)
sections = []
current = None
for line in text.splitlines():
    if section_pattern.fullmatch(line):
        if current is not None:
            sections.append(current)
        current = {"roots": [], "coordinates": []}
        continue
    if current is None:
        continue
    if line.startswith("[INFO] --- "):
        sections.append(current)
        current = None
        continue
    if not line.startswith("[INFO] "):
        continue
    payload = line[len("[INFO] "):]
    root_match = root_pattern.fullmatch(payload)
    if root_match:
        current["roots"].append(root_match.groupdict())
        continue
    match = pattern.fullmatch(payload)
    if match:
        if len(current["roots"]) != 1:
            raise SystemExit("dependency coordinate appeared before the unique project root")
        prefix = match.group("prefix")
        depth = 0 if not prefix else 1 + (len(prefix) - 3) // 3
        current["coordinates"].append({
            "prefix": prefix,
            "depth": depth,
            "group": match.group("group"),
            "artifact": match.group("artifact"),
            "type": match.group("type"),
            "classifier": match.group("classifier"),
            "version": match.group("version"),
            "scope": match.group("scope"),
        })
if current is not None:
    sections.append(current)
if len(sections) != 1 or len(sections[0]["roots"]) != 1:
    raise SystemExit("expected exactly one dependency-tree plugin section and one project root")
coordinates = sections[0]["coordinates"]
if not coordinates:
    raise SystemExit("no Maven dependency coordinates were parsed")

def require_expected(
    group, artifact, version, *, direct, allowed_scopes, required=True
):
    matches = [
        coordinate for coordinate in coordinates
        if coordinate["group"] == group and coordinate["artifact"] == artifact
    ]
    valid = [
        coordinate for coordinate in matches
        if coordinate["version"] == version
        and coordinate["type"] == "jar"
        and coordinate["classifier"] is None
        and coordinate["scope"] in allowed_scopes
        and (not direct or coordinate["depth"] == 1)
    ]
    if not matches and not required:
        return
    if len(matches) != 1 or len(valid) != 1:
        qualifier = "direct " if direct else ""
        scope_contract = "|".join(sorted(allowed_scopes))
        cardinality = "exactly one" if required else "zero or exactly one"
        raise SystemExit(
            f"expected {cardinality} {qualifier}unclassified JAR dependency "
            f"{group}:{artifact}:{version} with scope {scope_contract}"
        )

versions = {coordinate["version"] for coordinate in coordinates
            if coordinate["group"] == "org.apache.shardingsphere"}
if versions != {"5.5.3"}:
    raise SystemExit(f"unexpected ShardingSphere versions: {sorted(versions)}")
require_expected(
    "org.apache.shardingsphere",
    "shardingsphere-jdbc",
    "5.5.3",
    direct=True,
    allowed_scopes={"compile", "runtime", "test"},
)
require_expected(
    "io.github.ym0506.routecontract",
    "routecontract-shardingsphere-5.5",
    "0.1.0",
    direct=True,
    allowed_scopes={"test"},
)
for expected in (
    ("org.apache.calcite", "calcite-core", "1.42.0"),
    ("org.apache.calcite", "calcite-linq4j", "1.42.0"),
):
    require_expected(
        *expected,
        direct=False,
        allowed_scopes={"compile", "runtime", "test"},
    )
for expected in (
    ("net.minidev", "json-smart", "2.4.10"),
    ("net.minidev", "accessors-smart", "2.4.9"),
):
    require_expected(
        *expected,
        direct=False,
        allowed_scopes={"compile", "runtime", "test"},
        required=False,
    )
jackson_versions = {
    coordinate["version"] for coordinate in coordinates
    if coordinate["group"] == "com.fasterxml.jackson"
    or coordinate["group"].startswith("com.fasterxml.jackson.")
}
if jackson_versions != {"2.18.9"}:
    raise SystemExit(f"unexpected FasterXML Jackson versions: {sorted(jackson_versions)}")
jackson = [
    coordinate for coordinate in coordinates
    if coordinate["group"] == "com.fasterxml.jackson"
    or coordinate["group"].startswith("com.fasterxml.jackson.")
]
if any(
    coordinate["type"] != "jar"
    or coordinate["classifier"] is not None
    or coordinate["scope"] not in {"compile", "runtime", "test"}
    for coordinate in jackson
):
    raise SystemExit("FasterXML Jackson dependencies must be unclassified JARs in an allowed scope")
forbidden = {
    ("org.locationtech.jts.io", "jts-io-common"),
    ("com.google.protobuf", "protobuf-java"),
}
present = sorted({
    (coordinate["group"], coordinate["artifact"])
    for coordinate in coordinates
    if (coordinate["group"], coordinate["artifact"]) in forbidden
})
if present:
    raise SystemExit(f"resolved graph contains forbidden dependencies {present}")
PY

assert_regular_file "$cached_pom" "cached RouteContract POM"
test "$(sha256_file "$cached_pom")" = "$expected_pom_sha256" \
    || die "cached RouteContract POM hash mismatch"
test "$(tr -d '\n' < "${cached_pom}.sha256")" = "$expected_pom_sha256" \
    || die "cached RouteContract POM sidecar mismatch"
grep -Fqx "${artifact_id}-${version}.pom>${repository_id}=" \
    "${coordinate_directory}/_remote.repositories" \
    || die "cached RouteContract POM repository binding mismatch"
assert_absent_path "$ROUTECONTRACT_CANDIDATE_PATH" "pre-test candidate"
assert_absent_path "$ROUTECONTRACT_SUREFIRE_REPORT" "pre-test selected-test report"

test_status=0
set +e
mvn -B -ntp -Dstyle.color=never \
    -f "$ROUTECONTRACT_OWNING_POM" \
    "-Dmaven.repo.local=${consumer_cache}" \
    -DroutecontractPilot=true \
    "-DroutecontractRepositoryUrl=${repository_uri}" \
    "-Droutecontract.artifactJarPath=${cached_jar}" \
    "$checksum_algorithm_property" \
    -DskipTests=false \
    -Dmaven.test.skip=false \
    -Dmaven.test.failure.ignore=false \
    "-Dtest=${ROUTECONTRACT_TEST_CLASS}#${ROUTECONTRACT_TEST_METHOD}" \
    clean test >"$test_log" 2>&1
test_status=$?
set -e

if [[ "$ROUTECONTRACT_EXPECTED_OUTCOME" == "review" ]]; then
    if [[ "$test_status" -ne 1 ]]; then
        report_suppressed_log
        die "review run must fail only for the missing approved baseline"
    fi
else
    if [[ "$test_status" -ne 0 ]]; then
        report_suppressed_log
        die "matched run failed"
    fi
fi
assert_no_integrity_warning "$test_log"
validate_confined_path \
    "$ROUTECONTRACT_CANDIDATE_PATH" "$routecontract_owning_target" \
    "fresh candidate" regular
validate_confined_path \
    "$ROUTECONTRACT_SUREFIRE_REPORT" "$routecontract_owning_target" \
    "selected-test Surefire report" regular

python3 -I - \
    "$ROUTECONTRACT_EXPECTED_OUTCOME" \
    "$ROUTECONTRACT_SUREFIRE_REPORT" \
    "$ROUTECONTRACT_TEST_CLASS" \
    "$ROUTECONTRACT_TEST_METHOD" \
    "$ROUTECONTRACT_CANDIDATE_PATH" \
    "$ROUTECONTRACT_APPROVED_PATH" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

outcome, report_text, class_name, method_name, candidate, approved = sys.argv[1:]
root = ET.fromstring(pathlib.Path(report_text).read_bytes())
cases = root.findall("testcase")
expected_counts = ("1", "1", "0", "0") if outcome == "review" else ("1", "0", "0", "0")
actual_counts = tuple(root.attrib.get(name) for name in ("tests", "failures", "errors", "skipped"))
if actual_counts != expected_counts:
    raise SystemExit(f"unexpected selected-test counts: {actual_counts}")
if len(cases) != 1 or cases[0].attrib.get("classname") != class_name \
        or cases[0].attrib.get("name") != method_name:
    raise SystemExit("the exact selected Surefire testcase did not run once")
if outcome == "review":
    failures = cases[0].findall("failure")
    expected = (
        f"No approved baseline. Review {candidate} "
        f"and copy it to {approved} only after human approval."
    )
    if len(failures) != 1 or failures[0].attrib.get("message", "") != expected:
        raise SystemExit("review run did not have the exact missing-baseline failure")
else:
    if any(cases[0].findall(name) for name in ("failure", "error", "skipped")):
        raise SystemExit("matched testcase did not pass")
PY

assert_regular_file "$cached_jar" "cached RouteContract JAR"
test "$(sha256_file "$cached_jar")" = "$expected_jar_sha256" \
    || die "cached RouteContract JAR hash mismatch"
test "$(tr -d '\n' < "${cached_jar}.sha256")" = "$expected_jar_sha256" \
    || die "cached RouteContract JAR sidecar mismatch"
test "$(sha256_file "$cached_pom")" = "$expected_pom_sha256" \
    || die "cached RouteContract POM hash mismatch after test"
test "$(tr -d '\n' < "${cached_pom}.sha256")" = "$expected_pom_sha256" \
    || die "cached RouteContract POM sidecar mismatch after test"
grep -Fqx "${artifact_id}-${version}.jar>${repository_id}=" \
    "${coordinate_directory}/_remote.repositories" \
    || die "cached RouteContract JAR repository binding mismatch"
grep -Fqx "${artifact_id}-${version}.pom>${repository_id}=" \
    "${coordinate_directory}/_remote.repositories" \
    || die "cached RouteContract POM repository binding mismatch after test"

if [[ "$ROUTECONTRACT_EXPECTED_OUTCOME" == "review" ]]; then
    validate_confined_path \
        "$ROUTECONTRACT_APPROVED_PATH" "$routecontract_owning_directory" \
        "approved manifest" allow-missing
    test ! -e "$ROUTECONTRACT_APPROVED_PATH" \
        || die "review run created an approved manifest"
    test ! -L "$ROUTECONTRACT_APPROVED_PATH" \
        || die "review run created an approved-manifest symlink"
else
    validate_confined_path \
        "$ROUTECONTRACT_APPROVED_PATH" "$routecontract_owning_directory" \
        "approved manifest" regular
    test "$(file_identity "$ROUTECONTRACT_APPROVED_PATH")" = "$approved_identity" \
        || die "approved manifest changed during verification"
fi

printf 'ROUTECONTRACT_EXTERNAL_MAVEN outcome=%s VERIFIED\n' \
    "$ROUTECONTRACT_EXPECTED_OUTCOME"
