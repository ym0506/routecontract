# Runtime lifecycle consumer

This fixture exercises only ADR A-11, A-12 and A-13 against supplied reviewed local staged
artifacts. See [the finite acceptance plan](../../docs/runtime-lifecycle-acceptance.md).

The runner copies the existing `staged-split-artifact-consumer` build, settings, exact-runtime
lock and strict verification metadata, replaces its test sources with these probes, and applies
`runtime-evidence.gradle`. It compiles that independent graph once per exact runtime. It does not
run that fixture's original JUnit suite or build RouteContract production code.

`RuntimeLifecycleProbe` is a JDK-only launcher. Its process classpath contains only compiled
fixture classes. It loads the frozen dependency graph in a child of the JDK platform loader, so
the host cannot silently supply a RouteContract or ShardingSphere class. Each case gets its own
fresh JVM. Actual ShardingSphere discovery establishes the provider cache; the fixture neither
constructs hooks directly nor replaces provider collections.

A-12 uses a disposable pinned MySQL container and separately checks the business row, delegated
physical JDBC executions and hook-reported physical attempt. A-11 and A-13 must fail before the
application action and return no snapshot. A-13 records automatic discovery and capture failures
separately because the current capture entry checks loader identity before service discovery.

Source, receipt, all nine staged payloads, resolved classpaths, compiled probe classes and raw
case results remain bound before and after the run. A setup error or partial run cannot establish
all six acceptance cases. This fixture is not evidence of public 0.2 availability, arbitrary
plugin-container support or independent adoption.
