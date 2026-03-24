import os
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("TRIGGER_SECRET", "test-secret")

from app.main import app

client = TestClient(app)


def test_trigger_invalid_secret():
    r = client.post("/api/v1/admin/trigger/institutional?secret=wrong")
    assert r.status_code == 403


def test_trigger_unknown_job():
    r = client.post("/api/v1/admin/trigger/not_a_job?secret=test-secret")
    assert r.status_code == 404


@patch("app.api.admin.is_trading_day", return_value=False)
def test_trigger_skipped_on_non_trading_day(_mock_td):
    r = client.post("/api/v1/admin/trigger/institutional?secret=test-secret")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "skipped"
    assert "非台股" in body["reason"]


@patch("app.api.admin.cache_clear")
@patch("app.api.admin.latest_trading_day", return_value=date(2026, 3, 21))
@patch("app.api.admin.is_trading_day", return_value=True)
@patch("app.services.fetcher.fetch_institutional_stocks", new_callable=AsyncMock)
@patch("app.services.fetcher.fetch_institutional_market", new_callable=AsyncMock)
def test_trigger_institutional_all_steps_ok(_mkt, _stocks, *_):
    _mkt.return_value = date(2026, 3, 21)
    _stocks.return_value = date(2026, 3, 21)
    r = client.post("/api/v1/admin/trigger/institutional?secret=test-secret")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    assert j["date_match"] is True
    assert len(j["steps"]) == 2
    assert j["steps"][0]["fn"] == "fetch_institutional_market"
    assert j["steps"][0]["status"] == "ok"
    assert j["steps"][0]["duration_s"] is not None
    assert j["steps"][1]["status"] == "ok"


@patch("app.api.admin.cache_clear")
@patch("app.api.admin.latest_trading_day", return_value=date(2026, 3, 21))
@patch("app.api.admin.is_trading_day", return_value=True)
@patch("app.services.fetcher.fetch_institutional_stocks", new_callable=AsyncMock)
@patch("app.services.fetcher.fetch_institutional_market", new_callable=AsyncMock)
def test_trigger_partial_error_second_step_fails(_mkt, _stocks, *_):
    _mkt.return_value = date(2026, 3, 21)
    _stocks.side_effect = RuntimeError("T86 timeout")
    r = client.post("/api/v1/admin/trigger/institutional?secret=test-secret")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "partial_error"
    assert j["steps"][0]["status"] == "ok"
    assert j["steps"][1]["status"] == "error"
    assert "timeout" in j["steps"][1]["error"]


@patch("app.api.admin.cache_clear")
@patch("app.api.admin.latest_trading_day", return_value=date(2026, 3, 21))
@patch("app.api.admin.is_trading_day", return_value=True)
@patch("app.services.fetcher.fetch_institutional_stocks", new_callable=AsyncMock)
@patch("app.services.fetcher.fetch_institutional_market", new_callable=AsyncMock)
def test_trigger_all_steps_fail(_mkt, _stocks, *_):
    _mkt.side_effect = RuntimeError("BFI82U down")
    _stocks.side_effect = RuntimeError("T86 down")
    r = client.post("/api/v1/admin/trigger/institutional?secret=test-secret")
    j = r.json()
    assert j["status"] == "error"
    assert j["steps"][0]["status"] == "error"
    assert j["got_date"] is None
    assert j["steps"][1]["status"] == "error"


@patch("app.api.admin.send_job_result", new_callable=AsyncMock)
@patch("app.api.admin.cache_clear")
@patch("app.api.admin.latest_trading_day", return_value=date(2026, 3, 21))
@patch("app.api.admin.is_trading_day", return_value=True)
@patch("app.services.fetcher.fetch_margin", new_callable=AsyncMock)
def test_trigger_notify_true_calls_send_job_result(mock_margin, _itd, _ltd, _cc, send_job_result):
    mock_margin.return_value = date(2026, 3, 21)
    r = client.post("/api/v1/admin/trigger/margin?secret=test-secret&notify=true")
    assert r.status_code == 200
    send_job_result.assert_awaited_once()


@patch("app.api.admin.send_daily_digest", new_callable=AsyncMock)
def test_daily_digest_invalid_secret(_digest):
    r = client.post("/api/v1/admin/daily-digest?secret=wrong")
    assert r.status_code == 403
    _digest.assert_not_awaited()


@patch("app.api.admin.send_daily_digest", new_callable=AsyncMock)
def test_daily_digest_ok(_digest):
    r = client.post("/api/v1/admin/daily-digest?secret=test-secret")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    _digest.assert_awaited_once()
