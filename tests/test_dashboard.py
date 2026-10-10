from streamlit.testing.v1 import AppTest
from gexbook.dashboard.app import PAGES


def test_dashboard_pages_and_demo():
    app = AppTest.from_file("../app.py").run(timeout=15)
    assert not app.exception
    for page in PAGES:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception
        assert not app.error, [x.value for x in app.error]
    app.sidebar.radio[0].set_value("Backtesting").run()
    next(b for b in app.button if b.label == "Run synthetic verification example").click().run()
    assert not app.exception
    assert not app.error
    assert app.session_state["engine"].result.trades
    for page in ["Overview", "Bookmap Order Flow", "Strategy Monitor", "Risk Management"]:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception
        assert not app.error, [x.value for x in app.error]


def test_dashboard_manual_mapping_save_and_locked_anchor(tmp_path, monkeypatch):
    from pathlib import Path
    from gexbook.storage.sqlite import Store

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(app_path).run()
    app.session_state["level_rows"] = [
        {
            "id": "user-level",
            "kind": "Put Wall",
            "qqq_price": 500.0,
            "mnq_price": None,
            "importance": 1.0,
            "role": "support",
            "provenance": "manual",
            "metric": None,
            "approximate": True,
            "override_reason": "",
        }
    ]
    app.sidebar.radio[0].set_value("GEX Levels").run()
    next(b for b in app.button if b.label == "Map and save session snapshot").click().run()
    assert not app.exception and not app.error
    store = Store()
    saved = store.snapshots()
    assert len(saved) == 1 and saved[0].levels[0].mnq_price == 20000
    store.close()
    next(n for n in app.number_input if n.label == "Manual conversion factor").set_value(41.0)
    next(b for b in app.button if b.label == "Map and save session snapshot").click().run()
    assert not app.exception and not app.error
    store = Store()
    assert store.snapshots()[-1].anchor == saved[0].anchor
    store.close()
