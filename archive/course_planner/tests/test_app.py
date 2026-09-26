"""تست‌های مسیرهای HTTP ویزارد (SSR) با TestClient."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def post_json(client: TestClient, path: str, payload: dict):
    return client.post(path, data={"payload": json.dumps(payload)}, follow_redirects=True)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_landing_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "چیدمان" in response.text
    assert "شروع یک برنامه‌ی جدید" in response.text


def test_manual_wizard_flow(client: TestClient) -> None:
    assert client.post("/start", follow_redirects=True).status_code == 200

    step1 = post_json(
        client,
        "/step/1",
        {
            "courses": [
                {"name": "ریاضی ۲", "code": "MA201", "credits": 3, "priority": 3, "must": True},
                {"name": "برنامه‌سازی", "code": "CS210", "credits": 3, "priority": 2, "must": False},
            ],
            "target_credits": 6,
            "max_credits": 12,
        },
    )
    assert step1.status_code == 200
    assert "کلاس‌های موجود" in step1.text

    step2 = post_json(
        client,
        "/step/2",
        {
            "sections": [
                {
                    "course_id": "c1",
                    "instructor": "دکتر الف",
                    "preferred": True,
                    "meetings": [{"day": 0, "start": "08:00", "end": "09:30", "parity": "all"}],
                },
                {
                    "course_id": "c2",
                    "instructor": "مهندس ب",
                    "meetings": [{"day": 1, "start": "10:00", "end": "11:30", "parity": "all"}],
                },
            ]
        },
    )
    assert step2.status_code == 200
    assert "ساعاتی که کار واجب دارید" in step2.text

    step3 = post_json(
        client,
        "/step/3",
        {"blocked": [{"day": 2, "start": "08:00", "end": "12:00", "label": "کار"}]},
    )
    assert step3.status_code == 200
    assert "برنامه‌ی دلخواه" in step3.text

    result = post_json(
        client,
        "/step/4",
        {"prefs": {"fit": 1, "few_days": 2, "few_gaps": 1, "avoid_early": 1, "avoid_late": 0, "max_days": None, "day_start": "08:00", "day_end": "17:00"}},
    )
    assert result.status_code == 200
    assert "برنامه‌ی پیشنهادی" in result.text
    assert "بهترین برنامه" in result.text
    assert "ریاضی ۲" in result.text

    selected = client.post("/result/select", data={"option": 1}, follow_redirects=True)
    assert selected.status_code == 200
    assert "ثبت نهایی" in selected.text


def test_demo_flow_produces_alternatives(client: TestClient) -> None:
    response = client.post("/demo", follow_redirects=True)
    assert response.status_code == 200
    body = response.text
    assert "بهترین برنامه" in body
    assert "آزمایشگاه فیزیک ۲" in body
    assert "مقایسه‌ی گزینه‌ها" in body


def test_step1_validation_returns_persian_error(client: TestClient) -> None:
    client.post("/start")
    response = post_json(client, "/step/1", {"courses": [], "target_credits": 16, "max_credits": 20})
    assert response.status_code == 400
    assert "حداقل یک درس وارد کنید" in response.text


def test_step1_rejects_target_above_cap(client: TestClient) -> None:
    client.post("/start")
    response = post_json(
        client,
        "/step/1",
        {
            "courses": [{"name": "درس الف", "credits": 3, "priority": 2}],
            "target_credits": 24,
            "max_credits": 20,
        },
    )
    assert response.status_code == 400
    assert "نمی‌تواند از سقف واحد بیشتر باشد" in response.text


def test_step2_rejects_invalid_time_range(client: TestClient) -> None:
    client.post("/start")
    post_json(
        client,
        "/step/1",
        {"courses": [{"name": "درس الف", "credits": 3, "priority": 2}], "target_credits": 3, "max_credits": 12},
    )
    response = post_json(
        client,
        "/step/2",
        {"sections": [{"course_id": "c1", "meetings": [{"day": 0, "start": "10:00", "end": "09:00"}]}]},
    )
    assert response.status_code == 400
    assert "باید بعد از شروع" in response.text


def test_result_redirects_without_input(client: TestClient) -> None:
    client.post("/start")
    response = client.get("/result", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/step/1"
