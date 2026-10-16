"""Facebook, Stories and the IG post fallback must share Apify credit equally."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import apify_pool


MIDNIGHT = 20713 * 86400.0  # a UTC midnight
HOUR = 3600.0


def _status(remaining=3.02, *, checked_at=MIDNIGHT):
    # 3.00 spendable over exactly ten days => 0.30 per day, 0.10 per consumer.
    return {"accounts": [{
        "label": "A", "available": True, "exhausted": False, "remainingUsd": remaining,
        "checkedAt": checked_at, "cycleEnd": "2026-09-27T00:00:00Z",
    }]}


class AllocationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.state_path = Path(self.tempdir.name) / "pool.json"
        patcher = patch.object(apify_pool, "POOL_STATE_PATH", self.state_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def available(self, consumer, now, status=None):
        allocation = apify_pool.apify_allocation(status or _status(), now=now)
        return allocation["consumers"][consumer]["availableUsd"]

    def test_day_starts_with_an_equal_share_for_every_consumer(self):
        allocation = apify_pool.apify_allocation(_status(), now=MIDNIGHT)
        self.assertAlmostEqual(allocation["paceUsd"], 0.30)
        self.assertAlmostEqual(allocation["shareUsd"], 0.10)
        for consumer in apify_pool.CONSUMERS:
            self.assertAlmostEqual(self.available(consumer, MIDNIGHT), 0.10)

    def test_facebook_cannot_take_shares_others_can_still_claim(self):
        apify_pool.record_run("A", consumer="facebook", cost_usd=0.10, source_count=8, ok=True,
                              now=MIDNIGHT + HOUR)
        # One hour in, Stories and IG still hold 23/24 of their shares; only
        # the expired hour of each is free for anyone.
        self.assertAlmostEqual(self.available("facebook", MIDNIGHT + HOUR), 0.2 - 2 * 0.1 * 23 / 24, places=5)
        self.assertAlmostEqual(self.available("story", MIDNIGHT + HOUR), 0.2 - 0.1 * 23 / 24, places=5)

    def test_unused_shares_expire_to_whoever_still_needs_credit(self):
        apify_pool.record_run("A", consumer="facebook", cost_usd=0.10, source_count=8, ok=True,
                              now=MIDNIGHT + HOUR)
        noon = MIDNIGHT + 12 * HOUR
        # Half the day is gone: each idle consumer keeps half its share.
        self.assertAlmostEqual(self.available("facebook", noon), 0.10)
        self.assertAlmostEqual(self.available("story", noon), 0.15)
        # By the end of the day everything unspent is available to anyone.
        self.assertAlmostEqual(self.available("facebook", MIDNIGHT + 24 * HOUR - 1), 0.20, places=4)

    def test_borrowing_never_erodes_another_consumers_remaining_claim(self):
        noon = MIDNIGHT + 12 * HOUR
        apify_pool.record_run("A", consumer="facebook", cost_usd=0.20, source_count=15, ok=True, now=noon)
        allocation = apify_pool.apify_allocation(_status(), now=noon)
        self.assertAlmostEqual(allocation["consumers"]["story"]["availableUsd"], 0.05)
        self.assertAlmostEqual(allocation["consumers"]["instagram"]["availableUsd"], 0.05)
        self.assertAlmostEqual(allocation["consumers"]["facebook"]["availableUsd"], 0.0)

    def test_quota_snapshot_taken_after_a_run_does_not_shrink_todays_pace(self):
        apify_pool.record_run("A", consumer="story", cost_usd=0.04, source_count=9, ok=True,
                              now=MIDNIGHT + HOUR)
        fresh = _status(remaining=2.98, checked_at=MIDNIGHT + 2 * HOUR)
        stale = _status(remaining=3.02, checked_at=MIDNIGHT)
        for status in (fresh, stale):
            allocation = apify_pool.apify_allocation(status, now=MIDNIGHT + 2 * HOUR)
            self.assertAlmostEqual(allocation["paceUsd"], 0.30)
            self.assertAlmostEqual(allocation["consumers"]["story"]["spentUsd"], 0.04)

    def test_unreported_cost_is_charged_from_the_per_source_estimate(self):
        apify_pool.record_run("A", consumer="facebook", cost_usd=None, source_count=4, ok=True, now=MIDNIGHT)
        apify_pool.record_run("A", consumer="facebook", cost_usd=None, source_count=4, ok=False, now=MIDNIGHT)
        spent = apify_pool.apify_allocation(_status(), now=MIDNIGHT)["consumers"]["facebook"]["spentUsd"]
        self.assertAlmostEqual(spent, 4 * apify_pool.SOURCE_COST_ESTIMATE_USD["facebook"])
        with self.assertRaises(ValueError):
            apify_pool.record_run("A", consumer="youtube", cost_usd=0.1, source_count=1, ok=True)

    def test_spend_resets_each_utc_day_and_keeps_a_short_history(self):
        for day in range(20):
            apify_pool.record_run("A", consumer="story", cost_usd=0.01, source_count=2, ok=True,
                                  now=MIDNIGHT + day * 24 * HOUR)
        state = json.loads(self.state_path.read_text())
        self.assertEqual(len(state["spend"]["events"]), 1)
        self.assertEqual(len(state["spendHistory"]), apify_pool.SPEND_HISTORY_DAYS)
        allocation = apify_pool.apify_allocation(_status(), now=MIDNIGHT + 19 * 24 * HOUR)
        self.assertAlmostEqual(allocation["consumers"]["story"]["averageDailyUsd"], 0.01)

    def test_round_budget_spreads_the_allowance_over_the_rounds_left_today(self):
        self.assertAlmostEqual(apify_pool.round_budget_usd("facebook", _status(), round_hours=3,
                                                           now=MIDNIGHT), 0.10 * 3 / 24)
        late = MIDNIGHT + 22 * HOUR
        self.assertAlmostEqual(apify_pool.round_budget_usd("facebook", _status(), round_hours=3, now=late),
                               self.available("facebook", late))

    def test_facebook_interval_uses_credit_others_have_recently_left_unused(self):
        status = _status()
        without_history = apify_pool.recommended_interval_hours(status, source_count=100, now=MIDNIGHT)
        for day in range(1, 8):
            for consumer in ("story", "instagram"):
                apify_pool.record_run("A", consumer=consumer, cost_usd=0.01, source_count=2, ok=True,
                                      now=MIDNIGHT - day * 24 * HOUR)
        with_history = apify_pool.recommended_interval_hours(status, source_count=100, now=MIDNIGHT)
        # 100 pages x 0.013 at 0.10/day (capped at one week) vs 0.28/day.
        self.assertEqual(without_history, apify_pool.MAX_INTERVAL_HOURS)
        self.assertEqual(with_history, round(24 * 100 * 0.013 / 0.28, 2))
        self.assertEqual(apify_pool.recommended_interval_hours({"accounts": []}, source_count=300,
                                                               now=MIDNIGHT), apify_pool.MAX_INTERVAL_HOURS)


if __name__ == "__main__":
    unittest.main()
