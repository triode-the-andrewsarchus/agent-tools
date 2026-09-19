---
name: id-token-nicer
description: Protects LLMs from hallucinating opaque identifiers (UUIDs, sequential database IDs), minimizes token consumption, and hides sequential patterns using the id_tokenizer MCP tools.
---

# ID Token Nicer (`id_tokenizer`) — Skill Reference

LLM agents have well-documented failure modes when handling opaque identifiers:
1. **Hallucination**: LLMs often subtly alter or flip characters in raw UUIDs (`550e8400-e29b-41d4-a716-446655440000` -> `...-0001`), producing valid-looking but phantom identifiers.
2. **Token Waste**: Raw UUIDs consume 18–23 BPE tokens each in GPT-4/4o.
3. **Sequential Pattern Leakage**: Sequential IDs (`1, 2, 3...`) lead models to predict adjacent rows or leak database table volume.
4. **Public vs Private ID Mismatches**: Auto-increment integer databases often need UUID-shaped public identifiers without modifying database schemas.

The `id_tokenizer` MCP server provides bidirectional solutions:

---

## When to Use `id_tokenizer`

### 1. Mandatory for UUID-Heavy LLM Invocations
- When drafting prompts that contain raw UUIDs (customer IDs, transaction IDs, session tokens, trace IDs).
- **Call `substitute_ids`** before handing text to a model or worker: replaces UUIDs with safe placeholders like `${UUID_123}`. The model physically cannot hallucinate a UUID because it never sees one!
- **Call `restore_ids`** on the model's output to swap the real UUIDs back into place.
- If `unknown_placeholders` is non-empty in the `restore_ids` output, the model invented a placeholder (e.g. `${UUID_999}`) that never existed in the prompt — immediate hallucination detected!

### 2. For Context Window Efficiency & Token Budgeting
- Encode UUIDs into token-optimized word sequences (`style="token"`): each word is guaranteed to be exactly **1 token** across GPT-4, GPT-4o, Gemma, and Llama 3 tokenizers.
- Or encode into raw integer numeric format (`style="numeric"`), cutting token costs by **~40%** (13 tokens vs 22 tokens).

### 3. For Pattern Hiding & Obfuscation
- Use `style="shuffled"` with a secret salt to map sequential integer IDs (`1, 2, 3`) into scattered non-sequential integers while preserving digit count.
- Use `style="faux-uuid"` with a secret salt to generate deterministic, bijective UUID-formatted identifiers from integer primary keys without altering underlying tables.

### 4. For Hallucination Detection in Integers
- Use `style="factor"` with a prime factor (default 97). On decode, divisibility is checked; randomly invented numbers have only a ~1% chance of passing validation.

---

## MCP Tools Reference

### `substitute_ids`
Sanitizes text by replacing all RFC 4122 UUIDs with `${UUID_N}` placeholders.

```json
{
  "text": "Compare transaction 550e8400-e29b-41d4-a716-446655440000 with 6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "registry_id": "investigation-1"
}
```

**Output:**
```json
{
  "sanitized_text": "Compare transaction ${UUID_1} with ${UUID_2}",
  "total_uuids_found": 2,
  "unique_uuids_substituted": 2,
  "registry_id": "investigation-1",
  "active_registry_size": 2
}
```

### `restore_ids`
Restores original UUIDs from model response text.

```json
{
  "text": "Transaction ${UUID_1} settled before ${UUID_2}.",
  "registry_id": "investigation-1"
}
```

**Output:**
```json
{
  "restored_text": "Transaction 550e8400-e29b-41d4-a716-446655440000 settled before 6ba7b810-9dad-11d1-80b4-00c04fd430c8.",
  "placeholders_found": 2,
  "restored_count": 2,
  "unknown_placeholders": []
}
```

### `encode_id`
Encodes an identifier into a safe representation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `value` | string | *required* | The UUID or integer value |
| `id_type` | string | `null` | `uuid`, `int`, `u32`, `u64`, `u128` (auto-detected) |
| `style` | string | `"token"` | `"token"`, `"memorable"`, `"numeric"`, `"shuffled"`, `"faux-uuid"`, `"factor"` |
| `vocab_size` | int | `2048` | `2048`, `4096`, `8192`, `16384`, `32768` |
| `salt` | string | `""` | Secret salt for `shuffled` and `faux-uuid` |
| `factor` | int | `97` | Prime factor for `factor` style |
| `min_digits` | int | `3` | Minimum digits for `shuffled` |

### `decode_id`
Decodes an encoded representation back to the original UUID or integer. Verifies bloom filter, checksum, or factor divisibility.

```json
{
  "encoded": "nil-azzo-fun-also-oop-ized-eps-lsa-apk-hai-ived-ddb",
  "style": "token",
  "vocab_size": 2048
}
```

**Output:**
```json
{
  "decoded": "550e8400-e29b-41d4-a716-446655440000",
  "is_valid": true,
  "id_type": "uuid",
  "style": "token",
  "checksum_valid": true
}
```

---

## Recommended Agent Workflow

```
Raw Text with UUIDs
       │
       ▼
[substitute_ids] ──► Sanitized text with ${UUID_N}
                            │
                            ▼
               LLM Reasoning / Worker Pool
                            │
                            ▼
                  LLM Output with ${UUID_N}
                            │
                            ▼
  [restore_ids] ──► Original UUIDs safely restored
```
