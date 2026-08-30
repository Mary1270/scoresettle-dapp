![License](https://img.shields.io/badge/license-MIT-blue)
![GenLayer](https://img.shields.io/badge/GenLayer-genlayer--js-3E9B4F)
![Tests](https://img.shields.io/badge/tests-165%2F165%20passing-3E9B4F)

# ScoreSettle

A two-party, address-bound, deadline-gated, multi-source **sports score**
settlement Intelligent Contract for GenLayer, plus a minimal no-build-step
frontend that talks to it directly. Built from a clean slate for the sports
vertical — it borrows only proven *structural* patterns (the
fetch → LLM-extraction → deterministic-comparison pipeline,
`prompt_comparative` validator consensus) from a prior, unrelated GenLayer
project (a forex cross-rate oracle), and rebuilds every trust-sensitive
control from scratch specifically for two-party sports-score agreements.

**Contract:** deployed and live on GenLayer Studio at
`0xd641d7E80A309Ba01D1D62f071873f69b2978C14` —
[view on explorer](https://explorer-studio.genlayer.com/address/0xd641d7E80A309Ba01D1D62f071873f69b2978C14).

---

## Repository layout

```
contract.py     the Intelligent Contract (GenLayer / GenVM, Python)
index.html      the entire frontend — HTML/CSS/JS, no build step
tests/          contract.py's offline test suite (165/165 passing)
README.md
LICENSE
```

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

`pytest` also works with these same files (they're written as plain
`unittest.TestCase` classes, which `pytest` auto-discovers) if you have it
installed; the command above uses the standard-library `unittest` runner
instead so the suite needs no installation step at all.

---

## The three security properties this was built around

### 1. Party binding
`party_a` and `party_b` are never free-text names. `party_a` is always
whoever calls `create_agreement` (`gl.message.sender_address`); `party_b`
is an on-chain address supplied at creation time, and that *exact* address
must itself call `accept_agreement` before the agreement becomes binding
(`status` moves from `pending_acceptance` to `open`). Both sides are
therefore cryptographically tied to real wallets that actually signed a
transaction — never to a string either side could have typed on behalf of
someone else.

### 2. Resolution timing / deadline
Every agreement carries a `resolution_deadline` (an ISO-8601 UTC
timestamp) fixed at creation time — the expected full-time whistle — at
least **2 hours** and at most **7 days** out. `resolve_agreement` cannot
be called before that deadline (so nobody can race to resolve before the
match has actually finished) and cannot be called after
`resolution_deadline + 24 hours` (a deliberately short, single-day window:
sports results are reported live and go stale in the news cycle far
faster than a forex rate does). Once that window closes unresolved,
anyone can permissionlessly call `expire_agreement`.

### 3. Mandatory multi-source corroboration, a locked voting set, and one documented quorum rule
`required_source_domains` is not optional. Every agreement must commit at
least **2** distinct, reputable, allowlisted sports-data domains at
creation time (from `REPUTABLE_SPORTS_DOMAINS` — ESPN, BBC, Sky Sports,
Reuters, AP, Goal.com, FIFA.com, and the major US league sites, among
others), and `resolve_agreement` only succeeds once evidence from *all*
of those committed domains has been fetched, classified, and found to
agree. A single caller-chosen web page can never decide a settlement.
Each entry can optionally pin a specific section of a domain too — e.g.
`bbc.com/sport` narrows "any BBC page" down to "a page under BBC Sport
specifically."

Two further controls close what a purely domain-level commitment leaves
open:

- **Locked voting set.** The exact `source_urls` submitted on the FIRST
  `resolve_agreement` attempt are locked into `locked_source_urls`. Every
  later attempt on the same agreement — resolved or not — must resubmit
  that identical set (order-independent, case/whitespace-normalized) or
  is rejected before any fetch. Without this, a resolver could keep
  retrying with a different combination of otherwise-valid,
  committed-domain-satisfying URLs until one combination happened to read
  favorably — shopping for a result instead of corroborating one.
- **One documented quorum rule.** A verdict requires at least
  `MIN_INDEPENDENT_SOURCES` (2) eligible, independent sources, and the
  winning category must strictly outnumber both other categories. Any
  tie, or too few eligible sources, is `Indeterminate`. Dissenting
  sources can prevent a verdict but can never manufacture one alone —
  see `tests/test_aggregation.py` for explicit dissenting-source cases
  (a lone dissenter among three, a two-way split among four, a three-way
  tie).

---

## How resolution works

1. `resolve_agreement(agreement_id, source_urls)` is called with 2–6
   candidate URLs, after the deadline and before the resolution window
   closes.
2. Every domain (and any pinned path) committed at creation time must be
   matched by the submitted URLs, or the call is rejected before any
   network access happens.
3. Inside a single `gl.eq_principle.prompt_comparative` closure (so every
   validator runs the identical logic and only the *categorical* result
   needs to match, not exact wording):
   - each URL is fetched with `gl.nondet.web.render`;
   - fetched content is deterministically classified as usable, empty, or
     malformed;
   - usable content is sent to `gl.nondet.exec_prompt` with a hardened
     prompt asking four fixed-vocabulary questions: does this source
     cover the exact requested fixture (`TEAM_MATCH`), is the score
     clearly the FINAL result (`FRESHNESS`), what is the final score
     (`SCORE`, as `home-away`), and how does the total compare to the
     threshold (`COMPARISON`);
   - the contract — never the model — deterministically parses `SCORE`
     and computes the authoritative Above/Below/Equal comparison itself;
     the model's self-reported `COMPARISON` is used only as a
     self-consistency check;
   - sources are aggregated: a source only counts as independent evidence
     if it fetched cleanly, isn't a duplicate domain, is on the
     allowlist, and passed every quality check;
   - a verdict (`Above` / `Below` / `Equal` / `Indeterminate`) requires at
     least 2 independent agreeing sources, or the match is
     `Indeterminate` and the agreement stays open for a retry.
4. The winner is derived from the agreement's `comparison` field
   (`above`/`below`) crossed with the `final_verdict` — `Equal` and
   `Indeterminate` never resolve the agreement in either party's favor.

## v1 scope

The settlement metric is **total combined goals/points** scored by both
teams, compared to a fixed threshold (over/under style — e.g. "over 2.5
goals"). Margin-of-victory markets ("Team A wins by 2+") are intentionally
out of scope for v1; see the class docstring in `contract.py` for the full
list of disclosed limitations, including why `REPUTABLE_SPORTS_DOMAINS`
holds bare domains only (a domain's specific section is pinned via
`required_source_domains` instead, e.g. `bbc.com/sport`).

---

## Frontend

`index.html` is a single, dependency-free file (loads `genlayer-js` from
`esm.sh` at runtime) with panels for every public method: create, accept/
cancel, resolve, expire, read (with a final-verdict hero and a per-source
evidence table), check role, and total agreements. Every dynamic value on
the page is written with `textContent` / `document.createElement` only —
`innerHTML` is never used anywhere in the file, so no value returned from
the contract or fetched off-chain can ever be interpreted as markup.

`CONTRACT_ADDRESS` is already set to the deployed contract address above.

**Live and verified:** the frontend is deployed at
https://mary1270.github.io/scoresettle-dapp/ and has been tested against
the live deployed contract on GenLayer Studio — connecting a test
session, reading an existing agreement (parties, terms, status, and its
full per-source evidence table), checking a role, and fetching the total
agreement count all returned results matching the contract's actual
on-chain state.

---

## Test suite

165 offline `unittest` tests across four files, all passing:

- `test_party_binding_and_timing.py` — create/accept/cancel binding rules,
  deadline lead-time bounds, the 24h resolution window, `expire_agreement`,
  and the view methods (`get_role`, `total_agreements`).
- `test_teams_and_score_parsing.py` — fixture ("Team A vs Team B")
  validation, domain extraction and the domain-allowlist round-trip
  guarantee, endpoint (domain+path) parsing, and the two numeric parsers
  (`_parse_score` for "home-away" final scores, `_parse_plain_number` for
  the threshold).
- `test_aggregation.py` — the deterministic verdict-aggregation logic in
  isolation, plus the winner-assignment mapping.
- `test_end_to_end.py` — full `create → accept → resolve` flows with
  `gl.nondet.web.render` / `gl.nondet.exec_prompt` mocked, covering the
  happy path, every `quality_flag` (team mismatch, not-final score,
  score-unparseable, comparison mismatch), fetch failures, retry-after-
  `Indeterminate`, and every resolution guardrail (early/late calls,
  wrong source counts, missing committed domains/paths, double-resolve).

All tests use the same offline `genlayer` SDK stub pattern (see
`tests/genlayer_stub/`): storage types behave like plain dicts/lists,
`gl.message.sender_address` is settable per test to simulate different
callers, and `gl.nondet.web.render` / `gl.nondet.exec_prompt` are
monkeypatched per test case rather than hitting the network or a real
model. This does not simulate real multi-validator consensus — that
requires GenLayer Studio or testnet.

---

## Deploying

This package is already deployed and live:

- **Contract:** `0xd641d7E80A309Ba01D1D62f071873f69b2978C14` on GenLayer
  Studio — [explorer link](https://explorer-studio.genlayer.com/address/0xd641d7E80A309Ba01D1D62f071873f69b2978C14).
- **Frontend:** https://mary1270.github.io/scoresettle-dapp/ (GitHub Pages,
  `CONTRACT_ADDRESS` already pointed at the deployment above).

To deploy your own instance instead:

1. Deploy `contract.py` via GenLayer Studio (or the CLI) to get a new
   contract address.
2. Set `CONTRACT_ADDRESS` in `index.html` to that address.
3. Push your copy of this repository to GitHub and enable GitHub Pages
   (or host `index.html` anywhere static) for the frontend.
4. Submit the repository + release to the GenLayer Portal.

---

## Known limitations (disclosed, not hidden)

See the `contract.py` class docstring's "v1 SCOPE / KNOWN LIMITATIONS"
section for the full, exact list — summarized: total-goals-only settlement
metric (no margin markets yet), no fund custody (this contract produces a
decision, not a payout), and a domain-only reputable allowlist (paths are
pinned via `required_source_domains`, not baked into the allowlist).
