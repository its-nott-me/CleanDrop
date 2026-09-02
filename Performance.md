# CleanDrop — Performance Notes

Numbers below are real measurements taken on the actual target machine (Windows, Python 3.12.4), running the real project code (`database.py`, `host.py`, the actual local LLM server) — nothing here is estimated.

## Database & native messaging

| Operation | Mean | p50 | p95 | p99 |
|---|---|---|---|---|
| `save_download()` — SQLite insert | 3.07 ms | 2.53 ms | 3.85 ms | 14.42 ms |
| `get_expired_downloads()` — SQLite query | 2.45 ms | 2.22 ms | 3.01 ms | 7.55 ms |
| `schedule_deletion()` — SQLite update | 2.40 ms | 2.21 ms | 2.81 ms | 7.51 ms |
| Full native-messaging round trip (process spawn + protocol parse + save) | 95.07 ms | 93.22 ms | 105.11 ms | 116.51 ms |

Reproduce with `python benchmark.py` from `companion/`.

### Fixing a real bottleneck: SQLite journal mode

The first benchmark run showed `save_download()` at **45.01ms mean / 213.82ms p99** — 15-20x slower than the other single-statement operations, which made no sense for a single-row insert. Root cause: `get_connection()` never set any `PRAGMA`, so SQLite used its default rollback-journal mode, which creates and deletes a small `-journal` file on *every transaction*. On Windows, real-time antivirus scanning intercepts each of those file create/delete events, and the overhead compounds badly under frequent small writes.

**Fix:** enable WAL mode, which replaces per-transaction journal file churn with appends to a single persistent file:
```python
connection.execute("PRAGMA journal_mode=WAL")
connection.execute("PRAGMA synchronous=NORMAL")
```

| | Before (rollback journal) | After (WAL) | Improvement |
|---|---|---|---|
| Mean | 45.01 ms | 3.07 ms | **14.7x** |
| p50 | 38.72 ms | 2.53 ms | **15.3x** |
| p99 | 213.82 ms | 14.42 ms | **14.8x** |

The native-messaging round trip stayed essentially flat (105ms → 95ms) across the same fix, confirming it's dominated by Python interpreter process startup, not database or business logic — which is also *why* it was architecturally correct to move long-running work (LLM calls) out of that short-lived process entirely rather than trying to optimize it further.

## AI filename suggestion latency (real local LLM server)

| | Value |
|---|---|
| Mean | 1161.9 ms |
| p50 | 1075.6 ms |
| p95 | 1935.3 ms |
| Min | 375.8 ms |
| Max | 1979.2 ms |

Measured with `python benchmark_ai.py 10` against the actual running local model server — no cloud calls, no simulated data.

## Non-latency facts worth citing instead

These are true by construction (configuration, not measurement) and arguably more interesting than raw latency for a portfolio write-up:

- Expired downloads are checked for deletion within **30 seconds** of reaching their expiry time (`CHECK_INTERVAL` in `scheduler.py`).
- Downloads flagged for AI renaming are picked up within **5 seconds** of being saved (`AI_CHECK_INTERVAL`).
- Every scheduled deletion is preceded by a live filesystem-identity check (NTFS volume serial + file ID) — a file that's been moved, replaced, or tampered with since scheduling is **never** deleted, even if its `delete_after` timestamp has passed.

## Engineering points worth putting on a resume/portfolio

- Diagnosed a process-lifecycle bug where Chrome's one-shot native messaging model (`sendNativeMessage`) silently killed background threads mid-execution, and redesigned around it by separating ephemeral (per-event) work from persistent (polling) work across two cooperating processes.
- Identified and fixed a SQLite journaling bottleneck causing 15x higher write latency on Windows (antivirus-intercepted per-transaction journal file churn under the default rollback-journal mode); switching to WAL mode cut mean insert latency from 45ms to 3ms.
- Built a tiered, fallback-based context-matching system (exact URL match → same-origin referrer → live active-tab query) to work around Manifest V3 service worker state loss on restart/suspend.
- Implemented identity-based file tracking (filesystem ID, not path) so that downstream operations like AI-driven renaming can't invalidate scheduled deletions.
- Designed a local-first architecture where AI-assisted renaming calls a self-hosted LLM over `localhost` only, with zero external network dependency, measuring ~1.1s median inference latency end-to-end.