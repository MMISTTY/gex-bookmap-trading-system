from datetime import date
from gexbook.gex.source import inspect_source
from gexbook.gex.ingestion import parse_csv, derive_levels, DataError
import pytest


def test_barchart_profile_and_expired_historical_source():
    text = (
        "Strike,Call Gamma Exposure,Net Gamma Exposure,Call Open Interest\n"
        "760,100,25,100\nDownloaded from Barchart.com as of 10/7/2026, 4:40:36 PM\n"
    )
    src = inspect_source("QQQ-gamma-levels-exp-20261007-weekly.csv", text)
    assert src.kind == "gamma_profile"
    assert src.observed_on == date(2026, 10, 7)
    assert src.expires_on == date(2026, 10, 7)
    assert len(src.current_session_errors(date(2026, 10, 10))) == 2
    assert src.current_session_errors(date(2026, 10, 7)) == []


def test_trade_flow_rejected_instead_of_deduplicated_as_options_chain():
    text = (
        "Symbol,Price~,Exp Date,Type,Strike,Trade,Size,Side,Open Int\n"
        "QQQ,750,2026-10-16,Call,755,10.5,100,ask,200\n"
        "QQQ,750,2026-10-16,Call,755,10.6,150,bid,200\n"
    )
    profile = inspect_source("qqq-options-flow-10-07-2026.csv", text)
    assert profile.kind == "options_flow"
    with pytest.raises(DataError, match="individual trade prints"):
        parse_csv(text)


def test_gamma_weighted_wall_can_differ_from_oi_only_wall():
    report = parse_csv(
        "Type,Strike,Open Int,Gamma\nCall,750,1000,0.001\nCall,760,100,0.1\n"
        "Put,740,100,0.02\n"
    )
    levels, _ = derive_levels(report, 755)
    wall = next(level for level in levels if level.kind == "Call Wall")
    assert wall.qqq_price == 760
    assert "gamma" in wall.provenance
    assert wall.metric == pytest.approx(10)


def test_partial_gamma_falls_back_to_open_interest():
    report = parse_csv("Type,Strike,Open Int,Gamma\nCall,750,1000,\nCall,760,100,0.1\n")
    levels, notes = derive_levels(report, 755)
    assert next(x for x in levels if x.kind == "Call Wall").qqq_price == 750
    assert any("missing contract gamma" in x for x in notes)
