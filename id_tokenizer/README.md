# id-tokenizer — ID Tokenizer & Protection Component

Convert opaque identifiers into LLM-friendly phrases and placeholders for reliable AI referencing, hallucination prevention, and token reduction.

## Highlights

- **UUID Substitution**: `substitute_ids` and `restore_ids` swap UUIDs for `${UUID_N}` placeholders so models physically cannot hallucinate UUIDs.
- **Token-Optimized Word Lists**: Words chosen from the intersection of GPT-4, GPT-4o, Gemma, and Llama 3 tokenizers to guarantee 1 token per word.
- **O(n) Hashing & Validation**: xxHash64 direct slot indexing with precomputed bloom filters and FNV-1a checksums.
- **Pattern-Hiding & Faux UUIDs**: Salted Feistel permutations convert auto-increment integers into scattered numbers or authentic UUID-shaped identifiers.
- **Prime Factor Encoding**: Divisibility checks catch fabricated numeric IDs with ~99% error detection rates.

## MCP Server

Exposes tools:
- `substitute_ids`
- `restore_ids`
- `encode_id`
- `decode_id`
- `id_tokenizer_status`
