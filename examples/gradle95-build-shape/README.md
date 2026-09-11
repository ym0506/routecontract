# Gradle 9.5.1 dual-JDK build-shape check

This RouteContract-owned fixture verifies one narrow compatibility boundary: Gradle 9.5.1 runs
on JDK 21, the ordinary target sources and tests select JDK 21 while emitting Java 17 bytecode,
and an isolated RouteContract pilot source set compiles and runs on JDK 17. The verifier repeats
that boundary with the exact Spring Boot dependency-management BOM `3.5.16` and `4.1.0`. For each
cell it proves that enabling the pilot does not change the ordinary target runtime graph and that
RouteContract remains absent from that graph.

The pilot resolves
`io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2` only from an explicit,
absolute local Maven repository populated from the checksummed `v0.1.2` GitHub Release assets. It
verifies the exact coordinate JAR and POM paths and SHA-256 values before loading the API class.
Its configurations do not extend the target test configurations, so either Spring Boot BOM cannot
select the pilot's exact JUnit 5 dependencies.

This is dependency-management and JVM build-shape evidence only. It does **not** run Spring Boot,
does not add or validate a Spring Boot starter, does not exercise an external repository, and does
not establish adoption. It creates no baseline or candidate and runs no representative database
operation. The JSON receipt records those negative claim boundaries explicitly.

Run from the RouteContract repository root with preinstalled JDK 21 and JDK 17 homes:

```bash
JAVA_HOME=/absolute/jdk-21 \
  ./scripts/verify-gradle95-build-shape.sh \
    --release-assets-dir /absolute/path/to/exact-v0.1.2-release-assets \
    --jdk17-home /absolute/jdk-17 \
    --receipt-output /absolute/path/to/an/absent/receipt.json
```

`routecontractPilot` accepts only `true` or `false`; `routecontractBootBom` accepts only `3.5.16`
or `4.1.0`; and `routecontractRepository` is rejected unless the pilot is explicitly enabled.
Those fail-closed property boundaries are part of the verifier.
