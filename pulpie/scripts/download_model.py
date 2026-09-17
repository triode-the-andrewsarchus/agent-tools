#!/usr/bin/env python3
"""Pre-download and verify Pulpie model weights for local execution."""

import sys
import time
from pulpie_service.config import PulpieConfig
from pulpie_service.extractor import PulpieService


def main() -> None:
    cfg = PulpieConfig.from_env()
    print(f"==================================================")
    print(f"Pulpie Model Preload & Verification")
    print(f"Model configured: {cfg.model_name}")
    print(f"Preferred device: {cfg.device}")
    print(f"==================================================")

    svc = PulpieService(cfg)
    t0 = time.perf_counter()
    print(f"Checking / downloading weights from Hugging Face...")
    success = svc.ensure_loaded()
    elapsed = time.perf_counter() - t0

    if success:
        st = svc.status()
        print(f"✓ Model successfully loaded in {elapsed:.2f}s!")
        print(f"Device: {st.get('device')}")
        if st.get("cuda_available"):
            print(f"GPU: {st.get('gpu_name')}")
            print(f"VRAM Allocated: {st.get('vram_allocated_mb')} MB")
            print(f"VRAM Reserved:  {st.get('vram_reserved_mb')} MB")
        
        # Test a trivial extraction
        test_res = svc.clean_html("<html><body><nav>Menu</nav><p>Hello Pulpie World!</p></body></html>")
        print(f"Sanity test output: {test_res.content.strip()}")
        print(f"Sanity test latency: {test_res.latency_ms:.2f}ms")
        sys.exit(0)
    else:
        st = svc.status()
        print(f"✗ Failed to load model: {st.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
