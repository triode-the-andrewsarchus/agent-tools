"""MCP Server exposing ID Tokenizer and Substitution tools for LLM agent pipelines."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import uuid as _uuid
from typing import Annotated, Any, Dict, Optional

from mcp.server.mcpserver import MCPServer

from ._registry import FileRegistry, MemoryRegistry, UuidRegistry
from ._substitution import PLACEHOLDER_RE, UUID_RE, restore, substitute
from .id_tokenizer import Codec
from .shuffle import (
    factor_decode,
    factor_encode,
    faux_uuid_to_int,
    int_to_faux_uuid,
    shuffle_decode,
    shuffle_encode,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

# Cache of in-memory registries by identifier
_REGISTRIES: Dict[str, UuidRegistry] = {}


def _get_or_create_registry(
    registry_id: Optional[str] = None,
    registry_file: Optional[str] = None,
    factor: int = 97,
    mix: bool = True,
) -> UuidRegistry:
    if registry_file:
        return FileRegistry(registry_file, factor=factor, mix=mix)
    reg_id = registry_id or "default"
    if reg_id not in _REGISTRIES:
        _REGISTRIES[reg_id] = MemoryRegistry(factor=factor, mix=mix)
    return _REGISTRIES[reg_id]


def _fmt(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


def make_mcp_server() -> MCPServer:
    mcp = MCPServer(
        name="id_tokenizer",
        version="0.1.0",
        instructions=(
            "id_tokenizer protects LLMs from hallucinating opaque identifiers (UUIDs, sequential database IDs), "
            "reduces token consumption, and hides sequential patterns. "
            "Use substitute_ids before prompting an LLM to replace UUIDs with safe placeholders (${UUID_N}), "
            "and restore_ids after receiving responses to recover originals. "
            "Use encode_id and decode_id for token-optimized or memorable word phrases, faux UUIDs, and factor validation."
        ),
    )

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="substitute_ids",
        description=(
            "Scan text for RFC 4122 UUIDs and substitute them with short placeholders (e.g. ${UUID_123}) "
            "before passing text to an LLM. The LLM never sees real UUIDs, eliminating ID hallucination. "
            "Stores mappings in an in-memory or file-backed registry so originals can be restored later."
        ),
    )
    async def substitute_ids(
        text: Annotated[str, "Input text containing raw UUIDs to sanitize"],
        registry_id: Annotated[
            Optional[str],
            "Optional identifier for the in-memory registry session (default: 'default')",
        ] = "default",
        registry_file: Annotated[
            Optional[str],
            "Optional path to a JSON file to persist UUID mappings across process invocations",
        ] = None,
        factor: Annotated[
            int,
            "Prime factor multiplier for placeholder suffix validation (default: 97)",
        ] = 97,
        mix: Annotated[
            bool,
            "Whether to apply Feistel permutation to make placeholder suffixes non-sequential (default: true)",
        ] = True,
    ) -> str:
        reg = _get_or_create_registry(
            registry_id=registry_id,
            registry_file=registry_file,
            factor=factor,
            mix=mix,
        )
        # Find raw UUID matches before substitution
        matches = UUID_RE.findall(text)
        unique_matches = set(m.lower() for m in matches)

        sanitized, _ = substitute(text, reg)

        result = {
            "sanitized_text": sanitized,
            "total_uuids_found": len(matches),
            "unique_uuids_substituted": len(unique_matches),
            "registry_id": registry_id if not registry_file else None,
            "registry_file": registry_file,
            "active_registry_size": len(reg),
        }
        return _fmt(result)

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="restore_ids",
        description=(
            "Restore original UUIDs into an LLM response containing ${UUID_N} placeholders. "
            "Uses the registry populated during substitute_ids. Any unrecognized or hallucinated placeholders "
            "are preserved as-is and reported in unknown_placeholders."
        ),
    )
    async def restore_ids(
        text: Annotated[str, "LLM response text containing ${UUID_N} placeholders"],
        registry_id: Annotated[
            Optional[str],
            "Identifier of the in-memory registry session used during substitution (default: 'default')",
        ] = "default",
        registry_file: Annotated[
            Optional[str],
            "Path to the JSON registry file used during substitution",
        ] = None,
    ) -> str:
        reg: Optional[UuidRegistry] = None
        if registry_file:
            reg = FileRegistry(registry_file)
        else:
            reg_id = registry_id or "default"
            reg = _REGISTRIES.get(reg_id)

        if reg is None:
            return _fmt({
                "restored_text": text,
                "restored_count": 0,
                "unknown_placeholders": [],
                "error": f"Registry '{registry_id or registry_file}' not found. Run substitute_ids first.",
            })

        placeholders_found = PLACEHOLDER_RE.findall(text)
        unknown: list[str] = []
        for p in placeholders_found:
            k = p[2:-1]
            if reg.fetch(k) is None:
                unknown.append(p)

        restored = restore(text, reg)
        restored_count = len(placeholders_found) - len(unknown)

        return _fmt({
            "restored_text": restored,
            "placeholders_found": len(placeholders_found),
            "restored_count": restored_count,
            "unknown_placeholders": unknown,
        })

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="encode_id",
        description=(
            "Encode a UUID or integer into a word phrase, numeric string, faux-UUID, or factor-protected ID. "
            "Styles: 'token' (LLM token-optimized words, 1 token/word), 'memorable' (real English words), "
            "'numeric' (128-bit integer, ~40% fewer tokens for UUIDs), 'shuffled' (salted permutation), "
            "'faux-uuid' (maps integer to UUID format via salted Feistel), or 'factor' (divisibility check)."
        ),
    )
    async def encode_id(
        value: Annotated[str, "The UUID or integer value to encode"],
        id_type: Annotated[
            Optional[str],
            "Encoding type: 'uuid', 'int', 'u32', 'u64', 'u128'. Auto-detected if omitted.",
        ] = None,
        style: Annotated[
            str,
            "Encoding style: 'token' (default), 'memorable', 'numeric', 'shuffled', 'faux-uuid', 'factor'",
        ] = "token",
        vocab_size: Annotated[
            int,
            "Vocabulary size for word styles: 2048 (default), 4096, 8192, 16384, 32768",
        ] = 2048,
        separator: Annotated[str, "Separator between words (default: '-')"] = "-",
        salt: Annotated[str, "Secret salt for 'shuffled' or 'faux-uuid' styles"] = "",
        factor: Annotated[int, "Prime multiplier for 'factor' style (default: 97)"] = 97,
        min_digits: Annotated[int, "Minimum digits for 'shuffled' style (default: 3)"] = 3,
    ) -> str:
        clean_val = value.strip()
        eff_type = id_type

        # Auto-detect if not specified
        if not eff_type:
            try:
                _uuid.UUID(clean_val)
                eff_type = "uuid"
            except Exception:
                try:
                    int(clean_val)
                    eff_type = "int"
                except Exception:
                    eff_type = "uuid"

        try:
            if style == "numeric":
                if eff_type == "uuid":
                    n = int.from_bytes(_uuid.UUID(clean_val).bytes, "big")
                    encoded = str(n)
                else:
                    encoded = str(int(clean_val))
                return _fmt({
                    "encoded": encoded,
                    "id_type": eff_type,
                    "style": style,
                    "token_estimate": 13 if eff_type == "uuid" else len(encoded) // 3 + 1,
                })

            elif style == "faux-uuid":
                n = int(clean_val)
                encoded = int_to_faux_uuid(n, salt=salt)
                return _fmt({
                    "encoded": encoded,
                    "id_type": eff_type,
                    "style": style,
                    "salt_used": bool(salt),
                })

            elif style == "shuffled":
                n = int(clean_val)
                encoded = shuffle_encode(n, min_digits=min_digits, salt=salt)
                return _fmt({
                    "encoded": encoded,
                    "id_type": eff_type,
                    "style": style,
                    "digits": len(encoded),
                    "salt_used": bool(salt),
                })

            elif style == "factor":
                n = int(clean_val)
                encoded = str(factor_encode(n, factor=factor))
                return _fmt({
                    "encoded": encoded,
                    "id_type": eff_type,
                    "style": style,
                    "factor": factor,
                })

            elif style in ("token", "memorable"):
                codec = Codec(vocab_size=vocab_size, style=style)
                if eff_type == "uuid":
                    phrase = codec.uuid_to_words(clean_val)
                elif eff_type == "int":
                    phrase = codec.int_to_words(int(clean_val))
                elif eff_type == "u32":
                    phrase = codec.u32_to_words(int(clean_val))
                elif eff_type == "u64":
                    phrase = codec.u64_to_words(int(clean_val))
                elif eff_type == "u128":
                    phrase = codec.u128_to_words(int(clean_val))
                else:
                    phrase = codec.uuid_to_words(clean_val)

                if separator != "-":
                    phrase = phrase.replace("-", separator)

                words_count = len(phrase.split(separator))
                return _fmt({
                    "encoded": phrase,
                    "id_type": eff_type,
                    "style": style,
                    "vocab_size": vocab_size,
                    "word_count": words_count,
                    "token_estimate": words_count if style == "token" else round(words_count * 1.2),
                })
            else:
                return _fmt({"error": f"Unsupported style: {style}"})

        except Exception as e:
            return _fmt({"error": str(e), "value": value, "id_type": eff_type, "style": style})

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="decode_id",
        description=(
            "Decode an encoded identifier back to the original UUID or integer. "
            "Validates checksums, bloom filters, and factor divisibility to catch hallucinated, "
            "tampered, or invalid IDs."
        ),
    )
    async def decode_id(
        encoded: Annotated[str, "The encoded phrase, numeric string, faux-UUID, or factor value"],
        id_type: Annotated[
            Optional[str],
            "Expected ID type: 'uuid', 'int', 'u32', 'u64', 'u128'. Auto-detected if omitted.",
        ] = None,
        style: Annotated[
            str,
            "Encoding style used during encode: 'token' (default), 'memorable', 'numeric', 'shuffled', 'faux-uuid', 'factor'",
        ] = "token",
        vocab_size: Annotated[
            int,
            "Vocabulary size for word styles: 2048 (default), 4096, 8192, 16384, 32768",
        ] = 2048,
        salt: Annotated[str, "Secret salt used at encode time for 'shuffled' or 'faux-uuid' styles"] = "",
        factor: Annotated[int, "Prime multiplier used at encode time for 'factor' style (default: 97)"] = 97,
        min_digits: Annotated[int, "Minimum digits used at encode time for 'shuffled' style (default: 3)"] = 3,
    ) -> str:
        clean = encoded.strip()
        eff_type = id_type

        try:
            if style == "numeric":
                n = int(clean)
                if eff_type == "uuid" or (eff_type is None and n >= 2**64):
                    # 128-bit UUID integer
                    raw_bytes = n.to_bytes(16, "big")
                    return _fmt({
                        "decoded": str(_uuid.UUID(bytes=raw_bytes)),
                        "is_valid": True,
                        "id_type": "uuid",
                        "style": style,
                    })
                return _fmt({
                    "decoded": n,
                    "is_valid": True,
                    "id_type": "int",
                    "style": style,
                })

            elif style == "faux-uuid":
                decoded_int = faux_uuid_to_int(clean, salt=salt)
                return _fmt({
                    "decoded": decoded_int,
                    "is_valid": True,
                    "id_type": "int",
                    "style": style,
                })

            elif style == "shuffled":
                decoded_int = shuffle_decode(clean, min_digits=min_digits, salt=salt)
                return _fmt({
                    "decoded": decoded_int,
                    "is_valid": True,
                    "id_type": "int",
                    "style": style,
                })

            elif style == "factor":
                decoded_int = factor_decode(int(clean), factor=factor)
                return _fmt({
                    "decoded": decoded_int,
                    "is_valid": True,
                    "id_type": "int",
                    "style": style,
                })

            elif style in ("token", "memorable"):
                codec = Codec(vocab_size=vocab_size, style=style)
                # Normalize spaces to hyphens for decoding
                phrase = re.sub(r"\s+", "-", clean)
                word_count = len(phrase.split("-"))

                # Auto-detect uuid vs int if not specified
                if not eff_type:
                    expected_uuid_words = codec.uuid_word_count()
                    if word_count == expected_uuid_words:
                        eff_type = "uuid"
                    else:
                        eff_type = "int"

                if eff_type == "uuid":
                    decoded = codec.words_to_uuid(phrase)
                elif eff_type == "int":
                    decoded = codec.words_to_int(phrase)
                elif eff_type == "u32":
                    decoded = codec.words_to_u32(phrase)
                elif eff_type == "u64":
                    decoded = codec.words_to_u64(phrase)
                elif eff_type == "u128":
                    decoded = codec.words_to_u128(phrase)
                else:
                    decoded = codec.words_to_uuid(phrase)

                return _fmt({
                    "decoded": decoded,
                    "is_valid": True,
                    "id_type": eff_type,
                    "style": style,
                    "checksum_valid": True,
                })
            else:
                return _fmt({"is_valid": False, "error": f"Unsupported style: {style}"})

        except Exception as e:
            return _fmt({
                "is_valid": False,
                "error": str(e),
                "encoded": encoded,
                "style": style,
            })

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="id_tokenizer_status",
        description="Check ID Tokenizer service status, supported styles, vocabularies, and active registries.",
    )
    async def id_tokenizer_status() -> str:
        return _fmt({
            "service": "id_tokenizer",
            "version": "0.1.0",
            "active_in_memory_registries": len(_REGISTRIES),
            "registry_names": list(_REGISTRIES.keys()),
            "vocabularies": [2048, 4096, 8192, 16384, 32768],
            "styles": ["token", "memorable", "numeric", "shuffled", "faux-uuid", "factor"],
            "features": [
                "UUID substitution & restoration",
                "O(n) token-optimized single-token word encoding",
                "Bloom filter & FNV-1a checksum validation",
                "Salted Feistel pattern hiding",
                "Faux UUID generation",
                "Prime factor hallucination detection",
            ],
            "native_engine": "Rust (PyO3)",
        })

    return mcp


async def async_main() -> None:
    log.info("Starting id_tokenizer MCP server...")
    mcp = make_mcp_server()
    await mcp.run_stdio_async()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
