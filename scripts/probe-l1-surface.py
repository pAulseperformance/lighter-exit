#!/usr/bin/env python3
"""Probe the Lighter L1 exit surface: what the chain carries, and what the app sends.

The surface is split across two proxies since the 2026-11-08 upgrade:

  ZkLighter        deposits, withdrawPendingBalance(+Legacy), every view read
  L1CoreMessaging  withdraw, cancelAllOrders, createOrder, burnShares, changePubKey

A probe that only asks the chain would have passed on the day this tool broke: the
chain carried the exit functions on L1CoreMessaging while the app still posted them
to ZkLighter. So this checks BOTH halves:

  1. the shipped wiring  - which constants the app sends writes and reads to, and
                           which createOrder signature its ABI declares;
  2. the chain           - each proxy's implementation, and which contract actually
                           carries each selector, scanned over the whole runtime.

Read-only: eth_getStorageAt, eth_getCode, eth_call. No transaction is signed.

Usage:
  scripts/probe-l1-surface.py                        # wiring + expected-home check
  scripts/probe-l1-surface.py --print-selectors      # also dump each dispatcher set
  scripts/probe-l1-surface.py --simulate-from 0x...  # replay cancelAllOrders/withdraw
  scripts/probe-l1-surface.py --history 80000        # walk both impl slots (needs archive)

Exit code: 0 when the wiring and the chain agree with this file's expectation, 1 otherwise.
Addresses are read from src/lib/config.ts; override with --zk / --core. They are never
printed in full.
"""
import json
import os
import re
import sys
import urllib.request

SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
RPCS = [
    "https://rpc.mevblocker.io",
    "https://eth-mainnet.public.blastapi.io",
    "https://ethereum.blockpi.network/v1/rpc/public",
    "https://1rpc.io/eth",
    "https://ethereum-rpc.publicnode.com",
    "https://eth.llamarpc.com",
]
HEADERS = {
    "content-type": "application/json",
    "accept": "application/json",
    # Public RPC fronts 403 the default Python-urllib UA.
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(REPO, "src", "lib", "config.ts")
WRITE_HOOK = os.path.join(REPO, "src", "hooks", "useL1Action.ts")
READ_STEP = os.path.join(REPO, "src", "components", "steps", "PendingBalancesStep.tsx")
ABI_FILE = os.path.join(REPO, "src", "lib", "contract.ts")

CREATE_ORDER_UINT64 = "createOrder(uint48 _accountIndex, uint64 _marketIndex, uint48 _baseAmount, uint32 _price, uint8 _isAsk, uint8 _orderType)"
CREATE_ORDER_UINT16 = "createOrder(uint48 _accountIndex, uint16 _marketIndex"

# selector -> (signature, expected contract)
EXPECTED = {
    "8a857083": ("deposit(address,uint16,uint8,uint256)", "ZkLighter"),
    "ea2102e4": ("depositBatch(uint64[],address[],uint48[])", "ZkLighter"),
    "2f25807e": ("withdrawPendingBalance(address,uint16,uint128)", "ZkLighter"),
    "d1cbc64f": ("getPendingBalance(address,uint16)", "ZkLighter"),
    "abf6a038": ("addressToAccountIndex(address)", "ZkLighter"),
    "d20191bd": ("withdraw(uint48,uint16,uint8,uint64)", "L1CoreMessaging"),
    "a4b6f756": ("cancelAllOrders(uint48)", "L1CoreMessaging"),
    "3873d062": ("createOrder(uint48,uint64,uint48,uint32,uint8,uint8)", "L1CoreMessaging"),
    "ae150b39": ("burnShares(uint48,uint48,uint64)", "L1CoreMessaging"),
    "17010c68": ("changePubKey(uint48,uint8,bytes)", "L1CoreMessaging"),
}
DEAD = {
    "3c40c676": "createOrder(uint48,uint16,uint48,uint32,uint8,uint8) retired 2026-11-08",
}


class RpcUnavailable(RuntimeError):
    """Every front refused the transport. Distinct from a node-answered revert:
    reporting one as the other turns 'we could not ask' into 'the contract said no'."""


def rpc(method, params):
    last = None
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for url in RPCS:
        try:
            req = urllib.request.Request(url, data=body, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                out = json.load(r)
            if "error" in out:
                raise RuntimeError(str(out["error"])[:120])
            return out["result"]
        except Exception as exc:  # try the next front
            last = f"{url}: {exc}"
    raise RpcUnavailable(f"all RPC fronts failed for {method} ({last})")


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}")


def pick_config(name, text=None):
    text = read(CONFIG) if text is None else text
    i = text.find(f"export const {name}")
    if i < 0:
        raise SystemExit(f"{name} is not exported by {CONFIG}")
    m = re.search(r"(0x[0-9a-fA-F]{40})", text[i:i + 400])
    if not m:
        raise SystemExit(f"no literal address found for {name} in {CONFIG}")
    return m.group(1)


def arg_value(flag):
    """Value of --flag VALUE, or a clean exit when the flag is last on the line."""
    argv = sys.argv
    if flag not in argv:
        return None
    i = argv.index(flag)
    if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
        raise SystemExit(f"{flag} needs a value")
    return argv[i + 1]


def impl_of(proxy):
    raw = rpc("eth_getStorageAt", [proxy, SLOT, "latest"])
    if not raw or raw == "0x" + "0" * 64:
        return None
    return "0x" + raw[-40:]


def dispatcher_selectors(code_hex, region=8192):
    """PUSH4 immediates in the dispatcher region. Used for the printed count only:
    it also picks up string data ('all\\0'), so absence is never judged from it."""
    h = code_hex[2:] if code_hex.startswith("0x") else code_hex
    limit = min(len(h), region * 2)
    out = set()
    for i in range(0, limit - 10, 2):
        if h[i:i + 2] == "63":
            out.add(h[i + 2:i + 10])
    return out


def dispatched(code_hex, sel):
    """True when the runtime carries the solc dispatcher comparison for this selector.

    Not a substring test: a selector-shaped constant lives in real data (L1CoreMessaging
    holds 0xabf6a038 inside a PUSH32 at offset 10567), and a substring match there would
    report a function the contract does not dispatch. The comparison is `PUSH4 <sel> EQ`,
    which is what `if (msg.sig == 0x...)` compiles to, and it is scanned over the WHOLE
    runtime so a selector that moved out of the first 8 KB is still found.
    """
    h = code_hex[2:] if code_hex.startswith("0x") else code_hex
    return re.search("63" + sel + "14", h) is not None


def short(a):
    return f"{a[:10]}...{a[-4:]}" if a else "none"


def check_wiring():
    """The half the chain cannot answer: what the app actually sends, and to which name."""
    checks = [
        (WRITE_HOOK, "address: L1_CORE_MESSAGING", "priority transactions are sent to L1CoreMessaging"),
        (WRITE_HOOK, "abi: lighterAbi", "the write path still uses the declared ABI"),
        (READ_STEP, "address: ZKLIGHTER", "the pending-balance claim and reads stay on ZkLighter"),
    ]
    ok = True
    print("shipped wiring")
    for path, needle, what in checks:
        body = read(path)
        found = needle in body
        ok = ok and found
        print(f"{'OK ' if found else 'BAD'} {os.path.relpath(path, REPO):46} {what}")
    abi = read(ABI_FILE)
    wide = CREATE_ORDER_UINT64 in abi
    narrow = CREATE_ORDER_UINT16 in abi
    if not wide or narrow:
        ok = False
    print(f"{'OK ' if wide and not narrow else 'BAD'} {os.path.relpath(ABI_FILE, REPO):46} "
          f"createOrder declares the uint64 market index{' and the retired uint16 one!' if narrow else ''}")
    return ok


def main():
    zk = arg_value("--zk") or pick_config("ZKLIGHTER")
    core = arg_value("--core") or pick_config("L1_CORE_MESSAGING")
    verbose = "--print-selectors" in sys.argv
    ok = check_wiring()

    carried = {}
    codes = {}
    print("\ncontracts")
    for name, proxy in (("ZkLighter", zk), ("L1CoreMessaging", core)):
        impl = impl_of(proxy)
        if not impl:
            print(f"BAD {name:16} proxy {short(proxy)}: EIP-1967 slot empty, not a proxy")
            return 1
        code = rpc("eth_getCode", [impl, "latest"])
        if not code or code == "0x":
            print(f"BAD {name:16} proxy {short(proxy)}: impl {short(impl)} has no code")
            return 1
        codes[name] = code
        carried[name] = dispatcher_selectors(code)
        print(f"OK  {name:16} proxy {short(proxy)} impl {short(impl)} runtime "
              f"{(len(code) - 2) // 2} bytes, {len(carried[name])} PUSH4 values in the first 8 KB")
        if verbose:
            for s in sorted(carried[name]):
                label = EXPECTED.get(s, (DEAD.get(s, ""), ""))[0]
                print(f"      0x{s} {label}")

    print("\nselector                                        expected on        found on (whole runtime)")
    for sel, (sig, home) in EXPECTED.items():
        holders = [c for c in codes if dispatched(codes[c], sel)]
        verdict = ", ".join(holders) if holders else "NOWHERE"
        mark = "OK " if holders == [home] else "BAD"
        if mark == "BAD":
            ok = False
        print(f"{mark} {sig:46} {home:17} {verdict}")
    for sel, note in DEAD.items():
        holders = [c for c in codes if dispatched(codes[c], sel)]
        if holders:
            ok = False
        print(f"{'BAD' if holders else 'OK '} {note:46} {'RETIRED':17} "
              f"{', '.join(holders) if holders else 'absent everywhere (good)'}")

    sender = arg_value("--simulate-from")
    if sender:
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", sender):
            raise SystemExit("--simulate-from needs a 20-byte hex address")
        print(f"\nsimulating from {sender[:10]}...")
        # The account index must be the SENDER's: account 0 belongs to the treasury,
        # so a call carrying it would revert on authority and prove nothing about dispatch.
        data = "0xabf6a038" + sender[2:].lower().rjust(64, "0")
        index = None
        try:
            index = int(rpc("eth_call", [{"to": zk, "data": data}, "latest"]), 16)
        except RpcUnavailable:
            print("  no RPC front answered the account-index read; simulation skipped")
        except Exception as exc:
            print(f"  the account-index read failed ({str(exc)[:70]}); simulation skipped")
        if index == 0:
            print("  this address has no Lighter account index; a simulated call would only prove "
                  "an authorization failure, so it is skipped")
        elif index:
            def word(v):
                return f"{v:064x}"

            calls = [
                ("cancelAllOrders(acct)", "0xa4b6f756" + word(index)),
                ("withdraw(acct,1,0,1)", "0xd20191bd" + word(index) + word(1) + word(0) + word(1)),
                ("withdraw(acct,1,0,0)", "0xd20191bd" + word(index) + word(1) + word(0) + word(0)),
            ]
            for call, calldata in calls:
                for name, proxy in (("L1CoreMessaging", core), ("ZkLighter", zk)):
                    try:
                        out = rpc("eth_call", [{"from": sender, "to": proxy, "data": calldata}, "latest"])
                        result = f"answered {len(out) // 2 - 1} bytes" if out and out != "0x" else "answered 0x"
                    except RpcUnavailable:
                        result = "no answer (RPC unavailable)"
                    except Exception as exc:
                        result = f"node refused it ({str(exc)[:60]})"
                    print(f"  {call:24} on {name:16} {result}")

    span = arg_value("--history")
    if span:
        span = int(span)
        head = int(rpc("eth_blockNumber", []), 16)
        step = 2000
        print(f"\nwalking both impl slots back {span} blocks from {head} (needs archive state)")
        for name, proxy in (("ZkLighter", zk), ("L1CoreMessaging", core)):
            prev = None
            try:
                for b in range(head, head - span, -step):
                    impl = "0x" + rpc("eth_getStorageAt", [proxy, SLOT, hex(b)])[-40:]
                    if prev is not None and impl != prev:
                        print(f"  {name:16} changed between block {b} and {b + step}: "
                              f"{short(impl)} -> {short(prev)}")
                    prev = impl
            except Exception as exc:
                print(f"  {name:16} archive read unavailable on these fronts: {str(exc)[:90]}")

    print("\nVERDICT:", "wiring and chain agree with the expected split" if ok
          else "the wiring or the chain does not match the expected split")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
