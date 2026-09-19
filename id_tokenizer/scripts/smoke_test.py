#!/usr/bin/env python3
"""Interactive smoke test CLI for id_tokenizer component."""

import argparse
import asyncio
import json
import sys

from id_tokenizer import Codec, restore, substitute
from id_tokenizer.mcp_server import make_mcp_server


def run_smoke_test() -> None:
    print("=== ID Tokenizer Smoke Test ===")

    # 1. UUID Substitution
    sample_text = (
        "User 550e8400-e29b-41d4-a716-446655440000 placed order "
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8 on item 550e8400-e29b-41d4-a716-446655440000."
    )
    print(f"\n[1] Original Text:\n  {sample_text}")
    sanitized, reg = substitute(sample_text)
    print(f"  Sanitized (for LLM):\n  {sanitized}")
    assert "550e8400" not in sanitized
    assert "${UUID_" in sanitized

    restored = restore(sanitized, reg)
    print(f"  Restored (from LLM response):\n  {restored}")
    assert restored == sample_text
    print("  ✓ UUID substitution & restoration verified.")

    # 2. Token-Optimized Codec
    c = Codec(vocab_size=2048, style="token")
    phrase = c.uuid_to_words("550e8400-e29b-41d4-a716-446655440000")
    print(f"\n[2] Token-optimized words (2048 vocab):\n  {phrase}")
    roundtrip_uuid = c.words_to_uuid(phrase)
    assert roundtrip_uuid == "550e8400-e29b-41d4-a716-446655440000"
    print("  ✓ Token-optimized codec round-trip verified.")

    # 3. Integer to words
    int_phrase = c.int_to_words(42)
    assert c.words_to_int(int_phrase) == 42
    print(f"\n[3] Variable-length int 42 -> '{int_phrase}' -> 42")
    print("  ✓ Integer codec round-trip verified.")

    # 4. MCP Server Tools check
    mcp = make_mcp_server()
    tools = [t.name for t in mcp._tool_manager.list_tools()]
    print(f"\n[4] Registered MCP Tools: {tools}")
    assert "substitute_ids" in tools
    assert "restore_ids" in tools
    assert "encode_id" in tools
    assert "decode_id" in tools
    assert "id_tokenizer_status" in tools
    print("  ✓ MCP server tools verified.")

    print("\nALL SMOKE TESTS PASSED!")


def main() -> None:
    parser = argparse.ArgumentParser(description="id_tokenizer smoke test")
    parser.add_argument("--status", action="store_true", help="Print MCP server status")
    args = parser.parse_args()

    if args.status:
        mcp = make_mcp_server()
        tools = {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}
        res = asyncio.run(tools["id_tokenizer_status"]())
        print(res)
        return

    run_smoke_test()


if __name__ == "__main__":
    main()
