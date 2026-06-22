"""Tests for DynamicContextMiddleware.

Verifies that memory and current date are injected as a <system-reminder> into
the first HumanMessage exactly once per session (frozen-snapshot pattern).
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from langchain_core.messages import AIMessage, HumanMessage

from deerflow.agents.middlewares.dynamic_context_middleware import (
    _DYNAMIC_CONTEXT_REMINDER_KEY,
    DynamicContextMiddleware,
)

_SYSTEM_REMINDER_TAG = "<system-reminder>"


def _make_middleware(**kwargs) -> DynamicContextMiddleware:
    return DynamicContextMiddleware(**kwargs)


def _fake_runtime():
    return SimpleNamespace(context={})


def _reminder_msg(content: str, msg_id: str) -> HumanMessage:
    """Build a reminder HumanMessage the way the middleware would produce it."""
    return HumanMessage(
        content=content,
        id=msg_id,
        additional_kwargs={"hide_from_ui": True, _DYNAMIC_CONTEXT_REMINDER_KEY: True},
    )


# ---------------------------------------------------------------------------
# Basic injection
# ---------------------------------------------------------------------------


def test_injects_system_reminder_into_first_human_message():
    mw = _make_middleware()
    state = {"messages": [HumanMessage(content="Hello", id="msg-1")]}

    with mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=""), mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
        result = mw.before_agent(state, _fake_runtime())

    assert result is not None
    updated_msgs = result["messages"]
    assert len(updated_msgs) == 2

    reminder_msg = updated_msgs[0]
    assert isinstance(reminder_msg, HumanMessage)
    assert reminder_msg.id == "msg-1"  # takes the original ID (position swap)
    assert reminder_msg.additional_kwargs.get(_DYNAMIC_CONTEXT_REMINDER_KEY) is True
    assert _SYSTEM_REMINDER_TAG in reminder_msg.content
    assert "<current_date>2026-05-08, Friday</current_date>" in reminder_msg.content
    assert "Hello" not in reminder_msg.content  # reminder only — no user text

    user_msg = updated_msgs[1]
    assert isinstance(user_msg, HumanMessage)
    assert user_msg.id == "msg-1__user"  # derived ID
    assert user_msg.content == "Hello"


def test_memory_included_when_present():
    mw = _make_middleware()
    state = {"messages": [HumanMessage(content="Hi", id="msg-1")]}

    with (
        mock.patch(
            "deerflow.agents.lead_agent.prompt._get_memory_context",
            return_value="<memory>\nUser prefers Python.\n</memory>",
        ),
        mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
        result = mw.before_agent(state, _fake_runtime())

    # Reminder is the first returned message; user query is the second
    reminder_content = result["messages"][0].content
    assert "User prefers Python." in reminder_content
    assert "<current_date>2026-05-08, Friday</current_date>" in reminder_content
    assert result["messages"][1].content == "Hi"


# ---------------------------------------------------------------------------
# Project context injection (runtime user_id resolution)
# ---------------------------------------------------------------------------


def test_project_context_injected_via_runtime_user_id():
    """Regression: project_context must be read using runtime.context['user_id']
    (resolve_runtime_user_id), NOT the contextvar (get_effective_user_id, which
    falls back to 'default' in the gateway run path where the contextvar is unset).

    The app layer (enter_project) writes project-context.json under the extensions
    user_id, which equals runtime.context['user_id'] (set by
    inject_authenticated_user_context). If the middleware reads via the contextvar
    instead, it looks under 'default/' and never finds the file.
    """
    mw = _make_middleware()
    runtime_uid = "f8766d55-2b1b-422e-a945-5fcf268a8a39"
    tid = "d6c47689-f85e-4ac2-a825-33b1a57068e9"
    state = {"messages": [HumanMessage(content="Hi", id="m1")]}
    runtime = SimpleNamespace(context={"user_id": runtime_uid, "thread_id": tid})

    with TemporaryDirectory() as tmp:
        # File written by the app layer under the RUNTIME user_id (extensions UUID).
        write_dir = Path(tmp) / "users" / runtime_uid / "threads" / tid
        write_dir.mkdir(parents=True)
        (write_dir / "project-context.json").write_text(
            json.dumps(
                {
                    "project_id": "p1",
                    "project_name": "测试项目-RT",
                    "report_type": "fire_protection_design",
                    "template": {"template_name": "消防模板"},
                }
            ),
            encoding="utf-8",
        )
        # 'default' bucket exists but has NO file for this thread (the bug condition).
        (Path(tmp) / "users" / "default").mkdir(parents=True)

        with (
            mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=""),
            mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt,
            mock.patch("deerflow.config.paths.get_paths") as mock_paths,
        ):
            mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
            mock_paths.return_value = SimpleNamespace(
                thread_dir=lambda thread_id, user_id=None: Path(tmp) / "users" / user_id / "threads" / thread_id
            )
            result = mw.before_agent(state, runtime)

    assert result is not None
    reminder = result["messages"][0].content
    assert "<project_context>" in reminder
    assert "测试项目-RT" in reminder
    assert "fire_protection_design" in reminder


def test_project_context_thread_id_falls_back_to_configurable():
    """Regression (primary bug): the gateway sets thread_id in
    config['configurable']['thread_id'], NOT in runtime.context. before_agent must
    fall back to get_config().configurable.thread_id (mirroring ThreadDataMiddleware);
    otherwise thread_id is None, ``_get_project_context`` is skipped via its
    ``if thread_id`` guard, and project context NEVER reaches the agent.
    """
    mw = _make_middleware()
    runtime_uid = "f8766d55-2b1b-422e-a945-5fcf268a8a39"
    tid = "eaee753f-904b-4fcb-9811-9087716714b2"
    state = {"messages": [HumanMessage(content="Hi", id="m1")]}
    # runtime.context has user_id but NO thread_id (production gateway behavior)
    runtime = SimpleNamespace(context={"user_id": runtime_uid})

    with TemporaryDirectory() as tmp:
        write_dir = Path(tmp) / "users" / runtime_uid / "threads" / tid
        write_dir.mkdir(parents=True)
        (write_dir / "project-context.json").write_text(
            json.dumps(
                {
                    "project_id": "p1",
                    "project_name": "可回退测试",
                    "report_type": "fire_protection_design",
                    "template": {},
                }
            ),
            encoding="utf-8",
        )
        with (
            mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=""),
            mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt,
            mock.patch("deerflow.config.paths.get_paths") as mock_paths,
            mock.patch("langgraph.config.get_config", return_value={"configurable": {"thread_id": tid}}),
        ):
            mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
            mock_paths.return_value = SimpleNamespace(
                thread_dir=lambda thread_id, user_id=None: Path(tmp) / "users" / user_id / "threads" / thread_id
            )
            result = mw.before_agent(state, runtime)

    assert result is not None
    reminder = result["messages"][0].content
    assert "<project_context>" in reminder
    assert "可回退测试" in reminder


# ---------------------------------------------------------------------------
# Frozen-snapshot: no re-injection within a session
# ---------------------------------------------------------------------------


def test_skips_injection_if_already_present():
    """Second turn: separate reminder message already present → no update."""
    mw = _make_middleware()
    reminder_content = "<system-reminder>\n<current_date>2026-05-08, Friday</current_date>\n</system-reminder>"
    state = {
        "messages": [
            _reminder_msg(reminder_content, "msg-1"),
            HumanMessage(content="Hello", id="msg-1__user"),
            AIMessage(content="Hi there"),
            HumanMessage(content="Follow-up", id="msg-2"),
        ]
    }

    with mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
        result = mw.before_agent(state, _fake_runtime())

    assert result is None  # no update needed


def test_injects_only_into_first_human_message_not_later_ones():
    """Reminder targets the first HumanMessage; subsequent messages are not touched."""
    mw = _make_middleware()
    state = {
        "messages": [
            HumanMessage(content="First", id="msg-1"),
            AIMessage(content="Reply"),
            HumanMessage(content="Second", id="msg-2"),
        ]
    }

    with mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=""), mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
        result = mw.before_agent(state, _fake_runtime())

    assert result is not None
    msgs = result["messages"]
    # Only the two injected messages are returned (reminder + original first query)
    assert len(msgs) == 2
    assert msgs[0].id == "msg-1"  # reminder takes first message's ID
    assert msgs[0].additional_kwargs.get(_DYNAMIC_CONTEXT_REMINDER_KEY) is True
    assert _SYSTEM_REMINDER_TAG in msgs[0].content
    assert msgs[1].id == "msg-1__user"  # original content with derived ID
    assert msgs[1].content == "First"
    # "Second" (msg-2) is not in the returned update — it is left unchanged
    assert all(m.id != "msg-2" for m in msgs)


def test_summary_human_message_is_not_used_as_injection_target():
    """After summarization, the synthetic summary HumanMessage is not a user turn."""
    mw = _make_middleware()
    state = {
        "messages": [
            HumanMessage(content="Here is a summary of the conversation to date:\n\n...", id="summary-1", name="summary"),
            AIMessage(content="Earlier reply"),
            HumanMessage(content="Follow-up", id="msg-2"),
        ]
    }

    with mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=""), mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
        result = mw.before_agent(state, _fake_runtime())

    assert result is not None
    msgs = result["messages"]
    assert len(msgs) == 2
    assert msgs[0].id == "msg-2"
    assert msgs[0].additional_kwargs.get(_DYNAMIC_CONTEXT_REMINDER_KEY) is True
    assert msgs[1].id == "msg-2__user"
    assert msgs[1].content == "Follow-up"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_no_messages_returns_none():
    mw = _make_middleware()
    result = mw.before_agent({"messages": []}, _fake_runtime())
    assert result is None


def test_no_human_message_returns_none():
    mw = _make_middleware()
    state = {"messages": [AIMessage(content="assistant only")]}
    with mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=""):
        result = mw.before_agent(state, _fake_runtime())
    assert result is None


def test_list_content_message_handled_as_separate_reminder():
    """List-content (e.g. multi-modal) messages remain intact; reminder is a separate message."""
    mw = _make_middleware()
    original_content = [{"type": "text", "text": "Hello"}]
    state = {"messages": [HumanMessage(content=original_content, id="msg-1")]}

    with mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=""), mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
        result = mw.before_agent(state, _fake_runtime())

    assert result is not None
    msgs = result["messages"]
    assert len(msgs) == 2
    # Reminder is a plain string message with the flag set
    assert isinstance(msgs[0].content, str)
    assert msgs[0].additional_kwargs.get(_DYNAMIC_CONTEXT_REMINDER_KEY) is True
    assert _SYSTEM_REMINDER_TAG in msgs[0].content
    # Original list-content message is untouched
    assert msgs[1].content == original_content


def test_reminder_uses_original_id_user_message_uses_derived_id():
    """Reminder takes original ID (position swap); user message gets {id}__user."""
    mw = _make_middleware()
    original_id = "original-id-abc"
    state = {"messages": [HumanMessage(content="Hello", id=original_id)]}

    with mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=""), mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
        result = mw.before_agent(state, _fake_runtime())

    assert result["messages"][0].id == original_id
    assert result["messages"][1].id == f"{original_id}__user"


def test_message_without_id_gets_stable_uuid():
    """If the original HumanMessage has no ID, a UUID is generated and used consistently."""
    mw = _make_middleware()
    state = {"messages": [HumanMessage(content="Hello", id=None)]}

    with mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=""), mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
        result = mw.before_agent(state, _fake_runtime())

    assert result is not None
    reminder_id = result["messages"][0].id
    user_id = result["messages"][1].id
    assert reminder_id is not None
    assert reminder_id != "None"
    assert user_id == f"{reminder_id}__user"


def test_user_message_containing_system_reminder_tag_does_not_prevent_injection():
    """A user message containing '<system-reminder>' must not be mistaken for a reminder."""
    mw = _make_middleware()
    state = {
        "messages": [
            HumanMessage(content="What is <system-reminder>?", id="msg-1"),
        ]
    }

    with mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=""), mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
        result = mw.before_agent(state, _fake_runtime())

    # Injection must happen — the user message does NOT carry the reminder flag
    assert result is not None
    assert result["messages"][0].additional_kwargs.get(_DYNAMIC_CONTEXT_REMINDER_KEY) is True


# ---------------------------------------------------------------------------
# Midnight crossing
# ---------------------------------------------------------------------------


def test_midnight_crossing_injects_date_update_as_separate_message():
    """When the date has changed, a separate date-update reminder is injected before
    the current turn's HumanMessage using the ID-swap technique."""
    mw = _make_middleware()
    reminder_content = "<system-reminder>\n<current_date>2026-05-08, Friday</current_date>\n</system-reminder>"
    state = {
        "messages": [
            _reminder_msg(reminder_content, "msg-1"),
            HumanMessage(content="Hello", id="msg-1__user"),
            AIMessage(content="Response"),
            HumanMessage(content="Good morning", id="msg-2"),
        ]
    }

    with mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-09, Saturday"
        result = mw.before_agent(state, _fake_runtime())

    assert result is not None
    msgs = result["messages"]
    assert len(msgs) == 2

    # Date-update reminder takes the current message's ID
    assert msgs[0].id == "msg-2"
    assert msgs[0].additional_kwargs.get(_DYNAMIC_CONTEXT_REMINDER_KEY) is True
    assert _SYSTEM_REMINDER_TAG in msgs[0].content
    assert "<current_date>2026-05-09, Saturday</current_date>" in msgs[0].content
    assert "Good morning" not in msgs[0].content  # reminder only

    # Original user text appended with derived ID
    assert msgs[1].id == "msg-2__user"
    assert msgs[1].content == "Good morning"


def test_midnight_crossing_id_swap():
    """Date-update reminder uses original ID; user message uses {id}__user."""
    mw = _make_middleware()
    reminder_content = "<system-reminder>\n<current_date>2026-05-08, Friday</current_date>\n</system-reminder>"
    state = {
        "messages": [
            _reminder_msg(reminder_content, "msg-1"),
            HumanMessage(content="Next day message", id="msg-2"),
        ]
    }

    with mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-09, Saturday"
        result = mw.before_agent(state, _fake_runtime())

    assert result["messages"][0].id == "msg-2"
    assert result["messages"][1].id == "msg-2__user"


def test_no_second_midnight_injection_once_date_updated():
    """After a midnight update is persisted, the same-day path skips re-injection."""
    mw = _make_middleware()
    date_update_content = "<system-reminder>\n<current_date>2026-05-09, Saturday</current_date>\n</system-reminder>"
    state = {
        "messages": [
            _reminder_msg(
                "<system-reminder>\n<current_date>2026-05-08, Friday</current_date>\n</system-reminder>",
                "msg-1",
            ),
            HumanMessage(content="Hello", id="msg-1__user"),
            AIMessage(content="Response"),
            _reminder_msg(date_update_content, "msg-2"),
            HumanMessage(content="Good morning", id="msg-2__user"),
            AIMessage(content="Good morning!"),
            HumanMessage(content="Third turn", id="msg-3"),
        ]
    }

    with mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-09, Saturday"
        result = mw.before_agent(state, _fake_runtime())

    assert result is None  # same day as last injected date → no update
