"""
Tests for the list views (list_agreements / list_agreements_for) that let
a frontend browse agreements without the user typing an id.
"""
import datetime
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


def iso_in(seconds_from_now):
    dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=seconds_from_now
    )
    return dt.isoformat()


def make_agreement(c, creator=PARTY_A_ADDRESS, other=PARTY_B_ADDRESS, teams="Arsenal vs Chelsea"):
    set_caller(creator)
    return c.create_agreement(
        party_b_address=other,
        teams=teams,
        match_date="2026-09-05",
        threshold_score="2.5",
        comparison="above",
        description="list view test",
        resolution_deadline=iso_in(c.MIN_DEADLINE_LEAD_SECONDS + 5),
        required_source_domains=["espn.com", "bbc.com"],
    )


class ListAgreementsTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_empty_contract_returns_empty_page(self):
        page = json.loads(self.c.list_agreements(0, 10))
        self.assertEqual(page["total"], 0)
        self.assertEqual(page["items"], [])

    def test_newest_first_order(self):
        for i in range(3):
            make_agreement(self.c, teams=f"Team{i} vs Other{i}")
        page = json.loads(self.c.list_agreements(0, 10))
        self.assertEqual(page["total"], 3)
        self.assertEqual([a["agreement_id"] for a in page["items"]], ["2", "1", "0"])

    def test_pagination_offset_and_limit(self):
        for _ in range(5):
            make_agreement(self.c)
        first = json.loads(self.c.list_agreements(0, 2))
        second = json.loads(self.c.list_agreements(2, 2))
        third = json.loads(self.c.list_agreements(4, 2))
        self.assertEqual([a["agreement_id"] for a in first["items"]], ["4", "3"])
        self.assertEqual([a["agreement_id"] for a in second["items"]], ["2", "1"])
        self.assertEqual([a["agreement_id"] for a in third["items"]], ["0"])

    def test_offset_past_end_returns_no_items(self):
        make_agreement(self.c)
        page = json.loads(self.c.list_agreements(10, 5))
        self.assertEqual(page["items"], [])
        self.assertEqual(page["total"], 1)

    def test_limit_is_capped(self):
        page = json.loads(self.c.list_agreements(0, 10_000))
        self.assertEqual(page["limit"], self.c.MAX_LIST_PAGE_SIZE)

    def test_invalid_offset_and_limit_rejected(self):
        with self.assertRaises(gl.vm.UserError):
            self.c.list_agreements(-1, 5)
        with self.assertRaises(gl.vm.UserError):
            self.c.list_agreements(0, 0)

    def test_summary_omits_evidence_but_has_core_fields(self):
        make_agreement(self.c)
        item = json.loads(self.c.list_agreements(0, 1))["items"][0]
        self.assertNotIn("records", item)
        self.assertNotIn("locked_source_urls", item)
        for key in ("agreement_id", "status", "party_a", "party_b", "teams",
                    "comparison", "final_verdict", "winner", "resolution_deadline"):
            self.assertIn(key, item)
        self.assertEqual(item["status"], "pending_acceptance")

    def test_list_reflects_status_changes(self):
        aid = make_agreement(self.c)
        set_caller(PARTY_B_ADDRESS)
        self.c.accept_agreement(aid)
        item = json.loads(self.c.list_agreements(0, 1))["items"][0]
        self.assertEqual(item["status"], "open")


class ListAgreementsForTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_only_agreements_involving_address(self):
        make_agreement(self.c, creator=PARTY_A_ADDRESS, other=PARTY_B_ADDRESS)
        make_agreement(self.c, creator=PARTY_A_ADDRESS, other=STRANGER_ADDRESS)
        make_agreement(self.c, creator=STRANGER_ADDRESS, other=PARTY_B_ADDRESS)
        mine_b = json.loads(self.c.list_agreements_for(PARTY_B_ADDRESS, 0, 10))
        self.assertEqual(mine_b["total"], 2)
        self.assertEqual([a["agreement_id"] for a in mine_b["items"]], ["2", "0"])
        mine_a = json.loads(self.c.list_agreements_for(PARTY_A_ADDRESS, 0, 10))
        self.assertEqual([a["agreement_id"] for a in mine_a["items"]], ["1", "0"])

    def test_address_match_is_case_insensitive(self):
        make_agreement(self.c)
        upper = "0x" + PARTY_A_ADDRESS[2:].upper()
        page = json.loads(self.c.list_agreements_for(upper, 0, 10))
        self.assertEqual(page["total"], 1)

    def test_unrelated_address_gets_empty_page(self):
        make_agreement(self.c)
        page = json.loads(self.c.list_agreements_for(STRANGER_ADDRESS, 0, 10))
        self.assertEqual(page["total"], 0)
        self.assertEqual(page["items"], [])

    def test_pagination_over_matches(self):
        for _ in range(4):
            make_agreement(self.c)
        page = json.loads(self.c.list_agreements_for(PARTY_A_ADDRESS, 1, 2))
        self.assertEqual(page["total"], 4)
        self.assertEqual([a["agreement_id"] for a in page["items"]], ["2", "1"])

    def test_invalid_address_rejected(self):
        with self.assertRaises(gl.vm.UserError):
            self.c.list_agreements_for("not-an-address", 0, 5)


if __name__ == "__main__":
    unittest.main()
