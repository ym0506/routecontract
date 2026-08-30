#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: verify-gradle95-build-shape.sh \
  --release-assets-dir ABSOLUTE_DIRECTORY \
  --jdk17-home ABSOLUTE_JDK_HOME \
  --receipt-output ABSOLUTE_ABSENT_JSON_PATH
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

sha256_file() {
    python3 -I - "$1" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
with path.open("rb") as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
print(digest.hexdigest())
PY
}

if [[ "$#" -ne 6 ]]; then
    usage >&2
    exit 64
fi
release_assets_directory=""
jdk17_input=""
receipt_output=""
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --release-assets-dir)
            release_assets_directory="$2"
            shift 2
            ;;
        --jdk17-home)
            jdk17_input="$2"
            shift 2
            ;;
        --receipt-output)
            receipt_output="$2"
            shift 2
            ;;
        *)
            usage >&2
            exit 64
            ;;
    esac
done

for value in "$release_assets_directory" "$jdk17_input" "$receipt_output"; do
    [[ "$value" == /* ]] || die "every path argument must be absolute"
done
test -d "$release_assets_directory" && test ! -L "$release_assets_directory" \
    || die "release assets directory must be a real directory"
test -d "$jdk17_input" || die "JDK 17 home must exist"
test ! -e "$receipt_output" && test ! -L "$receipt_output" \
    || die "receipt output must start absent"
receipt_parent="$(dirname -- "$receipt_output")"
test -d "$receipt_parent" && test ! -L "$receipt_parent" \
    || die "receipt parent must be a real directory"
test -n "${JAVA_HOME:-}" && [[ "$JAVA_HOME" == /* ]] \
    || die "JAVA_HOME must identify the explicit JDK 21 Gradle runtime"

for command in git java python3 tar; do
    command -v "$command" >/dev/null 2>&1 \
        || die "required command is missing: $command"
done

script_path="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/$(basename -- "${BASH_SOURCE[0]}")"
repository_root="$(git -C "$(dirname -- "$script_path")/.." rev-parse --show-toplevel)"
repository_root="$(cd -- "$repository_root" && pwd -P)"
receipt_parent_real="$(cd -- "$receipt_parent" && pwd -P)"
receipt_output_real="$receipt_parent_real/$(basename -- "$receipt_output")"
case "$receipt_output_real" in
    "$repository_root"|"$repository_root"/*)
        die "receipt output must be outside the source repository"
        ;;
esac
fixture="$repository_root/examples/gradle95-build-shape"
installer="$repository_root/scripts/install-release-assets.py"
for path in \
    "$fixture/build.gradle.kts" \
    "$fixture/settings.gradle.kts" \
    "$fixture/gradlew" \
    "$fixture/gradle/wrapper/gradle-wrapper.jar" \
    "$fixture/gradle/wrapper/gradle-wrapper.properties" \
    "$installer"; do
    test -f "$path" && test ! -L "$path" \
        || die "required fixture file must be a regular non-symlink: $path"
done
test ! -e "$fixture/.gradle" || die "source fixture must not contain .gradle state"
test ! -e "$fixture/build" || die "source fixture must not contain build output"
source_status_before="$(git -C "$repository_root" status --porcelain=v1 \
    --untracked-files=all --ignore-submodules=none)"
test -z "$source_status_before" || die "source checkout must start clean"
source_revision="$(git -C "$repository_root" rev-parse HEAD)"
source_tree="$(git -C "$repository_root" rev-parse 'HEAD^{tree}')"

expected_wrapper_jar_sha256="497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7"
actual_wrapper_jar_sha256="$(sha256_file "$fixture/gradle/wrapper/gradle-wrapper.jar")"
test "$actual_wrapper_jar_sha256" = "$expected_wrapper_jar_sha256" \
    || die "Gradle 9.5.1 wrapper JAR SHA-256 changed"
python3 -I - "$fixture/gradle/wrapper/gradle-wrapper.properties" <<'PY'
import pathlib
import sys

expected = (
    "distributionBase=GRADLE_USER_HOME\n"
    "distributionPath=wrapper/dists\n"
    "distributionSha256Sum="
    "bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f\n"
    "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.5.1-bin.zip\n"
    "networkTimeout=10000\n"
    "retries=0\n"
    "retryBackOffMs=500\n"
    "validateDistributionUrl=true\n"
    "zipStoreBase=GRADLE_USER_HOME\n"
    "zipStorePath=wrapper/dists\n"
)
if pathlib.Path(sys.argv[1]).read_text(encoding="utf-8") != expected:
    raise SystemExit("Gradle 9.5.1 wrapper properties are not the exact reviewed bytes")
PY

runtime_jdk21="$(cd -- "$JAVA_HOME" && pwd -P)"
jdk17_home="$(cd -- "$jdk17_input" && pwd -P)"
test -x "$runtime_jdk21/bin/java" || die "JDK 21 java is not executable"
test -x "$jdk17_home/bin/java" || die "JDK 17 java is not executable"
runtime_version="$($runtime_jdk21/bin/java -XshowSettings:properties -version 2>&1 \
    | sed -n 's/^[[:space:]]*java.specification.version = //p')"
jdk17_version="$($jdk17_home/bin/java -XshowSettings:properties -version 2>&1 \
    | sed -n 's/^[[:space:]]*java.specification.version = //p')"
test "$runtime_version" = "21" || die "Gradle runtime must be JDK 21"
test "$jdk17_version" = "17" || die "pilot compiler/test home must be JDK 17"

temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/routecontract-gradle95-build-shape.XXXXXX")"
temporary_root="$(cd -- "$temporary_root" && pwd -P)"
cleanup() {
    case "$temporary_root" in
        */routecontract-gradle95-build-shape.*) rm -rf -- "$temporary_root" ;;
        *) printf 'Refusing to remove unexpected path: %s\n' "$temporary_root" >&2 ;;
    esac
}
trap cleanup EXIT INT TERM

local_repository="$temporary_root/local-maven"
python3 -I "$installer" \
    --release-assets-dir "$release_assets_directory" \
    --repository "$local_repository" \
    > "$temporary_root/install.log"
coordinate_root="$local_repository/io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.2"
artifact_jar="$coordinate_root/routecontract-shardingsphere-5.5-0.1.2.jar"
artifact_pom="$coordinate_root/routecontract-shardingsphere-5.5-0.1.2.pom"
test "$(sha256_file "$artifact_jar")" = \
    "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc" \
    || die "installed RouteContract JAR SHA-256 changed"
test "$(sha256_file "$artifact_pom")" = \
    "70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d" \
    || die "installed RouteContract POM SHA-256 changed"

toolchain_paths="$runtime_jdk21,$jdk17_home"

copy_fixture() {
    local destination="$1"
    mkdir "$destination"
    tar --exclude .gradle --exclude build -C "$fixture" -cf - . \
        | tar -C "$destination" -xf -
}

wrapper_seed_project="$temporary_root/wrapper-seed-project"
wrapper_seed_home="$temporary_root/wrapper-seed-home"
copy_fixture "$wrapper_seed_project"
test ! -e "$wrapper_seed_home" || die "wrapper seed home must start absent"
mkdir "$wrapper_seed_home"
env -i \
    "PATH=$runtime_jdk21/bin:$PATH" \
    "JAVA_HOME=$runtime_jdk21" \
    "HOME=$temporary_root" \
    "TMPDIR=$temporary_root" \
    "LC_ALL=C" \
    "GRADLE_USER_HOME=$wrapper_seed_home" \
    "$wrapper_seed_project/gradlew" --version \
    > "$temporary_root/wrapper-version.log" 2>&1
grep -Fxq 'Gradle 9.5.1' "$temporary_root/wrapper-version.log" \
    || die "checksum-pinned wrapper did not launch exact Gradle 9.5.1"
test -d "$wrapper_seed_home/wrapper/dists" \
    || die "wrapper seed did not materialize its isolated distribution"

case_gradle_home_count=0
case_gradle_homes_seen=""

run_gradle() {
    local project="$1"
    local log="$2"
    shift 2
    local project_cache="$project-cache"
    local case_home="$project-home"
    local case_tmp="$project-tmp"
    local case_gradle_home="$project-gradle-home"
    test ! -e "$project_cache" || die "project cache must start absent: $project"
    test ! -e "$case_home" || die "case HOME must start absent: $project"
    test ! -e "$case_tmp" || die "case TMPDIR must start absent: $project"
    test ! -e "$case_gradle_home" \
        || die "case GRADLE_USER_HOME must start absent: $project"
    case "$case_gradle_homes_seen" in
        *"|$case_gradle_home|"*) die "case GRADLE_USER_HOME was reused" ;;
    esac
    case_gradle_homes_seen="$case_gradle_homes_seen|$case_gradle_home|"
    case_gradle_home_count=$((case_gradle_home_count + 1))
    mkdir "$project_cache" "$case_home" "$case_tmp"
    mkdir "$case_gradle_home"
    cp -R "$wrapper_seed_home/wrapper" "$case_gradle_home/wrapper"
    env -i \
        "PATH=$runtime_jdk21/bin:$PATH" \
        "JAVA_HOME=$runtime_jdk21" \
        "HOME=$case_home" \
        "TMPDIR=$case_tmp" \
        "LC_ALL=C" \
        "GRADLE_USER_HOME=$case_gradle_home" \
        "$project/gradlew" \
        --no-daemon --no-build-cache --no-configuration-cache --no-watch-fs \
        --project-dir "$project" \
        --project-cache-dir "$project_cache" \
        -Dorg.gradle.java.installations.auto-detect=false \
        -Dorg.gradle.java.installations.auto-download=false \
        "-Dorg.gradle.java.installations.paths=$toolchain_paths" \
        "$@" > "$log" 2>&1
}

run_cell() {
    local bom="$1"
    local mode="$2"
    local name="boot-${bom}-${mode}"
    local project="$temporary_root/$name"
    local log="$temporary_root/$name.log"
    copy_fixture "$project"
    local arguments=(
        "-ProutecontractBootBom=$bom"
        clean test routeContractBuildShapeTargetGraph
    )
    if [[ "$mode" == "on" ]]; then
        arguments=(
            "-ProutecontractBootBom=$bom"
            -ProutecontractPilot=true
            "-ProutecontractRepository=$local_repository"
            clean test routeContractBuildShapeTargetGraph routeContractBuildShapePilot
        )
    fi
    run_gradle "$project" "$log" "${arguments[@]}"
    test "$(grep -c '^ROUTECONTRACT_BUILD_SHAPE_TARGET_GRAPH ' "$log")" = "1" \
        || die "$name did not emit one target graph marker"
    grep -Fq "bootBom=$bom" "$log" || die "$name did not bind its exact BOM"
    grep -Fq "routeContract=ABSENT" "$log" \
        || die "$name did not prove RouteContract absent from the target graph"
    if [[ "$bom" == "3.5.16" ]]; then
        grep -Fq "hikari=6.3.3 junit=5.12.2" "$log" \
            || die "$name selected the wrong Boot 3 dependency family"
    else
        grep -Fq "hikari=7.0.2 junit=6.0.3" "$log" \
            || die "$name selected the wrong Boot 4 dependency family"
    fi
    if [[ "$mode" == "on" ]]; then
        test "$(grep -c '^ROUTECONTRACT_BUILD_SHAPE_PILOT_GRAPH ' "$log")" = "1" \
            || die "$name did not emit one pilot graph marker"
        test "$(grep -c '^ROUTECONTRACT_BUILD_SHAPE_TOOLCHAINS ' "$log")" = "1" \
            || die "$name did not emit one toolchain marker"
        test "$(grep -c '^ROUTECONTRACT_BUILD_SHAPE_BYTECODE ' "$log")" = "1" \
            || die "$name did not emit one measured bytecode marker"
        grep -Fq 'mainClassMajor=61 pilotClassMajor=61' "$log" \
            || die "$name did not measure Java 17 class headers"
        report="$project/build/test-results/routeContractBuildShapePilot/TEST-io.github.ym0506.routecontract.examples.buildshape.RouteContractBuildShapePilotTest.xml"
        test -f "$report" || die "$name did not create its pilot JUnit report"
        grep -Fq "artifactOrigin=EXACT_LOCAL_RELEASE adoptionClaim=false externalTarget=false baselineApproved=false candidateChecked=false" "$report" \
            || die "$name did not preserve the runtime claim boundary"
    fi
    test -z "$(find "$project" -type f \( -name '*.candidate.json' -o -name '*.approved.json' \) -print -quit)" \
        || die "$name created a baseline or candidate"
}

run_rejected_case() {
    local name="$1"
    local expected="$2"
    shift 2
    local project="$temporary_root/rejected-$name"
    local log="$temporary_root/rejected-$name.log"
    copy_fixture "$project"
    set +e
    run_gradle "$project" "$log" "$@" help
    local status="$?"
    set -e
    test "$status" = "1" || die "$name must exit exactly 1 (actual $status)"
    grep -Fq "$expected" "$log" || die "$name did not emit the exact rejection"
}

run_rejected_case missing-bom \
    "Set routecontractBootBom to exactly 3.5.16 or 4.1.0"
run_rejected_case invalid-enable \
    "routecontractPilot must be exactly true or false" \
    -ProutecontractBootBom=3.5.16 -ProutecontractPilot=yes
run_rejected_case invalid-bom \
    "routecontractBootBom must be exactly 3.5.16 or 4.1.0" \
    -ProutecontractBootBom=3.5
run_rejected_case repository-while-off \
    "routecontractRepository is accepted only when routecontractPilot=true" \
    -ProutecontractBootBom=3.5.16 "-ProutecontractRepository=$local_repository"
run_rejected_case missing-repository \
    "Set the absolute routecontractRepository when routecontractPilot=true" \
    -ProutecontractBootBom=3.5.16 -ProutecontractPilot=true
run_rejected_case relative-repository \
    "routecontractRepository must be an absolute local directory" \
    -ProutecontractBootBom=3.5.16 \
    -ProutecontractPilot=true -ProutecontractRepository=relative-repository

run_cell 3.5.16 off
run_cell 3.5.16 on
run_cell 4.1.0 off
run_cell 4.1.0 on

target_3516_off="$(grep '^ROUTECONTRACT_BUILD_SHAPE_TARGET_GRAPH ' "$temporary_root/boot-3.5.16-off.log")"
target_3516_on="$(grep '^ROUTECONTRACT_BUILD_SHAPE_TARGET_GRAPH ' "$temporary_root/boot-3.5.16-on.log")"
target_410_off="$(grep '^ROUTECONTRACT_BUILD_SHAPE_TARGET_GRAPH ' "$temporary_root/boot-4.1.0-off.log")"
target_410_on="$(grep '^ROUTECONTRACT_BUILD_SHAPE_TARGET_GRAPH ' "$temporary_root/boot-4.1.0-on.log")"
test "$target_3516_off" = "$target_3516_on" \
    || die "target graph changed when the isolated pilot was enabled for Boot 3.5.16"
test "$target_410_off" = "$target_410_on" \
    || die "target graph changed when the isolated pilot was enabled for Boot 4.1.0"
pilot_3516="$(grep '^ROUTECONTRACT_BUILD_SHAPE_PILOT_GRAPH ' "$temporary_root/boot-3.5.16-on.log")"
pilot_410="$(grep '^ROUTECONTRACT_BUILD_SHAPE_PILOT_GRAPH ' "$temporary_root/boot-4.1.0-on.log")"
test "$pilot_3516" = "$pilot_410" \
    || die "pilot graph changed across Spring Boot BOM cells"
bytecode_3516="$(grep '^ROUTECONTRACT_BUILD_SHAPE_BYTECODE ' "$temporary_root/boot-3.5.16-on.log")"
bytecode_410="$(grep '^ROUTECONTRACT_BUILD_SHAPE_BYTECODE ' "$temporary_root/boot-4.1.0-on.log")"
test "$bytecode_3516" = "$bytecode_410" \
    || die "measured class headers changed across Spring Boot BOM cells"
main_class_major="$(printf '%s\n' "$bytecode_3516" \
    | sed -n 's/.* mainClassMajor=\([0-9][0-9]*\) .*/\1/p')"
pilot_class_major="$(printf '%s\n' "$bytecode_3516" \
    | sed -n 's/.* pilotClassMajor=\([0-9][0-9]*\)$/\1/p')"
test "$main_class_major" = "61" && test "$pilot_class_major" = "61" \
    || die "measured class headers are not Java 17 major 61"
test "$case_gradle_home_count" = "10" \
    || die "verifier did not use exactly ten unique case GRADLE_USER_HOME directories"

target_3516_sha="$(printf '%s\n' "$target_3516_off" | sed -n 's/.* sha256=\([0-9a-f]\{64\}\) .*/\1/p')"
target_410_sha="$(printf '%s\n' "$target_410_off" | sed -n 's/.* sha256=\([0-9a-f]\{64\}\) .*/\1/p')"
pilot_sha="$(printf '%s\n' "$pilot_3516" | sed -n 's/.* sha256=\([0-9a-f]\{64\}\) .*/\1/p')"
for digest in "$target_3516_sha" "$target_410_sha" "$pilot_sha"; do
    [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || die "graph marker has no exact SHA-256"
done

python3 -I - \
    "$receipt_output" "$source_revision" "$source_tree" \
    "$target_3516_sha" "$target_410_sha" "$pilot_sha" \
    "$main_class_major" "$pilot_class_major" <<'PY'
import json
import os
import pathlib
import sys

output = pathlib.Path(sys.argv[1])
receipt = {
    "schemaVersion": 1,
    "kind": "routecontract-gradle95-build-shape-receipt",
    "result": "PASS",
    "scope": "dependency-management-build-shape-only",
    "sourceRevision": sys.argv[2],
    "sourceTree": sys.argv[3],
    "sourceClean": True,
    "gradle": {
        "version": "9.5.1",
        "distributionSha256": "bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f",
        "wrapperJarSha256": "497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7",
        "runtimeJdkFeature": 21,
    },
    "toolchains": {
        "mainCompiler": 21,
        "mainBytecodeRelease": 17,
        "targetTestLauncher": 21,
        "pilotCompiler": 17,
        "pilotBytecodeRelease": 17,
        "pilotTestLauncher": 17,
        "measuredMainClassMajor": int(sys.argv[7]),
        "measuredPilotClassMajor": int(sys.argv[8]),
    },
    "bootBomCells": {
        "3.5.16": {"targetGraphSha256": sys.argv[4]},
        "4.1.0": {"targetGraphSha256": sys.argv[5]},
    },
    "pilotGraphSha256": sys.argv[6],
    "artifact": {
        "coordinate": "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2",
        "jarSha256": "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc",
        "pomSha256": "70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d",
        "origin": "exact-local-release-repository",
    },
    "targetGraphUnchangedWhenPilotEnabled": True,
    "routeContractAbsentFromTargetGraph": True,
    "isolation": {
        "caseGradleUserHomes": 10,
        "uniqueInitiallyAbsent": True,
        "dependencyCachesShared": False,
        "wrapperDistributionSeedOnly": True,
    },
    "externalTarget": False,
    "externalRepositoryExecuted": False,
    "adoptionClaim": False,
    "springBootRuntimeCompatibilityClaim": False,
    "springBootStarterCompatibilityClaim": False,
    "representativeDatabaseOperationExecuted": False,
    "baselineApproved": False,
    "candidateChecked": False,
}
payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
descriptor = os.open(output, flags, 0o600)
with os.fdopen(descriptor, "wb") as stream:
    stream.write(payload)
PY

receipt_sha256="$(sha256_file "$receipt_output")"
source_status_after="$(git -C "$repository_root" status --porcelain=v1 \
    --untracked-files=all --ignore-submodules=none)"
test -z "$source_status_after" \
    || die "build-shape verifier mutated the clean source checkout"
printf '%s\n' \
    "ROUTECONTRACT_GRADLE95_BUILD_SHAPE_VERIFY result=PASS cells=2 " \
    "gradleRuntime=21 pilotRuntime=17 adoptionClaim=false externalTarget=false " \
    "wrapperDistributionSha256=bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f " \
    "wrapperJarSha256=497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7 " \
    "receiptSha256=$receipt_sha256"
