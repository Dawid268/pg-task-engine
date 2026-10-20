# Reliability audit — 0.1.0a3 candidate

**Scope:** PostgreSQL-backed Python library and optional reference API,
not a production deployment. The assessment uses a dedicated database
whose name ends in `_test`. Other project databases are not involved.

## Verified behavior

| Area | Verification |
| --- | --- |
| Domain contracts | Boundary/error-code tests for request, status, progress and policies |
| Transactional enqueue | Real PostgreSQL tests, including concurrent idempotent submissions |
| Task dispatch | Workers only claim locally registered exact task name/version pairs |
| Retry | User handler exceptions are retryable; schema/JSON failures are not |
| Atomic claim | Thread, spawned-process and multi-process real DB tests |
| Lease fencing | An expired/superseded worker cannot commit stale results |
| Recovery | An OS-killed worker was reaped and a replacement completed the second attempt |
| JSONB correctness | Input/output NUL, Unicode, NaN, cycle and 64 KiB limit tests |
| PostgreSQL integer limits | Domain checks for INTEGER/BIGINT maximum values and UTF-8 text encoding |
| Migration safety | Version checksums, legacy 001 upgrade, unknown versions and SQL tampering |
| Client interfaces | CLI enqueue, inspect and migrate tested against PostgreSQL |
| Packaging | Wheel and sdist, MIT license, bundled migrations, isolated wheel installation |
| Python/PostgreSQL versions | Python 3.13 and 3.14 with PostgreSQL 16 and 18 |
| Dependency compatibility | Locked dependencies, plus a clean Python 3.14 install with latest allowed dev packages |
| Static assurance | Ruff, strict mypy, Twine and locked-dependency vulnerability audit |

The manual multi-process probe enqueued 200 jobs in a **fresh, disposable**
database. Four independent Python processes completed them with no failed
jobs or duplicate attempts (distribution 50/50/51/49 during one run).
This is a functional smoke/load probe, **not** a sustained benchmark or
throughput guarantee.

The process-crash probe killed a worker while its handler slept, waited
for lease expiry, called `reap_expired`, verified the old token was fenced,
and successfully completed the retry using a new worker. The temporary
audit databases were removed after the checks.

## Bugs caught by the audit

1. **Wrong worker consuming another task version** — previously a worker
   could claim and fail jobs without a local handler. Fixed through
   parameterized database-side task filtering.
2. **Lost retries for `ValueError`/`TypeError`** — previously handler
   exceptions were misclassified as permanent schema failures. Fixed by
   distinguishing validation phases from callback execution.
3. **PostgreSQL-incompatible NUL characters** — formerly accepted text
   and JSON caused raw database errors. Rejected at domain boundaries,
   including task identity, request, result and progress/error metadata.
4. **Unpinned FastAPI API drift** — fresh FastAPI 0.146+ rejects the
   deprecated constructor `root_path` argument under warnings-as-errors.
   The reference API now sets the ASGI root path without that parameter.
5. **Unchecked PostgreSQL storage ranges** — numbers above signed INTEGER
   (task versions, attempt limits, progress counts) or signed BIGINT
   (progress revision, attempt duration) used to fail at SQL time.
   Values now fail deterministically during Python validation.
6. **Unpaired surrogate characters in text** — names, progress units,
   queue names, keys or manual attempt error descriptions could raise
   database codec errors. All such values now validate UTF-8 encoding.
7. **Extreme timedelta values** — PostgreSQL cannot add an almost
   billion-day timeout/retry delay to its current timestamp. The models
   now reject durations longer than 36,500 days before enqueue.

These bugs are present in the frozen, historically tagged `v0.1.0a2`
source. **Do not publish `0.1.0a2`.** The corrected candidate
`0.1.0a3` was published as the first public Alpha on 20 October 2026.

## Exclusions and residual risk

Passing tests cannot prove 100% correctness. The coverage report measures
exercised lines and branches, **not** the probability of failures.

The audit does not establish:

- Days-long soak or stress behavior at sustained high throughput.
- All forms of network partition, PostgreSQL primary failover, power
  failure, backup/restore or cross-region disaster recovery.
- Arbitrary handler termination, deterministic exactly-once side effects,
  or remote service idempotency.
- Hardened multi-tenant authorization, deployment access controls, TLS
  termination or an HTTP management gateway.
- Database migration performance under live production-sized data.
- Compatibility with future untested Python or PostgreSQL releases.
- A successful upload to TestPyPI/PyPI or a production installation.

The previous `v0.1.0a2` TestPyPI workflow failed with `invalid-publisher`.
Both registries' Trusted Publishers were subsequently configured, allowing
successful TestPyPI and PyPI publication of `v0.1.0a3`. Registry
authentication remains a prerequisite for **future** releases. Do not
publish or modify the old immutable tag.

For execution commands and publication gates see
[OPERATIONS.md](OPERATIONS.md) and [RELEASING.md](RELEASING.md).
