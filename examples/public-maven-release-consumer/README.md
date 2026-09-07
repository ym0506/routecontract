# Public single-coordinate Maven consumer

This fixture verifies the published single-coordinate `0.1.x` line, starting at
`0.1.3`, with Apache Maven 3.9.14, Java 17 and Apache ShardingSphere-JDBC 5.5.3.
It is an internal distribution acceptance fixture, not external adoption evidence.

Run from the checkout after preparing and reviewing the exact three-payload
receipt:

```sh
python3 -I scripts/verify-public-maven-release-consumer.py \
  --receipt /absolute/path/reviewed-receipt.json \
  --evidence-directory /absolute/path/new-maven-evidence \
  --java-home /absolute/path/jdk-17
```

The evidence directory must be new and outside the checkout. Docker must be
available for the unchanged shared MySQL fixture. The wrapper copies that fixture
from `examples/public-gradle-release-consumer/src` into a new consumer outside the
checkout. It uses an absent Maven local repository, a private temporary home and
explicit fresh user/global settings. Every repository and plugin repository is
mirrored to anonymous `https://repo.maven.apache.org/maven2`; Maven's native
transport is selected with redirect following disabled.

Acceptance order is deliberate: resolve dependencies without compiling or running
tests; validate the entire selected ShardingSphere graph is exactly 5.5.3 and the
sole first-party dependency is the reviewed release; compare its resolved JAR and
POM bytes and repository markers with the receipt; then compile and run the three
real-MySQL tests. Recheck hashes, graph and receipt before recording success. The
Java fixture also checks the JAR from which RouteContract classes actually loaded,
the exact returned business row, approved-manifest MATCH and the 1-to-2 physical
JDBC execution attempt regression, including CLI exit codes and report output.

Maven does not consume Gradle `.module` metadata. The receipt validates its expected
hash, but this Maven run proves consumption of the JAR and POM only. Independent
public readback must verify all three published payloads. Expected receipt hashes
are reviewed expected bytes, not independent publisher authentication. Missing
public artifacts fail the run; there is no fallback to local staging or success
summary on failure.

Successful evidence is labelled `verified - MySQL` and
`verified - ShardingSphere-JDBC 5.5.3`. Preparation tests alone are
`verified - unit`; public execution remains `unverified` until a successful run.
The supported claim is SQLExecutionHook-reported physical JDBC execution attempts,
not a complete route plan, enclosing transaction commit or business success.
Retained raw logs and reports are local evidence and may contain SQL or JDBC URLs;
inspect and sanitize them before public sharing.
