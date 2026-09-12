#!/usr/bin/env python3
"""Interactive smoke test CLI for Pulpie service."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pulpie_service.config import PulpieConfig
from pulpie_service.extractor import PulpieService


def main() -> None:
    parser = argparse.ArgumentParser(description="Pulpie Extraction Smoke Test")
    parser.add_argument("--status", action="store_true", help="Print service and GPU health status")
    parser.add_argument("--file", type=str, help="Path to HTML file to extract")
    parser.add_argument("--url", type=str, help="URL to fetch and extract")
    parser.add_argument("--html", type=str, help="Inline HTML snippet to extract")
    parser.add_argument("--format", choices=["markdown", "html"], default="markdown", help="Output format")
    parser.add_argument("--sample", action="store_true", help="Run on standard sample HTML")
    args = parser.parse_args()

    svc = PulpieService(PulpieConfig.from_env())

    if args.status:
        st = svc.status()
        print(json.dumps(st, indent=2))
        return

    if args.url:
        print(f"Fetching and cleaning {args.url}...")
        res = asyncio.run(svc.clean_web_page(args.url, output_format=args.format))
        print(json.dumps(res.to_dict(), indent=2))
        return

    html_content = ""
    if args.file:
        html_content = Path(args.file).read_text(encoding="utf-8")
    elif args.html:
        html_content = args.html
    elif args.sample:
        html_content = """
        <html>
        <head><title>Sample Article</title></head>
        <body>
          <header><nav>Home | About | Contact</nav></header>
          <main>
            <h1>Real Content Heading</h1>
            <p>This is the central article content that should be preserved.</p>
            <ul><li>Item 1</li><li>Item 2</li></ul>
          </main>
          <footer>Copyright 2026 Boilerplate Inc.</footer>
        </body>
        </html>
        """
    else:
        parser.print_help()
        sys.exit(1)

    res = svc.clean_html(html_content, output_format=args.format)
    print("---------------- EXTRACTION RESULT ----------------")
    print(res.content)
    print("---------------- METRICS ----------------")
    print(f"Format:            {res.format}")
    print(f"Blocks kept/total: {res.n_main} / {res.n_blocks}")
    print(f"Input chars:       {res.char_count_in}")
    print(f"Output chars:      {res.char_count_out}")
    print(f"Token savings:     {res.token_savings_pct:.1f}%")
    print(f"Compression ratio: {res.compression_ratio:.3f}")
    print(f"Used fallback:     {res.used_fallback} (Method: {res.fallback_method or 'Pulpie neural model'})")
    print(f"Latency:           {res.latency_ms:.2f} ms")


if __name__ == "__main__":
    main()
