# Synthetic baseline review

`find-paid-orders-by-user.approved.json` is a copy of the repository's existing reviewed synthetic
baseline at [the public v0.1.3 consumer fixture](../../public-gradle-release-consumer/src/test/resources/manifests/find-paid-orders-by-user.approved.json).
Its bytes are unchanged:

```text
a082ca797ebe40be5b8c9409893de7d9a861086d8d4b760cbc00e925b2436a60
```

That checksum identifies the copied file, not proof of human approval. The copy carries only the
existing demonstration baseline's scope; the new test never creates or rewrites it. Public release
consumer runs are recorded in [the v0.1.3 release evidence](../../../docs/evidence/release-0.1.3-central.md).

Review rationale for this fixture:

- Operation `find-paid-orders-by-user` returns exactly order `(201, 3, PAID)`, checked separately.
- The equality query and inline sharding configuration target the odd data source.
- `ds_0` and `ds_1` map to the stable aliases `orders-even` and `orders-odd`.
- The approved strict budget permits one observed physical JDBC execution attempt and one observed
  data-source alias, with no callback-reported failures and exact execution signatures.
- The saved equality signature has two parameter types (`Long`, `String`) and one callback-returned
  attempt. A callback return does not prove the enclosing transaction committed.
- The alternative `BETWEEN 3 AND 3` query returns the same row but exceeds these deliberately
  narrow attempt and alias budgets under this fixture's configuration.

For the first-time rehearsal, capture to `build/routecontract/candidate.json`, inspect it against the
source and intended budgets, then explicitly create a separate `baselines/first-review.approved.json`
after your review. Do not overwrite the supplied baseline to make the range test pass.

For your own project, choose your operation, alias mapping and budgets, and have its authorized
owner or maintainer approve its exact baseline through the normal code-review process. Running
this example, copying this file or a tool checking its checksum does not approve that project's
baseline.
