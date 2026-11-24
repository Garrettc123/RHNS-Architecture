"""Regression tests for shared diagnostic goal validation."""

import importlib

import pytest
from fastapi.testclient import TestClient

api = importlib.import_module("api.main")


@pytest.fixture
def client():
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.mark.parametrize("length", [1, 2000])
@pytest.mark.parametrize("endpoint", ["/run", "/run/batch", "/reason"])
def test_goal_length_boundaries_accepted(client, endpoint, length):
    goal = "a" * length
    if endpoint == "/reason":
        response = client.post(endpoint, params={"goal": goal})
    else:
        payload = [goal] if endpoint == "/run/batch" else {"goal": goal}
        response = client.post(endpoint, json=payload)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("goal", ["", "a" * 2001])
@pytest.mark.parametrize("endpoint", ["/run", "/run/batch", "/reason"])
def test_invalid_goal_rejected_before_diagnosis(client, monkeypatch, endpoint, goal):
    def unexpected_diagnosis(*args, **kwargs):
        pytest.fail("Invalid goals must be rejected before diagnosis")

    monkeypatch.setattr(api, "_diagnose", unexpected_diagnosis)
    if endpoint == "/reason":
        response = client.post(endpoint, params={"goal": goal})
    else:
        payload = ["valid", goal] if endpoint == "/run/batch" else {"goal": goal}
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("count", [0, 21])
def test_invalid_batch_count_rejected(client, monkeypatch, count):
    def unexpected_diagnosis(*args, **kwargs):
        pytest.fail("Invalid batch sizes must be rejected before diagnosis")

    monkeypatch.setattr(api, "_diagnose", unexpected_diagnosis)
    response = client.post("/run/batch", json=["a"] * count)
    assert response.status_code == 422, response.text


def test_twenty_item_batch_remains_compatible(client):
    response = client.post("/run/batch", json=["a"] * 20)
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 20
    assert len(response.json()["results"]) == 20
