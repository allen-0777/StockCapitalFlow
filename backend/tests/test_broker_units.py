"""Broker API converts stored shares to lots without changing analysis units."""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import broker
from app.models.database import Base
from app.services.broker_analysis import get_key_branches, get_recent_flow


@pytest.fixture
def broker_db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        dates = [(date.today() - timedelta(days=n)).isoformat() for n in (3, 2, 1)]
        for day, close in zip(dates, (100, 110, 99)):
            db.execute(text('INSERT INTO stock_prices (date, stock_id, close, volume) '
                            "VALUES (:d, '2330', :c, 1234000)"), {'d': day, 'c': close})
        for branch, buy, sell in [('A', 617000, 500), ('B', 0, 1000000), ('C', 1, 0)]:
            for day in dates[:2]:
                db.execute(text('INSERT INTO broker_daily '
                                '(date, stock_id, branch_id, buy_shares, sell_shares) '
                                "VALUES (:d, '2330', :b, :buy, :sell)"),
                           {'d': day, 'b': branch, 'buy': buy, 'sell': sell})
        db.commit()
        yield db
    engine.dispose()


def test_broker_response_lots_preserve_analysis_and_storage(broker_db):
    raw_flow = get_recent_flow(broker_db, '2330')
    raw_keys = get_key_branches(broker_db, '2330', lookforward=1)
    flow = broker.broker_flow('2330', days=30, db=broker_db)
    assert flow['days'] == 30
    assert [b['branch_id'] for b in flow['branches']] == ['B', 'A', 'C']
    for actual, raw in zip(flow['branches'], raw_flow):
        assert actual == {**raw, **{k: raw[k] / 1000 for k in
                                   ('buy_shares', 'sell_shares', 'net_shares')}}
    a = flow['branches'][1]
    assert a['buy_shares'] == 1234.0
    assert a['sell_shares'] == 1.0
    assert a['net_shares'] == 1233.0
    assert flow['branches'][0]['net_shares'] == -2000.0
    assert flow['branches'][2]['net_shares'] == 0.002

    keys = broker.broker_keypoints('2330', lookforward=1, days=90, db=broker_db)['branches']
    assert keys == [{**b, 'recent_net': b['recent_net'] / 1000} for b in raw_keys]
    a = next(b for b in keys if b['branch_id'] == 'A')
    assert a['recent_net'] == 1233.0
    assert a['buy_count'] == 2
    assert a['win_rate'] == 0.5
    assert a['avg_return'] == 0.0
    assert a['score'] == 0.0
    # A one-share buy still passes the >0 share filter and counts in backtesting.
    assert next(b for b in keys if b['branch_id'] == 'C')['buy_count'] == 2
    assert broker.broker_flow('9999', days=30, db=broker_db)['branches'] == []
    assert broker.broker_keypoints('9999', lookforward=1, days=90, db=broker_db)['branches'] == []
    assert broker_db.execute(text("SELECT SUM(buy_shares) FROM broker_daily WHERE branch_id='A'")).scalar() == 1234000
    assert float(broker_db.execute(text('SELECT close FROM stock_prices ORDER BY date LIMIT 1')).scalar()) == 100
    assert broker_db.execute(text('SELECT volume FROM stock_prices LIMIT 1')).scalar() == 1234000
