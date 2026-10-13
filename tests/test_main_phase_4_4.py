"""API contract tests for the Phase 4.4 FastAPI control-plane integration."""
import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
SPEC = importlib.util.spec_from_file_location("phase44_test_main", MAIN_PATH)
assert SPEC is not None and SPEC.loader is not None
main = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = main
SPEC.loader.exec_module(main)


def test_health_endpoint_and_aliases():
    client = TestClient(main.app)
    for path in ("/", "/api"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["status"] == "online"


def test_workflow_request_rejects_blank_query():
    client = TestClient(main.app)
    response = client.post("/api/workflows", json={"query": "   "})
    assert response.status_code == 422


def test_route_contract_remains_available():
    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    expected = {
        "/workflows",
        "/api/workflows",
        "/workflows/{run_id}/events",
        "/api/workflows/{run_id}/events",
        "/workflows/{run_id}/gate",
        "/api/workflows/{run_id}/gate",
    }
    assert expected <= paths


def test_gate_reject_requires_feedback():
    try:
        main.GateDecisionRequest(decision="reject", feedback="  ")
    except Exception:
        return
    raise AssertionError("Empty rejection feedback should be rejected")


def test_gate_approve_does_not_require_feedback():
    request = main.GateDecisionRequest(decision="approve")
    assert request.decision == "approve"
