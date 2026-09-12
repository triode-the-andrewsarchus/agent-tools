#!/usr/bin/env python3
"""Comprehensive benchmark suite for Pulpie extraction service."""

import os
import sys
import time
from pathlib import Path

from pulpie_service.config import PulpieConfig
from pulpie_service.extractor import PulpieService


def main() -> None:
    corpus_dir = Path(__file__).resolve().parent.parent / "benchmark_corpus"
    if not corpus_dir.exists():
        print(f"Error: benchmark corpus not found at {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    html_files = sorted(corpus_dir.glob("*.html"))
    if not html_files:
        print(f"Error: no HTML files found in {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    print("================================================================================")
    print("                    PULPIE SERVICE BENCHMARK SUITE                             ")
    print("================================================================================")

    cfg = PulpieConfig.from_env()
    svc = PulpieService(cfg)

    # 1. Cold Start Measurement
    print("\n[1/3] Measuring Cold-Start Model Load Time...")
    t0 = time.perf_counter()
    loaded = svc.ensure_loaded()
    cold_load_time = time.perf_counter() - t0

    status = svc.status()
    print(f"  Cold start time:    {cold_load_time:.3f} s")
    print(f"  Model:              {status.get('model_configured')}")
    print(f"  Device:             {status.get('device')}")
    if status.get("cuda_available"):
        print(f"  GPU:                {status.get('gpu_name')}")
        print(f"  VRAM Allocated:     {status.get('vram_allocated_mb')} MB")
        print(f"  VRAM Reserved:      {status.get('vram_reserved_mb')} MB")

    # 2. Warm-up
    print("\n[2/3] Warming up inference engine...")
    svc.clean_html("<html><body><p>Warmup paragraph</p></body></html>")

    # 3. Benchmark across corpus
    print("\n[3/3] Running benchmark across 6 diverse corpus pages...")
    results = []
    total_in_chars = 0
    total_out_chars = 0
    total_latency_ms = 0.0
    iterations = 5

    for path in html_files:
        raw_html = path.read_text(encoding="utf-8")
        in_chars = len(raw_html)
        total_in_chars += in_chars

        # Run multiple iterations for accurate latency
        latencies = []
        last_res = None
        for _ in range(iterations):
            t_start = time.perf_counter()
            last_res = svc.clean_html(raw_html, output_format="markdown")
            latencies.append((time.perf_counter() - t_start) * 1000)

        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        total_latency_ms += avg_latency
        out_chars = len(last_res.content)
        total_out_chars += out_chars

        # Check structure preservation
        has_table = "|" in last_res.content and "-|-" in last_res.content or "<table" in last_res.content
        has_code = "```" in last_res.content or "<code>" in last_res.content
        has_headings = "#" in last_res.content

        results.append({
            "name": path.stem,
            "in_chars": in_chars,
            "out_chars": out_chars,
            "compression": (out_chars / max(1, in_chars)) * 100,
            "savings": last_res.token_savings_pct,
            "blocks_kept": f"{last_res.n_main}/{last_res.n_blocks}",
            "avg_latency_ms": avg_latency,
            "min_latency_ms": min_latency,
            "fallback": last_res.used_fallback,
            "has_table": has_table,
            "has_code": has_code,
            "has_headings": has_headings,
        })

    # Summary Table
    print("\n" + "=" * 95)
    print(f"{'Page Type':<22} | {'Input':<8} | {'Output':<8} | {'Comp%':<7} | {'Saved%':<7} | {'Blocks':<8} | {'Latency':<9}")
    print("-" * 95)
    for r in results:
        print(f"{r['name']:<22} | {r['in_chars']:<8} | {r['out_chars']:<8} | {r['compression']:>5.1f}% | {r['savings']:>5.1f}% | {r['blocks_kept']:<8} | {r['avg_latency_ms']:>6.2f} ms")
    print("=" * 95)

    overall_savings = (1.0 - (total_out_chars / max(1, total_in_chars))) * 100
    avg_page_latency = total_latency_ms / len(results)
    pages_per_sec = 1000.0 / avg_page_latency if avg_page_latency > 0 else 0

    print(f"\nAGGREGATE BENCHMARK METRICS:")
    print(f"  • Total input size:         {total_in_chars:,} chars (~{total_in_chars // 4:,} tokens)")
    print(f"  • Total cleaned size:       {total_out_chars:,} chars (~{total_out_chars // 4:,} tokens)")
    print(f"  • Overall token reduction:  {overall_savings:.1f}%")
    print(f"  • Mean extraction latency:  {avg_page_latency:.2f} ms per page")
    print(f"  • Single-stream throughput: {pages_per_sec:.1f} pages/second")
    print(f"  • Cold start load time:     {cold_load_time:.2f} s")
    if status.get("cuda_available"):
        print(f"  • VRAM footprint:           ~{status.get('vram_allocated_mb')} MB allocated")
    print("================================================================================\n")


if __name__ == "__main__":
    main()
