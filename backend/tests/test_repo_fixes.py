import asyncio
from datetime import date, timedelta
from pathlib import Path
import ssl
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api import broker, institutional, watchlist, admin, deps
from app.services import fetcher, finmind_client as fm


def test_workflows_and_pins():
    root = Path(__file__).resolve().parents[2]
    digest = (root / '.github/workflows/daily-fetch.yml').read_text()
    assert '/admin/daily-digest' in digest
    assert 'X-Trigger-Secret:' in digest
    assert '/trigger/daily-digest' not in digest and 'job-status/' not in digest
    assert '"ok"' in digest
    radar = (root / '.github/workflows/zheng2-radar.yml').read_text()
    assert '\n  schedule:' not in radar and 'workflow_dispatch:' in radar
    assert 'zheng2_radar.py is restored' in radar
    for name in ('fetch-direct', 'zheng2-radar', 'ci'):
        workflow = (root / f'.github/workflows/{name}.yml').read_text()
        assert 'pip install -r backend/requirements.txt' in workflow
    ci = (root / '.github/workflows/ci.yml').read_text()
    assert 'push, pull_request' in ci and "'3.11'" in ci and 'secrets' not in ci
    pins = (root / 'backend/requirements.txt').read_text().splitlines()
    assert len(pins) == 15 and all('==' in line for line in pins)
    assert 'certifi==2026.10.19' in pins
    env = (root / 'backend/.env.example').read_text()
    assert '\nDATABASE_URL=' not in env and 'API_KEY=' in env
    for path in ('store/useStore.js', 'components/Widget_BrokerFlow.jsx'):
        assert 'headers: apiKeyHeaders' in (root / 'frontend/src' / path).read_text()


def test_tls_and_parsers():
    assert fetcher._ssl_ctx.verify_mode == ssl.CERT_REQUIRED
    assert fetcher._ssl_ctx.check_hostname is True
    assert fetcher._parse_num('1,234') == 1234
    assert fetcher._parse_num('--') == 0
    for value in ('bad', 'nan', 'inf'):
        assert fetcher._parse_num(value) is None
    assert fetcher._parse_twse_date({'date': '20261020'}) == date(2026, 10, 20)
    for value in (None, '', '20260230', 'bad'):
        with pytest.raises(ValueError):
            fetcher._parse_twse_date({'date': value})


@pytest.mark.asyncio
@pytest.mark.parametrize('fn', [fetcher.fetch_institutional_market, fetcher.fetch_institutional_stocks, fetcher.fetch_margin])
async def test_invalid_payload_never_writes(fn):
    with patch.object(fetcher, '_get_json_with_retry', AsyncMock(return_value={'stat': 'OK', 'date': 'bad'})), patch.object(fetcher, 'SessionLocal') as db:
        with pytest.raises(ValueError):
            await fn()
        db.assert_not_called()


@pytest.mark.asyncio
async def test_bad_stock_row_skipped(caplog):
    good = ['2330', '台積電'] + ['1000'] * 10
    bad = ['9999', 'bad'] + ['garbage'] * 10
    db = MagicMock()
    with patch.object(fetcher, '_get_json_with_retry', AsyncMock(return_value={'stat': 'OK', 'date': '20261020', 'data': [bad, [], good]})), patch.object(fetcher, 'SessionLocal') as local:
        local.return_value.__enter__.return_value = db
        assert await fetcher.fetch_institutional_stocks() == date(2026, 10, 20)
    assert db.execute.call_args_list[1].args[1][0]['foreign_buy'] == 1
    assert len(db.execute.call_args_list[1].args[1]) == 1
    assert 'Rejected 2' in caplog.text


def test_query_literals():
    app = FastAPI()
    app.include_router(institutional.router)
    app.dependency_overrides[institutional.get_db] = lambda: MagicMock()
    client = TestClient(app)
    assert client.get('/api/v1/institutional/ranking?type=invalid').status_code == 422
    assert client.get('/api/v1/institutional/ranking?order=invalid').status_code == 422
    schema = app.openapi()['paths']['/api/v1/institutional/ranking']['get']['parameters']
    assert schema[0]['schema']['default'] == 'foreign'


@pytest.mark.parametrize('key,header,expected', [('secret', '', 401), ('secret', 'wrong', 401), ('secret', 'secret', 200), ('', '', 200)])
def test_mutation_auth(monkeypatch, key, header, expected):
    monkeypatch.setenv('API_KEY', key)
    app = FastAPI()
    app.include_router(watchlist.router)
    app.include_router(broker.router)
    app.dependency_overrides[watchlist.get_db] = lambda: MagicMock()
    client = TestClient(app)
    headers = {'X-API-Key': header}
    with patch.object(broker, 'fetch_broker_daily', AsyncMock(return_value=1)), patch.object(broker, 'fetch_stock_price', AsyncMock(return_value=1)):
        assert client.post('/api/v1/stocks/2330/broker/fetch', headers=headers).status_code == expected
    assert client.delete('/api/v1/users/1/watchlist/2330', headers=headers).status_code == expected
    # GET stays public even with a configured key.
    assert client.get('/api/v1/users/1/watchlist').status_code == 200
    assert all(any(d.call is deps.require_api_key for d in route.dependant.dependencies) for route in app.routes if getattr(route, 'methods', set()) & {'POST', 'DELETE', 'PUT', 'PATCH'})


def test_unset_key_warns_once(monkeypatch, caplog):
    monkeypatch.delenv('API_KEY', raising=False)
    monkeypatch.setattr(deps, '_warned_missing_key', False)
    deps.require_api_key('')
    deps.require_api_key('')
    assert caplog.text.count('API_KEY is unset') == 1


@pytest.mark.parametrize('headers,query,status', [({'X-Trigger-Secret': 'secret'}, '', 200), ({}, '?secret=secret', 200), ({'X-Trigger-Secret': 'wrong'}, '', 403)])
def test_admin_secret(monkeypatch, headers, query, status):
    monkeypatch.setenv('TRIGGER_SECRET', 'secret')
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin.get_db] = lambda: MagicMock()
    with patch.object(admin, 'send_daily_digest', AsyncMock()) as send:
        result = TestClient(app).post('/api/v1/admin/daily-digest' + query, headers=headers)
        assert result.status_code == status
        if status == 200:
            assert result.json() == {'status': 'ok'}
            send.assert_awaited_once()


def test_portable_broker_sql():
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = SimpleNamespace(from_d='2026-10-01', to_d='2026-10-20')
    assert broker._date_range(db, '2330', 30)['to'] == '2026-10-20'
    sql, params = db.execute.call_args.args
    assert 'date(' not in str(sql) and params['cutoff'] == (date.today() - timedelta(days=30)).isoformat()
    from app.services import broker_analysis
    assert 'HAVING SUM(buy_shares - sell_shares) > 0' in Path(broker_analysis.__file__).read_text()


def response(status=200, body=None, headers=None):
    resp = MagicMock()
    resp.status = status
    resp.headers = headers or {}
    resp.json = AsyncMock(return_value=body if body is not None else {'status': 200, 'data': []})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


@pytest.fixture
def fm_mock(monkeypatch):
    monkeypatch.setattr(fm, '_sleep', AsyncMock())
    monkeypatch.setattr(fm, '_min_interval', 0)
    monkeypatch.setattr(fm, '_semaphore', asyncio.Semaphore(2))
    monkeypatch.setattr(fm, '_rate_lock', asyncio.Lock())
    return MagicMock()


@pytest.mark.asyncio
@pytest.mark.parametrize('http,body,error,attempts', [(200, {'status': 400, 'msg': 'bad'}, fm.FinMindAPIError, 1), (402, None, fm.FinMindQuotaError, 1), (200, {'status': 402}, fm.FinMindQuotaError, 1), (503, None, fm.FinMindAPIError, 3), (200, {'status': 500}, fm.FinMindAPIError, 3)])
async def test_finmind_errors(fm_mock, http, body, error, attempts):
    fm_mock.get.return_value = response(http, body)
    with pytest.raises(error):
        await fm.finmind_get(fm_mock, 'test', '', '')
    assert fm_mock.get.call_count == attempts


@pytest.mark.asyncio
@pytest.mark.parametrize('first', [response(429, headers={'Retry-After': '5'}), asyncio.TimeoutError(), aiohttp.ClientError('offline')])
async def test_finmind_retry_then_success(fm_mock, first):
    fm_mock.get.side_effect = [first, response(body={'status': 200, 'data': [{'date': '2026-10-20'}]})]
    assert await fm.finmind_get(fm_mock, 'test', '', '') == [{'date': '2026-10-20'}]
    assert fm_mock.get.call_count == 2
    fm._sleep.assert_awaited_once()
    if not isinstance(first, Exception):
        assert fm._sleep.call_args.args[0] == 5


@pytest.mark.asyncio
async def test_finmind_empty_and_rate_limit(fm_mock, monkeypatch):
    fm_mock.get.return_value = response()
    monkeypatch.setattr(fm, '_min_interval', 1)
    monkeypatch.setattr(fm, '_last_request', fm.time.monotonic())
    assert await fm.finmind_get(fm_mock, 'test', '', '') == []
    assert 0 < fm._sleep.call_args.args[0] <= 1


@pytest.mark.asyncio
@pytest.mark.parametrize('source_date', [None, '2026-10-19', '2026-10-20'])
async def test_options_preserve_enrichment(source_date):
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE daily_options (date TEXT PRIMARY KEY, pc_ratio REAL, call_max_strike REAL, put_max_strike REAL, call_total_oi INTEGER, put_total_oi INTEGER, foreign_call_net_yi REAL, foreign_put_net_yi REAL)'))
        db.execute(text("INSERT INTO daily_options VALUES ('2026-10-20', 150, 20000, 19000, 100, 150, 1, 2)"))
    taifex = [{'Date': '20261020', 'ContractCode': '臺指選擇權', 'Item': '外資及陸資', 'CallPut': 'CALL', 'ContractValueofOpenInterest(Long)(Thousands)': '300000', 'ContractValueofOpenInterest(Short)(Thousands)': '100000'}]
    rows = [] if source_date is None else [dict(date=source_date, contract_date='202610', trading_session='position', open_interest=oi, call_put=side, strike_price=strike) for side, oi, strike in [('call', 200, 21000), ('put', 100, 18000)]]
    with patch.object(fetcher, '_get_taifex_json', AsyncMock(return_value=taifex)), patch.object(fetcher, '_taipei_today', return_value=date(2026, 10, 20)), patch.object(fetcher, 'SessionLocal', side_effect=lambda: Session(engine)), patch.object(fm, 'get_shared_session', AsyncMock()), patch.object(fm, 'finmind_get', AsyncMock(return_value=rows)):
        await fetcher.fetch_options_data()
    with engine.connect() as db:
        row = db.execute(text('SELECT * FROM daily_options')).mappings().one()
        assert row['foreign_call_net_yi'] == 2
        assert row['pc_ratio'] == (50 if source_date == '2026-10-20' else 150)
        assert row['call_total_oi'] == (200 if source_date == '2026-10-20' else 100)
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('force,trading,result,expected', [(False, True, None, 1), (False, True, date(2026, 10, 19), 1), (False, True, date(2026, 10, 20), 0), (True, True, None, 0), (True, False, None, 0), (False, False, None, 0)])
async def test_daily_freshness(force, trading, result, expected, capsys):
    from scripts import fetch_daily
    fn = AsyncMock(return_value=result)
    with patch.dict(fetch_daily.JOBS, {'test': ['fetch_margin']}, clear=True), patch.object(fetch_daily, 'is_trading_day', return_value=trading), patch.object(fetch_daily, 'latest_trading_day', return_value=date(2026, 10, 20)), patch.object(fetcher, 'fetch_margin', fn), patch.object(fm, 'close_shared_session', AsyncMock()):
        assert await fetch_daily.run(['test'], force=force) == expected
    if expected:
        assert 'Stale/missing data' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_daily_continues_after_errors():
    from scripts import fetch_daily
    second = AsyncMock(return_value=None)
    with patch.dict(fetch_daily.JOBS, {'test': ['fetch_margin', 'fetch_turnover']}, clear=True), patch.object(fetcher, 'fetch_margin', AsyncMock(side_effect=fm.FinMindAPIError(400, 'bad'))), patch.object(fetcher, 'fetch_turnover', second), patch.object(fm, 'close_shared_session', AsyncMock()):
        assert await fetch_daily.run(['test'], force=True) == 1
    second.assert_awaited_once()


@pytest.mark.asyncio
async def test_finmind_concurrency_is_bounded(fm_mock):
    active = peak = 0

    async def enter():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        return resp

    async def leave(*args):
        nonlocal active
        active -= 1

    resp = response()
    resp.__aenter__.side_effect = enter
    resp.__aexit__.side_effect = leave
    fm_mock.get.return_value = resp
    await asyncio.gather(*(fm.finmind_get(fm_mock, 'test', '', '') for _ in range(6)))
    assert peak == 2 and active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [asyncio.TimeoutError(), aiohttp.ClientError('offline')])
async def test_finmind_transport_exhaustion(fm_mock, error):
    fm_mock.get.side_effect = error
    with pytest.raises(type(error)):
        await fm.finmind_get(fm_mock, 'test', '', '')
    assert fm_mock.get.call_count == 3
    assert fm._sleep.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('module_name,args', [
    ('app.services.finmind_fetcher', ('test', '', '')),
    ('app.services.industry_sync', (None, 'test', '', '')),
])
async def test_finmind_callers_propagate_failures(module_name, args):
    import importlib
    module = importlib.import_module(module_name)
    with patch.object(module, 'finmind_get', AsyncMock(side_effect=fm.FinMindAPIError(400, 'bad'))), patch.object(module, 'get_shared_session', AsyncMock()):
        with pytest.raises(fm.FinMindAPIError):
            await module._get_finmind(*args)


@pytest.mark.asyncio
async def test_concentration_maps_finmind_error_to_503():
    from app.api import concentration
    from fastapi import HTTPException
    with patch.object(concentration, 'finmind_get', AsyncMock(side_effect=fm.FinMindAPIError(400, 'bad'))), patch.object(concentration, 'get_shared_session', AsyncMock()):
        with pytest.raises(HTTPException) as exc:
            await concentration._get_finmind('test', '', '')
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_admin_marks_finmind_failure():
    with patch.dict(admin.JOB_STEPS, {'test': ('fetch_options_data',)}, clear=True), patch.object(fetcher, 'fetch_options_data', AsyncMock(side_effect=fm.FinMindAPIError(400, 'bad'))):
        steps, _ = await admin._run_steps_for_job('test', date(2026, 10, 20))
    assert admin._summarize_job_status(steps) == 'error'
    assert 'status=400' in steps[0]['error']


@pytest.mark.asyncio
@pytest.mark.parametrize('fn,body', [
    (fetcher.fetch_institutional_market, {'stat': 'OK', 'date': '20261020', 'data': [['投信', '', '', 'bad']]}),
    (fetcher.fetch_margin, {'stat': 'OK', 'date': '20261020', 'tables': [{'data': [['融資金額', '', '', '', 'bad', '100']]}]}),
])
async def test_invalid_aggregate_rows_do_not_write_zero(fn, body, caplog):
    with patch.object(fetcher, '_get_json_with_retry', AsyncMock(return_value=body)), patch.object(fetcher, 'SessionLocal') as db:
        with pytest.raises(ValueError, match='No valid'):
            await fn()
    db.assert_not_called()
    assert 'Rejected 1' in caplog.text


@pytest.mark.asyncio
async def test_market_keeps_valid_rows_only(caplog):
    body = {'stat': 'OK', 'date': '20261020', 'data': [['投信', '', '', '100000000'], ['外資及陸資', '', '', 'bad']]}
    with patch.object(fetcher, '_get_json_with_retry', AsyncMock(return_value=body)), patch.object(fetcher, 'SessionLocal'), patch.object(fetcher, '_upsert_chip') as upsert:
        assert await fetcher.fetch_institutional_market() == date(2026, 10, 20)
    assert upsert.call_args.kwargs == {'trust_buy': 1}
    assert 'Rejected 1' in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('row', [[], ['115/10/20', '', 'bad']])
async def test_invalid_turnover_never_writes(row, caplog):
    with patch.object(fetcher, '_get_json_with_retry', AsyncMock(return_value={'stat': 'OK', 'date': '20261020', 'data': [row]})), patch.object(fetcher, 'SessionLocal') as db:
        with pytest.raises(ValueError, match='Invalid turnover'):
            await fetcher.fetch_turnover()
    db.assert_not_called()
    assert 'Rejected 1' in caplog.text


@pytest.mark.asyncio
async def test_futures_skips_malformed_rows(caplog):
    rows = [dict(Date='20261020', ContractCode='臺股期貨', Item='外資及陸資', **{'OpenInterest(Long)': '1,000', 'OpenInterest(Short)': '200'}),
            dict(Date='20261020', ContractCode='小型臺指期貨', Item='外資及陸資', **{'OpenInterest(Long)': 'bad', 'OpenInterest(Short)': '200'})]
    with patch.object(fetcher, '_get_taifex_json', AsyncMock(return_value=rows)), patch.object(fetcher, 'SessionLocal'), patch.object(fetcher, '_upsert_chip') as upsert:
        assert await fetcher.fetch_futures_oi() == date(2026, 10, 20)
    assert upsert.call_args.kwargs['tx_foreign_long'] == 1000
    assert 'mtx_retail_long' not in upsert.call_args.kwargs
    assert 'Rejected 1' in caplog.text


def test_daily_main_exits_nonzero_on_failure(monkeypatch):
    from scripts import fetch_daily
    monkeypatch.setattr('sys.argv', ['fetch_daily.py', '--jobs', 'margin'])
    with patch.object(fetch_daily, 'init_db'), patch.object(fetch_daily, 'run', AsyncMock(return_value=1)), pytest.raises(SystemExit) as exc:
        fetch_daily.main()
    assert exc.value.code == 1


def test_normalize_db_url_uses_installed_psycopg2_driver():
    from app.models.database import normalize_db_url
    assert normalize_db_url("postgres://u:p@h:6543/db") == "postgresql+psycopg2://u:p@h:6543/db"
    assert normalize_db_url("postgresql://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert normalize_db_url("postgresql+psycopg2://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert normalize_db_url("sqlite:///x.db") == "sqlite:///x.db"
