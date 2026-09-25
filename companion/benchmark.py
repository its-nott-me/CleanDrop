"""
CleanDrop companion benchmark.

Measures real latency of the core companion operations against your
actual database.py / host.py — no mocked components other than the
downloads themselves, which are synthetic test data.

Run on the SAME machine (and ideally the compiled exe's environment)
you intend to cite numbers for — sandbox/dev-container numbers are not
representative of your real deployment target.

Usage:
    python benchmark.py
"""

import json
import os
import statistics
import struct
import subprocess
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database


def percentile(data, p):
    data = sorted(data)
    k = (len(data) - 1) * p
    f = int(k)
    c = min(f + 1, len(data) - 1)
    if f == c:
        return data[f]
    return data[f] + (data[c] - data[f]) * (k - f)


def bench(label, fn, n):
    times = []
    for i in range(n):
        t0 = time.perf_counter()
        fn(i)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)

    result = {
        "mean_ms": statistics.mean(times),
        "p50_ms": percentile(times, 0.50),
        "p95_ms": percentile(times, 0.95),
        "p99_ms": percentile(times, 0.99),
    }

    print(f"\n{label} (n={n})")
    for key, value in result.items():
        print(f"  {key:8s}: {value:.4f} ms")

    return result


def make_download(i):
    return {
        "id": 9_000_000 + i,
        "filename": f"{tempfile.gettempdir()}/cleandrop_bench_{i}.jpg",
        "url": f"https://example.com/f{i}.jpg",
        "referrer": "https://example.com/",
        "mime": "image/jpeg",
        "fileSize": 12345,
        "startTime": "2026-08-28T00:00:00Z",
        "endTime": "2026-08-28T00:00:01Z",
        "incognito": False,
        "page_title": "Example Page",
        "page_description": "An example page",
    }


def send_native_message(i):
    msg = json.dumps({
        "event": "schedule_deletion",
        "id": 9_500_000 + i,
        "filename": f"{tempfile.gettempdir()}/cleandrop_native_{i}.jpg",
        "url": f"https://example.com/n{i}.jpg",
        "referrer": "https://example.com/",
        "mime": "image/jpeg",
        "fileSize": 4096,
        "startTime": "2026-08-28T00:00:00Z",
        "endTime": "2026-08-28T00:00:01Z",
        "incognito": False,
        "deleteAfter": "2099-01-01T00:00:00+00:00",
    }).encode("utf-8")

    subprocess.run(
        [sys.executable, "host.py"],
        input=struct.pack("<I", len(msg)) + msg,
        capture_output=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )


def main():
    print("CleanDrop companion benchmark")
    print(f"Python: {sys.version.split()[0]}  Platform: {sys.platform}")

    database.initialize_database()

    from files.identity import get_file_identity
    identity = get_file_identity(__file__)

    results = {}

    results["create_scheduled_download_ms"] = bench(
        "create_scheduled_download() [SQLite insert]",
        lambda i: database.create_scheduled_download(
            make_download(i), identity, "2099-01-01T00:00:00+00:00"
        ),
        500,
    )

    results["get_expired_downloads_ms"] = bench(
        "get_expired_downloads() [SQLite query]",
        lambda i: database.get_expired_downloads(),
        200,
    )

    results["update_delete_status_ms"] = bench(
        "update_delete_status() [SQLite update]",
        lambda i: database.update_delete_status(i + 1, "DELETED"),
        500,
    )

    # host.py now needs a real file on disk for schedule_deletion
    # to succeed (it checks existence before creating the row).
    native_test_dir = Path(tempfile.gettempdir())
    for i in range(50):
        (native_test_dir / f"cleandrop_native_{i}.jpg").touch()

    results["native_messaging_roundtrip_ms"] = bench(
        "Full native-messaging round trip [process spawn + protocol + schedule]",
        send_native_message,
        50,
    )

    print("\n--- summary (JSON) ---")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()