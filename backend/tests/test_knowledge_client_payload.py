"""knowledge RAGFlowClient payload 组装单测——扩参回归（permission/language/pagerank）。"""

from typing import Any

import pytest

from app.extensions.knowledge.client import RAGFlowClient


class _CaptureHttp:
    """替换 httpx.AsyncClient：捕获 post/put 的 json payload，返回固定成功响应。"""

    captured: dict[str, Any] = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    # post/put 须为 async：client.py 里是 `await client.post(...)`（同步返回会被 await 拒绝）
    async def post(self, url, headers=None, json=None):
        _CaptureHttp.captured["post"] = {"url": url, "json": json}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"code": 0, "data": {"id": "ds-1"}}

        return _Resp()

    async def put(self, url, headers=None, json=None):
        _CaptureHttp.captured["put"] = {"url": url, "json": json}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"code": 0}

        return _Resp()


@pytest.fixture
def capture_http(monkeypatch):
    _CaptureHttp.captured = {}
    monkeypatch.setattr("httpx.AsyncClient", _CaptureHttp)
    return _CaptureHttp.captured


@pytest.mark.asyncio
async def test_create_dataset_payload_with_permission(capture_http):
    client = RAGFlowClient()
    await client.create_dataset(
        name="kb-a",
        description="d",
        embedding_model="bge-m3",
        chunk_method="laws",
        parser_config={"chunk_token_num": 256},
        permission="team",
    )
    payload = capture_http["post"]["json"]
    # v1.0 契约：parse_type=1 + parser_id 映射；description 不进 create（内部两步化）
    assert payload["parse_type"] == 1
    assert payload["parser_id"] == "laws"
    assert "chunk_method" not in payload
    assert "description" not in payload
    assert payload["permission"] == "team"
    assert payload["parser_config"] == {"chunk_token_num": 256}
    # description 经 create 后 update 补
    assert capture_http["put"]["json"] == {"description": "d"}


@pytest.mark.asyncio
async def test_create_dataset_permission_none_omitted(capture_http):
    client = RAGFlowClient()
    await client.create_dataset(name="kb-b")
    payload = capture_http["post"]["json"]
    assert "permission" not in payload
    # v1.0 BuiltIn 必须显式 parser_id：缺省 naive（服务端兜底不变量）
    assert payload["parse_type"] == 1
    assert payload["parser_id"] == "naive"


@pytest.mark.asyncio
async def test_update_dataset_full_kwargs(capture_http):
    client = RAGFlowClient()
    await client.update_dataset(
        "ds-1",
        parser_config={"chunk_token_num": 384},
        language="Chinese",
        pagerank=0,
        permission="me",
    )
    payload = capture_http["put"]["json"]
    assert payload == {
        "parser_config": {"chunk_token_num": 384},
        "language": "Chinese",
        "pagerank": 0,
        "permission": "me",
    }


@pytest.mark.asyncio
async def test_update_dataset_none_fields_omitted(capture_http):
    client = RAGFlowClient()
    await client.update_dataset("ds-1", name="renamed")
    assert capture_http["put"]["json"] == {"name": "renamed"}
