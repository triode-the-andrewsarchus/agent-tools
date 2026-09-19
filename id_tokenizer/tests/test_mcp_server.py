import json
import pytest
from id_tokenizer.mcp_server import make_mcp_server


@pytest.fixture
def mcp():
    return make_mcp_server()


@pytest.mark.asyncio
async def test_substitute_and_restore(mcp):
    # Find tools from mcp server
    tools = {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}
    assert "substitute_ids" in tools
    assert "restore_ids" in tools

    raw_text = "Check order 550e8400-e29b-41d4-a716-446655440000 against customer 6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    sub_res_str = await tools["substitute_ids"](text=raw_text, registry_id="test_session")
    sub_res = json.loads(sub_res_str)

    assert sub_res["total_uuids_found"] == 2
    assert "${UUID_" in sub_res["sanitized_text"]
    assert "550e8400" not in sub_res["sanitized_text"]

    # Now simulate model response using the placeholders
    model_response = f"Analyzed {sub_res['sanitized_text']} successfully."
    restore_res_str = await tools["restore_ids"](text=model_response, registry_id="test_session")
    restore_res = json.loads(restore_res_str)

    assert restore_res["restored_count"] == 2
    assert "550e8400-e29b-41d4-a716-446655440000" in restore_res["restored_text"]
    assert "6ba7b810-9dad-11d1-80b4-00c04fd430c8" in restore_res["restored_text"]
    assert len(restore_res["unknown_placeholders"]) == 0


@pytest.mark.asyncio
async def test_restore_unknown_placeholder(mcp):
    tools = {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}
    text_with_hallucination = "Result ${UUID_9999999} not found."
    restore_res_str = await tools["restore_ids"](text=text_with_hallucination, registry_id="test_session_empty")
    restore_res = json.loads(restore_res_str)
    # The registry has no UUID_9999999
    # If registry not found or empty
    if "error" in restore_res:
        assert "not found" in restore_res["error"]
    else:
        assert "${UUID_9999999}" in restore_res["unknown_placeholders"]


@pytest.mark.asyncio
async def test_encode_and_decode_id(mcp):
    tools = {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}

    # 1. UUID with token style
    orig_uuid = "550e8400-e29b-41d4-a716-446655440000"
    enc_str = await tools["encode_id"](value=orig_uuid, style="token", vocab_size=2048)
    enc = json.loads(enc_str)
    assert "encoded" in enc

    dec_str = await tools["decode_id"](encoded=enc["encoded"], style="token", vocab_size=2048)
    dec = json.loads(dec_str)
    assert dec["is_valid"] is True
    assert dec["decoded"].lower() == orig_uuid.lower()

    # 2. Integer with faux-uuid style
    orig_int = 42
    enc_faux_str = await tools["encode_id"](value=str(orig_int), style="faux-uuid", salt="my-salt")
    enc_faux = json.loads(enc_faux_str)
    assert len(enc_faux["encoded"]) == 36

    dec_faux_str = await tools["decode_id"](encoded=enc_faux["encoded"], style="faux-uuid", salt="my-salt")
    dec_faux = json.loads(dec_faux_str)
    assert dec_faux["is_valid"] is True
    assert dec_faux["decoded"] == orig_int


@pytest.mark.asyncio
async def test_status_tool(mcp):
    tools = {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}
    status_str = await tools["id_tokenizer_status"]()
    status = json.loads(status_str)
    assert status["service"] == "id_tokenizer"
    assert "vocabularies" in status
