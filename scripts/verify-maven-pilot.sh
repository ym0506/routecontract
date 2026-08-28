#!/usr/bin/env bash
set +x
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$script_directory/.." && pwd)"
fixture_source="$repository_root/examples/maven-pilot"
installer="$script_directory/install-release-assets.py"
checksum_preparer="$script_directory/prepare_maven_v0_1_0_checksums.py"

expected_installer_sha256="d21a7c71eb725e8d5f0675cfb88815b26be130d63711dc025a06347317652d33"
expected_checksum_preparer_sha256="546f801ae6056ae82dc6cbf8c3852056e7ec7ca9acfc7c077d06fc8d20247b89"
expected_index_sha256="820ed33eb8bfe8d47f3ec8782d2aa99f2879227c4ee066ecafc467e61abb8684"
expected_jar_sha256="d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
expected_pom_sha256="05570bfa238ef77db255a46efdd5bbb25e994ae0137db86491a46a25e28deac9"
expected_candidate_sha256="796d38c21c599812a4c0e31cae90c7f9377a109e3836beed4a04ff2bf554c818"
expected_candidate_bytes="655"
release_base="https://github.com/ym0506/routecontract/releases/download/v0.1.0"
artifact_id="routecontract-shardingsphere-5.5"
version="0.1.0"
group_path="io/github/ym0506/routecontract"
repository_id="routecontract-verified-file-repository"
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

usage() {
    cat <<'EOF'
Usage: ./scripts/verify-maven-pilot.sh [--release-assets-dir /absolute/path]

Without an argument, the verifier anonymously downloads the exact immutable
v0.1.0 GitHub Release assets.  The optional directory is only a download-cache
shortcut; the exact installer still validates its flat inventory and every
declared SHA-256 before use.

The verifier requires Java 17, Apache Maven 3.9.14, Python 3.10+, Docker, and
network access for uncached Maven Central dependencies and container images.
It runs only in private temporary copies.  Its synthetic candidate-to-baseline
copy proves a mechanical match path, not human approval or external adoption.
EOF
}

die() {
    printf 'ROUTECONTRACT_MAVEN_VERIFY_ERROR %s\n' "$1" >&2
    exit 2
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command is missing: $1"
}

sha256_file() {
    python3 -I -c \
        'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
        "$1"
}

file_size() {
    python3 -I -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).stat().st_size)' "$1"
}

fixture_digest() {
    python3 -I - "$1" <<'PY'
import hashlib
import os
import pathlib
import stat
import sys

root = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
    relative = path.relative_to(root)
    if "target" in relative.parts:
        continue
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise SystemExit(f"fixture source must not contain symbolic links: {relative}")
    if not stat.S_ISREG(metadata.st_mode):
        continue
    name = relative.as_posix().encode("utf-8")
    data = path.read_bytes()
    digest.update(len(name).to_bytes(8, "big"))
    digest.update(name)
    digest.update(len(data).to_bytes(8, "big"))
    digest.update(data)
print(digest.hexdigest())
PY
}

copy_fixture() {
    destination="$1"
    test ! -e "$destination" || die "fixture destination already exists: $destination"
    mkdir "$destination"
    tar -C "$fixture_source" --exclude 'target' --exclude '*/target' -cf - . \
        | tar -C "$destination" -xf -
    if find "$destination" -type d -name target -print -quit | grep -q .; then
        die "fixture copy unexpectedly contains a target directory"
    fi
}

seed_profile_off_cache() {
    fixture="$1"
    cache="$2"
    log="$3"
    test ! -e "$cache" || die "consumer cache must start absent: $cache"
    mvn -B -ntp -Dstyle.color=never \
        -f "$fixture/pom.xml" \
        "-Dmaven.repo.local=$cache" \
        -P=-routecontract-pilot \
        -pl support -am -DskipTests clean install >"$log" 2>&1
    assert_no_integrity_warning "$log"
    test ! -e "$cache/$group_path/$artifact_id" \
        || die "profile-off seed unexpectedly resolved RouteContract: $cache"
}

assert_no_integrity_warning() {
    log="$1"
    if grep -Eiq \
        'Could not validate integrity|Checksum validation failed|no checksums available' \
        "$log"; then
        die "successful Maven log contains an integrity warning: $log"
    fi
}

assert_one_fixed_line() {
    expected="$1"
    log="$2"
    count="$(grep -Fxc "$expected" "$log" || true)"
    if test "$count" != 1; then
        printf '%s\n' "--- Maven log tail ($log) ---" >&2
        tail -n 120 "$log" >&2 || true
        die "expected exactly one marker in $log: $expected"
    fi
}

parse_surefire() {
    expected_outcome="$1"
    report_directory="$2"
    expected_candidate_path="$3"
    expected_approved_path="$4"
    python3 -I - \
        "$expected_outcome" "$report_directory" \
        "$expected_candidate_path" "$expected_approved_path" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

outcome, directory_text, candidate_text, approved_text = sys.argv[1:]
directory = pathlib.Path(directory_text)
reports = sorted(directory.glob("TEST-*.xml"))
if len(reports) != 1:
    raise SystemExit(f"expected exactly one Surefire XML report, found {len(reports)}")
root = ET.parse(reports[0]).getroot()
tests = int(root.attrib.get("tests", "-1"))
failures = int(root.attrib.get("failures", "-1"))
errors = int(root.attrib.get("errors", "-1"))
skipped = int(root.attrib.get("skipped", "-1"))
cases = root.findall("testcase")
expected_class = "io.github.ym0506.routecontract.examples.maven.MavenRouteContractPilotTest"
expected_method = "keepsTheApprovedExecutionStructure"
if len(cases) != 1 or cases[0].attrib.get("classname") != expected_class \
        or cases[0].attrib.get("name") != expected_method:
    raise SystemExit("the exact selected Maven pilot testcase did not run once")
if outcome == "missing":
    if (tests, failures, errors, skipped) != (1, 1, 0, 0):
        raise SystemExit(f"unexpected missing-baseline Surefire counts: {root.attrib}")
    failures_found = cases[0].findall("failure")
    expected_message = (
        f"No approved baseline. Review {candidate_text} "
        f"and copy it to {approved_text} only after human approval."
    )
    if len(failures_found) != 1 or failures_found[0].attrib.get("message") != expected_message:
        raise SystemExit("missing-baseline run did not have the exact sole failure")
elif outcome == "matched":
    if (tests, failures, errors, skipped) != (1, 0, 0, 0):
        raise SystemExit(f"unexpected matched Surefire counts: {root.attrib}")
    if any(cases[0].findall(name) for name in ("failure", "error", "skipped")):
        raise SystemExit("matched Maven pilot testcase did not pass")
else:
    raise SystemExit(f"unknown expected Surefire outcome: {outcome}")
PY
}

if [[ "$#" -eq 0 ]]; then
    provided_assets=""
elif [[ "$#" -eq 2 && "$1" == "--release-assets-dir" ]]; then
    provided_assets="$2"
else
    usage >&2
    exit 64
fi

for required in curl docker java mvn python3 tar; do
    require_command "$required"
done
for required_file in "$fixture_source/pom.xml" "$installer" "$checksum_preparer"; do
    test -f "$required_file" || die "required file is missing: $required_file"
    test ! -L "$required_file" || die "required file must not be a symbolic link: $required_file"
done

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

test "$(sha256_file "$installer")" = "$expected_installer_sha256" \
    || die "release installer does not match the immutable v0.1.0 hash"
test "$(sha256_file "$checksum_preparer")" = "$expected_checksum_preparer_sha256" \
    || die "checksum preparer does not match the reviewed guide hash"
test ! -e "$fixture_source/integration-tests/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json" \
    || die "source fixture must not contain an approved or synthetic baseline"
test ! -L "$fixture_source/integration-tests/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json" \
    || die "source fixture baseline path must not be a symbolic link"

source_fixture_sha256="$(fixture_digest "$fixture_source")"
temporary_parent="${TMPDIR:-/tmp}"
temporary_parent="${temporary_parent%/}"
temporary_root="$(mktemp -d "$temporary_parent/routecontract-maven-pilot.XXXXXX")"
cleanup() {
    case "$temporary_root" in
        */routecontract-maven-pilot.*)
            rm -rf -- "$temporary_root"
            ;;
        *)
            printf 'Refusing to remove unexpected temporary path: %s\n' "$temporary_root" >&2
            ;;
    esac
}
trap cleanup EXIT

if [[ -n "$provided_assets" ]]; then
    [[ "$provided_assets" == /* ]] \
        || die "provided Release assets directory must be an absolute path"
    test -d "$provided_assets" \
        || die "provided Release assets directory does not exist"
    test ! -L "$provided_assets" \
        || die "provided Release assets directory must not be a symbolic link"
    release_assets_directory="$provided_assets"
    asset_source="provided-cache"
else
    release_assets_directory="$temporary_root/release-assets"
    mkdir "$release_assets_directory"
    for asset in "${assets[@]}"; do
        curl --disable --proto '=https' --tlsv1.2 --fail --location \
            --silent --show-error --retry 3 --connect-timeout 15 --max-time 300 \
            --max-filesize 5242880 \
            --output "$release_assets_directory/$asset" \
            "$release_base/$asset"
    done
    asset_source="anonymous-github-release"
fi

test "$(sha256_file "$release_assets_directory/SHA256SUMS")" = "$expected_index_sha256" \
    || die "SHA256SUMS does not match the immutable v0.1.0 index hash"

explicit_repository="$temporary_root/routecontract-maven-repository"
install_output="$(python3 -I "$installer" \
    --release-assets-dir "$release_assets_directory" \
    --repository "$explicit_repository")"
printf '%s\n' "$install_output" | grep -Fqx \
    'Installed coordinate: io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0' \
    || die "release installer did not report the exact v0.1.0 coordinate"
python3 -I "$checksum_preparer" --repository "$explicit_repository" \
    >"$temporary_root/checksum-preparation.log"

coordinate="$explicit_repository/$group_path/$artifact_id/$version"
repository_uri="$(python3 -I -c \
    'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True).as_uri())' \
    "$explicit_repository")"

profile_off_fixture="$temporary_root/profile-off"
bad_checksum_fixture="$temporary_root/bad-checksum"
graph_fixture="$temporary_root/graph"
missing_fixture="$temporary_root/missing-baseline"
matched_fixture="$temporary_root/mechanical-match"
copy_fixture "$profile_off_fixture"
copy_fixture "$bad_checksum_fixture"
copy_fixture "$graph_fixture"
copy_fixture "$missing_fixture"
copy_fixture "$matched_fixture"

profile_off_log="$temporary_root/profile-off.log"
mvn -B -ntp -Dstyle.color=never \
    -f "$profile_off_fixture/pom.xml" \
    "-Dmaven.repo.local=$temporary_root/cache-profile-off" \
    -P=-routecontract-pilot \
    clean verify >"$profile_off_log" 2>&1
assert_one_fixed_line \
    'ROUTECONTRACT_MAVEN_PROFILE_OFF businessResult=PASS routecontractDependency=ABSENT mysql=8.4.11 shardingsphere=5.5.3' \
    "$profile_off_log"
assert_no_integrity_warning "$profile_off_log"
test ! -e "$temporary_root/cache-profile-off/$group_path/$artifact_id" \
    || die "profile-off cache unexpectedly contains RouteContract"
test ! -e "$profile_off_fixture/integration-tests/target/test-classes/io/github/ym0506/routecontract/examples/maven/MavenRouteContractPilotTest.class" \
    || die "profile-off build compiled the pilot source"
test ! -e "$profile_off_fixture/integration-tests/target/routecontract/orders.find-by-user-id.candidate.json" \
    || die "profile-off build created a candidate"

profile_off_effective_pom="$temporary_root/profile-off-effective-pom.xml"
profile_off_effective_log="$temporary_root/profile-off-effective-pom.log"
mvn -B -ntp -Dstyle.color=never \
    -f "$profile_off_fixture/integration-tests/pom.xml" \
    "-Dmaven.repo.local=$temporary_root/cache-profile-off" \
    -P=-routecontract-pilot \
    -DskipTests=true \
    -Dmaven.test.skip=true \
    org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom \
    "-Doutput=$profile_off_effective_pom" >"$profile_off_effective_log" 2>&1
assert_no_integrity_warning "$profile_off_effective_log"
python3 -I - "$profile_off_effective_pom" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

path = pathlib.Path(sys.argv[1])
if path.is_symlink() or not path.is_file():
    raise SystemExit("profile-off effective POM is not a regular file")
namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
root = ET.parse(path).getroot()

def text(element, child):
    selected = element.find(child, namespace)
    if selected is None or selected.text is None:
        raise SystemExit(f"profile-off effective POM is missing {child}")
    return selected.text.strip()

def coordinate(dependency):
    return text(dependency, "m:groupId"), text(dependency, "m:artifactId")

managed = root.findall(
    "m:dependencyManagement/m:dependencies/m:dependency", namespace
)
inactive_management = {
    ("com.fasterxml.jackson", "jackson-bom"),
    ("org.apache.calcite", "calcite-core"),
    ("org.apache.calcite", "calcite-linq4j"),
    ("net.minidev", "json-smart"),
    ("net.minidev", "accessors-smart"),
}
present_management = {coordinate(dependency) for dependency in managed}
unexpected_management = sorted(inactive_management & present_management)
if unexpected_management:
    raise SystemExit(
        f"profile-off effective POM activated pilot-only dependency management: "
        f"{unexpected_management}"
    )

dependencies = root.findall("m:dependencies/m:dependency", namespace)
by_coordinate = {}
for dependency in dependencies:
    by_coordinate.setdefault(coordinate(dependency), []).append(dependency)
for forbidden in (
    ("io.github.ym0506.routecontract", "routecontract-shardingsphere-5.5"),
    ("org.apache.calcite", "calcite-core"),
):
    if forbidden in by_coordinate:
        raise SystemExit(
            f"profile-off effective POM activated pilot-only dependency {forbidden}"
        )
for expected in (
    ("org.apache.shardingsphere", "shardingsphere-jdbc"),
    ("com.mysql", "mysql-connector-j"),
):
    matches = by_coordinate.get(expected, [])
    if len(matches) != 1:
        raise SystemExit(
            f"profile-off effective POM must contain exactly one base dependency {expected}"
        )
    if matches[0].find("m:exclusions", namespace) is not None:
        raise SystemExit(
            f"profile-off effective POM inherited pilot-only exclusions for {expected}"
        )

repository_ids = {
    text(repository, "m:id")
    for repository in root.findall("m:repositories/m:repository", namespace)
}
if "routecontract-verified-file-repository" in repository_ids:
    raise SystemExit("profile-off effective POM activated the RouteContract repository")
active_sources = {
    (source.text or "").strip()
    for source in root.findall(
        "m:build/m:plugins/m:plugin/m:executions/m:execution/"
        "m:configuration/m:sources/m:source",
        namespace,
    )
}
if "src/routeContractPilot/java" in active_sources:
    raise SystemExit("profile-off effective POM activated the pilot source root")
PY

seed_profile_off_cache \
    "$bad_checksum_fixture" \
    "$temporary_root/cache-bad-checksum" \
    "$temporary_root/bad-checksum-profile-off-seed.log"
seed_profile_off_cache \
    "$graph_fixture" \
    "$temporary_root/cache-graph" \
    "$temporary_root/graph-profile-off-seed.log"
seed_profile_off_cache \
    "$missing_fixture" \
    "$temporary_root/cache-missing-baseline" \
    "$temporary_root/missing-baseline-profile-off-seed.log"
seed_profile_off_cache \
    "$matched_fixture" \
    "$temporary_root/cache-mechanical-match" \
    "$temporary_root/mechanical-match-profile-off-seed.log"

bad_repository="$temporary_root/routecontract-maven-repository-bad"
cp -R "$explicit_repository" "$bad_repository"
bad_sidecar="$bad_repository/$group_path/$artifact_id/$version/$artifact_id-$version.jar.sha256"
python3 -I - "$bad_sidecar" <<'PY'
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
if path.is_symlink() or not path.is_file():
    raise SystemExit("bad-checksum fixture sidecar is missing or unsafe")
path.write_bytes(("0" * 64 + "\n").encode("ascii"))
PY
bad_repository_uri="$(python3 -I -c \
    'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True).as_uri())' \
    "$bad_repository")"
bad_checksum_log="$temporary_root/bad-checksum.log"
set +e
mvn -B -ntp -Dstyle.color=never \
    -f "$bad_checksum_fixture/integration-tests/pom.xml" \
    "-Dmaven.repo.local=$temporary_root/cache-bad-checksum" \
    -DroutecontractPilot=true \
    "-DroutecontractRepositoryUrl=$bad_repository_uri" \
    "-Droutecontract.artifactJarPath=$temporary_root/cache-bad-checksum/$group_path/$artifact_id/$version/$artifact_id-$version.jar" \
    "$checksum_algorithm_property" \
    -Dtest=io.github.ym0506.routecontract.examples.maven.MavenRouteContractPilotTest#keepsTheApprovedExecutionStructure \
    clean test >"$bad_checksum_log" 2>&1
bad_checksum_exit=$?
set -e
test "$bad_checksum_exit" = 1 \
    || die "bad SHA-256 sidecar must produce Maven exit 1, observed $bad_checksum_exit"
grep -Fq \
    "Checksum validation failed, expected '0000000000000000000000000000000000000000000000000000000000000000' (REMOTE_EXTERNAL) but is actually '$expected_jar_sha256'" \
    "$bad_checksum_log" \
    || die "bad-checksum run did not report the exact SHA-256 mismatch"
test ! -e "$bad_checksum_fixture/integration-tests/target/routecontract/orders.find-by-user-id.candidate.json" \
    || die "bad-checksum run executed the pilot and created a candidate"
if grep -Fq 'ROUTECONTRACT_MAVEN_PILOT' "$bad_checksum_log"; then
    die "bad-checksum run reached the RouteContract pilot"
fi

graph_log="$temporary_root/dependency-tree.log"
mvn -B -ntp -Dstyle.color=never \
    -f "$graph_fixture/integration-tests/pom.xml" \
    "-Dmaven.repo.local=$temporary_root/cache-graph" \
    -DroutecontractPilot=true \
    "-DroutecontractRepositoryUrl=$repository_uri" \
    "-Droutecontract.artifactJarPath=$temporary_root/cache-graph/$group_path/$artifact_id/$version/$artifact_id-$version.jar" \
    "$checksum_algorithm_property" \
    -DskipTests=false \
    -Dmaven.test.skip=false \
    -Dtest=io.github.ym0506.routecontract.examples.maven.MavenRouteContractPilotTest#keepsTheApprovedExecutionStructure \
    org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree >"$graph_log" 2>&1
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

def require_expected(group, artifact, version, *, direct):
    matches = [
        coordinate for coordinate in coordinates
        if coordinate["group"] == group and coordinate["artifact"] == artifact
    ]
    valid = [
        coordinate for coordinate in matches
        if coordinate["version"] == version
        and coordinate["type"] == "jar"
        and coordinate["classifier"] is None
        and coordinate["scope"] == "test"
        and (not direct or coordinate["depth"] == 1)
    ]
    if len(matches) != 1 or len(valid) != 1:
        qualifier = "direct " if direct else ""
        raise SystemExit(
            f"expected exactly one {qualifier}unclassified test-scope JAR dependency "
            f"{group}:{artifact}:{version}"
        )

versions = {coordinate["version"] for coordinate in coordinates
            if coordinate["group"] == "org.apache.shardingsphere"}
if versions != {"5.5.3"}:
    raise SystemExit(f"unexpected ShardingSphere versions: {sorted(versions)}")
require_expected(
    "org.apache.shardingsphere", "shardingsphere-jdbc", "5.5.3", direct=True
)
require_expected(
    "io.github.ym0506.routecontract",
    "routecontract-shardingsphere-5.5",
    "0.1.0",
    direct=True,
)
for expected in (
    ("org.apache.calcite", "calcite-core", "1.42.0"),
    ("org.apache.calcite", "calcite-linq4j", "1.42.0"),
    ("net.minidev", "json-smart", "2.4.10"),
    ("net.minidev", "accessors-smart", "2.4.9"),
):
    require_expected(*expected, direct=False)
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

missing_log="$temporary_root/missing-baseline.log"
set +e
mvn -B -ntp -Dstyle.color=never \
    -f "$missing_fixture/integration-tests/pom.xml" \
    "-Dmaven.repo.local=$temporary_root/cache-missing-baseline" \
    -DroutecontractPilot=true \
    "-DroutecontractRepositoryUrl=$repository_uri" \
    "-Droutecontract.artifactJarPath=$temporary_root/cache-missing-baseline/$group_path/$artifact_id/$version/$artifact_id-$version.jar" \
    "$checksum_algorithm_property" \
    -Dtest=io.github.ym0506.routecontract.examples.maven.MavenRouteContractPilotTest#keepsTheApprovedExecutionStructure \
    clean test >"$missing_log" 2>&1
missing_exit=$?
set -e
test "$missing_exit" = 1 \
    || die "missing-baseline run must produce Maven exit 1, observed $missing_exit"
assert_no_integrity_warning "$missing_log"
missing_marker="ROUTECONTRACT_MAVEN_PILOT businessResult=PASS capture=COMPLETE observedPhysicalAttempts=1 observedDataSourceNames=[ds_0] candidate=$missing_fixture/integration-tests/target/routecontract/orders.find-by-user-id.candidate.json"
assert_one_fixed_line "$missing_marker" "$missing_log"
candidate="$missing_fixture/integration-tests/target/routecontract/orders.find-by-user-id.candidate.json"
approved="$missing_fixture/integration-tests/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"
test -f "$candidate" && test ! -L "$candidate" \
    || die "missing-baseline run did not create a regular candidate"
test ! -e "$approved" && test ! -L "$approved" \
    || die "missing-baseline harness unexpectedly contains an approved baseline"
test "$(sha256_file "$candidate")" = "$expected_candidate_sha256" \
    || die "missing-baseline candidate SHA-256 is not deterministic"
test "$(file_size "$candidate")" = "$expected_candidate_bytes" \
    || die "missing-baseline candidate byte count changed"
parse_surefire \
    missing \
    "$missing_fixture/integration-tests/target/surefire-reports" \
    "$candidate" \
    "$approved"
python3 -I - "$candidate" <<'PY'
import json
import pathlib
import sys

document = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_counts = {
    "observedPhysicalAttemptCount": 1,
    "callbackReturnedCount": 1,
    "callbackFailureCount": 0,
    "unknownOutcomeCount": 0,
    "distinctObservedDataSourceNameCount": 1,
}
if document.get("operationId") != "maven-pilot-orders.find-by-user-id":
    raise SystemExit("candidate operation ID changed")
if document.get("captureStatus") != "COMPLETE" or document.get("counts") != expected_counts:
    raise SystemExit("candidate capture boundary changed")
attempts = document.get("attempts")
if not isinstance(attempts, list) or len(attempts) != 1:
    raise SystemExit("candidate must contain exactly one aggregated attempt")
attempt = attempts[0]
if attempt.get("observedDataSourceAlias") != "orders-shard-a":
    raise SystemExit("candidate data-source alias changed")
if attempt.get("outcome") != "CALLBACK_RETURNED" or attempt.get("multiplicity") != 1:
    raise SystemExit("candidate outcome changed")
if attempt.get("parameterTypes") != ["java.lang.Long"] or attempt.get("parameterCount") != 1:
    raise SystemExit("candidate parameter shape changed")
PY

matched_approved="$matched_fixture/integration-tests/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"
mkdir -p "$(dirname "$matched_approved")"
cp "$candidate" "$matched_approved"
matched_log="$temporary_root/mechanical-match.log"
mvn -B -ntp -Dstyle.color=never \
    -f "$matched_fixture/integration-tests/pom.xml" \
    "-Dmaven.repo.local=$temporary_root/cache-mechanical-match" \
    -DroutecontractPilot=true \
    "-DroutecontractRepositoryUrl=$repository_uri" \
    "-Droutecontract.artifactJarPath=$temporary_root/cache-mechanical-match/$group_path/$artifact_id/$version/$artifact_id-$version.jar" \
    "$checksum_algorithm_property" \
    -Dtest=io.github.ym0506.routecontract.examples.maven.MavenRouteContractPilotTest#keepsTheApprovedExecutionStructure \
    clean test >"$matched_log" 2>&1
assert_no_integrity_warning "$matched_log"
matched_candidate="$matched_fixture/integration-tests/target/routecontract/orders.find-by-user-id.candidate.json"
matched_marker="ROUTECONTRACT_MAVEN_PILOT businessResult=PASS capture=COMPLETE observedPhysicalAttempts=1 observedDataSourceNames=[ds_0] candidate=$matched_candidate"
assert_one_fixed_line "$matched_marker" "$matched_log"
assert_one_fixed_line 'ROUTECONTRACT_MAVEN_PILOT candidateCheck=MATCHED' "$matched_log"
test "$(sha256_file "$matched_candidate")" = "$expected_candidate_sha256" \
    || die "mechanical-match candidate SHA-256 changed"
cmp -s "$matched_candidate" "$matched_approved" \
    || die "mechanical-match candidate differs from the synthetic harness copy"
parse_surefire \
    matched \
    "$matched_fixture/integration-tests/target/surefire-reports" \
    "$matched_candidate" \
    "$matched_approved"

graph_cache_coordinate="$temporary_root/cache-graph/$group_path/$artifact_id/$version"
test "$(sha256_file "$graph_cache_coordinate/$artifact_id-$version.pom")" = "$expected_pom_sha256" \
    || die "graph cache did not retain the exact Release POM"
test "$(tr -d '\n' < "$graph_cache_coordinate/$artifact_id-$version.pom.sha256")" = "$expected_pom_sha256" \
    || die "graph cache did not record the exact POM SHA-256 sidecar"
grep -Fqx "$artifact_id-$version.pom>$repository_id=" \
    "$graph_cache_coordinate/_remote.repositories" \
    || die "graph cache did not bind the POM to the explicit repository ID"

for cache in cache-missing-baseline cache-mechanical-match; do
    cache_coordinate="$temporary_root/$cache/$group_path/$artifact_id/$version"
    test "$(sha256_file "$cache_coordinate/$artifact_id-$version.jar")" = "$expected_jar_sha256" \
        || die "$cache did not retain the exact Release JAR"
    test "$(sha256_file "$cache_coordinate/$artifact_id-$version.pom")" = "$expected_pom_sha256" \
        || die "$cache did not retain the exact Release POM"
    test "$(tr -d '\n' < "$cache_coordinate/$artifact_id-$version.jar.sha256")" = "$expected_jar_sha256" \
        || die "$cache did not record the exact JAR SHA-256 sidecar"
    test "$(tr -d '\n' < "$cache_coordinate/$artifact_id-$version.pom.sha256")" = "$expected_pom_sha256" \
        || die "$cache did not record the exact POM SHA-256 sidecar"
    grep -Fqx "$artifact_id-$version.jar>$repository_id=" \
        "$cache_coordinate/_remote.repositories" \
        || die "$cache did not bind the JAR to the explicit repository ID"
    grep -Fqx "$artifact_id-$version.pom>$repository_id=" \
        "$cache_coordinate/_remote.repositories" \
        || die "$cache did not bind the POM to the explicit repository ID"
done

test "$(fixture_digest "$fixture_source")" = "$source_fixture_sha256" \
    || die "verifier changed the source fixture"
test ! -e "$fixture_source/integration-tests/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json" \
    || die "verifier wrote a baseline into the source fixture"

printf '%s\n' \
    'ROUTECONTRACT_MAVEN_FIXTURE profileOff=PASS routecontractDependency=ABSENT businessResult=PASS' \
    "ROUTECONTRACT_MAVEN_FIXTURE badChecksum=REJECTED algorithm=SHA-256 expectedJarSha256=$expected_jar_sha256" \
    'ROUTECONTRACT_MAVEN_FIXTURE graph=PASS shardingsphere=5.5.3 jackson=2.18.9 calcite=1.42.0 minidev=2.4.x forbiddenDependencies=ABSENT' \
    "ROUTECONTRACT_MAVEN_FIXTURE missingBaseline=EXPECTED_FAILURE candidateSha256=$expected_candidate_sha256 candidateBytes=$expected_candidate_bytes" \
    "ROUTECONTRACT_MAVEN_FIXTURE mechanicalMatch=PASS candidateSha256=$expected_candidate_sha256" \
    "ROUTECONTRACT_MAVEN_FIXTURE assetSource=$asset_source maven=3.9.14 java=17 mysql=8.4.11" \
    'ROUTECONTRACT_MAVEN_FIXTURE evidenceBoundary=SAME_CHECKOUT_NOT_EXTERNAL_ADOPTION humanApprovedBaseline=false' \
    '[ROUTECONTRACT MAVEN PILOT VERIFIED]'
