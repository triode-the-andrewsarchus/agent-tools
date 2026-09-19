# ID Protection & Hallucination Prevention Policy — id_tokenizer Integration

You have access to the `id_tokenizer` MCP server for identifier sanitization, token reduction, and pattern protection.

## Delegation Policy

1. **Protect LLMs from Raw UUIDs**:
   Whenever preparing prompts or sending tasks to subagents, local workers, or external models that reference concrete database UUIDs, invoke `substitute_ids` first. The model will reason over lightweight `${UUID_N}` placeholders, completely eliminating flipped-nibble hallucinations.

2. **Restore Placeholders in Agent Output**:
   When downstream responses are received, pass them to `restore_ids` before presenting final results to the user or writing to database records. Check `unknown_placeholders`: if any appear, treat them as model hallucinations.

3. **Pattern-Hiding for Sequential IDs**:
   Do not expose raw sequential integer IDs in public-facing interfaces, test fixtures, or external outputs when auto-increment order leaks sensitive metrics. Use `encode_id` with `style="shuffled"` or `style="faux-uuid"`.

4. **Divisibility Guarantees**:
   For integer identification where hallucination could cause silent corruption, protect values using `style="factor"`.
