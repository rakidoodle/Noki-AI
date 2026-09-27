from free_agent.messages import trim_history


def test_history_trims_complete_user_turns():
    old = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "a"}]},
        {"role": "tool", "tool_call_id": "a", "content": "result"},
        {"role": "assistant", "content": "first answer"},
    ]
    recent = [
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "second answer"},
    ]
    limit = sum(len(str(message)) for message in recent)
    assert trim_history(old + recent, max_chars=limit) == recent


def test_oversized_latest_turn_is_dropped():
    history = [{"role": "user", "content": "x" * 100},
               {"role": "assistant", "content": "answer"}]
    assert trim_history(history, max_chars=20) == []
