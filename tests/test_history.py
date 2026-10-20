"""Economic and durability invariants for the separate July-start accounts."""
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantit.markets.cn import CNAdapter
from quantit.markets.us import USAdapter
from quantit.markets.registry import MarketRegistry
from quantit.paper.db import create_session
from quantit.paper.history import (HistoryBroker, HistoryRunner, NextOpenAdapter, actions_before_open,
                                   at_open, read_days, run_book)
from quantit.paper.history_data import nominal_prices


def bars():
    days = pd.bdate_range('2024-07-01', periods=5)
    return pd.DataFrame({'open': 10., 'high': 12., 'low': 9., 'close': 11.,
                         'volume': 1000000., 'dividends': 0., 'stock_splits': 0.}, index=days)


def broker_for(frame, day=1, cn=False):
    base, symbol, book = (CNAdapter(), '600000.SS', 'cn') if cn else (USAdapter(), 'AAPL', 'us')
    adapter = NextOpenAdapter(base, {symbol: frame}, {symbol: frame}, frame.index[day])
    registry = MarketRegistry()
    registry.register(adapter)
    broker = HistoryBroker(create_session('sqlite:///:memory:'), registry,
                           now=lambda: at_open(adapter.day, book), max_quote_age_days=0)
    broker.ensure_accounts()
    return broker, adapter, symbol, book


def test_signals_stop_before_execution_and_quote_uses_open():
    frame = bars()
    frame.loc[frame.index[2]:, 'close'] = 9999
    broker, adapter, symbol, _ = broker_for(frame, day=2)
    seen = adapter.fetch_bars(symbol, '1d', '2020-01-01', '2030-01-01')
    assert seen.index.max() == frame.index[1]
    assert seen.close.max() == 11
    assert adapter.fetch_quote(symbol).last == 10
    adapter.day += pd.Timedelta(days=20)
    with pytest.raises(ValueError, match='No opening quote'):
        adapter.fetch_quote(symbol)


def test_post_start_adjustment_cannot_change_absolute_signal_units():
    frame = bars()
    broker, adapter, symbol, _ = broker_for(frame)
    adjusted = frame.copy()
    adjusted.loc[:, ['open','high','low','close']] *= .5
    adapter.signals = {symbol: adjusted}
    assert adapter.fetch_bars(symbol,'1d','2020-01-01','2030-01-01').close.iloc[-1] == 11


def test_minimum_fees_t_plus_one_and_participation_are_enforced():
    frame = bars()
    broker, adapter, symbol, book = broker_for(frame, cn=True)
    order = broker.place_order(book, symbol, 'buy', 100)
    assert order.status == 'filled'
    assert order.commission == 5
    assert order.fill_price == pytest.approx(10.005)
    assert broker.get_account(book).cash == pytest.approx(1e6 - 1000.5 - 5)
    assert 'T+1' in broker.place_order(book,symbol,'sell',100).reject_reason
    adapter.day = frame.index[2]
    assert broker.place_order(book,symbol,'sell',100).status == 'filled'
    adapter.raw[symbol].loc[frame.index[1], 'volume'] = 1000
    assert broker.place_order(book,symbol,'buy',100).status == 'rejected'


def test_limits_and_min_fee_insufficient_cash_are_recorded():
    frame = bars()
    broker, adapter, symbol, book = broker_for(frame, cn=True)
    adapter.raw[symbol].loc[adapter.day, 'open'] = 12.1
    assert 'limit' in broker.place_order(book,symbol,'buy',100).reject_reason
    adapter.raw[symbol].loc[adapter.day, 'open'] = 10
    account = broker.get_account(book)
    account.cash = 1003
    broker.session.commit()
    assert broker.place_order(book,symbol,'buy',100).status == 'rejected'
    assert broker.get_account(book).cash == 1003


def test_split_and_dividend_are_separate_from_tradable_cash():
    frame = bars()
    broker, adapter, symbol, book = broker_for(frame)
    broker.place_order(book,symbol,'buy',100)
    cash = broker.get_account(book).cash
    day = frame.index[2]
    frame.loc[day, ['stock_splits','open','close','dividends']] = [2,5,5.5,.2]
    entitlement, events = actions_before_open(broker,book,{symbol:frame},day)
    position = broker.get_position(book,symbol)
    assert position.quantity == 200
    assert position.lots[0].remaining == 200
    assert entitlement == 40
    assert broker.get_account(book).cash == cash
    assert len(events) == 2
    restored = nominal_prices(frame)
    assert restored.loc[frame.index[0], 'close'] == 22
    assert restored.loc[day, 'close'] == 5.5


def test_daily_atomic_rollback_retry_and_idempotence(tmp_path, monkeypatch):
    frame = bars()
    frame['open'] = 11
    args = dict(root=tmp_path, strategy='us', book='us', raw={'SPY':frame,'AAPL':frame},
                signal_frames={'SPY':frame,'AAPL':frame}, calendar=frame.index,
                config={}, scores=None, hk_scores=pd.DataFrame(), cn_scores=pd.DataFrame(),
                start='2024-07-02', end='2024-07-04', feed_id='test')
    def tick(self, **kwargs):
        self.broker.place_order('us','AAPL','buy',1)
        if self.broker.now().day == 3:
            raise ValueError('mid-day crash')
    monkeypatch.setattr(HistoryRunner, 'tick', tick)
    days, errors = run_book(**args)
    assert [d['day'] for d in days] == ['2024-07-02'], errors
    assert len(errors) == 1
    assert len(read_days(tmp_path/'books/us.db')) == 1
    monkeypatch.setattr(HistoryRunner, 'tick', lambda self, **kw: self.broker.place_order('us','AAPL','buy',1))
    days, errors = run_book(**args)
    assert not errors and len(days) == 3
    assert days[-1]['positions'][0]['quantity'] == 3
    assert sum(d['fills'] for d in days) == 3
    again, errors = run_book(**args)
    assert again == days and not errors
    assert all(d['cash'] + d['receivable'] + sum(p['value'] for p in d['positions']) == d['equity'] for d in days)


def test_suspended_model_holding_remains_in_account():
    from quantit.paper.history import model_rebalance, marked_positions
    frame = bars()
    broker, adapter, symbol, book = broker_for(frame, cn=True)
    broker.place_order(book,symbol,'buy',100)
    adapter.day = frame.index[2]
    frame.loc[adapter.day,'volume'] = 0
    scores = pd.DataFrame({'SH600000': [1.]}, index=[adapter.day])
    model_rebalance(broker,book,scores,{'rebalance':1,'top_k':1,'turnover_limit':1},1,{symbol:frame},adapter.day)
    assert broker.get_position(book,symbol).quantity == 100
    assert len(broker.list_orders(book)) == 1
    positions, stale = marked_positions(broker,book,{symbol:frame},adapter.day)
    assert stale == [symbol]
    assert positions[0]['value'] == 1100


def test_hk_board_lots_and_etf_stamp_exemption():
    from quantit.markets.hk import HKAdapter
    frame=bars()
    adapter=NextOpenAdapter(HKAdapter(), {'2800.HK':frame}, {'2800.HK':frame}, frame.index[1])
    assert adapter.lot_size('0005.HK') == 400
    assert adapter.lot_size('0002.HK') == 500
    with pytest.raises(ValueError,match='Unknown HK'):
        adapter.lot_size('1234.HK')
    registry=MarketRegistry(); registry.register(adapter)
    broker=HistoryBroker(create_session('sqlite:///:memory:'),registry,now=lambda:at_open(adapter.day,'hk'))
    broker.ensure_accounts()
    lot=adapter.lot_size('2800.HK')
    order=broker.place_order('hk','2800.HK','buy',lot)
    assert order.status=='filled'
    assert order.commission == pytest.approx(max(18,order.fill_price*lot*.0008))
    assert broker.get_account('hk').cash == pytest.approx(1e6-order.fill_price*lot-order.commission)


def test_history_api_is_readonly_and_validates_membership(tmp_path, monkeypatch):
    from quantit.api.history import attach_history_routes
    from quantit.paper.models import RecoveryDay
    monkeypatch.setenv('QUANTIT_HISTORY_ROOT', str(tmp_path))
    app=FastAPI(); attach_history_routes(app)
    client=TestClient(app)
    assert client.get('/api/v1/history').json()['ready'] is False
    assert not list(tmp_path.iterdir())
    (tmp_path/'books').mkdir()
    path=tmp_path/'books/us.db'
    session=create_session(f'sqlite:///{path}')
    session.add(RecoveryDay(market_id='us',day='2024-07-02',status='complete',detail='{"cash":100}',equity=100))
    session.commit(); session.close()
    (tmp_path/'report.json').write_text(json.dumps({'strategies':[{'id':'us','days':[{'day':'2024-07-02'}]}]}))
    assert client.get('/api/v1/history/us/2024-07-02').json()=={'cash':100}
    assert client.get('/api/v1/history/us/2024-07-03').status_code==404
    assert client.get('/api/v1/history/unknown/2024-07-02').status_code==404
    assert client.get('/api/v1/history/us/not-a-date').status_code==404
    assert client.post('/api/v1/history/us/2024-07-02').status_code==405


def test_heartbeat_expiry_is_not_reported_as_running(tmp_path):
    from quantit.api.history import service_status
    (tmp_path/'service.json').write_text(json.dumps({'state':'waiting','heartbeat':'2020-01-01T00:00:00+00:00'}))
    assert service_status(tmp_path)['fresh'] is False


def test_service_skips_already_completed_close_without_network(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from scripts import run_history_service as service
    now=datetime(2026,10,20,14,0,tzinfo=timezone.utc)
    key=service.close_key(now)
    assert key == 'us2026-10-19_hk2026-10-20_cn2026-10-20'
    (tmp_path/'cycle.json').write_text(json.dumps({'completed_key':key}))
    monkeypatch.setattr(service,'download',lambda *a,**kw:pytest.fail('Unnecessary download'))
    service.cycle(tmp_path,{},now=now)
    assert json.loads((tmp_path/'service.json').read_text())['state']=='waiting'


def test_service_refresh_failure_still_runs_rule_books(tmp_path,monkeypatch):
    from datetime import datetime,timezone
    from scripts import run_history_service as service
    source=tmp_path/'source'; source.mkdir()
    pd.DataFrame({'dummy':[1]}).to_parquet(source/'panel.parquet')
    signals=tmp_path/'signals';signals.mkdir()
    (signals/'manifest.json').write_text(json.dumps({'data_asof':'2026-10-19'}))
    monkeypatch.setattr(service,'request_symbols',lambda *a:{'510300.SS':'cn'})
    monkeypatch.setattr(service,'download',lambda *a,**kw:{'symbols':{'510300.SS':{'last':'2026-10-20'}}})
    commands=[]
    def execute(root,argv,stage):
        commands.append(argv)
        if 'closeloop.data.refresh' in argv:
            raise RuntimeError('Provider unavailable')
        (root/'report.json').write_text(json.dumps({'strategies':[{'id':'us','status':'ready'}]}))
    monkeypatch.setattr(service,'command',execute)
    config={'start':'2026-07-01','source_data':str(source),'signals':str(signals),'experiment':'frozen-experiment'}
    with pytest.raises(RuntimeError,match='Provider unavailable'):
        service.cycle(tmp_path,config,now=datetime(2026,10,20,14,tzinfo=timezone.utc))
    assert any('quantit.paper.history' in argv for argv in commands)
    assert 'completed_key' not in json.loads((tmp_path/'cycle.json').read_text())


def test_verified_split_prices_preserve_equity_and_remove_false_gap():
    from quantit.paper.history_data import split_adjusted_from_nominal,quality_issues
    frame=bars()
    frame.loc[frame.index[2]:,['open','high','low','close']]/=2
    corrected=split_adjusted_from_nominal(frame,[{'ex_date':str(frame.index[2].date()),'ratio':2}])
    restored=nominal_prices(corrected)
    assert restored.close.tolist()==frame.close.tolist()
    assert restored.volume.tolist()==frame.volume.tolist()
    assert quality_issues(corrected,'cn')==[]
    wrong=frame.copy(); wrong['stock_splits']=0
    assert any('gap' in x['reason'] for x in quality_issues(wrong,'cn'))
    broker,adapter,symbol,book=broker_for(restored)
    broker.place_order(book,symbol,'buy',100)
    before=broker.get_position(book,symbol).quantity*restored.close.iloc[1]
    actions_before_open(broker,book,{symbol:restored},restored.index[2])
    after=broker.get_position(book,symbol).quantity*restored.close.iloc[2]
    assert before==after


@pytest.mark.parametrize('column,value',[('close',float('inf')),('open',0)])
def test_price_quality_gate_catches_invalid_ohlc(column,value):
    from quantit.paper.history_data import quality_issues
    frame=bars();frame.loc[frame.index[1],column]=value
    assert any(x['reason']=='Invalid OHLC' for x in quality_issues(frame,'cn'))


def test_latest_cn_ohlc_crosscheck_replaces_stale_open_with_saved_source(tmp_path):
    from quantit.paper.history_data import verify_cn_latest
    frame=bars(); frame['adj_close']=frame.close*.9
    day=str(frame.index[-1].date())
    (tmp_path/'source').mkdir()
    (tmp_path/'source/000333.SZ-latest-tencent.json').write_text(json.dumps({'data':{'sz000333':{'day':[[day,'10.5','11','12','9','1000']]}}}))
    fixed,evidence=verify_cn_latest(tmp_path,'000333.SZ',frame)
    assert fixed.open.iloc[-1]==10.5
    assert fixed.adj_close.iloc[-1]==pytest.approx(9.9)
    assert fixed.volume.equals(frame.volume)
    assert evidence['differences']['open']=={'yahoo':10.,'tencent':10.5}


def test_ohlc_envelope_inconsistency_is_visible_without_inventing_prices():
    from quantit.paper.history_data import quality_issues
    frame=bars();frame.loc[frame.index[1],'high']=10.5
    issues=quality_issues(frame,'hk')
    assert issues==[{'day':'2024-07-02','reason':'Open/close outside reported daily range','severity':'warning'}]


def test_frozen_predictions_select_only_pre_start_model_and_reject_unmatured_labels(tmp_path, monkeypatch):
    import numpy as np
    pytest.importorskip("lightgbm", reason="Frozen-model export requires the optional research environment")
    from closeloop.model import history_signals as hs
    from closeloop.model.experiment import file_hash
    data=tmp_path/'data';data.mkdir()
    experiment=tmp_path/'experiment';experiment.mkdir()
    dates=pd.bdate_range('2024-01-01',periods=25)
    panel=pd.DataFrame(np.ones((25,2)),index=dates,columns=pd.MultiIndex.from_tuples([('close','SH600000'),('volume','SH600000')]))
    panel.to_parquet(data/'panel.parquet')
    features=pd.DataFrame({'f':np.ones(25)},index=pd.MultiIndex.from_product([dates,['SH600000']],names=['date','instrument']))
    features.to_parquet(experiment/'features.parquet')
    name='alpha158_lgbm_h1'
    strategy={'id':name,'name':'test','horizon':1,'validation':{'end':'2024-01-05'},'training_folds':[
        {'fold':1,'test_start':'2024-01-10','train':{'end':'2024-01-02'},'embargo':1},
        {'fold':2,'test_start':'2024-01-26','train':{'end':'2024-01-23'},'embargo':1}]}
    report={'panel_sha256':file_hash(data/'panel.parquet'),'strategies':[strategy]}
    (experiment/'report.json').write_text(json.dumps(report))
    (experiment/f'{name}-selection.json').write_text(json.dumps({'config':{'top_k':1}}))
    (experiment/f'{name}-fold1.txt').write_text('frozen')
    loaded=[]
    class FakeModel:
        def __init__(self,model_file):loaded.append(model_file)
        def feature_name(self):return ['f']
        def predict(self,x):return np.ones(len(x))
    monkeypatch.setattr(hs.lgb,'Booster',FakeModel)
    result=hs.prepare(experiment,data,tmp_path/'signals','2024-01-24')
    assert loaded==[str(experiment/f'{name}-fold1.txt')]
    assert result['strategies'][name]['model']['train_end']=='2024-01-02'
    predictions=pd.read_parquet(tmp_path/'signals'/f'{name}.parquet')
    assert str(predictions.index.min().date())=='2024-01-24'
    strategy['training_folds'][0]['train']['end']='2024-01-23'
    (experiment/'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='not mature'):
        hs.prepare(experiment,data,tmp_path/'bad-signals','2024-01-24')
