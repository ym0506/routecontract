#!/usr/bin/env bash
set +x
set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$script_directory/.." && pwd)"

mysql_marker='ROUTECONTRACT_MANIFEST_DEMO businessResult=UNCHANGED observedPhysicalAttempts=1->2 verificationStatus=POLICY_VIOLATION blockingCodes=[RCM201,RCM202] privacy=MINIMIZED'
fingerprint_marker='ROUTECONTRACT_FINGERPRINT_DRIFT_DEMO businessResult=UNCHANGED observedPhysicalAttempts=1->1 observedDataSourceAliases=[orders-odd]->[orders-odd] fingerprintMultiset=CHANGED parameterTypeShape=[Long]->[Long,Long] verificationStatus=DRIFT blockingCodes=[RCM301,RCM302] privacy=MINIMIZED'
ci_marker='ROUTECONTRACT_FILE_CI_DEMO approvedAttempts=1 candidateAttempts=2 status=POLICY_VIOLATION blockingCodes=[RCM201,RCM202]'
ci_attempt_diff='RCM201 BLOCKING ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2'
ci_data_source_diff='RCM202 BLOCKING DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2'
standalone_marker='ROUTECONTRACT_STANDALONE artifact=published-jar spi=auto-discovered mysql=8.4.11 shardingsphere=5.5.3 observedPhysicalAttempts=1 observedDataSourceNames=[ds_0]'

usage() {
    cat <<'EOF'
Usage: ./scripts/video-demo-session.sh [--final-recording] <mysql|fingerprint|ci|standalone>

  mysql        Run the real-MySQL 1 -> 2 manifest regression; exit 0 on verified evidence.
  fingerprint  Run the real-MySQL same-budget fingerprint drift; exit 0 on verified evidence.
  ci           Run the file-based intentional-red gate; exit 1 only on the expected failure.
  standalone   Verify the published JAR consumer and SPI discovery; exit 0 on verified evidence.

The mysql, fingerprint, and ci modes emit only exact, privacy-reviewed evidence
lines extracted from child output; verified_child_exit records the checked exit.
Raw child-process output is withheld in every mode.
An evidence or exit-code mismatch returns 2 and must be debugged off-camera.

Final recording must add --final-recording and provide all four values below
from the independently sealed publication record, never by deriving them from
the checkout being recorded:

  ROUTECONTRACT_FINAL_COMMIT  exact lowercase 40-character commit SHA
  ROUTECONTRACT_FINAL_TREE    exact lowercase 40-character tree SHA
  ROUTECONTRACT_FINAL_ORIGIN  canonical https://github.com/<owner>/<repository>
  ROUTECONTRACT_FINAL_TAG     annotated stable vMAJOR.MINOR.PATCH tag

That mode fails closed unless the script is in the expected repository root,
HEAD and its tree match, origin matches, the annotated tag peels to HEAD, and
the tracked/untracked worktree is clean. Ordinary one-argument modes remain
local rehearsal modes and make no final-revision claim.
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

verify_final_recording_checkout() {
    local expected_commit="${ROUTECONTRACT_FINAL_COMMIT:-}"
    local expected_tree="${ROUTECONTRACT_FINAL_TREE:-}"
    local expected_origin="${ROUTECONTRACT_FINAL_ORIGIN:-}"
    local expected_tag="${ROUTECONTRACT_FINAL_TAG:-}"
    local discovered_root
    local canonical_repository_root
    local canonical_discovered_root
    local actual_commit
    local actual_tree
    local actual_origin
    local normalized_origin
    local worktree_status
    local tag_type
    local tagged_commit

    if [[ ! "$expected_commit" =~ ^[0-9a-f]{40}$ ]]; then
        safe_error recording_preflight expected_commit 40_LOWERCASE_HEX MISSING_OR_INVALID
        return 2
    fi
    if [[ ! "$expected_tree" =~ ^[0-9a-f]{40}$ ]]; then
        safe_error recording_preflight expected_tree 40_LOWERCASE_HEX MISSING_OR_INVALID
        return 2
    fi
    if [[ ! "$expected_origin" =~ ^https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9_.-]+$ ]] \
        || [[ "$expected_origin" == *.git ]]; then
        safe_error recording_preflight expected_origin CANONICAL_GITHUB_HTTPS_URL MISSING_OR_INVALID
        return 2
    fi
    if [[ ! "$expected_tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        safe_error recording_preflight expected_tag STABLE_SEMVER_TAG MISSING_OR_INVALID
        return 2
    fi

    if ! discovered_root="$(git -C "$repository_root" rev-parse --show-toplevel 2>/dev/null)"; then
        safe_error recording_preflight repository_root GIT_WORKTREE MISMATCH
        return 2
    fi
    canonical_repository_root="$(cd -- "$repository_root" && pwd -P)"
    canonical_discovered_root="$(cd -- "$discovered_root" && pwd -P)"
    if [[ "$canonical_discovered_root" != "$canonical_repository_root" ]]; then
        safe_error recording_preflight repository_root SCRIPT_REPOSITORY_ROOT MISMATCH
        return 2
    fi

    if ! actual_commit="$(git -C "$repository_root" rev-parse --verify 'HEAD^{commit}' 2>/dev/null)" \
        || [[ "$actual_commit" != "$expected_commit" ]]; then
        safe_error recording_preflight head_commit EXPECTED_FINAL_COMMIT MISMATCH
        return 2
    fi
    if ! actual_tree="$(git -C "$repository_root" rev-parse --verify 'HEAD^{tree}' 2>/dev/null)" \
        || [[ "$actual_tree" != "$expected_tree" ]]; then
        safe_error recording_preflight head_tree EXPECTED_FINAL_TREE MISMATCH
        return 2
    fi
    if ! actual_origin="$(
        git -C "$repository_root" config --local --no-includes --get-all remote.origin.url \
            2>/dev/null
    )" || [[ "$actual_origin" == *$'\n'* ]]; then
        safe_error recording_preflight origin EXPECTED_CANONICAL_ORIGIN MISMATCH
        return 2
    fi
    normalized_origin="${actual_origin%.git}"
    if [[ "$normalized_origin" != "$expected_origin" ]]; then
        safe_error recording_preflight origin EXPECTED_CANONICAL_ORIGIN MISMATCH
        return 2
    fi
    if ! tag_type="$(git -C "$repository_root" cat-file -t "refs/tags/$expected_tag" 2>/dev/null)" \
        || [[ "$tag_type" != tag ]]; then
        safe_error recording_preflight annotated_tag ANNOTATED_STABLE_TAG MISMATCH
        return 2
    fi
    if ! tagged_commit="$(git -C "$repository_root" rev-parse --verify "refs/tags/$expected_tag^{commit}" 2>/dev/null)" \
        || [[ "$tagged_commit" != "$expected_commit" ]]; then
        safe_error recording_preflight tag_commit EXPECTED_FINAL_COMMIT MISMATCH
        return 2
    fi
    if ! worktree_status="$(git -C "$repository_root" status --porcelain=v1 --untracked-files=all 2>/dev/null)"; then
        safe_error recording_preflight clean_worktree CLEAN MISMATCH
        return 2
    fi
    if [[ -n "$worktree_status" ]]; then
        safe_error recording_preflight clean_worktree CLEAN DIRTY
        return 2
    fi

    printf '%s\n' 'video_recording_preflight status=VERIFIED'
}

extract_unique_trimmed_line() {
    local raw_output="$1"
    local expected="$2"
    local line
    local trimmed
    local exact_line=''
    local indented_line=''
    local exact_count=0
    local indented_count=0

    while IFS= read -r line || [[ -n "$line" ]]; do
        trimmed="${line#"${line%%[![:space:]]*}"}"
        if [[ "$line" == "$expected" ]]; then
            exact_line="$line"
            exact_count=$((exact_count + 1))
        elif [[ "$trimmed" == "$expected" ]]; then
            indented_line="$line"
            indented_count=$((indented_count + 1))
        fi
    done <<<"$raw_output"

    if [[ "$exact_count" -eq 1 ]]; then
        printf '%s\n' "$exact_line"
        return 0
    fi
    if [[ "$exact_count" -eq 0 && "$indented_count" -eq 1 ]]; then
        printf '%s\n' "$indented_line"
        return 0
    fi
    return 1
}

extract_unique_build_failure_line() {
    local raw_output="$1"
    local line
    local trimmed
    local matched_line=''
    local match_count=0
    local duration_piece='[0-9]+([.][0-9]+)?(ms|s|m|h)'

    while IFS= read -r line || [[ -n "$line" ]]; do
        trimmed="${line#"${line%%[![:space:]]*}"}"
        trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
        if [[ $trimmed =~ ^BUILD\ FAILED\ in\ ${duration_piece}(\ ${duration_piece})*$ ]]; then
            matched_line="$trimmed"
            match_count=$((match_count + 1))
        fi
    done <<<"$raw_output"

    if [[ "$match_count" -ne 1 ]]; then
        return 1
    fi
    printf '%s\n' "$matched_line"
}

run_mysql_demo() {
    local raw_output
    local observed_exit
    local extracted_marker

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
    if ! extracted_marker="$(extract_unique_trimmed_line "$raw_output" "$mysql_marker")"; then
        safe_error mysql unique_evidence_marker 1 MISMATCH
        return 2
    fi

    printf '%s\n' "$extracted_marker"
    printf 'verified_child_exit     %s\n' "$observed_exit"
}

run_fingerprint_demo() {
    local raw_output
    local observed_exit
    local extracted_marker
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
    if ! extracted_marker="$(extract_unique_trimmed_line "$raw_output" "$fingerprint_marker")"; then
        safe_error fingerprint unique_evidence_marker 1 MISMATCH
        return 2
    fi

    printf '%s\n' "$extracted_marker"
    printf 'verified_child_exit     %s\n' "$observed_exit"
}

run_ci_demo() {
    local raw_output
    local observed_exit
    local extracted_marker
    local extracted_attempt_diff
    local extracted_data_source_diff
    local extracted_build_failure

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
    if ! extracted_marker="$(extract_unique_trimmed_line "$raw_output" "$ci_marker")"; then
        safe_error ci unique_evidence_marker 1 MISMATCH
        return 2
    fi
    if ! extracted_attempt_diff="$(extract_unique_trimmed_line "$raw_output" "- $ci_attempt_diff")"; then
        safe_error ci unique_RCM201_line 1 MISMATCH
        return 2
    fi
    if ! extracted_data_source_diff="$(extract_unique_trimmed_line "$raw_output" "- $ci_data_source_diff")"; then
        safe_error ci unique_RCM202_line 1 MISMATCH
        return 2
    fi
    if ! extracted_build_failure="$(extract_unique_build_failure_line "$raw_output")"; then
        safe_error ci unique_build_failure_line 1 MISMATCH
        return 2
    fi

    printf '%s\n' \
        "$extracted_marker" \
        "$extracted_attempt_diff" \
        "$extracted_data_source_diff" \
        "$extracted_build_failure"
    printf 'verified_child_exit     %s\n' "$observed_exit"
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
privacy                  raw child output withheld | actual data-source name withheld
standalone_demo_exit     0
EOF
}

final_recording=false
if [[ "${1:-}" == --final-recording ]]; then
    final_recording=true
    shift
fi

if [[ "$#" -ne 1 ]]; then
    usage >&2
    exit 64
fi

if [[ "$final_recording" == true ]]; then
    if ! verify_final_recording_checkout; then
        exit 2
    fi
fi

case "$1" in
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
