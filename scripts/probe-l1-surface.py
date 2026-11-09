#!/usr/bin/env python3
"""Probe the Lighter L1 exit surface as it is deployed right now.

The surface is split across two proxies since the 2026-11-08 upgrade:

  ZkLighter       deposits, withdrawPendingBalance(+Legacy), every view read
  L1CoreMessaging withdraw, cancelAllOrders, createOrder, burnShares, changePubKey

This script answers, from the chain and not from a doc: which implementation each
proxy points at, which contract actually carries each exit selector, and whether a
simulated priority transaction dispatches from a real sender.

Read-only: eth_getStorageAt, eth_getCode, eth_call. No transaction is signed.

Usage:
  scripts/probe-l1-surface.py                        # both proxies, expected-home check
  scripts/probe-l1-surface.py --print-selectors      # also dump each dispatcher set
  scripts/probe-l1-surface.py --simulate-from 0x...  # replay cancelAllOrders/withdraw
  scripts/probe-l1-surface.py --history 80000        # walk the impl slot back (needs archive state)

Exit code: 0 when every expected selector sits on its expected contract, 1 otherwise.
Addresses are read from src/lib/config.ts so the probe tests what the app ships;
override with --zk / --core. They are never printed in full.
"""
import json
import os
import re
import sys
import urllib.error
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
    raise RuntimeError(f"all RPC fronts failed for {method} ({last})")


def pick_config(name):
    with open(CONFIG) as f:
        text = f.read()
    i = text.index(f"export const {name}")
    m = re.search(r"(0x[0-9a-fA-F]{40})", text[i:i + 400])
    if not m:
        raise SystemExit(f"no literal address found for {name} in {CONFIG}")
    return m.group(1)


def impl_of(proxy):
    raw = rpc("eth_getStorageAt", [proxy, SLOT, "latest"])
    if not raw or raw == "0x" + "0" * 64:
        return None
    return "0x" + raw[-40:]


def dispatcher_selectors(code_hex, region=8192):
    h = code_hex[2:] if code_hex.startswith("0x") else code_hex
    limit = min(len(h), region * 2)
    out = set()
    for i in range(0, limit - 10, 2):
        if h[i:i + 2] == "63":
            out.add(h[i + 2:i + 10])
    return out


def short(a):
    return f"{a[:10]}...{a[-4:]}" if a else "none"


def main():
    argv = sys.argv
    zk = pick_config("ZKLIGHTER") if "--zk" not in argv else argv[argv.index("--zk") + 1]
    core = pick_config("L1_CORE_MESSAGING") if "--core" not in argv else argv[argv.index("--core") + 1]
    verbose = "--print-selectors" in argv

    ok = True
    carried = {}
    for name, proxy in (("ZkLighter", zk), ("L1CoreMessaging", core)):
        impl = impl_of(proxy)
        if not impl:
            print(f"{name:16} proxy {short(proxy)}: EIP-1967 slot empty, not a proxy")
            return 1
        code = rpc("eth_getCode", [impl, "latest"])
        if not code or code == "0x":
            print(f"{name:16} proxy {short(proxy)}: impl {short(impl)} has no code")
            return 1
        sels = dispatcher_selectors(code)
        carried[name] = sels
        print(f"{name:16} proxy {short(proxy)} impl {short(impl)} runtime {(len(code) - 2) // 2} bytes, "
              f"{len(sels)} dispatcher selectors")
        if verbose:
            for s in sorted(sels):
                label = EXPECTED.get(s, (DEAD.get(s, ""), ""))[0]
                print(f"   0x{s} {label}")

    print("\nselector                                        expected on        found on")
    for sel, (sig, home) in EXPECTED.items():
        holders = [c for c in carried if sel in carried[c]]
        verdict = ", ".join(holders) if holders else "NOWHERE"
        mark = "OK " if holders and holders[0] == home and len(holders) == 1 else "BAD"
        if mark == "BAD":
            ok = False
        print(f"{mark} {sig:46} {home:17} {verdict}")
    for sel, note in DEAD.items():
        holders = [c for c in carried if sel in carried[c]]
        print(f"{'OK ' if not holders else 'BAD'} {note:46} {'DEAD':17} {', '.join(holders) or 'absent (good)'}")
        if holders:
            ok = False

    if "--simulate-from" in argv:
        sender = argv[argv.index("--simulate-from") + 1]
        print(f"\nsimulating from {sender[:10]}... (unrelated to the expected-home table)")

        def word(value):
            return f"{value:064x}"

        calls = [
            ("cancelAllOrders(acct)", "0xa4b6f756" + word(0)),
            ("withdraw(acct,1,0,1)", "0xd20191bd" + word(0) + word(1) + word(0) + word(1)),
            ("withdraw(acct,1,0,0)", "0xd20191bd" + word(0) + word(1) + word(0) + word(0)),
        ]
        for call, data in calls:
            for name, proxy in (("L1CoreMessaging", core), ("ZkLighter", zk)):
                try:
                    out = rpc("eth_call", [{"from": sender, "to": proxy, "data": data}, "latest"])
                    result = f"answered {len(out) // 2 - 1} bytes" if out and out != "0x" else "answered 0x"
                except Exception as exc:
                    result = f"revert ({str(exc)[:60]})"
                print(f"  {call:24} on {name:16} {result}")

    if "--history" in argv:
        span = int(argv[argv.index("--history") + 1])
        head = int(rpc("eth_blockNumber", []), 16)
        print(f"\nwalking the ZkLighter slot back {span} blocks from {head} (needs archive state)")
        step = 2000
        prev = None
        seen = []
        try:
            for b in range(head, head - span, -step):
                raw = rpc("eth_getStorageAt", [zk, SLOT, hex(b)])
                impl = "0x" + raw[-40:]
                if prev is not None and impl != prev:
                    seen.append((b, impl))
                prev = impl
        except Exception as exc:
            print(f"  archive read unavailable on these fronts: {str(exc)[:120]}")
        for b, impl in seen:
            print(f"  change at or after block {b}: {short(impl)}")

    print("\nVERDICT:", "every expected selector is on its expected contract" if ok
          else "the split does not match what this probe expects")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
