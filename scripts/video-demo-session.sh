#!/usr/bin/env bash
set +x
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$script_directory/.." && pwd)"

mysql_marker='ROUTECONTRACT_MANIFEST_DEMO businessResult=UNCHANGED observedPhysicalAttempts=1->2 verificationStatus=POLICY_VIOLATION blockingCodes=[RCM201,RCM202] privacy=MINIMIZED'
fingerprint_marker='ROUTECONTRACT_FINGERPRINT_DRIFT_DEMO businessResult=UNCHANGED observedPhysicalAttempts=1->1 observedDataSourceAliases=[orders-odd]->[orders-odd] fingerprintMultiset=CHANGED verificationStatus=DRIFT blockingCodes=[RCM301,RCM302] privacy=MINIMIZED'
ci_marker='ROUTECONTRACT_FILE_CI_DEMO approvedAttempts=1 candidateAttempts=2 status=POLICY_VIOLATION blockingCodes=[RCM201,RCM202]'
ci_attempt_diff='RCM201 BLOCKING ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2'
ci_data_source_diff='RCM202 BLOCKING DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2'
standalone_marker='ROUTECONTRACT_STANDALONE artifact=published-jar spi=auto-discovered mysql=8.4.11 shardingsphere=5.5.3 observedPhysicalAttempts=1 observedDataSourceNames=[ds_0]'

usage() {
    cat <<'EOF'
Usage: ./scripts/video-demo-session.sh <mysql|fingerprint|ci|standalone>

  mysql        Run the real-MySQL 1 -> 2 manifest regression; exit 0 on verified evidence.
  fingerprint  Run the real-MySQL same-budget fingerprint drift; exit 0 on verified evidence.
  ci           Run the file-based intentional-red gate; exit 1 only on the expected failure.
  standalone   Verify the published JAR consumer and SPI discovery; exit 0 on verified evidence.

Only fixed, privacy-reviewed lines are emitted. Raw child-process output is withheld.
An evidence or exit-code mismatch returns 2 and must be debugged off-camera.
EOF
}

safe_error() {
    local phase="$1"
    local check="$2"
    local expected="$3"
    local observed="$4"

    printf 'VIDEO_DEMO_ERROR phase=%s check=%s expected=%s observed=%s\n' \
        "$phase" "$check" "$expected" "$observed" >&2
    printf '%s\n' \
        'raw_output=WITHHELD_FOR_PRIVACY debug=run_the_original_script_off_camera' >&2
    return 2
}

run_mysql_demo() {
    local raw_output
    local observed_exit

    printf '%s\n' \
        'video_phase=mysql status=RUNNING child_output=WITHHELD_UNTIL_VERIFIED'
    set +e
    raw_output="$("$script_directory/run-demo.sh" 2>&1)"
    observed_exit=$?
    set -e

    if [[ "$observed_exit" -ne 0 ]]; then
        safe_error mysql child_exit 0 "$observed_exit"
        return 2
    fi
    if [[ "$raw_output" != *"$mysql_marker"* ]]; then
        safe_error mysql evidence_marker PRESENT MISSING
        return 2
    fi

    cat <<'EOF'
[MYSQL BASELINE -> CANDIDATE]
environment             Java 17 | MySQL 8.4.11 digest-pinned | ShardingSphere-JDBC 5.5.3
businessResult          UNCHANGED (one row in both captures)
observedAttempts        1 -> 2
observedDataSources     1 -> 2
approvedAliases         [orders-odd]
candidateAliases        [orders-even,orders-odd]
verificationStatus      POLICY_VIOLATION
blockingCodes           [RCM201,RCM202]
RCM201                  ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2
RCM202                  DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2
privacy                 MINIMIZED | screen output allowlisted
demo_exit               0
EOF
}

run_fingerprint_demo() {
    local raw_output
    local observed_exit
    local test_name='io.github.ym0506.routecontract.example.ObservedExecutionRegressionCorpusMySqlTest.strategyRemovalProducesTwoDifferentObservableRegressionShapes'

    printf '%s\n' \
        'video_phase=fingerprint status=RUNNING child_output=WITHHELD_UNTIL_VERIFIED'
    set +e
    raw_output="$("$repository_root/gradlew" \
        --no-daemon \
        --no-build-cache \
        -p "$repository_root" \
        :mysql-example:test \
        --rerun-tasks \
        --tests "$test_name" 2>&1)"
    observed_exit=$?
    set -e

    if [[ "$observed_exit" -ne 0 ]]; then
        safe_error fingerprint child_exit 0 "$observed_exit"
        return 2
    fi
    if [[ "$raw_output" != *"$fingerprint_marker"* ]]; then
        safe_error fingerprint evidence_marker PRESENT MISSING
        return 2
    fi

    cat <<'EOF'
[SAME-BUDGET FINGERPRINT DRIFT]
businessResult          UNCHANGED
observedAttempts        1 -> 1
observedDataSources     1 -> 1
observedAliases         [orders-odd] -> [orders-odd]
fingerprintMultiset     CHANGED
verificationStatus      DRIFT
blockingCodes           [RCM301,RCM302]
privacy                 MINIMIZED | screen output allowlisted
fingerprint_demo_exit   0
EOF
}

run_ci_demo() {
    local raw_output
    local observed_exit

    printf '%s\n' \
        'video_phase=ci status=RUNNING child_output=WITHHELD_UNTIL_VERIFIED'
    set +e
    raw_output="$("$script_directory/demo-manifest-ci-failure.sh" 2>&1)"
    observed_exit=$?
    set -e

    if [[ "$observed_exit" -ne 1 ]]; then
        safe_error ci child_exit 1 "$observed_exit"
        return 2
    fi
    if [[ "$raw_output" != *"$ci_marker"* ]]; then
        safe_error ci evidence_marker PRESENT MISSING
        return 2
    fi
    if [[ "$raw_output" != *"$ci_attempt_diff"* ]]; then
        safe_error ci RCM201 PRESENT MISSING
        return 2
    fi
    if [[ "$raw_output" != *"$ci_data_source_diff"* ]]; then
        safe_error ci RCM202 PRESENT MISSING
        return 2
    fi
    if [[ "$raw_output" != *'BUILD FAILED'* ]]; then
        safe_error ci build_failure PRESENT MISSING
        return 2
    fi

    cat <<EOF
[INTENTIONAL CI GATE]
approvedAttempts        1
candidateAttempts       2
verificationStatus      POLICY_VIOLATION
blockingCodes           [RCM201,RCM202]
$ci_attempt_diff
$ci_data_source_diff
BUILD FAILED (intentional)
ci_exit                 1
EOF
    return 1
}

run_standalone_demo() {
    local raw_output
    local observed_exit

    printf '%s\n' \
        'video_phase=standalone status=RUNNING child_output=WITHHELD_UNTIL_VERIFIED'
    set +e
    raw_output="$("$script_directory/verify-standalone-consumer.sh" 2>&1)"
    observed_exit=$?
    set -e

    if [[ "$observed_exit" -ne 0 ]]; then
        safe_error standalone child_exit 0 "$observed_exit"
        return 2
    fi
    if [[ "$raw_output" != *"$standalone_marker"* ]]; then
        safe_error standalone evidence_marker PRESENT MISSING
        return 2
    fi

    cat <<'EOF'
[PUBLISHED-JAR CONSUMER]
artifact                 published-jar
spi                      auto-discovered
environment              MySQL 8.4.11 | ShardingSphere-JDBC 5.5.3
observedAttempts         1
observedDataSources      1 (name withheld from screen)
privacy                  screen output allowlisted
standalone_demo_exit     0
EOF
}

case "${1:-}" in
    mysql)
        run_mysql_demo
        ;;
    fingerprint)
        run_fingerprint_demo
        ;;
    ci)
        run_ci_demo
        ;;
    standalone)
        run_standalone_demo
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage >&2
        exit 64
        ;;
esac
