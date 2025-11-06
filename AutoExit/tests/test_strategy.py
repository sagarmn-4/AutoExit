import asyncio
import csv
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure project package is importable
ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.position_monitor import PositionMonitor
from utils.trade_manager import TradeManager


class FakeKite:
    def __init__(self, positions=None):
        self._positions = positions or []

    def positions(self):
        return {"net": self._positions}


class FakeKiteHelper:
    """Minimal fake for KiteHelper expected interface in tests."""

    def __init__(self, positions=None, ltp_map=None):
        self.kite = FakeKite(positions)
        self._ltp = ltp_map or {}

    def get_ltp(self, instrument_token):
        # instrument_token may be like "NFO:SYMBOL" or numeric token
        return self._ltp.get(instrument_token, 100.0)

    def exit_all_positions(self):
        return True


class TestPositionMonitor(unittest.IsolatedAsyncioTestCase):
    async def test_places_paper_exit_for_new_long_position(self):
        # One long position should trigger paper exit order flow once
        positions = [
            {
                "tradingsymbol": "NIFTY25NOV17500CE",
                "product": "NRML",
                "quantity": 75,
                "average_price": 200.0,
                "exchange": "NFO",
            }
        ]
        helper = FakeKiteHelper(positions=positions)
        mon = PositionMonitor(helper)

        # Patch the symbol imported in position_monitor module
        with patch("strategies.position_monitor.send_telegram") as mock_send:
            await mon._check_positions()
            self.assertEqual(len(mon.tracked_positions), 1)
            self.assertTrue(mock_send.called)

            # Second check with same positions should not duplicate
            await mon._check_positions()
            self.assertEqual(len(mon.tracked_positions), 1)


class TestTradeManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="autoexit_tests_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_paper_trade_lifecycle(self):
        ltp_map = {"NFO:NIFTY25NOV17500CE": 210.5}
        helper = FakeKiteHelper(ltp_map=ltp_map)

        tm = TradeManager(helper, paper_mode=True)
        # redirect paper trades file into temp dir
        tm.paper_trades_file = Path(self.tmpdir) / "paper_trades.csv"
        tm._init_paper_trades_file()

        order_id = tm.enter_trade("NIFTY25NOV17500CE", 75, "BUY")
        self.assertIsNotNone(order_id)
        self.assertTrue(str(order_id).startswith("SIM_"))

        # Exit and ensure CSV is updated
        self.assertTrue(tm.exit_trade("NIFTY25NOV17500CE", rr_stage="T1"))

        with open(tm.paper_trades_file, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "CLOSED")
        self.assertEqual(rows[0]["rr_stage"], "T1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
