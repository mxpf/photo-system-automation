# Production Font Collection

The production collection is the set of top-level font-family folders left in `Fonts/` after restricted and unresolved families are isolated.

## Policy

- Production-approved: official open-source evidence or an included license explicitly permitting commercial work.
- Restricted: trials, test builds, personal-use files, unlicensed builds, suspect-source files, and web-only licenses.
- Review: fonts with unresolved purchase, entitlement, or provenance records.
- Nothing is deleted. Restricted and unresolved families remain preserved under `_Quarantine/`.

## Counts

- Production-approved families: 1,826
- Restricted families: 158
- License/provenance review: 210

## Canonical-family check

No production-approved family names collide after case, spacing, and punctuation normalization. The existing family folder is therefore the canonical version for each approved family.
