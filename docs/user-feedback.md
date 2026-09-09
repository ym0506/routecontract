# 질문·도입 도움·사용 경험 / Questions, integration help and feedback

ShardingSphere-JDBC를 사용한다면 설치 전에 현재 검증 방법이나 최근 SQL·샤딩 변경 경험을
알려주세요. RouteContract가 지금 환경에 맞지 않는 이유도 도움이 됩니다. 공개 저장소를
관리하지 않아도 참여할 수 있습니다.

If you use ShardingSphere-JDBC, start with your current verification method or a recent SQL/sharding
change. No installation, public repository, or maintainer role is needed to ask about fit.
Unsupported versions and not-a-fit experiences are useful too; describing them does not expand the
released support boundary.

Use the [short feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml).
Only a short question or experience and the public-information check are required. For example:

```text
ShardingSphere-JDBC 5.5.3, Java 17, Maven.
We currently check returned rows after changing sharding predicates.
Can I add this to an existing test without changing the application's normal build?
```

```text
ShardingSphere-JDBC 5.5.2를 사용하고 있습니다.
지금은 SQL 변경 후 조회 결과만 검사합니다.
현재 버전에서 적용할 수 없다면 어떤 지원이 필요한지 알고 싶습니다.
```

## One test, then a later change

1. **Discuss fit.** Share only the version, build tool and problem you want to check. A private
   project can stay private. Do not provide repository access, source archives, production data,
   raw SQL, bind values, connection details, full logs or screenshots in public feedback.
2. **Try the demo if useful.** [Run the released MySQL demonstration in your browser](first-project.md#try-in-your-browser),
   or read the [application evaluations](application-evaluations.md) without installing anything.
   A demo run helps explain the tool; it is not a project integration.
3. **Use one existing test.** Follow the [v0.1.3 first-project guide](first-project.md) ([한국어](first-project.ko.md)) in a repository
   you are authorized to modify. Keep its business assertion. The supported released boundary is
   Java 17, exact ShardingSphere-JDBC 5.5.3 and synchronous non-batch `PreparedStatement` operations.
   A valid first candidate establishes a pilot; the target's authorized owner or maintainer must
   review the budgets, aliases and exact baseline before candidate checks can use that baseline.
4. **Check the next real change.** After a completed integration, record whether a later SQL,
   configuration or middleware change used the check and whether the result helped a decision.
   An intentional change, false positive, blocker or decision to remove the library is useful
   feedback. Repeated unchanged demo runs do not establish this stage.

Baseline approval remains the target repository's responsibility. RouteContract's maintainer,
an assistant, a generator or CI cannot supply that approval on the target's behalf. No response,
integration-completion time or compatibility outside the stated scope is promised.

## Recording use and evidence

Use stage and evidence quality answer different questions. A private team can use RouteContract
without publishing its code or CI. Its report remains self-reported unless the relevant result has
been inspected; lack of public links does not mean lack of use.

| Dimension | Record | Meaning |
| --- | --- | --- |
| Use stage | Conversation / demo / project pilot / completed integration / repeat use | Pilot: valid candidate from one own-project operation. Integration: target-approved baseline and successful check. Repeat use: check on a later real change. |
| Assistance | Maintainer-assisted / independently completed / unknown | Identify who performed the relevant step. A maintainer's fixture is not an external user's project. |
| Verification | Self-reported / inspected result / publicly reproducible evidence | State exactly what was inspected, at which revision and in which environment; do not promote a report to verified use automatically. |
| Publication permission | Not granted / approved scope | A public comment is not blanket permission to name an employer, publish a case study or describe an endorsement. |

For a publicly inspectable integration, link the source revision, dependency, representative test,
reviewed baseline and its approval record, and successful CI run for that revision. Preserve the
actual environment label: H2 does not verify MySQL. Private details are not required for public
feedback, and publication is not a prerequisite for local or private-CI use.

Downloads, stars, generated patches, draft PRs and author-run examples do not establish external
project use. A successful test does not by itself prove production use, performance improvement,
security or endorsement. Record failed attempts and unknowns alongside successes. Historical RC
studies and submission evidence retain their original cutoff and definitions; these current product
definitions do not relabel old study results.

## Optional public assisted pilot

[Discussion #34](https://github.com/ym0506/routecontract/discussions/34) is a separate, public-repository
assisted-pilot channel. Its invitation is for an authorized owner or maintainer of the target public
repository using Java 17, exact ShardingSphere-JDBC 5.5.3 and an existing synchronous non-batch
`PreparedStatement` test. It is not a third-party repository nomination channel. Copy its existing
reply format only when requesting that specific pilot:

```text
interested
Repository: https://github.com/OWNER/REPOSITORY
Build: Gradle or Maven
```

For that pilot, RouteContract maintainers inspect public code only. An optional unpublished,
review-only first-pass patch may be prepared when the target's license, contribution rules and AI
policy permit it. Obtain separate confirmation from an authorized target owner or maintainer before
opening an external public PR. The target's authorized maintainer separately approves the baseline.
The advertised 30 minutes covers initial scoping, not a response, patch or completion-time guarantee.
Do not send credentials, raw SQL, binds, JDBC URLs, customer data, private topology, hostnames,
absolute paths, logs, screenshots or unnecessary personal information in Discussion #34 or through a
private channel. These participation conditions apply to that assisted pilot, not to self-service use
or the short feedback form above.
