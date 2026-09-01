"""
CleanDrop AI filename latency benchmark.

This measures the ONE thing benchmark.py deliberately can't: real
inference latency from your local LLM server. That number depends
entirely on your model choice and hardware, so run this yourself
with your actual server running rather than trusting a number
measured on someone else's machine.

Requires your local LLM server (e.g. llama.cpp server) running at
the URL configured in ai/filename_model.py before running this.

Usage:
    python benchmark_ai.py [N]
"""

import statistics
import sys
import time

sys.path.insert(0, ".")

from ai.filename_model import suggest_filename


SAMPLE_CONTEXTS = [
    {
        "path": "/downloads/IMG_20260828.jpg",
        "filename": "IMG_20260828.jpg",
        "mime": "image/jpeg",
        "url": "https://en.wikipedia.org/wiki/Jade_vine",
        "referrer": "https://en.wikipedia.org/wiki/Jade_vine",
        "page_title": "Jade vine - Wikipedia",
        "page_description": "Strongyodon macrobotrys is a species of leguminous vine.",
    },
    {
        "path": "/downloads/document.pdf",
        "filename": "document.pdf",
        "mime": "application/pdf",
        "url": "https://example.com/files/document.pdf",
        "referrer": "https://example.com/reports",
        "page_title": "Quarterly Financial Report",
        "page_description": "Q3 2026 earnings summary",
    },
    {
        "path": "/downloads/xg31680746179.jpg.pagespeed.ic.j4c8VWiPkc.jpg",
        "filename": "xg31680746179.jpg.pagespeed.ic.j4c8VWiPkc.jpg",
        "mime": "image/jpeg",
        "url": "https://example-garden-blog.com/tulips.jpg",
        "referrer": "https://example-garden-blog.com/spring-flowers",
        "page_title": "10 Best Spring Flowers For Your Garden",
        "page_description": "A guide to planting tulips, daffodils, and crocuses.",
    },
]


def percentile(data, p):
    data = sorted(data)
    k = (len(data) - 1) * p
    f = int(k)
    c = min(f + 1, len(data) - 1)
    if f == c:
        return data[f]
    return data[f] + (data[c] - data[f]) * (k - f)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10

    times = []

    for i in range(n):
        context = SAMPLE_CONTEXTS[i % len(SAMPLE_CONTEXTS)]

        t0 = time.perf_counter()
        try:
            result = suggest_filename(context)
        except Exception as error:
            print(f"  [{i}] ERROR: {error}")
            continue
        t1 = time.perf_counter()

        elapsed_ms = (t1 - t0) * 1000
        times.append(elapsed_ms)

        print(f"  [{i}] {elapsed_ms:8.1f} ms -> {result}")

    if not times:
        print("\nNo successful calls — is your local LLM server running?")
        return

    print(f"\nAI filename suggestion latency (n={len(times)})")
    print(f"  mean : {statistics.mean(times):.1f} ms")
    print(f"  p50  : {percentile(times, 0.50):.1f} ms")
    print(f"  p95  : {percentile(times, 0.95):.1f} ms")
    print(f"  min  : {min(times):.1f} ms")
    print(f"  max  : {max(times):.1f} ms")


if __name__ == "__main__":
    main()