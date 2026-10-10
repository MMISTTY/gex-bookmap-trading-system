from datetime import datetime, timedelta
from dataclasses import replace
import pytest
from gexbook.gex.ingestion import parse_csv, derive_levels, DataError
from gexbook.mapping.anchors import synchronized_anchor, map_level, override_level
from gexbook.models import Level, Snapshot, timestamp
from gexbook.storage.sqlite import Store

NOW = datetime.fromisoformat("2026-01-05T14:30:00+00:00")


def test_barchart_long_and_unsigned_signs():
    r = parse_csv(
        'Type,Strike,Open Int,Gamma,IV,Expiration\nCall,500,"1,000",0.01,20%,01/09/2026\nPut,490,500,0.02,25%,01/09/2026\nDownloaded by Barchart\n'
    )
    assert r.contracts[0].iv == 0.2
    levels, notes = derive_levels(r, 500)
    assert any(level.kind == "Call Wall" and level.qqq_price == 500 for level in levels)
    assert all("Major Positive" not in level.kind for level in levels)
    assert any("Gamma Flip unavailable" in n for n in notes)
    levels, _ = derive_levels(r, 500, "calls_positive_puts_negative")
    assert any(level.kind == "Major Negative GEX" and level.approximate for level in levels)


def test_wide_missing_gamma_is_reported():
    r = parse_csv("Strike,Call OI,Put OI,Call Volume,Put Volume\n500,100,200,50,80\n")
    levels, notes = derive_levels(r, 500)
    assert len(levels) == 2
    assert any("contract gamma" in n for n in notes)


def test_existing_signed_profile_requires_units():
    r = parse_csv("Strike,Net GEX\n490,-100\n510,200\n")
    levels, notes = derive_levels(r, 500)
    assert not levels
    levels, _ = derive_levels(r, 500, "provided_signed", "USD per 1%")
    assert any(level.kind == "Major Positive GEX" and level.qqq_price == 510 for level in levels)
    assert not any(level.kind == "Gamma Flip" for level in levels)


def test_manual_flip_and_mnq_only_levels():
    r = parse_csv(
        "Level Type,QQQ Price,MNQ Price,Role\nGamma Flip,499,,neutral\nSupport,,20000,support\n"
    )
    assert len(r.levels) == 2 and r.levels[1].qqq_price is None


@pytest.mark.parametrize(
    "text",
    [
        "Type,Strike,Open Int\nCall,500,NaN\n",
        "Type,Strike,Open Int\nCall,500,-1\n",
        "Type,Strike,Open Int\nCall,500,1\nCall,500,2\n",
        "Strike,Call OI\n500,1,2\n",
        "foo,bar\n1,2\n",
        "Type,Strike,Gamma\nUnknown,500,.1\n",
    ],
)
def test_corrupt_options_fail_closed(text):
    with pytest.raises(DataError):
        parse_csv(text)


def test_mapping_sync_lock_override_and_history(tmp_path):
    a = synchronized_anchor("session", 500, 20000, NOW, NOW, NOW)
    level = map_level(Level("a", "Support", 501, role="support"), a)
    assert level.mnq_price == 20040 and a.factor == 40
    assert (
        override_level(level, mnq_price=20041.13, reason="manual reference").mnq_price == 20041.25
    )
    with pytest.raises(ValueError):
        synchronized_anchor("s", 500, 20000, NOW, NOW + timedelta(seconds=3), NOW)
    store = Store(tmp_path / "db.sqlite")
    store.lock_anchor(a)
    with pytest.raises(ValueError):
        store.lock_anchor(replace(a, factor=41))
    s = Snapshot("s", NOW, NOW + timedelta(hours=1), (level,), a, "manual")
    store.save_snapshot(s)
    assert store.snapshots()[0] == s
    store.close()


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        timestamp("2026-11-01T01:30:00")
