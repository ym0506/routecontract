#!/usr/bin/env bash
set +x
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$script_directory/.." && pwd)"
video_demo="$script_directory/video-demo-session.sh"

usage() {
    cat <<'EOF'
Usage: ./scripts/quickstart-demo.sh

Runs the privacy-safe real-MySQL 1 -> 2 regression followed by the
intentional non-zero CI gate. The quickstart exits 0 only when the MySQL
evidence is verified and the underlying CI gate exits with the expected 1.
EOF
}

quickstart_error() {
    local phase="$1"
    local check="$2"
    local expected="$3"
    local observed="$4"

    printf 'QUICKSTART_ERROR phase=%s check=%s expected=%s observed=%s\n' \
        "$phase" "$check" "$expected" "$observed" >&2
    printf '%s\n' \
        'child_output=WITHHELD_FOR_PRIVACY debug=run_the_phase_specific_script_off_camera' >&2
    exit 2
}

require_contains() {
    local phase="$1"
    local output="$2"
    local expected="$3"
    local check="$4"

    if [[ "$output" != *"$expected"* ]]; then
        quickstart_error "$phase" "$check" PRESENT MISSING
    fi
}

if [[ "$#" -ne 0 ]]; then
    usage >&2
    exit 64
fi

if ! command -v java >/dev/null 2>&1; then
    quickstart_error preflight java PRESENT MISSING
fi
if ! command -v docker >/dev/null 2>&1; then
    quickstart_error preflight docker_cli PRESENT MISSING
fi
if [[ ! -x "$repository_root/gradlew" ]]; then
    quickstart_error preflight gradle_wrapper EXECUTABLE MISSING
fi
if [[ ! -x "$video_demo" ]]; then
    quickstart_error preflight video_demo EXECUTABLE MISSING
fi

if ! java_version_output="$(java -version 2>&1)"; then
    quickstart_error preflight java_version READABLE UNAVAILABLE
fi
java_version_line="${java_version_output%%$'\n'*}"
if [[ "$java_version_line" =~ \"([0-9]+)(\.[^\"]*)?\" ]]; then
    java_major="${BASH_REMATCH[1]}"
else
    quickstart_error preflight java_major 17 UNPARSEABLE
fi
if [[ "$java_major" != 17 ]]; then
    quickstart_error preflight java_major 17 "$java_major"
fi
if ! docker info >/dev/null 2>&1; then
    quickstart_error preflight docker_daemon REACHABLE UNREACHABLE
fi

cat <<'EOF'
[QUICKSTART PREFLIGHT]
javaMajor              17
dockerDaemon           REACHABLE
gradleWrapper          READY
firstRunDownloads      NETWORK_MAY_BE_REQUIRED
phase=mysql            RUNNING
EOF

set +e
mysql_output="$("$video_demo" mysql 2>&1)"
mysql_exit=$?
set -e
if [[ "$mysql_exit" -ne 0 ]]; then
    quickstart_error mysql child_exit 0 "$mysql_exit"
fi
require_contains mysql "$mysql_output" \
    'businessResult          UNCHANGED (one row in both captures)' business_result
require_contains mysql "$mysql_output" \
    'observedAttempts        1 -> 2' observed_attempts
require_contains mysql "$mysql_output" \
    'observedDataSources     1 -> 2' observed_data_sources
require_contains mysql "$mysql_output" \
    'RCM201                  ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2' RCM201
require_contains mysql "$mysql_output" \
    'RCM202                  DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2' RCM202
require_contains mysql "$mysql_output" 'demo_exit               0' verified_exit

printf '%s\n' 'phase=mysql            VERIFIED' 'phase=ci               RUNNING'

set +e
ci_output="$("$video_demo" ci 2>&1)"
ci_exit=$?
set -e
if [[ "$ci_exit" -ne 1 ]]; then
    quickstart_error ci child_exit 1 "$ci_exit"
fi
require_contains ci "$ci_output" \
    'RCM201 BLOCKING ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2' RCM201
require_contains ci "$ci_output" \
    'RCM202 BLOCKING DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2' RCM202
require_contains ci "$ci_output" 'BUILD FAILED (intentional)' build_failure
require_contains ci "$ci_output" 'ci_exit                 1' verified_exit

cat <<'EOF'
phase=ci               VERIFIED
[ROUTECONTRACT QUICKSTART VERIFIED]
environment            Java 17 | MySQL 8.4.11 digest-pinned | ShardingSphere-JDBC 5.5.3
businessResult         UNCHANGED (one row in both captures)
observedAttempts       1 -> 2
observedDataSources    1 -> 2
RCM201                 ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2
RCM202                 DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2
realMysqlDemoExit      0
intentionalCiGateExit  1 (expected build rejection)
privacy                raw child output withheld | raw SQL/binds not retained
aliases                reviewed aliases remain | minimized != anonymized
quickstartExit         0
EOF
