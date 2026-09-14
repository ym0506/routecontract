# Published inventory from merged compile and runtime graphs

The pinned SBOM producer combines `compileClasspath` and `runtimeClasspath` dependency
graphs. It does not preserve the configuration that supplied each edge. In the retained
5.5.2 adapter graph, both Jackson annotation versions are reachable: `2.18.9` is locked
only for compile, while `2.21` belongs to runtime. `j2objc-annotations:2.8` is also
compile-only. Their component test properties are false and cannot distinguish these
configurations.

The retained read-only diagnosis has SHA-256
`d2d70cf87aeb25952f7716a9c03b8c79f1e00c36d1422cf0f1d71b56ae313fcf`.

Use the exact `compileClasspath` and `runtimeClasspath` memberships from one strictly
parsed lock file. First account for every third-party node reachable from the unchanged
POM dependencies against their union, including descendants of compile-only nodes.
Reject unexplained coordinates and entries locked only for tests. Then exclude only
compile-minus-runtime nodes during the runtime traversal. The resulting third-party
runtime closure must still equal the complete runtime lock set.

Acceptance uses a small composed fixture containing both Jackson annotation versions,
Guava's compile-only annotation dependency, and the existing direct core compile edge:

1. Preserve every merged SBOM component and return the exact runtime lock set.
2. Reject an unlocked reachable coordinate, including one below a compile-only node.
3. Reject a reachable addition present only in test configurations.
4. Reject a missing runtime node or edge, including a runtime node reachable only through
   a compile-only node that the runtime traversal excludes.
5. Preserve the exact direct POM dependency and first-party compile/third-party runtime
   scope checks.

Run `python3 -B -m unittest discover -s scripts/tests -p test_published_configuration_inventory.py -v`
before and after the production change. A passing focused result is `verified - unit`.
Configuration membership comes from the lock; this result does not establish the runtime
origin of every merged graph edge. The retained separate diagnosis identifies the excluded
coordinates. Rechecking copied SBOMs is not a Java rebuild, complete source scan, CI result
or release approval. Existing license and core acceptance bundles remain unchanged.

Local verification on 2026-09-08, Python 3.12.14: the merged-configuration success case
failed before the change. Afterward, all six configuration tests, eight core-project tests
and 127 existing policy tests passed. The same twelve finalized SBOM documents passed the
complete six-role inventory, containing 318 Maven packages. All thirty retained raw/finalized
SBOM, POM and lock inputs kept their recorded hashes.

The separate input audit retains the excluded 5.5.2 compile-only coordinates
`com.fasterxml.jackson.core:jackson-annotations:2.18.9` and
`com.google.j2objc:j2objc-annotations:2.8`, with their exact graph references and lock entries.
Their SBOM/license records remain present and unchanged. They remain part of the aggregate
scan inventory; only the module runtime traversal excludes them using configuration-specific
lock membership. No Java artifacts were rebuilt, and the clean-source OSV scan and CI run
remain unverified until the reviewed fix is integrated and executed there.
