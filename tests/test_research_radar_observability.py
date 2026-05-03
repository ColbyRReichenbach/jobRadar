import sys
from types import SimpleNamespace

from backend.services.research_radar import observability


def test_emit_langsmith_run_trace_uses_optional_client(monkeypatch):
    calls: list[dict] = []

    class FakeClient:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def create_run(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-key")
    monkeypatch.setitem(sys.modules, "langsmith", SimpleNamespace(Client=FakeClient))
    monkeypatch.setattr(observability, "_LANGSMITH_CLIENT", None)
    monkeypatch.setattr(observability, "_LANGSMITH_IMPORT_FAILED", False)

    observability.emit_langsmith_run_trace(
        run_id="run-123",
        profile_id="profile-456",
        user_id="user-789",
        input_payload={"mode": "research"},
        output_payload={"status": "published"},
        error_message=None,
        metadata={"status": "published"},
    )

    assert calls
    assert calls[0]["name"] == "research_radar.run"
    assert calls[0]["project_name"] == "apptrail-radar"
    assert calls[0]["extra"]["metadata"]["run_id"] == "run-123"
    assert calls[0]["extra"]["metadata"]["status"] == "published"
