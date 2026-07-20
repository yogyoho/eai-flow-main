"""回归测试: sse_consumer 缓冲 values 全量快照(bug-174)。

Found by /qa on 2026-07-20.
Report: bug-174 — useStream trackStreamMode 把 values 加回 streamMode, 后端
worker.py 也主动 publish values, 导致流式 run 每个 node 重发整条消息历史
(长报告 payload 爆炸 + 前端 mergeMessages 全量处理 + 渲染全量 re-parse)。
修复: sse_consumer 缓冲 values 只留最后一个, end 前补发, 保留 run 最终 state。
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest

pytestmark = pytest.mark.asyncio


async def test_sse_consumer_buffers_midstream_values_only_emits_last_before_end() -> None:
    """流式期间多个 values 全量快照只保留最后一个, end 前补发。"""
    from app.gateway.services import sse_consumer
    from deerflow.runtime import MemoryStreamBridge, RunManager, RunStatus

    bridge = MemoryStreamBridge()
    run_manager = RunManager()
    record = await run_manager.create("thread-values-buffer")
    await run_manager.set_status(record.run_id, RunStatus.running)

    await bridge.publish(
        record.run_id,
        "metadata",
        {"run_id": record.run_id, "thread_id": record.thread_id},
    )
    # 流式期间多个 values 全量快照(模拟多 node 执行, 每次都带完整 messages 历史)
    await bridge.publish(
        record.run_id,
        "values",
        {"title": "v1", "messages": [{"type": "ai", "content": "a"}]},
    )
    await bridge.publish(
        record.run_id,
        "values",
        {"title": "v2", "messages": [{"type": "ai", "content": "ab"}]},
    )
    await bridge.publish(
        record.run_id,
        "values",
        {"title": "final", "messages": [{"type": "ai", "content": "done"}]},
    )
    # 其他事件类型应原样透传, 不受 values 缓冲影响
    await bridge.publish(record.run_id, "updates", {"node": "lead_agent"})
    await bridge.publish_end(record.run_id)  # 触发 END_SENTINEL

    # run 正常结束, 标记 terminal 避免 sse_consumer finally 触发 cancel
    await run_manager.set_status(record.run_id, RunStatus.success)

    class _ConnectedRequest:
        headers: dict[str, str] = {}

        async def is_disconnected(self) -> bool:
            return False

    frames: list[str] = []
    async for frame in sse_consumer(bridge, record, _ConnectedRequest(), run_manager):
        frames.append(frame)

    event_types = [
        re.match(r"event: (\w+)", f).group(1) for f in frames if f.startswith("event: ")
    ]
    # 中间 v1/v2 被缓冲丢弃; 只在 end 前补发最终 values(final); updates 原样透传
    assert event_types == ["metadata", "updates", "values", "end"], event_types

    # 补发的 values 必须是最后一个(final), 不是中间的 v1/v2
    values_frame = next(f for f in frames if f.startswith("event: values"))
    values_data = json.loads(values_frame.split("data: ", 1)[1].split("\n", 1)[0])
    assert values_data["title"] == "final", values_data
    assert values_data["messages"][-1]["content"] == "done"


async def test_sse_consumer_drop_values_disabled_passes_all_through(monkeypatch) -> None:
    """GATEWAY_SSE_DROP_VALUES=false 时, values 原样透传(回滚开关有效)。"""
    import app.gateway.services as services
    from app.gateway.services import sse_consumer
    from deerflow.runtime import MemoryStreamBridge, RunManager, RunStatus

    bridge = MemoryStreamBridge()
    run_manager = RunManager()
    record = await run_manager.create("thread-values-passthrough")
    await run_manager.set_status(record.run_id, RunStatus.running)

    await bridge.publish(record.run_id, "metadata", {"run_id": record.run_id})
    await bridge.publish(record.run_id, "values", {"title": "v1"})
    await bridge.publish(record.run_id, "values", {"title": "v2"})
    await bridge.publish_end(record.run_id)
    await run_manager.set_status(record.run_id, RunStatus.success)

    class _ConnectedRequest:
        headers: dict[str, str] = {}

        async def is_disconnected(self) -> bool:
            return False

    monkeypatch.setattr(services, "_SSE_DROP_VALUES", False)

    frames: list[str] = []
    async for frame in sse_consumer(bridge, record, _ConnectedRequest(), run_manager):
        frames.append(frame)

    event_types = [
        re.match(r"event: (\w+)", f).group(1) for f in frames if f.startswith("event: ")
    ]
    # 关闭过滤后, 两个 values 都原样透传
    assert event_types == ["metadata", "values", "values", "end"], event_types
