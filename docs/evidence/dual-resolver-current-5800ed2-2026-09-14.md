# Current dual-adapter boundary qualification

A developer who accidentally installs both adapters should receive a native
dependency conflict before application code executes. The verifier must establish
the intended conflict from actual build-tool evidence; a failed build alone is
not sufficient.

**Status: incomplete.** Current producer
`5800ed2960aefbf63c01d2ebaf2265278d662494` uses receipt SHA-256
`9a4d745ff11508a8ab08dd8bced6a7893d8f6e6ff5baab34b3445aea652ba49c`.
The corrected verifier source is `3e3f693ce6a00b1292693d15fb4cbaf05d0e3a16`.
Its 22-input manifest SHA-256 is
`313bb68f5692d730cd283ff7967f00bac6f7111d72c37deb957d54094e9771a0`.
The current native scope is Java 17.0.20.1+1, Gradle 9.7.1 and Maven 3.9.14
on local macOS arm64. This fixture performs no SQL or MySQL tests.
The [minimized native record](dual-resolver-current-5800ed2-2026-09-14.json)
binds the three recorded passes, remaining failure and additional diagnostic
to their actual graph/log hashes.

## Gradle findings

Three complete-plan invocations stopped at distinct verifier failures. They are
not one successful execution, and their counts must not be added together.

| Invocation | Native progress | Retained outcome |
| --- | --- | --- |
| Original verifier | First 5.5.2 case correctly rejects both adapters | FAILED: named root and capability exception type unrecognized |
| Root/capability correction | First case passes; opposite order exposes intrinsic formats | FAILED: new intrinsic exception formats unrecognized |
| Intrinsic-format correction | First three Gradle identities pass | FAILED: 5.5.3 opposite-first lacks both required adapter paths |

The first corrected behavior accepts the fixed fixture's actual named root and
the exact Gradle 9 capability exception type. It still verifies five ordinary
root requests in declaration order and both module rejection sections against
the published capabilities. Foreign roots, mixed roots, unrelated exception types
and substituted providers remain failures.

The second correction accepts native executor path conflicts and compact SPI
constraint conflicts. Compact messages must name exactly both versions and their
adapter providers with `runtimeElements`; those facts are checked against the
receipt-pinned module constraints. The complete compact cause must also occur
under the actual native SPI rejection section. Published reason text is retained
as metadata evidence, not described as text printed by the compact diagnostic.

The third invocation records these native outcomes:

- `gradle-5.5.2-selected-first`: capability rejection passed.
- `gradle-5.5.2-opposite-first`: capability plus intrinsic strict rejection passed.
- `gradle-5.5.3-selected-first`: capability plus intrinsic strict rejection passed.
- `gradle-5.5.3-opposite-first`: FAILED; the path validator remains strict.

For the last identity, both adapters have native capability rejections, but the
executor and SPI failure paths contain only ordinary 5.5.3 requests. They omit
both contradictory adapter paths required by the existing acceptance rule.
Receipt metadata establishes that the strict declarations exist; it does not
establish that the missing paths were emitted by this resolver invocation.

A separate one-case diagnostic added an init script that reads Gradle's native
`ModuleRejectedFailure` assessment without changing dependency declarations.
It also contains only 5.5.3 `REQUESTED` paths. This does not recover the missing
evidence, qualify the case, or prove an upstream Gradle bug. No failed run was
rewritten, and no capability or strict dependency was removed to get a pass.

The first separate Maven-six invocation reached the first native Enforcer goal
but failed downloading `commons-io:commons-io:2.22.0` with HTTP 504. It remains
a transport failure, not an adapter-policy rejection. Two subsequent direct
HTTPS downloads returned 200, matched the published SHA-1 and had identical
SHA-256 `2b9a7b1f726fb86216dbd2c8321eabe0221dbd5b1be81c18e1cb53811b104758`.
Those availability probes did not seed a consumer cache or qualify any Maven
identity. Maven results require their own completed invocation and retained audit.

## Verification and reproduction

The focused verifier suite passes 63 tests. Both complete Python roots pass:
`scripts/tests` has 1,087 cases with three existing opt-in skips;
`submission/tools/tests` has 346 cases without skips. The added tests cover
actual root/type variants, compact provider/version pairs, source metadata,
native cause ownership and rejection of malformed or unrelated evidence.

Follow the [finite ten-case acceptance instructions](../dual-resolver-boundary-acceptance.md)
at the pinned verifier revision with the exact candidate repository and receipt,
Java 17, the Gradle 9.7.1 distribution, Maven 3.9.14 and the frozen manifest above.
Use a new evidence directory and all ten identities for full qualification.
The last current full-plan invocation is expected to retain the failure above;
do not interpret that failure as a passing negative case. Existing Maven
identities may be executed separately, but their result cannot close the missing
Gradle identity or be called a complete ten-case invocation.

Evidence label: **verified - unit** for the parser tests. Native outcomes are
limited to the specific identities above. Current A-15/A-17 qualification,
human expected-manifest review and public 0.2 publication remain incomplete.
