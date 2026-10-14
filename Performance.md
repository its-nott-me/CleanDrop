# CleanDrop - Performance & Engineering Notes

This document records performance measurements and key engineering decisions for CleanDrop, measured on the actual target environment: Windows, Python 3.12.4, the project’s real `database.py` and `host.py` implementations, and the running local LLM server.

**All latency figures below are measured, not estimated.** Configuration-based timings and architectural properties are identified separately from benchmark results.

## 1. Database & Native Messaging Performance

### SQLite Operations

| Operation | Mean | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| `save_download()` - SQLite insert | 3.07 ms | 2.53 ms | 3.85 ms | 14.42 ms |
| `get_expired_downloads()` - SQLite query | 2.45 ms | 2.22 ms | 3.01 ms | 7.55 ms |
| `schedule_deletion()` - SQLite update | 2.40 ms | 2.21 ms | 2.81 ms | 7.51 ms |

### Native Messaging Round Trip

| Metric | Latency |
|---|---:|
| Mean | 95.07 ms |
| p50 | 93.22 ms |
| p95 | 105.11 ms |
| p99 | 116.51 ms |

The native-messaging measurement includes process startup, protocol parsing, and saving the received download record.

**Reproduce the benchmarks:**

Run the following commands from the `companion/` directory:

```bash
python benchmark.py
python benchmark_ai.py 10
```

The first command benchmarks database operations and native messaging. The second measures AI filename-suggestion latency using 10 benchmark iterations.

## 2. Bottleneck Investigation: SQLite Journal Mode

The initial benchmark revealed an unexpected performance bottleneck in `save_download()`.

| Metric | Before: Rollback Journal | After: WAL | Improvement |
|---|---:|---:|---:|
| Mean | 45.01 ms | 3.07 ms | 14.7× faster |
| p50 | 38.72 ms | 2.53 ms | 15.3× faster |
| p99 | 213.82 ms | 14.42 ms | 14.8× faster |

A single-row insert was taking substantially longer than the other single-statement database operations. The issue was not the insert itself, but the overhead associated with SQLite's default rollback-journal mode.

### Root Cause

The database connection did not explicitly configure its journal mode. Under the default rollback-journal configuration, SQLite uses a separate journal file for transaction rollback and recovery.

On Windows, repeated journal-file creation and deletion can incur additional filesystem overhead, potentially amplified by real-time antivirus scanning. This was consistent with the unusually high write latency and tail latency observed in the initial measurements.

### Fix

The connection was configured to use Write-Ahead Logging (WAL) and `synchronous=NORMAL`:

```python
connection.execute("PRAGMA journal_mode=WAL")
connection.execute("PRAGMA synchronous=NORMAL")
```

WAL allows SQLite to record changes in a persistent write-ahead log instead of repeatedly creating and deleting a rollback-journal file for each transaction.

The result was a reduction in mean insert latency from **45.01 ms to 3.07 ms**, approximately a **14.7× improvement**.

The `synchronous=NORMAL` setting reduces synchronization overhead while retaining SQLite's transactional guarantees, but it can sacrifice the durability of the most recent committed transactions in certain power-loss or operating-system-crash scenarios. WAL also introduces checkpointing and associated operational considerations.

### Why the Native Messaging Latency Barely Changed

Native-messaging latency changed from approximately 105 ms to 95 ms across the benchmark runs, while database insert latency improved dramatically.

This suggests that database writes were not the dominant component of the native-messaging round trip. Python interpreter startup and per-message process initialization are likely significant contributors.

The architectural response was to keep native messaging focused on short-lived event handling and move long-running operations, including LLM inference, into a persistent companion process.

This avoids making browser communication wait for work that does not need to happen inside the native-messaging process.

## 3. AI Filename Suggestion Latency

The local LLM benchmark was executed against the actual running model server. No cloud inference or simulated responses were involved.

| Metric | Latency |
|---|---:|
| Mean | 1,161.9 ms |
| p50 | 1,075.6 ms |
| p95 | 1,935.3 ms |
| Minimum | 375.8 ms |
| Maximum | 1,979.2 ms |

**Key observations:**

- Median latency is approximately **1.08 seconds**.
- The mean is approximately **1.16 seconds**, indicating that average inference latency is slightly higher than the median.
- The measured p95 is approximately **1.94 seconds**.
- The local-first inference path avoids dependence on external AI APIs for filename suggestions.

These figures describe the tested hardware, model, server configuration, and workload. They should not be treated as universal performance guarantees.

## 4. Scheduling & Deletion Guarantees

The following are properties of the configured scheduling intervals and file-identity checks, rather than latency measurements.

| Behavior | Configuration / Guarantee |
|---|---|
| Expired-download polling | Every 30 seconds |
| AI-renaming polling | Every 5 seconds |
| Deletion safety | Verify filesystem identity before deleting |

### Expired Download Processing

The scheduler checks for expired downloads every 30 seconds.

Under normal scheduler operation, an expired download is therefore eligible for processing within approximately 30 seconds of its expiry time, plus execution and filesystem-operation overhead.

This is a polling interval, not a hard real-time deadline. Scheduler delays, process downtime, and filesystem errors can extend the actual processing time.

### AI Renaming

Downloads flagged for AI-assisted renaming are picked up by a scheduler that polls every 5 seconds.

The configured polling interval provides a nominal upper bound of 5 seconds before the next check when the scheduler is running normally. Actual completion time additionally depends on queue processing, LLM inference latency, and filesystem operations.

### Identity-Based Deletion Safety

Before deleting a scheduled file, CleanDrop verifies its filesystem identity using the NTFS volume serial number and file ID.

The deletion decision is based on the identity of the original file, not merely its path. This matters because a path can refer to a different file after the original has been moved, replaced, or otherwise modified.

If the identity check fails, the scheduled deletion is rejected rather than deleting whichever file currently occupies that path.

This also protects against a rename operation invalidating a scheduled deletion simply because the file's path changed.

The guarantee depends on the identity check being performed correctly and on filesystem operations being handled safely; it should not be interpreted as protection against every possible filesystem race or storage failure.

## 5. Key Engineering Decisions

### 5.1 Process Lifecycle & Native Messaging

**Problem:** Chrome's `sendNativeMessage` uses a short-lived native-messaging host process for an individual message. Background threads started by that process cannot be relied upon to survive after the response is sent and the process exits.

**Solution:** Separate ephemeral message handling from persistent background processing across two cooperating processes.

**Impact:** Long-running work, particularly LLM inference and polling-based tasks, no longer depends on the lifetime of an individual browser message handler.

### 5.2 SQLite Write Optimization

**Problem:** SQLite's default rollback-journal configuration was associated with unexpectedly high write latency on Windows.

**Solution:** Enable WAL mode and configure `synchronous=NORMAL`.

**Measured impact:** Mean insert latency decreased from 45.01 ms to 3.07 ms, a 14.7× improvement.

### 5.3 Resilient Browser Context Matching

**Problem:** Manifest V3 service workers can be suspended or restarted, causing previously held in-memory state to disappear.

**Solution:** Use a tiered context-matching strategy:

1. Exact URL match.
2. Same-origin referrer match.
3. Live active-tab query as a fallback.

**Impact:** Context resolution does not depend exclusively on transient service-worker state.

### 5.4 Filesystem Identity Tracking

**Problem:** Tracking scheduled deletions by path alone can target the wrong file if the original file is moved, replaced, or renamed.

**Solution:** Record filesystem identity using the NTFS volume serial number and file ID, then verify that identity before deletion.

**Impact:** A changed path alone does not redirect a scheduled deletion to an unrelated file.

### 5.5 Local-First AI Inference

**Problem:** Cloud inference introduces external service dependencies and network requirements for a feature that can run locally.

**Solution:** Run a self-hosted LLM and send filename-suggestion requests to the local server over `localhost`.

**Measured impact:** Median end-to-end AI filename-suggestion latency of approximately 1.08 seconds in the tested environment.

**Architectural impact:** AI-assisted renaming does not require an external inference API or an internet connection for the local inference request. Other application functionality may have separate network requirements.

## 6. Summary

CleanDrop's performance work focused on identifying real bottlenecks and addressing their underlying causes rather than optimizing components without evidence.

The most significant measured improvement was the SQLite journal-mode change, which reduced mean insert latency by approximately 93% and improved p99 latency by approximately 93%.

The broader design separates short-lived browser communication from persistent background work, uses local AI inference, and verifies filesystem identity before scheduled deletion. Together, these decisions prioritize responsiveness, operational reliability, and safe file handling.

### Benchmark Environment

- **Operating system:** Windows
- **Python:** 3.12.4
- **Database:** SQLite
- **AI inference:** Actual locally running LLM server
- **Benchmark scripts:** `companion/benchmark.py`, `companion/benchmark_ai.py`
- **Results:** Measurements from the tested development environment; performance may vary with hardware, workload, filesystem, antivirus configuration, and model settings.
