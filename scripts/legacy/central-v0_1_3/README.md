# Preserved 0.1.3 Central bundle verifier

`prepare-central-upload-bundle.py` is the exact schema-1 verifier from published
0.1.3 source revision `f1efd71e32078dd5812268a1ad24ee73110ff61f` (also unchanged
at main revision `961c4baab5c6b690fdad997ed70806c82e2ede8b`).

- Basename: `prepare-central-upload-bundle.py`
- SHA-256: `87f60774cbcdbf2eb75884621875487b4673c073de933f73670d405c8cbf4df3`
- Size: 62,090 bytes

Existing reviewed bundle receipts bind that basename and hash. Preserve this
file byte for byte; do not rename it, run a formatter on it, or rewrite receipts
to accommodate a different verifier. Its versioned directory prevents the
unreleased 0.2 schema-2 bundle tool from replacing the 0.1 public readback gate.

`scripts/verify-public-release-central-readback.py` loads this verifier for
single-artifact 0.1.x verification. The top-level bundle tool and the split
public readback command remain separate. The independent signed schema-1 test
fixture is `scripts/tests/fixtures/central_schema1.py`.
