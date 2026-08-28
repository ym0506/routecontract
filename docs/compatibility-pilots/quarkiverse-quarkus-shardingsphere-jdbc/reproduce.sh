#!/usr/bin/env bash
set -euo pipefail

readonly EXPECTED_UPSTREAM_COMMIT="90e023ce45d58842011724d5b7e7e04d710eb459"
readonly EXPECTED_UPSTREAM_TREE="523e367826826da44e5b75249a828645eb032889"
readonly EXPECTED_MAVEN_VERSION="3.9.14"
readonly EXPECTED_JAR_SHA256="d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
readonly EXPECTED_POM_SHA256="05570bfa238ef77db255a46efdd5bbb25e994ae0137db86491a46a25e28deac9"
readonly EXPECTED_SUMS_SHA256="820ed33eb8bfe8d47f3ec8782d2aa99f2879227c4ee066ecafc467e61abb8684"
readonly EXPECTED_CANDIDATE_SHA256="60e94c17e2df96ff7f4769f33a6a7b4f3431b0cd0995d47906e6f63a3d1601e4"
readonly EXPECTED_CANDIDATE_BYTES="679"
readonly RELEASE_JAR="routecontract-shardingsphere-5.5-0.1.0.jar"
readonly RELEASE_POM="routecontract-shardingsphere-5.5.pom"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat >&2 <<'EOF'
Usage: reproduce.sh ABSOLUTE_DISPOSABLE_UPSTREAM_CHECKOUT ABSOLUTE_RELEASE_ASSETS_DIR

The checkout must be clean and exactly at the pinned Quarkiverse commit. The release-assets
directory must contain the v0.1.0 JAR, POM and SHA256SUMS. This script applies the two-path patch
to the disposable checkout and intentionally leaves that checkout modified. It never creates an
approved baseline.

Optional: set MAVEN_REPO_SEED to an absolute Maven local-repository directory. It is copied only
into the private scratch directory; the RouteContract coordinate is then removed before testing.
EOF
  exit 2
}

sha256_file() {
  local target="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$target" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$target" | awk '{print $1}'
  else
    fail "sha256sum or shasum is required"
  fi
}

require_hash() {
  local target="$1"
  local expected="$2"
  [[ -f "$target" && ! -L "$target" ]] || fail "missing regular file: $target"
  local actual
  actual="$(sha256_file "$target")"
  [[ "$actual" == "$expected" ]] || fail "SHA-256 mismatch for $target: $actual"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

[[ "$#" -eq 2 ]] || usage
[[ "$1" == /* && "$2" == /* ]] || fail "both arguments must be absolute paths"

for command_name in awk cmp cp find git grep java mktemp mvn python3 tr wc; do
  require_command "$command_name"
done

readonly KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PATCH_FILE="$KIT_DIR/routecontract-pilot.patch"
readonly UPSTREAM_DIR="$(cd "$1" && pwd -P)"
readonly ASSETS_DIR="$(cd "$2" && pwd -P)"
readonly APPROVED_RELATIVE="integration-tests/src/routeContractPilot/resources/route-contracts/accounts.insert.json"
readonly CANDIDATE_RELATIVE="integration-tests/target/routecontract/accounts.insert.candidate.json"
readonly PILOT_CLASS_RELATIVE="integration-tests/target/test-classes/io/quarkiverse/shardingsphere/jdbc/it/RouteContractInsertPilotTest.class"
readonly REPORT_RELATIVE="integration-tests/target/surefire-reports/TEST-io.quarkiverse.shardingsphere.jdbc.it.RouteContractInsertPilotTest.xml"
readonly PROFILE_OFF_DEPLOYMENT_REPORT="deployment/target/surefire-reports/TEST-io.quarkiverse.shardingsphere.jdbc.test.ShardingsphereJdbcTest.xml"
readonly PROFILE_OFF_DEV_MODE_REPORT="deployment/target/surefire-reports/TEST-io.quarkiverse.shardingsphere.jdbc.test.ShardingsphereJdbcDevModeTest.xml"
readonly PROFILE_OFF_INTEGRATION_REPORT="integration-tests/target/surefire-reports/TEST-io.quarkiverse.shardingsphere.jdbc.it.ShardingTablesTest.xml"

require_hash "$ASSETS_DIR/$RELEASE_JAR" "$EXPECTED_JAR_SHA256"
require_hash "$ASSETS_DIR/$RELEASE_POM" "$EXPECTED_POM_SHA256"
require_hash "$ASSETS_DIR/SHA256SUMS" "$EXPECTED_SUMS_SHA256"

[[ -n "${JAVA_HOME:-}" ]] || fail "JAVA_HOME must point to JDK 17"
readonly JAVA_SPECIFICATION_VERSION="$(java -XshowSettings:properties -version 2>&1 \
  | awk -F '= ' '/java.specification.version = / {print $2; exit}')"
[[ "$JAVA_SPECIFICATION_VERSION" == "17" ]] \
  || fail "JDK 17 is required; found specification version $JAVA_SPECIFICATION_VERSION"
readonly MAVEN_VERSION="$(mvn -version | awk 'NR == 1 {print $3}')"
[[ "$MAVEN_VERSION" == "$EXPECTED_MAVEN_VERSION" ]] \
  || fail "Maven $EXPECTED_MAVEN_VERSION is required; found $MAVEN_VERSION"

[[ "$(git -C "$UPSTREAM_DIR" rev-parse HEAD)" == "$EXPECTED_UPSTREAM_COMMIT" ]] \
  || fail "upstream commit is not the pinned commit"
[[ "$(git -C "$UPSTREAM_DIR" rev-parse 'HEAD^{tree}')" == "$EXPECTED_UPSTREAM_TREE" ]] \
  || fail "upstream tree is not the pinned tree"
[[ -z "$(git -C "$UPSTREAM_DIR" status --porcelain=v1 --untracked-files=all)" ]] \
  || fail "upstream checkout is not clean"
[[ ! -e "$UPSTREAM_DIR/$APPROVED_RELATIVE" ]] || fail "an approved baseline already exists"
git -C "$UPSTREAM_DIR" apply --check "$PATCH_FILE"

temporary_parent="${TMPDIR:-/tmp}"
temporary_parent="${temporary_parent%/}"
readonly SCRATCH_DIR="$(mktemp -d "$temporary_parent/routecontract-quarkiverse-pilot.XXXXXX")"
cleanup() {
  rm -rf -- "$SCRATCH_DIR"
}
trap cleanup EXIT INT TERM

readonly MAVEN_LOCAL_REPO="$SCRATCH_DIR/m2"
readonly FILE_REPO="$SCRATCH_DIR/routecontract-file-repository"
readonly ARTIFACT_DIR="$FILE_REPO/io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.0"
mkdir -p "$MAVEN_LOCAL_REPO" "$ARTIFACT_DIR"

if [[ -n "${MAVEN_REPO_SEED:-}" ]]; then
  [[ "$MAVEN_REPO_SEED" == /* ]] || fail "MAVEN_REPO_SEED must be an absolute path"
  readonly SEED_DIR="$(cd "$MAVEN_REPO_SEED" && pwd -P)"
  if find "$SEED_DIR" -type l -print -quit | grep -q .; then
    fail "MAVEN_REPO_SEED must not contain symbolic links"
  fi
  cp -R "$SEED_DIR"/. "$MAVEN_LOCAL_REPO"/
  if find "$MAVEN_LOCAL_REPO" -type l -print -quit | grep -q .; then
    fail "copied Maven seed unexpectedly contains symbolic links"
  fi
  rm -rf -- "$MAVEN_LOCAL_REPO/io/github/ym0506/routecontract"
fi

cp "$ASSETS_DIR/$RELEASE_JAR" "$ARTIFACT_DIR/$RELEASE_JAR"
cp "$ASSETS_DIR/$RELEASE_POM" \
  "$ARTIFACT_DIR/routecontract-shardingsphere-5.5-0.1.0.pom"
printf '%s\n' "$EXPECTED_JAR_SHA256" >"$ARTIFACT_DIR/$RELEASE_JAR.sha256"
printf '%s\n' "$EXPECTED_POM_SHA256" \
  >"$ARTIFACT_DIR/routecontract-shardingsphere-5.5-0.1.0.pom.sha256"

git -C "$UPSTREAM_DIR" apply "$PATCH_FILE"
readonly EXPECTED_STATUS=$' M integration-tests/pom.xml\n?? integration-tests/src/routeContractPilot/'
[[ "$(git -C "$UPSTREAM_DIR" status --short)" == "$EXPECTED_STATUS" ]] \
  || fail "patch changed paths outside the expected two-path scope"
git -C "$UPSTREAM_DIR" diff --check
[[ ! -e "$UPSTREAM_DIR/$APPROVED_RELATIVE" ]] || fail "patch created an approved baseline"

readonly MAVEN_REPOSITORY_OPTION="-Dmaven.repo.local=$MAVEN_LOCAL_REPO"
readonly CHECKSUM_OPTION="-Daether.checksums.algorithms.routecontract-v0.1.0-local=SHA-256"

(
  cd "$UPSTREAM_DIR"
  mvn -B -ntp "$MAVEN_REPOSITORY_OPTION" "$CHECKSUM_OPTION" \
    -DskipTests=false \
    -Dmaven.test.skip=false \
    -Dmaven.test.failure.ignore=false \
    clean test
)
python3 - \
  "$UPSTREAM_DIR/$PROFILE_OFF_DEPLOYMENT_REPORT" \
  'io.quarkiverse.shardingsphere.jdbc.test.ShardingsphereJdbcTest' \
  'writeYourOwnUnitTest' \
  "$UPSTREAM_DIR/$PROFILE_OFF_DEV_MODE_REPORT" \
  'io.quarkiverse.shardingsphere.jdbc.test.ShardingsphereJdbcDevModeTest' \
  'writeYourOwnDevModeTest' \
  "$UPSTREAM_DIR/$PROFILE_OFF_INTEGRATION_REPORT" \
  'io.quarkiverse.shardingsphere.jdbc.it.ShardingTablesTest' \
  'test' <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

arguments = sys.argv[1:]
if len(arguments) != 9:
    raise SystemExit("expected three exact profile-off report triples")
report_paths = [pathlib.Path(arguments[offset]) for offset in range(0, len(arguments), 3)]
actual_reports = {
    report
    for parent in {path.parent for path in report_paths}
    for report in parent.glob("TEST-*.xml")
}
if actual_reports != set(report_paths):
    raise SystemExit("profile-off Surefire report inventory is not the exact reviewed set")
for offset in range(0, len(arguments), 3):
    report_path = pathlib.Path(arguments[offset])
    expected_class = arguments[offset + 1]
    expected_method = arguments[offset + 2]
    if not report_path.is_file() or report_path.is_symlink():
        raise SystemExit(f"missing regular profile-off report: {report_path}")
    root = ET.parse(report_path).getroot()
    totals = {
        key: root.attrib.get(key)
        for key in ("tests", "failures", "errors", "skipped")
    }
    expected_totals = {"tests": "1", "failures": "0", "errors": "0", "skipped": "0"}
    if totals != expected_totals:
        raise SystemExit(f"unexpected profile-off report totals: {report_path}: {totals}")
    cases = root.findall(".//testcase")
    matching = [
        case for case in cases
        if case.attrib.get("classname") == expected_class
        and case.attrib.get("name") == expected_method
    ]
    if len(cases) != 1 or len(matching) != 1:
        raise SystemExit(f"unexpected profile-off testcase identity: {report_path}")
    if any(matching[0].find(tag) is not None for tag in ("failure", "error", "skipped")):
        raise SystemExit(f"profile-off testcase has a failure, error, or skip child: {report_path}")
PY
[[ ! -e "$UPSTREAM_DIR/$CANDIDATE_RELATIVE" ]] \
  || fail "profile-off build unexpectedly created a RouteContract candidate"
[[ ! -e "$UPSTREAM_DIR/$PILOT_CLASS_RELATIVE" ]] \
  || fail "profile-off build unexpectedly compiled the opt-in pilot source"
[[ ! -e "$UPSTREAM_DIR/$APPROVED_RELATIVE" ]] \
  || fail "profile-off build unexpectedly created an approved baseline"
(
  cd "$UPSTREAM_DIR"
  mvn -B -ntp "$MAVEN_REPOSITORY_OPTION" "$CHECKSUM_OPTION" \
    -pl integration-tests -am dependency:tree \
    '-Dincludes=io.github.ym0506.routecontract:*'
) >"$SCRATCH_DIR/profile-off-dependency-tree.log" 2>&1
if grep -F 'io.github.ym0506.routecontract:' "$SCRATCH_DIR/profile-off-dependency-tree.log" >/dev/null; then
  fail "profile-off dependency tree unexpectedly contains RouteContract"
fi

validate_expected_failure() {
  local run_number="$1"
  local log_path="$SCRATCH_DIR/profile-on-$run_number.log"
  local candidate_path="$UPSTREAM_DIR/$CANDIDATE_RELATIVE"
  local report_path="$UPSTREAM_DIR/$REPORT_RELATIVE"
  local command_status

  set +e
  (
    cd "$UPSTREAM_DIR"
    mvn -B -ntp "$MAVEN_REPOSITORY_OPTION" "$CHECKSUM_OPTION" \
      -DroutecontractPilot=true \
      "-Droutecontract.repository=$FILE_REPO" \
      -Dtest=RouteContractInsertPilotTest \
      -Dsurefire.failIfNoSpecifiedTests=false \
      -DskipTests=false \
      -Dmaven.test.skip=false \
      -Dmaven.test.failure.ignore=false \
      clean test
  ) >"$log_path" 2>&1
  command_status="$?"
  set -e

  [[ "$command_status" -ne 0 ]] || fail "profile-on run $run_number unexpectedly passed"
  [[ "$(grep -Fc 'ROUTECONTRACT_QUARKIVERSE_PILOT businessRows=0->1 attempts=1 dataSources=[ds_1] status=COMPLETE' "$log_path" || true)" == "1" ]] \
    || fail "profile-on run $run_number did not emit the exact bounded result marker once"
  [[ -f "$report_path" ]] || fail "profile-on run $run_number did not create its Surefire report"

  python3 - "$report_path" <<'PY'
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
expected = {"tests": "1", "failures": "1", "errors": "0", "skipped": "0"}
actual = {key: root.attrib.get(key) for key in expected}
if actual != expected:
    raise SystemExit(f"unexpected Surefire totals: {actual}")
failures = root.findall(".//failure")
if len(failures) != 1:
    raise SystemExit(f"expected one failure element, found {len(failures)}")
message = failures[0].attrib.get("message", "")
expected_message = (
    "No approved baseline. Review target/routecontract/accounts.insert.candidate.json "
    "and copy its exact bytes only after human approval."
)
if message != expected_message:
    raise SystemExit(f"unexpected pilot failure message: {message!r}")
PY

  [[ -f "$candidate_path" ]] || fail "profile-on run $run_number did not create a candidate"
  [[ "$(sha256_file "$candidate_path")" == "$EXPECTED_CANDIDATE_SHA256" ]] \
    || fail "profile-on run $run_number candidate hash changed"
  [[ "$(wc -c <"$candidate_path" | tr -d '[:space:]')" == "$EXPECTED_CANDIDATE_BYTES" ]] \
    || fail "profile-on run $run_number candidate size changed"
  [[ ! -e "$UPSTREAM_DIR/$APPROVED_RELATIVE" ]] \
    || fail "profile-on run $run_number created an approved baseline"

  if [[ "$run_number" == "1" ]]; then
    cp "$candidate_path" "$SCRATCH_DIR/candidate-run-1.json"
  else
    cmp "$SCRATCH_DIR/candidate-run-1.json" "$candidate_path" \
      || fail "profile-on candidates differ between runs"
  fi
}

validate_expected_failure 1
validate_expected_failure 2

printf '%s\n' \
  'ROUTECONTRACT_QUARKIVERSE_PROFILE_OFF fullReactor=PASS pilotDependency=ABSENT' \
  'ROUTECONTRACT_QUARKIVERSE_PROFILE_ON run1=EXPECTED_BASELINE_FAILURE run2=EXPECTED_BASELINE_FAILURE' \
  "ROUTECONTRACT_QUARKIVERSE_CANDIDATE sha256=$EXPECTED_CANDIDATE_SHA256 bytes=$EXPECTED_CANDIDATE_BYTES deterministicRuns=2" \
  'ROUTECONTRACT_QUARKIVERSE_BOUNDARY environment=H2 humanApprovedBaseline=false externalUser=false adoption=false endorsement=false'
