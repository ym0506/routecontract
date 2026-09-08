# Gradle A-24 staged consumer result

**28/28 cases passed**, independently audited on macOS with Gradle 8.14.4,
Java 17.0.15, MySQL 8.4.11 and Testcontainers 1.21.4. This verifies the Gradle
portion against reviewed unsigned RouteContract 0.2.0 bytes.

| DSL | Exact ShardingSphere-JDBC | Cases | Actual MySQL JUnit tests |
| --- | --- | ---: | ---: |
| Groovy | 5.5.2 | 7/7 | 6 |
| Groovy | 5.5.3 | 7/7 | 6 |
| Kotlin | 5.5.2 | 7/7 | 6 |
| Kotlin | 5.5.3 | 7/7 | 6 |

Each profile covers online, offline, checksum corruption, protected wrong origin,
a separate disabled-origin-policy control, wrong anchor and wrong non-anchor.
The eight positive cases ran **24 MySQL tests**, with zero failures, errors or
skips. All 20 negative/control cases passed their specific checks. Offline runs
used closed prime endpoints, preserved caches, a proved Java network barrier and
actual no-pull invocations for the fixed images.

The first attempt stopped after six cases because Groovy misread a report string
expression; a parentheses-only fix passed a fresh targeted check before the
complete run. That initial attempt also retained one Testcontainers startup
retry after a local JDBC EOF. No startup retry was observed in the complete run.

Evidence labels: `verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.2`,
`verified - ShardingSphere-JDBC 5.5.3`. Source:
`4e066942f6e244345fe908970b81446f9e08f64e`.

SHA-256 bindings:

- Raw summary: `b9b8afedffaf2312ac9fcdd446f1728ee0d08e47f7b6070de81e0d8d7670b2d7`
- Independent audit: `5a1dcbba757143581495ac354c5d835a49b1d6328b5e823a8670a5aaf46899dd`
- Reviewed staging receipt: `38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43`

[The minimized JSON](a24-gradle-consumer-2026-09-08.json) records all 28 identities
and per-case evidence digests. Raw execution details remain private.

Maven acceptance is reported separately. One complete run per listed case does
not establish longevity, broader platform/JDK support, public 0.2 availability or
external adoption. Network isolation covers the sandboxed JVM descendants and
fixed fixture; global Docker/container networking is outside that boundary.
