"""Verify the static data-source instruction is present in the rendered system prompt."""

from deerflow.agents.lead_agent.prompt import apply_prompt_template


def test_system_prompt_mentions_data_source_tools():
    # agent_name left default (None) to avoid the unrelated custom-agent soul
    # path (paths.user_agent_dir AttributeError in agents_config — pre-existing).
    prompt = apply_prompt_template()
    assert "list_data_sources" in prompt
    assert "query_data_source" in prompt
    assert "外部数据源" in prompt
