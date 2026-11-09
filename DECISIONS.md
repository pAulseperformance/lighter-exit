# DECISIONS: lighter-exit

> Created 2026-10-27 by `spec_gate.py scaffold`.

One entry per decision, newest first, append-only. Each names the pick, the loser and why, and what
would show it was wrong. Anything one-way door gets its own paragraph.

## D-002: the L1 surface is two proxies, and the probe checks the app and the chain, 2026-11-09

**Pick:** treat the exit surface as two contracts. `ZkLighter` keeps deposits, `withdrawPendingBalance(+Legacy)` and every view read; `L1CoreMessaging` carries `withdraw`, `cancelAllOrders`, `createOrder`, `burnShares` and `changePubKey`, with `createOrder`'s market index widened from `uint16` to `uint64` (`0x3873d062`, retiring `0x3c40c676`). Addresses are read from the chain, never from a doc: Lighter's environments page publishes `L1CoreMessaging` for testnet only. `scripts/probe-l1-surface.py` exits non-zero unless the app's send target, the app's ABI and both implementations agree, and `lighter_contract_watch.py` watches both EIP-1967 slots hourly.

**Loser:** a single-proxy watch and a doc-pinned address. That pairing fired "exit functions gone" on 2026-11-08 while the functions had only moved, and every Ethereum fallback reverted for about fourteen hours until the repoint landed.

**Wrong if:** a third proxy appears and the probe stays green, because its expected-home table would then be incomplete; or the widened market index turns out not to be what `L1CoreMessaging` dispatches, which the selector `0x3873d062` would answer.

**One-way door:** the expected-home table in the probe is now the written contract. Moving a function between proxies is an edit to that table, reviewable as such, rather than a discovery made in an alert.

## D-001: adopt the repo dossier, 2026-10-27

**Pick:** every change lands against a `SPEC.md` that names the repo and the deploy target, a
`ROADMAP.md` that says what is next, and this file. **Loser:** carrying the answer in plans and
sessions only, which is what let placement drift. **Wrong if:** within a month the three files are
untouched while the work moves, in which case the dossier is ceremony here and should be dropped
rather than fed.
