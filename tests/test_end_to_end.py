"""
End-to-end tests of resolve_agreement. gl.nondet.web.render and
gl.nondet.exec_prompt are mocked per test to simulate specific source
content and LLM responses; every other step (fetching, prompt
construction, deterministic score comparison, aggregation, party
binding of the winner) runs for real through contract.py.
"""
import datetime
import json
import unittest
from unittest.mock import patch

from _bootstrap import (
    PARTY_A_ADDRESS,
    PARTY_B_ADDRESS,
    gl,
    make_contract,
    set_caller,
)


def iso_in(seconds_from_now: float) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=seconds_from_now
    )
    return dt.isoformat()


def create_and_accept(c, comparison="above", threshold_score="2.5",
                       required_source_domains=None):
    required_source_domains = required_source_domains or ["espn.com", "bbc.com"]
    set_caller(PARTY_A_ADDRESS)
    aid = c.create_agreement(
        party_b_address=PARTY_B_ADDRESS,
        teams="Manchester United vs Liverpool",
        match_date="2026-09-05",
        threshold_score=threshold_score,
        comparison=comparison,
        description="End-to-end test agreement",
        resolution_deadline=iso_in(c.MIN_DEADLINE_LEAD_SECONDS + 5),
        required_source_domains=required_source_domains,
    )
    set_caller(PARTY_B_ADDRESS)
    c.accept_agreement(aid)

    # Fast-forward past the deadline without waiting in real time, by
    # rewriting stored timestamps directly.
    record = json.loads(c.agreements[aid])
    record["resolution_deadline"] = iso_in(-5)
    record["resolution_window_closes_at"] = iso_in(c.RESOLUTION_WINDOW_SECONDS)
    c.agreements[aid] = json.dumps(record, sort_keys=True)
    return aid


FINAL_HIGH_SCORING_CONTENT = (
    "Manchester United beat Liverpool 3-1 in a thrilling full-time "
    "final result at Old Trafford this afternoon, sealing the win."
)
FINAL_LOW_SCORING_CONTENT = (
    "Manchester United held Liverpool to a goalless 0-0 draw in a "
    "tense full-time final result at Old Trafford this afternoon."
)
LIVE_IN_PROGRESS_CONTENT = (
    "LIVE 62': Manchester United lead Liverpool 2-1 as the match "
    "continues into the second half at Old Trafford this afternoon."
)
WRONG_FIXTURE_CONTENT = (
    "Chelsea beat Arsenal 4-2 in a thrilling full-time final result "
    "at Stamford Bridge this afternoon, sealing the win for Chelsea."
)


def llm_response_for(content):
    if "3-1" in content and "LIVE" not in content:
        return "TEAM_MATCH: Match\nFRESHNESS: Final\nSCORE: 3-1\nCOMPARISON: Above"
    if "0-0" in content:
        return "TEAM_MATCH: Match\nFRESHNESS: Final\nSCORE: 0-0\nCOMPARISON: Below"
    if "LIVE" in content:
        return "TEAM_MATCH: Match\nFRESHNESS: Current\nSCORE: 2-1\nCOMPARISON: Above"
    if "Chelsea" in content:
        return "TEAM_MATCH: Mismatch\nFRESHNESS: Final\nSCORE: 4-2\nCOMPARISON: Above"
    return "TEAM_MATCH: Unclear\nFRESHNESS: Unknown\nSCORE: Unclear\nCOMPARISON: Unclear"


class ResolveHappyPathTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_two_sources_above_threshold_party_a_wins(self):
        aid = create_and_accept(self.c, comparison="above")
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_HIGH_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_HIGH_SCORING_CONTENT)
        ):
            result = json.loads(
                self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
            )
        self.assertEqual(result["final_verdict"], "Above")
        self.assertEqual(result["winner"], "party_a")
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["independent_source_count"], 2)

    def test_two_sources_below_threshold_party_b_wins_when_comparison_above(self):
        aid = create_and_accept(self.c, comparison="above")
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_LOW_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_LOW_SCORING_CONTENT)
        ):
            result = json.loads(
                self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
            )
        self.assertEqual(result["final_verdict"], "Below")
        self.assertEqual(result["winner"], "party_b")

    def test_comparison_below_flips_winner(self):
        aid = create_and_accept(self.c, comparison="below")
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_LOW_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_LOW_SCORING_CONTENT)
        ):
            result = json.loads(
                self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
            )
        self.assertEqual(result["final_verdict"], "Below")
        self.assertEqual(result["winner"], "party_a")

    def test_extra_reputable_source_still_resolves(self):
        aid = create_and_accept(self.c, comparison="above")
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_HIGH_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_HIGH_SCORING_CONTENT)
        ):
            result = json.loads(
                self.c.resolve_agreement(
                    aid, ["https://espn.com/x", "https://bbc.com/sport/x", "https://nba.com/x"]
                )
            )
        self.assertEqual(result["independent_source_count"], 3)
        self.assertEqual(result["status"], "resolved")


class ResolveQualityFlagTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_live_score_flagged_not_final(self):
        aid = create_and_accept(self.c, comparison="above")
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": LIVE_IN_PROGRESS_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(LIVE_IN_PROGRESS_CONTENT)
        ):
            result = json.loads(
                self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
            )
        self.assertEqual(result["final_verdict"], "Indeterminate")
        self.assertEqual(result["winner"], "unresolved")
        for rec in result["records"]:
            self.assertEqual(rec["quality_flag"], "not_final_score")

    def test_wrong_fixture_flagged_team_mismatch(self):
        aid = create_and_accept(self.c, comparison="above")
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": WRONG_FIXTURE_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(WRONG_FIXTURE_CONTENT)
        ):
            result = json.loads(
                self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
            )
        self.assertEqual(result["final_verdict"], "Indeterminate")
        for rec in result["records"]:
            self.assertEqual(rec["quality_flag"], "team_mismatch")

    def test_llm_comparison_mismatch_excluded(self):
        aid = create_and_accept(self.c, comparison="above")
        bad_llm = "TEAM_MATCH: Match\nFRESHNESS: Final\nSCORE: 3-1\nCOMPARISON: Below"
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_HIGH_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": bad_llm
        ):
            result = json.loads(
                self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
            )
        self.assertEqual(result["final_verdict"], "Indeterminate")
        for rec in result["records"]:
            self.assertEqual(rec["quality_flag"], "comparison_mismatch")

    def test_empty_content_flagged_empty_fetch(self):
        aid = create_and_accept(self.c, comparison="above")
        with patch.object(gl.nondet.web, "render", side_effect=lambda url, mode="text": ""):
            result = json.loads(
                self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
            )
        for rec in result["records"]:
            self.assertEqual(rec["fetch_status"], "empty")
            self.assertEqual(rec["quality_flag"], "team_mismatch")

    def test_fetch_timeout_recorded(self):
        aid = create_and_accept(self.c, comparison="above")

        def raise_timeout(url, mode="text"):
            raise Exception("Request timed out")

        with patch.object(gl.nondet.web, "render", side_effect=raise_timeout):
            result = json.loads(
                self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
            )
        for rec in result["records"]:
            self.assertEqual(rec["fetch_status"], "timeout")

    def test_unresolved_agreement_stays_open_and_can_retry(self):
        aid = create_and_accept(self.c, comparison="above")
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": LIVE_IN_PROGRESS_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(LIVE_IN_PROGRESS_CONTENT)
        ):
            first = json.loads(
                self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
            )
        self.assertEqual(first["status"], "open")

        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_HIGH_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_HIGH_SCORING_CONTENT)
        ):
            second = json.loads(
                self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
            )
        self.assertEqual(second["status"], "resolved")
        self.assertEqual(second["resolution_attempts"], 2)


class ResolveSourceLockTests(unittest.TestCase):
    """
    Covers the voting-source-set lock: the exact source_urls submitted
    on the first resolve_agreement attempt are locked, and every later
    attempt on the same agreement must resubmit that identical set.
    """

    def setUp(self):
        self.c = make_contract()

    def test_first_attempt_locks_source_set(self):
        aid = create_and_accept(self.c, comparison="above")
        urls = ["https://espn.com/x", "https://bbc.com/sport/x"]
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": LIVE_IN_PROGRESS_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(LIVE_IN_PROGRESS_CONTENT)
        ):
            result = json.loads(self.c.resolve_agreement(aid, urls))
        self.assertEqual(sorted(u.lower() for u in result["locked_source_urls"]), sorted(u.lower() for u in urls))

    def test_locked_after_resolved_first_attempt_too(self):
        aid = create_and_accept(self.c, comparison="above")
        urls = ["https://espn.com/x", "https://bbc.com/sport/x"]
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_HIGH_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_HIGH_SCORING_CONTENT)
        ):
            result = json.loads(self.c.resolve_agreement(aid, urls))
        self.assertEqual(result["status"], "resolved")
        self.assertIsNotNone(result["locked_source_urls"])

    def test_retry_with_identical_source_set_allowed(self):
        aid = create_and_accept(self.c, comparison="above")
        urls = ["https://espn.com/x", "https://bbc.com/sport/x"]
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": LIVE_IN_PROGRESS_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(LIVE_IN_PROGRESS_CONTENT)
        ):
            self.c.resolve_agreement(aid, urls)

        # Retry with the EXACT same set (just reordered) - allowed.
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_HIGH_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_HIGH_SCORING_CONTENT)
        ):
            result = json.loads(self.c.resolve_agreement(aid, list(reversed(urls))))
        self.assertEqual(result["status"], "resolved")

    def test_retry_with_different_source_set_rejected(self):
        aid = create_and_accept(self.c, comparison="above")
        urls = ["https://espn.com/x", "https://bbc.com/sport/x"]
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": LIVE_IN_PROGRESS_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(LIVE_IN_PROGRESS_CONTENT)
        ):
            self.c.resolve_agreement(aid, urls)

        different_urls = ["https://espn.com/y", "https://bbc.com/sport/y"]
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(aid, different_urls)

    def test_retry_adding_an_extra_source_rejected(self):
        aid = create_and_accept(self.c, comparison="above")
        urls = ["https://espn.com/x", "https://bbc.com/sport/x"]
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": LIVE_IN_PROGRESS_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(LIVE_IN_PROGRESS_CONTENT)
        ):
            self.c.resolve_agreement(aid, urls)

        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(aid, urls + ["https://nba.com/x"])

    def test_locked_source_set_case_and_whitespace_insensitive(self):
        aid = create_and_accept(self.c, comparison="above")
        urls = ["https://espn.com/x", "https://bbc.com/sport/x"]
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": LIVE_IN_PROGRESS_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(LIVE_IN_PROGRESS_CONTENT)
        ):
            self.c.resolve_agreement(aid, urls)

        reshuffled_case = [" HTTPS://ESPN.COM/x ", "https://BBC.com/sport/x"]
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_HIGH_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_HIGH_SCORING_CONTENT)
        ):
            result = json.loads(self.c.resolve_agreement(aid, reshuffled_case))
        self.assertEqual(result["status"], "resolved")

    def test_unlocked_agreement_has_null_locked_source_urls(self):
        aid = create_and_accept(self.c, comparison="above")
        record = json.loads(self.c.get_agreement(aid))
        self.assertIsNone(record["locked_source_urls"])

    def test_failed_domain_commitment_attempt_does_not_lock(self):
        aid = create_and_accept(
            self.c, required_source_domains=["espn.com", "bbc.com", "nba.com"]
        )
        # Missing nba.com entirely - required-domain check fails before
        # the source set would ever be locked.
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
        record = json.loads(self.c.get_agreement(aid))
        self.assertIsNone(record["locked_source_urls"])
        # A subsequent attempt with a DIFFERENT valid set is still
        # allowed, since nothing was ever locked.
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_HIGH_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_HIGH_SCORING_CONTENT)
        ):
            result = json.loads(
                self.c.resolve_agreement(
                    aid, ["https://espn.com/x", "https://bbc.com/sport/x", "https://nba.com/x"]
                )
            )
        self.assertEqual(result["status"], "resolved")


class ResolveGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_cannot_resolve_pending_acceptance_agreement(self):
        set_caller(PARTY_A_ADDRESS)
        aid = self.c.create_agreement(
            party_b_address=PARTY_B_ADDRESS,
            teams="Manchester United vs Liverpool",
            match_date="2026-09-05",
            threshold_score="2.5",
            comparison="above",
            description="Not yet accepted",
            resolution_deadline=iso_in(self.c.MIN_DEADLINE_LEAD_SECONDS + 5),
            required_source_domains=["espn.com", "bbc.com"],
        )
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])

    def test_cannot_resolve_before_deadline(self):
        set_caller(PARTY_A_ADDRESS)
        aid = self.c.create_agreement(
            party_b_address=PARTY_B_ADDRESS,
            teams="Manchester United vs Liverpool",
            match_date="2026-09-05",
            threshold_score="2.5",
            comparison="above",
            description="Deadline not reached",
            resolution_deadline=iso_in(self.c.MIN_DEADLINE_LEAD_SECONDS + 5),
            required_source_domains=["espn.com", "bbc.com"],
        )
        set_caller(PARTY_B_ADDRESS)
        self.c.accept_agreement(aid)
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])

    def test_cannot_resolve_after_window_closes(self):
        aid = create_and_accept(self.c)
        record = json.loads(self.c.agreements[aid])
        record["resolution_deadline"] = iso_in(-100000)
        record["resolution_window_closes_at"] = iso_in(-5)
        self.c.agreements[aid] = json.dumps(record, sort_keys=True)
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])

    def test_too_few_source_urls_rejected(self):
        aid = create_and_accept(self.c)
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(aid, ["https://espn.com/x"])

    def test_too_many_source_urls_rejected(self):
        aid = create_and_accept(self.c)
        urls = [f"https://espn.com/x{i}" for i in range(7)]
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(aid, urls)

    def test_missing_committed_domain_rejected(self):
        aid = create_and_accept(
            self.c, required_source_domains=["espn.com", "bbc.com", "nba.com"]
        )
        # Omits nba.com entirely.
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])

    def test_missing_committed_endpoint_path_rejected(self):
        aid = create_and_accept(
            self.c, required_source_domains=["espn.com", "bbc.com/sport"]
        )
        # bbc.com present but wrong path (not under /sport).
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(
                aid, ["https://espn.com/x", "https://bbc.com/news/x"]
            )

    def test_matching_committed_endpoint_path_accepted(self):
        aid = create_and_accept(
            self.c, required_source_domains=["espn.com", "bbc.com/sport"]
        )
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_HIGH_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_HIGH_SCORING_CONTENT)
        ):
            result = json.loads(
                self.c.resolve_agreement(
                    aid, ["https://espn.com/x", "https://bbc.com/sport/football/x"]
                )
            )
        self.assertEqual(result["status"], "resolved")

    def test_cannot_resolve_already_resolved_agreement(self):
        aid = create_and_accept(self.c)
        with patch.object(
            gl.nondet.web, "render", side_effect=lambda url, mode="text": FINAL_HIGH_SCORING_CONTENT
        ), patch.object(
            gl.nondet, "exec_prompt", side_effect=lambda p, response_format="text": llm_response_for(FINAL_HIGH_SCORING_CONTENT)
        ):
            self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement(aid, ["https://espn.com/x", "https://bbc.com/sport/x"])

    def test_resolve_nonexistent_agreement(self):
        with self.assertRaises(gl.vm.UserError):
            self.c.resolve_agreement("999", ["https://espn.com/x", "https://bbc.com/sport/x"])


if __name__ == "__main__":
    unittest.main()
