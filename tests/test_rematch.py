"""
Tests for propose_rematch: a party to a RESOLVED agreement proposes a
new agreement against the same counterparty, reusing the source's
description and committed source domains.
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
    create_and_accept,
    iso_in,
)
from test_list_views import make_agreement
from test_stats_profile import resolve


def rematch_args(c, **over):
    args = dict(
        teams="Real Madrid vs Barcelona",
        match_date="2026-12-01",
        threshold_score="3.5",
        comparison="below",
        resolution_deadline=iso_in(c.MIN_DEADLINE_LEAD_SECONDS + 60),
    )
    args.update(over)
    return args


class ProposeRematchTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()
        self.src = create_and_accept(self.c, comparison="above")
        resolve(self.c, self.src, FINAL_HIGH_SCORING_CONTENT)

    def test_party_a_rematch_swaps_nothing_and_keeps_counterparty(self):
        set_caller(PARTY_A_ADDRESS)
        new_id = self.c.propose_rematch(self.src, **rematch_args(self.c))
        rec = json.loads(self.c.get_agreement(new_id))
        self.assertEqual(rec["party_a"].lower(), PARTY_A_ADDRESS.lower())
        self.assertEqual(rec["party_b"].lower(), PARTY_B_ADDRESS.lower())
        self.assertEqual(rec["status"], "pending_acceptance")
        self.assertEqual(rec["rematch_of"], self.src)
        self.assertEqual(rec["threshold_score"], "3.5")
        self.assertEqual(rec["comparison"], "below")
        self.assertEqual(rec["teams"].lower(), "real madrid vs barcelona")

    def test_party_b_can_propose_and_becomes_party_a(self):
        set_caller(PARTY_B_ADDRESS)
        new_id = self.c.propose_rematch(self.src, **rematch_args(self.c))
        rec = json.loads(self.c.get_agreement(new_id))
        self.assertEqual(rec["party_a"].lower(), PARTY_B_ADDRESS.lower())
        self.assertEqual(rec["party_b"].lower(), PARTY_A_ADDRESS.lower())

    def test_carries_description_and_source_domains(self):
        src = json.loads(self.c.get_agreement(self.src))
        set_caller(PARTY_A_ADDRESS)
        new_id = self.c.propose_rematch(self.src, **rematch_args(self.c))
        rec = json.loads(self.c.get_agreement(new_id))
        self.assertEqual(rec["description"], src["description"])
        self.assertEqual(rec["required_source_domains"], src["required_source_domains"])

    def test_counterparty_can_accept_the_rematch(self):
        set_caller(PARTY_A_ADDRESS)
        new_id = self.c.propose_rematch(self.src, **rematch_args(self.c))
        set_caller(PARTY_B_ADDRESS)
        self.c.accept_agreement(new_id)
        rec = json.loads(self.c.get_agreement(new_id))
        self.assertEqual(rec["status"], "open")

    def test_stranger_cannot_propose(self):
        set_caller(STRANGER_ADDRESS)
        with self.assertRaises(gl.vm.UserError):
            self.c.propose_rematch(self.src, **rematch_args(self.c))

    def test_unknown_source_rejected(self):
        set_caller(PARTY_A_ADDRESS)
        with self.assertRaises(gl.vm.UserError):
            self.c.propose_rematch("999", **rematch_args(self.c))

    def test_source_must_be_resolved(self):
        set_caller(PARTY_A_ADDRESS)
        open_id = create_and_accept(self.c)
        with self.assertRaises(gl.vm.UserError):
            self.c.propose_rematch(open_id, **rematch_args(self.c))
        pending = make_agreement(self.c)
        with self.assertRaises(gl.vm.UserError):
            self.c.propose_rematch(pending, **rematch_args(self.c))

    def test_create_rules_still_apply(self):
        set_caller(PARTY_A_ADDRESS)
        with self.assertRaises(gl.vm.UserError):
            self.c.propose_rematch(
                self.src, **rematch_args(self.c, resolution_deadline=iso_in(60))
            )
        with self.assertRaises(gl.vm.UserError):
            self.c.propose_rematch(
                self.src, **rematch_args(self.c, comparison="sideways")
            )

    def test_failed_rematch_creates_nothing(self):
        before = self.c.total_agreements()
        set_caller(STRANGER_ADDRESS)
        try:
            self.c.propose_rematch(self.src, **rematch_args(self.c))
        except gl.vm.UserError:
            pass
        self.assertEqual(self.c.total_agreements(), before)

    def test_rematch_of_visible_in_list_summaries_and_chain(self):
        set_caller(PARTY_A_ADDRESS)
        new_id = self.c.propose_rematch(self.src, **rematch_args(self.c))
        items = json.loads(self.c.list_agreements(0, 5))["items"]
        newest = items[0]
        self.assertEqual(newest["agreement_id"], new_id)
        self.assertEqual(newest["rematch_of"], self.src)
        self.assertIsNone(items[-1]["rematch_of"])

    def test_original_agreement_untouched(self):
        before = self.c.get_agreement(self.src)
        set_caller(PARTY_A_ADDRESS)
        self.c.propose_rematch(self.src, **rematch_args(self.c))
        self.assertEqual(self.c.get_agreement(self.src), before)


if __name__ == "__main__":
    unittest.main()
