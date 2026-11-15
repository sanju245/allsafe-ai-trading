import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_indicators import score_events, summarize, segments
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.instruments import InstrumentId
from app.market_data.timeframes import Timeframe
from datetime import datetime, timedelta, date
from app.market_data.sessions import IST


def data():
    return [Candle(timestamp=datetime(2026,1,5,9,15,tzinfo=IST)+timedelta(minutes=5*i),
                   open=100+i,high=102+i,low=99+i,close=101+i,
                   instrument=InstrumentId.NIFTY50,timeframe=Timeframe.M5,
                   source=DataSource(name="SYNTHETIC-TEST-ONLY",kind=DataSourceKind.SAMPLE)) for i in range(15)]


def test_entry_uses_next_open_and_exit_30_minutes_later():
    rows,_=score_events(data(),{"TEST":[0,1]+[0]*13},date(2026,1,5),date(2026,1,5))
    row=next(r for r in rows if r["horizon_minutes"]==30)
    assert row["entry"]==102 and row["exit"]==108
    assert datetime.fromisoformat(row["exit_time"])-datetime.fromisoformat(row["entry_time"])==timedelta(minutes=30)


def test_intraday_gap_splits_indicator_history():
    candles=data()
    chunks=segments(candles[:5]+candles[6:])
    assert [len(c) for c in chunks]==[5,9]


def test_empty_denominator_is_not_zero_accuracy():
    assert summarize([])["accuracy_pct"] is None
