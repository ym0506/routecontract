#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  echo 'Usage: run-final-supply-chain-scan.sh --revision <40-lowercase-hex>' >&2
}

fail() {
  echo "supply-chain scan failed: $*" >&2
  exit 1
}

if [[ $# -ne 2 || "$1" != '--revision' || ! "$2" =~ ^[0-9a-f]{40}$ ]]; then
  usage
  exit 2
fi

scan_revision="$2"
script_source="${BASH_SOURCE[0]}"
if [[ -L "${script_source}" || ! -f "${script_source}" ]]; then
  fail 'runner must be invoked from a regular non-symlink file'
fi
script_directory="$(cd -P "$(dirname "${script_source}")" && pwd)"
repository_root="$(cd -P "${script_directory}/.." && pwd)"
cd "${repository_root}"

scanner_lock='security/osv-scanner.lock.json'
scanner_config='security/osv-scanner.toml'
official_validator_lock='security/cyclonedx-cli.lock.json'
policy_file='security/supply-chain-policy.json'
checker='scripts/verify-supply-chain-policy.py'
official_validator='scripts/validate-official-cyclonedx.py'
verified_sbom='build/reports/verified-sbom/aggregate/bom.json'
verified_sbom_xml='build/reports/verified-sbom/aggregate/bom.xml'
core_sbom='build/reports/verified-sbom/routecontract-core/bom.json'
core_sbom_xml='build/reports/verified-sbom/routecontract-core/bom.xml'
core_pom='routecontract-core/build/publications/mavenJava/pom-default.xml'
core_lock='routecontract-core/gradle.lockfile'
published_sbom='build/reports/verified-sbom/routecontract-shardingsphere-5.5/bom.json'
published_sbom_xml='build/reports/verified-sbom/routecontract-shardingsphere-5.5/bom.xml'
adapter552_sbom='build/reports/verified-sbom/routecontract-shardingsphere-5.5.2/bom.json'
adapter552_sbom_xml='build/reports/verified-sbom/routecontract-shardingsphere-5.5.2/bom.xml'
example_sbom='build/reports/verified-sbom/mysql-example/bom.json'
example_sbom_xml='build/reports/verified-sbom/mysql-example/bom.xml'
mysql552_sbom='build/reports/verified-sbom/mysql-5.5.2-example/bom.json'
mysql552_sbom_xml='build/reports/verified-sbom/mysql-5.5.2-example/bom.xml'
published_pom='routecontract-shardingsphere-5.5/build/publications/mavenJava/pom-default.xml'
published_lock='routecontract-shardingsphere-5.5/gradle.lockfile'
adapter552_pom='routecontract-shardingsphere-5.5.2/build/publications/mavenJava/pom-default.xml'
adapter552_lock='routecontract-shardingsphere-5.5.2/gradle.lockfile'
gradle_wrapper='gradlew'
report_directory='build/reports/security'
tool_directory='build/security-tools/final-scan'
inventory_file="${report_directory}/derived/gradle.lockfile"
raw_scan_file="${report_directory}/osv-raw.json"
evidence_file="${report_directory}/supply-chain-evidence.json"

# Every argument is a repository-relative path. Existing components are checked
# with lstat so mkdir, chmod, curl, scanner execution, and final writes never
# accept an ignored build/cache path redirected through a symbolic link.
guard_internal_paths() {
  python3 - "${repository_root}" "$@" <<'PY'
import os
from pathlib import Path
import stat
import sys

root = Path(sys.argv[1])
for value in sys.argv[2:]:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise SystemExit(f"supply-chain scan failed: unsafe repository path: {value}")
    current = root
    for part in relative.parts:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        except OSError as error:
            raise SystemExit(
                f"supply-chain scan failed: cannot inspect repository path {value}: {error}"
            )
        if stat.S_ISLNK(mode):
            raise SystemExit(
                f"supply-chain scan failed: repository path contains a symbolic link: {current}"
            )
PY
}

require_regular_file() {
  local path="$1"
  guard_internal_paths "${path}"
  if [[ ! -f "${path}" || -L "${path}" ]]; then
    fail "required input is not a regular non-symlink file: ${path}"
  fi
}

verify_clean_revision() {
  local repository_top
  local resolved_commit
  local status_output

  repository_top="$(cd -P "$(git rev-parse --show-toplevel)" && pwd)"
  [[ "${repository_top}" == "${repository_root}" ]] \
    || fail 'runner is not executing at the Git worktree root'
  resolved_commit="$(git rev-parse --verify "${scan_revision}^{commit}")"
  [[ "${resolved_commit}" == "${scan_revision}" ]] \
    || fail 'requested revision does not resolve to the exact commit'
  [[ "$(git rev-parse --verify HEAD)" == "${scan_revision}" ]] \
    || fail 'requested revision is not the checked-out HEAD'
  status_output="$(git status --porcelain=v1 --untracked-files=all --ignore-submodules=none)"
  [[ -z "${status_output}" ]] \
    || fail 'worktree is dirty; commit or remove tracked, staged, and untracked changes'
  git diff-files --quiet --ignore-submodules=none -- \
    || fail 'worktree files differ from the index'
  git diff-index --quiet --cached "${scan_revision}" -- \
    || fail 'index differs from the requested revision'
}

verify_clean_revision
source_tree="$(git rev-parse --verify "${scan_revision}^{tree}")"
[[ "${source_tree}" =~ ^[0-9a-f]{40}$ ]] \
  || fail 'requested revision tree is not a 40-character lowercase object ID'

guard_internal_paths \
  'scripts' \
  'security' \
  "${script_source#${repository_root}/}" \
  "${scanner_lock}" \
  "${scanner_config}" \
  "${official_validator_lock}" \
  "${policy_file}" \
  "${checker}" \
  "${official_validator}" \
  "${gradle_wrapper}" \
  'build' \
  'build/reports' \
  "${report_directory}" \
  "${report_directory}/derived" \
  'build/security-tools' \
  "${tool_directory}" \
  "${verified_sbom}" \
  "${verified_sbom_xml}" \
  "${core_sbom}" \
  "${core_sbom_xml}" \
  "${core_pom}" \
  "${core_lock}" \
  "${published_sbom}" \
  "${published_sbom_xml}" \
  "${adapter552_sbom}" \
  "${adapter552_sbom_xml}" \
  "${example_sbom}" \
  "${example_sbom_xml}" \
  "${mysql552_sbom}" \
  "${mysql552_sbom_xml}" \
  "${published_pom}" \
  "${published_lock}" \
  "${adapter552_pom}" \
  "${adapter552_lock}"
require_regular_file "${scanner_lock}"
require_regular_file "${scanner_config}"
[[ ! -s "${scanner_config}" ]] \
  || fail 'the explicit OSV scanner configuration must be exactly empty'
require_regular_file "${official_validator_lock}"
require_regular_file "${policy_file}"
require_regular_file "${checker}"
require_regular_file "${official_validator}"
require_regular_file "${gradle_wrapper}"
require_regular_file "${core_lock}"
require_regular_file "${published_lock}"
require_regular_file "${adapter552_lock}"

# Final evidence is immutable for a single checkout. Reject it before touching
# any generation output so a rerun cannot silently erase or replace evidence.
if [[ -e "${raw_scan_file}" || -L "${raw_scan_file}" \
   || -e "${evidence_file}" || -L "${evidence_file}" ]]; then
  fail 'prior final scan output exists; archive or remove it explicitly before a new run'
fi

python3 "${checker}" preflight \
  --scanner-lock "${scanner_lock}" \
  --scanner-config "${scanner_config}" \
  --policy "${policy_file}"

# Remove only the fifteen enumerated derived inputs, after proving none can escape
# the worktree through a symlink. Gradle must recreate every one from this exact
# revision. A repository-wide clean would unnecessarily destroy unrelated or
# prior local evidence and would make the pre-existing-evidence check illusory.
for generated_input in \
    "${verified_sbom}" \
    "${verified_sbom_xml}" \
    "${core_sbom}" \
    "${core_sbom_xml}" \
    "${core_pom}" \
    "${published_sbom}" \
    "${published_sbom_xml}" \
    "${adapter552_sbom}" \
    "${adapter552_sbom_xml}" \
    "${example_sbom}" \
    "${example_sbom_xml}" \
    "${mysql552_sbom}" \
    "${mysql552_sbom_xml}" \
    "${published_pom}" \
    "${adapter552_pom}"; do
  guard_internal_paths "${generated_input}"
  if [[ -e "${generated_input}" || -L "${generated_input}" ]]; then
    [[ -f "${generated_input}" && ! -L "${generated_input}" ]] \
      || fail "prior generated input is not a regular non-symlink file: ${generated_input}"
    rm -f -- "${generated_input}"
  fi
done

# Generate every audited inventory from this exact clean revision. Accepting a
# caller-provided SBOM would allow evidence from an older dependency graph to be
# rebound to this revision.
./gradlew --no-daemon --no-build-cache \
  --rerun-tasks \
  prepareVerifiedSbom \
  :routecontract-core:generatePomFileForMavenJavaPublication \
  :routecontract-shardingsphere-5.5:generatePomFileForMavenJavaPublication \
  :routecontract-shardingsphere-5.5.2:generatePomFileForMavenJavaPublication
verify_clean_revision
[[ "$(git rev-parse --verify "${scan_revision}^{tree}")" == "${source_tree}" ]] \
  || fail 'requested revision tree changed while generating the audited inventory'
require_regular_file "${verified_sbom}"
require_regular_file "${verified_sbom_xml}"
require_regular_file "${core_sbom}"
require_regular_file "${core_sbom_xml}"
require_regular_file "${core_pom}"
require_regular_file "${published_sbom}"
require_regular_file "${published_sbom_xml}"
require_regular_file "${adapter552_sbom}"
require_regular_file "${adapter552_sbom_xml}"
require_regular_file "${example_sbom}"
require_regular_file "${example_sbom_xml}"
require_regular_file "${mysql552_sbom}"
require_regular_file "${mysql552_sbom_xml}"
require_regular_file "${published_pom}"
require_regular_file "${adapter552_pom}"

mkdir -p "${tool_directory}" "${report_directory}/derived"
guard_internal_paths \
  "${tool_directory}" \
  "${report_directory}" \
  "${report_directory}/derived"
[[ -d "${tool_directory}" && ! -L "${tool_directory}" ]] \
  || fail 'scanner tool directory is not a regular directory'
[[ -d "${report_directory}/derived" && ! -L "${report_directory}/derived" ]] \
  || fail 'scanner report directory is not a regular directory'
chmod 0700 "${tool_directory}" "${report_directory}" "${report_directory}/derived"

# Copy the freshly generated inputs into a new mode-restricted directory and
# consume only those copies. Keep both the source outputs and the copies in the
# later fingerprint so ordinary mutation of either side cannot be hidden while
# the external scanner or checker runs.
audit_input_directory="$(mktemp -d "${report_directory}/derived/audited-inputs.XXXXXXXX")"
guard_internal_paths "${audit_input_directory}"
[[ -d "${audit_input_directory}" && ! -L "${audit_input_directory}" ]] \
  || fail 'mktemp did not create a regular audited-input directory'
chmod 0700 "${audit_input_directory}"
audited_sbom="${audit_input_directory}/aggregate-bom.json"
audited_sbom_xml="${audit_input_directory}/aggregate-bom.xml"
audited_core_sbom="${audit_input_directory}/core-bom.json"
audited_core_sbom_xml="${audit_input_directory}/core-bom.xml"
audited_core_pom="${audit_input_directory}/core-pom.xml"
audited_core_lock="${audit_input_directory}/core-gradle.lockfile"
audited_published_sbom="${audit_input_directory}/published-bom.json"
audited_published_sbom_xml="${audit_input_directory}/published-bom.xml"
audited_adapter552_sbom="${audit_input_directory}/adapter552-bom.json"
audited_adapter552_sbom_xml="${audit_input_directory}/adapter552-bom.xml"
audited_example_sbom="${audit_input_directory}/example-bom.json"
audited_example_sbom_xml="${audit_input_directory}/example-bom.xml"
audited_mysql552_sbom="${audit_input_directory}/mysql552-bom.json"
audited_mysql552_sbom_xml="${audit_input_directory}/mysql552-bom.xml"
audited_published_pom="${audit_input_directory}/published-pom.xml"
audited_published_lock="${audit_input_directory}/published-gradle.lockfile"
audited_adapter552_pom="${audit_input_directory}/adapter552-pom.xml"
audited_adapter552_lock="${audit_input_directory}/adapter552-gradle.lockfile"
raw_scan_temporary=''
evidence_temporary=''

cleanup() {
  rm -f -- "${raw_scan_temporary:-}" "${evidence_temporary:-}"
  for private_input in \
      "${audited_sbom}" \
      "${audited_sbom_xml}" \
      "${audited_core_sbom}" \
      "${audited_core_sbom_xml}" \
      "${audited_core_pom}" \
      "${audited_core_lock}" \
      "${audited_published_sbom}" \
      "${audited_published_sbom_xml}" \
      "${audited_adapter552_sbom}" \
      "${audited_adapter552_sbom_xml}" \
      "${audited_example_sbom}" \
      "${audited_example_sbom_xml}" \
      "${audited_mysql552_sbom}" \
      "${audited_mysql552_sbom_xml}" \
      "${audited_published_pom}" \
      "${audited_published_lock}" \
      "${audited_adapter552_pom}" \
      "${audited_adapter552_lock}" \
      "${inventory_file}"; do
    if [[ -e "${private_input}" && ! -L "${private_input}" ]]; then
      chmod 0600 "${private_input}" 2>/dev/null || true
      rm -f -- "${private_input}" 2>/dev/null || true
    fi
  done
  rmdir -- "${audit_input_directory}" 2>/dev/null || true
}
trap cleanup EXIT

copy_audited_input() {
  local source="$1"
  local destination="$2"
  require_regular_file "${source}"
  guard_internal_paths "${destination}"
  [[ ! -e "${destination}" && ! -L "${destination}" ]] \
    || fail "audited-input destination already exists: ${destination}"
  cp -- "${source}" "${destination}"
  require_regular_file "${destination}"
  chmod 0400 "${destination}"
  cmp -s -- "${source}" "${destination}" \
    || fail "audited-input copy differs from generated source: ${source}"
}

fingerprint_audited_inputs() {
  python3 - "$@" <<'PY'
import hashlib
import os
from pathlib import Path
import stat
import sys

digest = hashlib.sha256()
for value in sys.argv[1:]:
    path = Path(value)
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise SystemExit(f"cannot inspect pinned audit input {value}: {error}")
    if not stat.S_ISREG(metadata.st_mode):
        raise SystemExit(f"pinned audit input is not a regular file: {value}")
    encoded_path = value.encode("utf-8")
    content = path.read_bytes()
    digest.update(len(encoded_path).to_bytes(8, "big"))
    digest.update(encoded_path)
    digest.update(len(content).to_bytes(8, "big"))
    digest.update(content)
print(digest.hexdigest())
PY
}

copy_audited_input "${verified_sbom}" "${audited_sbom}"
copy_audited_input "${verified_sbom_xml}" "${audited_sbom_xml}"
copy_audited_input "${core_sbom}" "${audited_core_sbom}"
copy_audited_input "${core_sbom_xml}" "${audited_core_sbom_xml}"
copy_audited_input "${core_pom}" "${audited_core_pom}"
copy_audited_input "${core_lock}" "${audited_core_lock}"
copy_audited_input "${published_sbom}" "${audited_published_sbom}"
copy_audited_input "${published_sbom_xml}" "${audited_published_sbom_xml}"
copy_audited_input "${adapter552_sbom}" "${audited_adapter552_sbom}"
copy_audited_input "${adapter552_sbom_xml}" "${audited_adapter552_sbom_xml}"
copy_audited_input "${example_sbom}" "${audited_example_sbom}"
copy_audited_input "${example_sbom_xml}" "${audited_example_sbom_xml}"
copy_audited_input "${mysql552_sbom}" "${audited_mysql552_sbom}"
copy_audited_input "${mysql552_sbom_xml}" "${audited_mysql552_sbom_xml}"
copy_audited_input "${published_pom}" "${audited_published_pom}"
copy_audited_input "${published_lock}" "${audited_published_lock}"
copy_audited_input "${adapter552_pom}" "${audited_adapter552_pom}"
copy_audited_input "${adapter552_lock}" "${audited_adapter552_lock}"

# Bind the exact private copies used below to the freshly generated originals.
# Keep this baseline for the entire scan instead of accepting a later mutation
# as a new fingerprint after the official validator has returned.
source_and_copy_paths=(
  "${verified_sbom}"
  "${verified_sbom_xml}"
  "${core_sbom}"
  "${core_sbom_xml}"
  "${core_pom}"
  "${core_lock}"
  "${published_sbom}"
  "${published_sbom_xml}"
  "${adapter552_sbom}"
  "${adapter552_sbom_xml}"
  "${example_sbom}"
  "${example_sbom_xml}"
  "${mysql552_sbom}"
  "${mysql552_sbom_xml}"
  "${published_pom}"
  "${published_lock}"
  "${adapter552_pom}"
  "${adapter552_lock}"
  "${audited_sbom}"
  "${audited_sbom_xml}"
  "${audited_core_sbom}"
  "${audited_core_sbom_xml}"
  "${audited_core_pom}"
  "${audited_core_lock}"
  "${audited_published_sbom}"
  "${audited_published_sbom_xml}"
  "${audited_adapter552_sbom}"
  "${audited_adapter552_sbom_xml}"
  "${audited_example_sbom}"
  "${audited_example_sbom_xml}"
  "${audited_mysql552_sbom}"
  "${audited_mysql552_sbom_xml}"
  "${audited_published_pom}"
  "${audited_published_lock}"
  "${audited_adapter552_pom}"
  "${audited_adapter552_lock}"
)

verify_copy_parity() {
  cmp -s -- "${verified_sbom}" "${audited_sbom}" \
    || fail 'audited aggregate JSON differs from its generated source'
  cmp -s -- "${verified_sbom_xml}" "${audited_sbom_xml}" \
    || fail 'audited aggregate XML differs from its generated source'
  cmp -s -- "${core_sbom}" "${audited_core_sbom}" \
    || fail 'audited core JSON differs from its generated source'
  cmp -s -- "${core_sbom_xml}" "${audited_core_sbom_xml}" \
    || fail 'audited core XML differs from its generated source'
  cmp -s -- "${core_pom}" "${audited_core_pom}" \
    || fail 'audited core POM differs from its generated source'
  cmp -s -- "${core_lock}" "${audited_core_lock}" \
    || fail 'audited core lock differs from its tracked source'
  cmp -s -- "${published_sbom}" "${audited_published_sbom}" \
    || fail 'audited published JSON differs from its generated source'
  cmp -s -- "${published_sbom_xml}" "${audited_published_sbom_xml}" \
    || fail 'audited published XML differs from its generated source'
  cmp -s -- "${adapter552_sbom}" "${audited_adapter552_sbom}" \
    || fail 'audited adapter552 JSON differs from its generated source'
  cmp -s -- "${adapter552_sbom_xml}" "${audited_adapter552_sbom_xml}" \
    || fail 'audited adapter552 XML differs from its generated source'
  cmp -s -- "${example_sbom}" "${audited_example_sbom}" \
    || fail 'audited example JSON differs from its generated source'
  cmp -s -- "${example_sbom_xml}" "${audited_example_sbom_xml}" \
    || fail 'audited example XML differs from its generated source'
  cmp -s -- "${mysql552_sbom}" "${audited_mysql552_sbom}" \
    || fail 'audited mysql552 JSON differs from its generated source'
  cmp -s -- "${mysql552_sbom_xml}" "${audited_mysql552_sbom_xml}" \
    || fail 'audited mysql552 XML differs from its generated source'
  cmp -s -- "${published_pom}" "${audited_published_pom}" \
    || fail 'audited published POM differs from its generated source'
  cmp -s -- "${published_lock}" "${audited_published_lock}" \
    || fail 'audited published lock differs from its tracked source'
  cmp -s -- "${adapter552_pom}" "${audited_adapter552_pom}" \
    || fail 'audited adapter552 POM differs from its generated source'
  cmp -s -- "${adapter552_lock}" "${audited_adapter552_lock}" \
    || fail 'audited adapter552 lock differs from its tracked source'
}

verify_copy_parity
source_and_copy_fingerprint="$(fingerprint_audited_inputs "${source_and_copy_paths[@]}")"
[[ "${source_and_copy_fingerprint}" =~ ^[0-9a-f]{64}$ ]] \
  || fail 'cannot fingerprint generated sources and audited copies'

verify_source_and_copy_inputs() {
  local current_fingerprint
  verify_copy_parity
  current_fingerprint="$(fingerprint_audited_inputs "${source_and_copy_paths[@]}")" \
    || fail 'a generated source or audited copy is missing or invalid'
  [[ "${current_fingerprint}" == "${source_and_copy_fingerprint}" ]] \
    || fail 'a generated source or audited copy changed after it was bound'
}
verify_source_and_copy_inputs

# Validate the exact twelve private SBOM copies consumed by the inventory and
# policy checker. The wrapper also fingerprints those inputs around every
# official CLI subprocess; the runner retains its independent source/copy
# baseline before and after the complete invocation.
python3 "${official_validator}" \
  --input-root "${repository_root}/${audit_input_directory}" \
  --pair aggregate 'aggregate-bom.json' 'aggregate-bom.xml' \
  --pair core 'core-bom.json' 'core-bom.xml' \
  --pair adapter553 'published-bom.json' 'published-bom.xml' \
  --pair adapter552 'adapter552-bom.json' 'adapter552-bom.xml' \
  --pair mysql553 'example-bom.json' 'example-bom.xml' \
  --pair mysql552 'mysql552-bom.json' 'mysql552-bom.xml'
verify_source_and_copy_inputs
verify_clean_revision
[[ "$(git rev-parse --verify "${scan_revision}^{tree}")" == "${source_tree}" ]] \
  || fail 'requested revision tree changed during official CycloneDX validation'

case "$(uname -s):$(uname -m)" in
  Darwin:arm64)
    scanner_platform='darwin-arm64'
    ;;
  Linux:x86_64)
    scanner_platform='linux-x86_64'
    ;;
  *)
    fail 'only Darwin arm64 and Linux x86_64 are pinned'
    ;;
esac

lock_values="$({
  python3 - "${scanner_lock}" "${scanner_platform}" <<'PY'
import json
from pathlib import Path
import sys

lock = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
asset = lock["scanner"]["platforms"][sys.argv[2]]
database = lock["database"]
values = (
    lock["scanner"]["version"],
    lock["scanner"]["commit"],
    lock["scanner"]["scalibrVersion"],
    asset["url"],
    asset["sha256"],
    str(asset["size"]),
    database["url"],
    database["sha256"],
    str(database["size"]),
)
if any(not isinstance(value, str) or "\t" in value or "\n" in value for value in values):
    raise SystemExit("scanner lock contains unsafe values")
print("\t".join(values))
PY
})"
IFS=$'\t' read -r scanner_version scanner_commit scalibr_version \
  scanner_url scanner_sha scanner_size database_url database_sha database_size <<<"${lock_values}"

scanner_binary="${tool_directory}/osv-scanner-${scanner_platform}-${scanner_sha}"
database_cache_root="${tool_directory}/database-${database_sha}"
database_file="${database_cache_root}/osv-scalibr/Maven/all.zip"
guard_internal_paths "${scanner_binary}" "${database_cache_root}" "${database_file}"

download_verified() {
  local url="$1"
  local expected_sha="$2"
  local destination="$3"
  local expected_size="${4:-}"
  local temporary_file

  guard_internal_paths "${destination}"
  if [[ -e "${destination}" || -L "${destination}" ]]; then
    if [[ ! -f "${destination}" || -L "${destination}" ]]; then
      fail "cached path is not a regular non-symlink file: ${destination}"
    fi
    if [[ "$(shasum -a 256 "${destination}" | awk '{print $1}')" != "${expected_sha}" ]]; then
      fail "cached file checksum mismatch: $(basename "${destination}")"
    fi
    if [[ -n "${expected_size}" \
       && "$(wc -c < "${destination}" | tr -d ' ')" != "${expected_size}" ]]; then
      fail "cached file size mismatch: $(basename "${destination}")"
    fi
    return 0
  fi

  mkdir -p "$(dirname "${destination}")"
  guard_internal_paths "$(dirname "${destination}")" "${destination}"
  temporary_file="$(mktemp "${tool_directory}/download.XXXXXXXX")"
  if [[ ! -f "${temporary_file}" || -L "${temporary_file}" ]]; then
    fail 'mktemp did not create a regular download file'
  fi
  if ! curl --fail --location --retry 3 --silent --show-error \
      --output "${temporary_file}" -- "${url}"; then
    rm -f "${temporary_file}"
    return 1
  fi
  if [[ ! -f "${temporary_file}" || -L "${temporary_file}" \
     || "$(shasum -a 256 "${temporary_file}" | awk '{print $1}')" != "${expected_sha}" ]]; then
    rm -f "${temporary_file}"
    fail "downloaded checksum mismatch: $(basename "${destination}")"
  fi
  if [[ -n "${expected_size}" \
     && "$(wc -c < "${temporary_file}" | tr -d ' ')" != "${expected_size}" ]]; then
    rm -f "${temporary_file}"
    fail "downloaded size mismatch: $(basename "${destination}")"
  fi
  if [[ -e "${destination}" || -L "${destination}" ]]; then
    rm -f "${temporary_file}"
    fail "download destination appeared during verification: ${destination}"
  fi
  mv "${temporary_file}" "${destination}"
  guard_internal_paths "${destination}"
  [[ -f "${destination}" && ! -L "${destination}" ]] \
    || fail "download destination is not a regular file: ${destination}"
}

verify_pinned_file() {
  local path="$1"
  local expected_sha="$2"
  local expected_size="$3"
  local label="$4"
  require_regular_file "${path}"
  [[ "$(wc -c < "${path}" | tr -d ' ')" == "${expected_size}" ]] \
    || fail "${label} size changed"
  [[ "$(shasum -a 256 "${path}" | awk '{print $1}')" == "${expected_sha}" ]] \
    || fail "${label} checksum changed"
}

download_verified "${scanner_url}" "${scanner_sha}" "${scanner_binary}" "${scanner_size}"
guard_internal_paths "${scanner_binary}"
chmod 0755 "${scanner_binary}"
[[ "$(shasum -a 256 "${scanner_binary}" | awk '{print $1}')" == "${scanner_sha}" ]] \
  || fail 'scanner checksum changed before execution'
download_verified "${database_url}" "${database_sha}" "${database_file}" "${database_size}"

scanner_version_output="$("${scanner_binary}" --version 2>&1)"
grep -Fqx "osv-scanner version: ${scanner_version}" <<<"${scanner_version_output}"
grep -Fqx "osv-scalibr version: ${scalibr_version}" <<<"${scanner_version_output}"
grep -Fqx "commit: ${scanner_commit}" <<<"${scanner_version_output}"
verify_pinned_file "${scanner_binary}" "${scanner_sha}" "${scanner_size}" 'scanner binary'
verify_pinned_file "${database_file}" "${database_sha}" "${database_size}" 'scanner database'

guard_internal_paths "${inventory_file}"
if [[ -e "${inventory_file}" || -L "${inventory_file}" ]]; then
  [[ -f "${inventory_file}" && ! -L "${inventory_file}" ]] \
    || fail "prior derived inventory is not a regular non-symlink file: ${inventory_file}"
  rm -f -- "${inventory_file}"
fi

python3 "${checker}" inventory \
  --sbom "${audited_sbom}" \
  --sbom-xml "${audited_sbom_xml}" \
  --core-sbom "${audited_core_sbom}" \
  --core-sbom-xml "${audited_core_sbom_xml}" \
  --core-pom "${audited_core_pom}" \
  --core-lock "${audited_core_lock}" \
  --published-sbom "${audited_published_sbom}" \
  --published-sbom-xml "${audited_published_sbom_xml}" \
  --adapter552-sbom "${audited_adapter552_sbom}" \
  --adapter552-sbom-xml "${audited_adapter552_sbom_xml}" \
  --example-sbom "${audited_example_sbom}" \
  --example-sbom-xml "${audited_example_sbom_xml}" \
  --mysql552-sbom "${audited_mysql552_sbom}" \
  --mysql552-sbom-xml "${audited_mysql552_sbom_xml}" \
  --published-pom "${audited_published_pom}" \
  --published-lock "${audited_published_lock}" \
  --adapter552-pom "${audited_adapter552_pom}" \
  --adapter552-lock "${audited_adapter552_lock}" \
  --policy "${policy_file}" \
  --output "${inventory_file}"
require_regular_file "${inventory_file}"
chmod 0400 "${inventory_file}"
verify_source_and_copy_inputs
inventory_fingerprint="$(fingerprint_audited_inputs "${inventory_file}")"
[[ "${inventory_fingerprint}" =~ ^[0-9a-f]{64}$ ]] \
  || fail 'cannot fingerprint the derived scanner inventory'

verify_audited_inputs() {
  local current_inventory_fingerprint
  verify_source_and_copy_inputs
  current_inventory_fingerprint="$(fingerprint_audited_inputs "${inventory_file}")" \
    || fail 'the derived scanner inventory is missing or invalid'
  [[ "${current_inventory_fingerprint}" == "${inventory_fingerprint}" ]] \
    || fail 'the derived scanner inventory changed during the scan'
}

raw_scan_temporary="$(mktemp "${report_directory}/osv-raw.XXXXXXXX.json")"
evidence_temporary="$(mktemp "${report_directory}/supply-chain-evidence.XXXXXXXX.json")"
[[ -f "${raw_scan_temporary}" && ! -L "${raw_scan_temporary}" \
   && -f "${evidence_temporary}" && ! -L "${evidence_temporary}" ]] \
  || fail 'mktemp did not create regular report files'

verify_clean_revision
python3 "${checker}" preflight \
  --scanner-lock "${scanner_lock}" \
  --scanner-config "${scanner_config}" \
  --policy "${policy_file}"
verify_pinned_file "${scanner_binary}" "${scanner_sha}" "${scanner_size}" 'scanner binary'
verify_pinned_file "${database_file}" "${database_sha}" "${database_size}" 'scanner database'
verify_audited_inputs
set +e
OSV_SCALIBR_LOCAL_DB_CACHE_DIRECTORY="${repository_root}/${database_cache_root}" \
  "${scanner_binary}" scan source \
  --offline \
  --offline-vulnerabilities \
  --all-packages \
  --config "${repository_root}/${scanner_config}" \
  --format=json \
  --output-file "${raw_scan_temporary}" \
  --lockfile "${inventory_file}"
scanner_exit=$?
set -e
verify_pinned_file "${scanner_binary}" "${scanner_sha}" "${scanner_size}" 'scanner binary'
verify_pinned_file "${database_file}" "${database_sha}" "${database_size}" 'scanner database'
verify_audited_inputs
python3 "${checker}" preflight \
  --scanner-lock "${scanner_lock}" \
  --scanner-config "${scanner_config}" \
  --policy "${policy_file}"
verify_clean_revision
if [[ ${scanner_exit} -ne 0 && ${scanner_exit} -ne 1 ]]; then
  fail "OSV-Scanner exited ${scanner_exit}"
fi

python3 "${checker}" verify \
  --sbom "${audited_sbom}" \
  --sbom-xml "${audited_sbom_xml}" \
  --core-sbom "${audited_core_sbom}" \
  --core-sbom-xml "${audited_core_sbom_xml}" \
  --core-pom "${audited_core_pom}" \
  --core-lock "${audited_core_lock}" \
  --published-sbom "${audited_published_sbom}" \
  --published-sbom-xml "${audited_published_sbom_xml}" \
  --adapter552-sbom "${audited_adapter552_sbom}" \
  --adapter552-sbom-xml "${audited_adapter552_sbom_xml}" \
  --example-sbom "${audited_example_sbom}" \
  --example-sbom-xml "${audited_example_sbom_xml}" \
  --mysql552-sbom "${audited_mysql552_sbom}" \
  --mysql552-sbom-xml "${audited_mysql552_sbom_xml}" \
  --published-pom "${audited_published_pom}" \
  --published-lock "${audited_published_lock}" \
  --adapter552-pom "${audited_adapter552_pom}" \
  --adapter552-lock "${audited_adapter552_lock}" \
  --policy "${policy_file}" \
  --scanner-lock "${scanner_lock}" \
  --scanner-config "${scanner_config}" \
  --scanner-platform "${scanner_platform}" \
  --inventory "${inventory_file}" \
  --raw-scan "${raw_scan_temporary}" \
  --revision "${scan_revision}" \
  --source-tree "${source_tree}" \
  --output "${evidence_temporary}"
verify_audited_inputs

# Recheck after every external program has finished. The final files are not
# published if HEAD, the index, or any non-ignored worktree content changed.
verify_clean_revision
[[ "$(git rev-parse --verify "${scan_revision}^{tree}")" == "${source_tree}" ]] \
  || fail 'requested revision tree changed during the scan'
guard_internal_paths \
  "${raw_scan_temporary}" \
  "${evidence_temporary}" \
  "${raw_scan_file}" \
  "${evidence_file}"
if [[ -e "${raw_scan_file}" || -L "${raw_scan_file}" \
   || -e "${evidence_file}" || -L "${evidence_file}" ]]; then
  fail 'final scan output destination appeared during the scan'
fi
mv "${raw_scan_temporary}" "${raw_scan_file}"
raw_scan_temporary=''
mv "${evidence_temporary}" "${evidence_file}"
evidence_temporary=''
cleanup
trap - EXIT
echo "sanitized supply-chain evidence: ${evidence_file}"
