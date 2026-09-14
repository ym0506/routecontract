# OSV fixed release branches

The pinned scan can report several valid fixed release branches for one Maven
package. Parsing those branches must preserve every value so policy reports all
findings. It must not choose an upgrade, compare ecosystem versions as SemVer,
or accept a vulnerable dependency. Every finding remains forbidden, including a
finding with no same-package fixed release.

Acceptance, specified before the correction:

- Collect fixed release strings from every affected record whose ecosystem is
  exactly `Maven` and whose package name matches the scanned package exactly.
  Deduplicate and sort lexically only for deterministic serialization.
- Emit `fixedVersions` as an array. `ECOSYSTEM` and `SEMVER` fixed events describe
  releases; `GIT` fixed events describe commits and stay in the retained raw OSV
  evidence, outside this release array. Retain object/array validation, reject
  blank or non-string fixed values and missing/unknown range types, and reject
  advisories without an exact affected-package match.
- Preserve the protobuf branches `3.25.5`, `4.27.5`, `4.28.2` and the httpcore5
  branches `5.4.3`, `5.5-beta2`. Preserve the Commons Lang 2 finding with an empty
  release array; another affected package's Lang 3 fix is not its fix.
- Keep all six observed package/advisory pairs and report all their minimized
  metadata in the existing forbidden-policy error. No finding may produce
  successful release evidence. Existing success evidence keeps `findings: []`.
- Keep exact scanner inventory equality and group/advisory identity checks.

The regression fixture minimizes the six finding-bearing package entries from
the separately retained local scan: only package identity, group IDs, advisory
ID/severity, and exact affected package/range records remain. The complete raw
scan SHA-256 is
`7a44ad08038b3321072a75a0b8a83af70b83d4d598321da0adac55de218bd0fe`.
Its pinned Maven database generation is `1788523358826365`, SHA-256
`bc2546e64b47af11125e1c35a07ef66afa28716de2cf48f28bf50aa66a0fcf7d`;
scanner 2.5.0 is the existing policy-pinned scanner. These are local diagnostic
inputs, not downloaded CI raw scan evidence.

The [OSV schema](https://ossf.github.io/osv-schema/#affectedrangesevents-field)
allows multiple affected ranges and distinguishes release ranges from Git
commit ranges. This correction uses the scanner's existing finding decision;
the displayed branch list is metadata, not a compatibility recommendation.

Reproduce the focused acceptance without Java builds or another scan:

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_osv_fixed_branches.py' -v
python3 -B -m unittest discover -s scripts/tests -p 'test_verify_supply_chain_policy.py' -v
```

Verification: `verified - unit`, Python 3.12.14; 13 focused regressions and 127
existing policy tests pass. The already retained 318-package raw scan parses to
all six findings and is rejected with their complete minimized metadata. This
parser correction does not remediate any of the six dependencies, complete CI
unsigned preparation, or change the publication hold.
