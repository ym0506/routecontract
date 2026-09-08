# Real Maven legacy resolver acceptance for A-27

Status: [45/45 actual Maven cases verified against reviewed source `86a0be5`](evidence/legacy-resolver-86a0be5-2026-09-08.md).
The [earlier 4e06694 execution](evidence/legacy-resolver-4e06694-2026-09-08.md) and
[initial staging evidence](evidence/maven-legacy-resolver-2026-09-08.md) are preserved separately.
This work implements the Maven
portion of A-27 with the existing pinned legacy registry and reviewed 0.2
staging. It corrects the ADR's selected-only Enforcer assumption; shared input
pins, production code, public releases, and A-28 SQL/classpath acceptance remain unchanged.

Maven's ordinary version declarations are soft requirements. Nearest definition
wins, and equal-depth conflicts use declaration order; Maven does not generally
select the highest declared version. A dependency version such as `[0.1.3]` is a
hard singleton requirement. See the primary
[dependency mediation guide](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
and [POM version requirement specification](https://maven.apache.org/pom.html#Dependency_Version_Requirement_Specification).

Pinned Enforcer 3.6.3 `BannedDependencies` traverses a verbose graph, including
conflict-loser nodes, rather than only the selected runtime tree; see its
[rule implementation](https://github.com/apache/maven-enforcer/blob/enforcer-3.6.3/enforcer-rules/src/main/java/org/apache/maven/enforcer/rules/dependency/BannedDependenciesBase.java#L99-L129).
Consequently, selecting current bytes through ordinary mediation does not by
itself make the legacy ban pass. The actual selected graph and Enforcer outcome
must be recorded separately; the fixture must not weaken the ban to manufacture
a successful ordinary-mediation result.

The fixture must preserve those semantics. It must not declare duplicate direct
dependencies for the same Maven conflict id, fabricate a `strictly` feature, or
count a generated request-time exception as dependency resolution. Two small
generated fixture POMs carry distinct legacy/current requests to the same depth;
their bytes, request versions, and order are retained as fixture inputs. These
carrier POMs contain no substitute RouteContract classes or implementation.

For each genuinely distributed legacy version (`0.1.0`, `0.1.2`, `0.1.3`, and
`0.1.0-rc2`), the required real Maven 3.9.14 / Java 17 cases are:

1. Legacy alone resolves its exact published JAR (legacy-lane control).
2. Legacy + current core, both orders, selects the real graph and then fails
   through consumer-owned Enforcer `BannedDependencies` for the selected legacy
   coordinate. Repeat with legacy + current adapter552 in both orders.
3. Equal-depth bare same-GA legacy/current requests, both orders: old-first
   selects the legacy artifact and the asserted 0.2 consumer's Enforcer rejects
   it; current-first selects exact current adapter553 plus transitive core JARs,
   with no legacy JAR on the resolved classpath, but the verbose legacy node is
   still expected to be rejected by pinned Enforcer. Both actual outcomes must
   be demonstrated. A passing asserted 0.2 consumer may never contain old bytes.
4. Explicit consumer `dependencyManagement` pins that GA to 0.2.0. Both carrier
   declaration orders must resolve only exact current adapter553/core bytes.
   This is a separately labeled managed-selection case, not automatic
   highest-version mediation.
5. Both carriers use incompatible hard singleton ranges `[legacy]` and
   `[0.2.0]`, in both orders, with no dependency-management override. Maven's
   actual dependency resolver must report an unsatisfiable version conflict;
   an Enforcer ban or missing artifact is not a substitute.

A latest-legacy + core control omits the ownership policy and must actually
resolve both JARs. Its matching enabled cases must fail through Enforcer.
The complete matrix therefore contains 45 cases. No-Enforcer controls are
explicit separate consumers; no `enforcer.skip` escape is used.

Every case starts with an absent Maven dependency cache outside the checkout,
uses explicit local/global settings and strict checksum handling, and retains
its actual POMs, settings, commands, logs, selected tree and classpath where
resolution succeeds. First-party payloads come exclusively from a loopback
repository populated with verified legacy/staged bytes. Third-party payloads
come from Maven Central through the existing controlled mirror. Generated
carrier POMs are scoped to the fixture repository,
have recorded hashes, and refer only to the supplied real coordinates.
Hard singleton ranges need no generated available-version metadata in Maven
3.9.14: its [version-range resolver](https://github.com/apache/maven/blob/maven-3.9.14/maven-resolver-provider/src/main/java/org/apache/maven/repository/internal/DefaultVersionRangeResolver.java#L140-L144)
uses the identical lower/upper bound directly.

The fixture may cache third-party Central HTTP responses once at the repository
side for the duration of a run. This cache starts absent, imports no `.m2` or
foreign repository, uses the existing certificate-validating Central-only
transport, retains URL/status/SHA-256/size provenance, checks cached bytes again,
and keeps the existing 100 MiB body bound. Cache payloads and metadata use
descriptor-relative no-follow access; symlinked cache entries and directories
are rejected. `responseDeliveries` counts verified response objects returned by
the cache, while `cacheHits` counts only reuse after the original download.
Neither count proves completed HTTP delivery or Maven consumption; consumed
artifacts require separate graph/classpath/hash/origin evidence. The initial download deadline is
bounded at 600 seconds to accommodate the observed slow native compression JAR
download and is checked again after every body read, including EOF. The shared
mirror source remains unchanged. Each Maven dependency
cache must still start absent and retrieve its own files through HTTP with
strict checksums; repository response reuse is explicitly reported.

The runner must bind all nine staged payloads to the reviewed receipt and check
that their recorded source has unchanged production/publication inputs, including
LICENSE/NOTICE, relative to the test checkout. The shared legacy loader checks
the real published JAR/POM bytes, the public 0.1.3 `.module`, and class/service
layout. It keeps tag-only 0.1.1/RC1 separate from executable inputs. Maven itself
consumes POM/JAR metadata; a checked `.module` is not Maven resolver evidence.

Every materialized first-party JAR and consumed POM must match its input pin and
controlled-repository marker. Successful current selection must exclude legacy
JARs from the resolved classpath. Negative Enforcer cases must retain their
real selected graph first and identify `BannedDependencies` plus the legacy
coordinate from the selected or verbose conflict-loser node. Strict failures must identify both hard version requirements
and the actual Maven resolver conflict, with no missing-artifact/checksum/network
failure accepted as coverage. Recheck fixture/repository inputs at completion;
partial runs cannot mark the full Maven matrix verified.

Retain exact commands/tool versions and per-case report/log hashes. Public
evidence is minimized and contains no private local paths. This is resolver and
JAR materialization evidence; no SQL, business success, runtime collision guard,
Maven Central publication of 0.2, or external adoption follows from it.
