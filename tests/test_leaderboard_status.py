"""
Tests for list_agreements_by_status and get_leaderboard, the read-only
views behind the status tabs and the Leaderboard page.
"""
import json
import unittest

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
)
from test_list_views import make_agreement
from test_stats_profile import resolve


class ListByStatusTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_filters_by_status_newest_first(self):
        make_agreement(self.c)
        b = make_agreement(self.c)
        make_agreement(self.c)
        set_caller(PARTY_B_ADDRESS)
        self.c.accept_agreement(b)
        pending = json.loads(self.c.list_agreements_by_status("pending_acceptance", 0, 10))
        self.assertEqual(pending["total"], 2)
        self.assertEqual([a["agreement_id"] for a in pending["items"]], ["2", "0"])
        opened = json.loads(self.c.list_agreements_by_status("open", 0, 10))
        self.assertEqual([a["agreement_id"] for a in opened["items"]], ["1"])
        self.assertEqual(opened["status"], "open")

    def test_pagination_over_matches(self):
        for _ in range(4):
            make_agreement(self.c)
        page = json.loads(self.c.list_agreements_by_status("pending_acceptance", 1, 2))
        self.assertEqual(page["total"], 4)
        self.assertEqual([a["agreement_id"] for a in page["items"]], ["2", "1"])

    def test_cancelled_status(self):
        aid = make_agreement(self.c)
        set_caller(PARTY_A_ADDRESS)
        self.c.cancel_agreement(aid)
        page = json.loads(self.c.list_agreements_by_status("cancelled", 0, 5))
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["status"], "cancelled")

    def test_empty_when_nothing_matches(self):
        make_agreement(self.c)
        page = json.loads(self.c.list_agreements_by_status("resolved", 0, 5))
        self.assertEqual(page["total"], 0)
        self.assertEqual(page["items"], [])

    def test_unknown_status_rejected(self):
        with self.assertRaises(gl.vm.UserError):
            self.c.list_agreements_by_status("banana", 0, 5)

    def test_invalid_paging_rejected(self):
        with self.assertRaises(gl.vm.UserError):
            self.c.list_agreements_by_status("open", -1, 5)
        with self.assertRaises(gl.vm.UserError):
            self.c.list_agreements_by_status("open", 0, 0)

    def test_summary_has_no_evidence(self):
        make_agreement(self.c)
        item = json.loads(self.c.list_agreements_by_status("pending_acceptance", 0, 1))["items"][0]
        self.assertNotIn("records", item)


class LeaderboardTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_empty_when_nothing_resolved(self):
        make_agreement(self.c)
        board = json.loads(self.c.get_leaderboard(10))
        self.assertEqual(board["total_ranked"], 0)
        self.assertEqual(board["items"], [])

    def test_ranks_winner_first_with_stats(self):
        a1 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a1, FINAL_HIGH_SCORING_CONTENT)
        a2 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a2, FINAL_HIGH_SCORING_CONTENT)
        a3 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a3, FINAL_LOW_SCORING_CONTENT)
        board = json.loads(self.c.get_leaderboard(10))
        self.assertEqual(board["total_ranked"], 2)
        first, second = board["items"]
        self.assertEqual(first["rank"], 1)
        self.assertEqual(first["address"], PARTY_A_ADDRESS.lower())
        self.assertEqual((first["wins"], first["losses"], first["decided"]), (2, 1, 3))
        self.assertEqual(first["win_rate_percent"], 66)
        self.assertEqual(second["rank"], 2)
        self.assertEqual(second["address"], PARTY_B_ADDRESS.lower())
        self.assertEqual((second["wins"], second["losses"]), (1, 2))
        self.assertEqual(second["win_rate_percent"], 33)

    def test_limit_truncates_but_total_ranked_stays(self):
        a1 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a1, FINAL_HIGH_SCORING_CONTENT)
        board = json.loads(self.c.get_leaderboard(1))
        self.assertEqual(len(board["items"]), 1)
        self.assertEqual(board["total_ranked"], 2)

    def test_unresolved_and_open_agreements_ignored(self):
        create_and_accept(self.c)
        make_agreement(self.c, creator=STRANGER_ADDRESS, other=PARTY_A_ADDRESS)
        board = json.loads(self.c.get_leaderboard(10))
        self.assertEqual(board["total_ranked"], 0)

    def test_tie_broken_by_address(self):
        a1 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a1, FINAL_HIGH_SCORING_CONTENT)
        a2 = create_and_accept(self.c, comparison="above")
        resolve(self.c, a2, FINAL_LOW_SCORING_CONTENT)
        board = json.loads(self.c.get_leaderboard(10))
        addrs = [i["address"] for i in board["items"]]
        self.assertEqual(addrs, sorted(addrs))

    def test_limit_validation_and_cap(self):
        with self.assertRaises(gl.vm.UserError):
            self.c.get_leaderboard(0)
        board = json.loads(self.c.get_leaderboard(10_000))
        self.assertEqual(board["limit"], self.c.MAX_LIST_PAGE_SIZE)


if __name__ == "__main__":
    unittest.main()
