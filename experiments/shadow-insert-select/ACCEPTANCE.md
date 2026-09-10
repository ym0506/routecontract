# Shadow INSERT SELECT reproduction acceptance

Source problem: apache/shardingsphere#39750; proposed upstream fix #39751.
The author reported master, not a released-version reproduction. This independent
experiment will establish behavior on exact ShardingSphere-JDBC 5.5.3 with real
MySQL. It does not test or modify the author's patch.

Required evidence before publishing a result:

1. Resolve RouteContract 0.1.3 from Maven Central; no local library source build.
2. Two disposable MySQL 8.4.11 instances, one primary and one shadow, with identical
   synthetic source rows and independently read target tables.
3. A nonmatching VALUES insert reports primary; a matching VALUES insert reports
   shadow. Both affect one row and the direct physical table reads must agree.
4. For nonmatching INSERT SELECT, record JDBC affected rows, hook-reported data
   source names, and direct target-table contents. Do not assume the issue is
   present before running it.
5. If the reported bug is reproduced, characterize it explicitly and also run an
   enforcing contract command which must exit nonzero for the unexpected shadow
   data source. Keep the application affected-row assertion unchanged.
6. Verify that the failure is the intended data-source assertion, not startup,
   instrumentation, dependencies, an unsupported capture or absent tests.
7. Record exact JDK, Maven, MySQL image digest, library hash, test counts, commands
   and limits. Never publish raw connection data or runtime logs.

This is an independent issue reproduction, not external product adoption, proof
of the upstream fix, Proxy coverage, a performance test, or a library release.
