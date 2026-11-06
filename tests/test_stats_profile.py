"""
Tests for the read-only stats views (get_stats / get_profile) that power
the dashboard strip and the player profile page.
"""
import json
import unittest
from unittest.mock import patch

from _bootstrap import (
    PARTY_A_ADDRESS,
    PARTY_B_ADDRESS,
    STRANGER_ADDRESS,
    gl,
    make_contract,
    set_caller,
)
from test_end_to_end import (
    FINAL_HIGH_SCORING_CONTENT,
    FINAL_LOW_SCORING_CONTENT,
    create_and_accept,
    llm_response_for,
)
from test_list_views import make_agreement


def resolve(c, aid, content):
    with patch.object(
        gl.nondet.web, "render", side_effect=lambda url, mode="text": content
    ), patch.object(
        gl.nondet, "exec_prompt",
        side_effect=lambda p, response_format="text": llm_response_for(content),
    ):
        return json.loads(
            c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
        )


class GetStatsTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_empty_contract(self):
        stats = json.loads(self.c.get_stats())
        self.assertEqual(stats["total"], 0)
        self.assertEqual(sum(stats["by_status"].values()), 0)
        self.assertEqual(stats["resolved"]["winner_counts"], {"party_a": 0, "party_b": 0})

    def test_counts_by_status(self):
        make_agreement(self.c)
        aid = make_agreement(self.c)
        set_caller(PARTY_B_ADDRESS)
        self.c.accept_agreement(aid)
        stats = json.loads(self.c.get_stats())
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["by_status"]["pending_acceptance"], 1)
        self.assertEqual(stats["by_status"]["open"], 1)
        self.assertEqual(sum(stats["by_status"].values()), 2)

    def test_cancelled_is_counted(self):
        aid = make_agreement(self.c)
        set_caller(PARTY_A_ADDRESS)
        self.c.cancel_agreement(aid)
        stats = json.loads(self.c.get_stats())
        self.assertEqual(stats["by_status"]["cancelled"], 1)

    def test_resolved_winner_and_verdict_counts(self):
        a1 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a1, FINAL_HIGH_SCORING_CONTENT)
        a2 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a2, FINAL_LOW_SCORING_CONTENT)
        stats = json.loads(self.c.get_stats())
        self.assertEqual(stats["by_status"]["resolved"], 2)
        self.assertEqual(stats["resolved"]["winner_counts"], {"party_a": 1, "party_b": 1})
        self.assertEqual(stats["resolved"]["verdict_counts"]["Above"], 1)
        self.assertEqual(stats["resolved"]["verdict_counts"]["Below"], 1)


class GetProfileTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_unknown_address_is_all_zero(self):
        make_agreement(self.c)
        p = json.loads(self.c.get_profile(STRANGER_ADDRESS))
        self.assertEqual(p["total"], 0)
        self.assertEqual((p["wins"], p["losses"]), (0, 0))
        self.assertIsNone(p["win_rate_percent"])

    def test_created_and_invited_counts(self):
        make_agreement(self.c, creator=PARTY_A_ADDRESS, other=PARTY_B_ADDRESS)
        make_agreement(self.c, creator=PARTY_A_ADDRESS, other=STRANGER_ADDRESS)
        make_agreement(self.c, creator=STRANGER_ADDRESS, other=PARTY_A_ADDRESS)
        p = json.loads(self.c.get_profile(PARTY_A_ADDRESS))
        self.assertEqual((p["total"], p["created"], p["invited"]), (3, 2, 1))
        self.assertEqual(p["by_status"]["pending_acceptance"], 3)
        self.assertIsNone(p["win_rate_percent"])

    def test_wins_losses_and_rate(self):
        a1 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a1, FINAL_HIGH_SCORING_CONTENT)
        a2 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a2, FINAL_LOW_SCORING_CONTENT)
        a3 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a3, FINAL_HIGH_SCORING_CONTENT)
        pa = json.loads(self.c.get_profile(PARTY_A_ADDRESS))
        pb = json.loads(self.c.get_profile(PARTY_B_ADDRESS))
        self.assertEqual((pa["wins"], pa["losses"], pa["win_rate_percent"]), (2, 1, 66))
        self.assertEqual((pb["wins"], pb["losses"], pb["win_rate_percent"]), (1, 2, 33))

    def test_address_is_case_insensitive_and_normalized(self):
        make_agreement(self.c)
        upper = "0x" + PARTY_A_ADDRESS[2:].upper()
        p = json.loads(self.c.get_profile(upper))
        self.assertEqual(p["total"], 1)
        self.assertEqual(p["address"], PARTY_A_ADDRESS.lower())

    def test_invalid_address_rejected(self):
        with self.assertRaises(gl.vm.UserError):
            self.c.get_profile("nope")


if __name__ == "__main__":
    unittest.main()
