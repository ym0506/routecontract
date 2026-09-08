# Ten bounded resolver and current-API checks

Verified locally on Java 17 against reviewed unsigned 0.2.0 payloads from
`86a0be5d2e444f3b73925122fa448d9d1a324edd`. The coverage combines **four retained Gradle
cases, four retained Maven dual-adapter cases and two final runtime guards from
three distinct executions**. The [minimized JSON](dual-resolver-boundaries-86a0be5-2026-09-08.json)
binds each case to its original run, inputs and preserved failure history.

| Boundary | Exact versions and orders | Completed |
| --- | --- | ---: |
| Native Gradle capability rejection | Gradle 8.14.4; 5.5.2/5.5.3; both adapter declaration orders | 4 |
| Native Maven Enforcer rejection | Maven 3.9.14 / Enforcer 3.6.3; 5.5.2/5.5.3; both orders | 4 |
| Current-API runtime rejection before action | Separate Java 17 processes; both coherent opposite runtimes; Enforcer absent | 2 |

Each runtime guard compiled against the current API, verified the complete actual
opposite-runtime JAR set and its three loaded anchors, then checked that the
selected adapter's database ABI resource was absent from both the actual loader
and every classpath entry. The 5.5.2 adapter observed 26 ShardingSphere 5.5.3 JARs;
the 5.5.3 adapter observed 48 ShardingSphere 5.5.2 JARs. Both calls rejected before
application action entry, with the exact resource-specific unsupported-runtime
reason and no cause or suppressed exception. All inspected file hashes were
checked before and after capture.

All six historical failed invocations remain failed. In particular, the old
runtime fixture rejected a valid fail-closed reason because its whole-message
expectation was too narrow. Its retained failure is separate from the two new
guard passes with explicit resource-absence evidence. There was no single
successful ten-case invocation.

This check executed **zero SQL/MySQL operations and zero JUnit tests**. Gradle
rejected graphs and Enforcer rejected subtrees are not executable-runtime claims.
A-24 positives and independent security/release gates remain separate; this result
does not establish publication, external adoption, or other JDK/platform support.

The private aggregate audit is bound by SHA-256
`ae47fdf2d7b9460386d184e6c42241231b5bd75899ea4e88432ae77cab59263b`. Receipt, individual result, input and original summary hashes
are recorded in the minimized JSON; local filesystem paths and cache inventories
are omitted.
