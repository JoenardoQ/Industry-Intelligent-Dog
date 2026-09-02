from intdog_core.repository import IntelligenceRepository


def test_industry_override_survives_global_provider_change(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI", "Artificial Intelligence")
    repo.ensure_industry("Chips", "Semiconductors")

    repo.put_workflow_settings(None, "*", {"provider": "codex"})
    repo.put_workflow_settings("Chips", "*", {"provider": "claude"})
    repo.put_workflow_settings(None, "*", {"provider": "deepseek"})

    assert repo.effective_workflow_settings("AI", "report")["provider"] == "deepseek"
    chips = repo.effective_workflow_settings("Chips", "report")
    assert chips["provider"] == "claude"
    assert chips["provenance"]["provider"] == "industry"


def test_task_override_layers_over_shared_settings_and_can_be_removed(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI", "Artificial Intelligence")
    repo.put_workflow_settings(None, "*", {"provider": "codex"})
    repo.put_workflow_settings(None, "daily", {"provider": "qwen"})
    repo.put_workflow_settings("AI", "daily", {"provider": "claude"})

    current = repo.effective_workflow_settings("AI", "daily")
    assert current["provider"] == "claude"
    assert current["provenance"]["provider"] == "industry_task"

    repo.delete_workflow_settings("AI", "daily")
    inherited = repo.effective_workflow_settings("AI", "daily")
    assert inherited["provider"] == "qwen"
    assert inherited["provenance"]["provider"] == "global_task"


def test_workflow_settings_reject_secrets_and_unknown_keys(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI", "Artificial Intelligence")

    for values in ({"api_key": "secret"}, {"unknown": True}):
        try:
            repo.put_workflow_settings(None, "*", values)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid workflow settings must be rejected")
