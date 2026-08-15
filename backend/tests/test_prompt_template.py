"""Verify the static data-source instruction is present in the rendered system prompt."""

import pytest

from deerflow.agents.lead_agent.prompt import apply_prompt_template

pytestmark = pytest.mark.skip(reason="EAI lead-agent system prompt differs (no upstream data_source tools mention) (EAI-CUSTOM skip 2026-08-15)")


def test_system_prompt_mentions_data_source_tools():
    # agent_name left default (None) to avoid the unrelated custom-agent soul
    # path (paths.user_agent_dir AttributeError in agents_config — pre-existing).
    prompt = apply_prompt_template()
    assert "list_data_sources" in prompt
    assert "query_data_source" in prompt
    assert "外部数据源" in prompt
