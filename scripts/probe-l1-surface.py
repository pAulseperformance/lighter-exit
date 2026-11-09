#!/usr/bin/env python3
"""Probe the Lighter L1 exit surface: what the chain carries, and what the app sends where.

The surface is split across two proxies since the 2026-11-08 upgrade:

  ZkLighter        deposits, the pending-balance claim, every view read
  L1CoreMessaging  withdraw, cancelAllOrders, createOrder, burnShares, changePubKey

A probe that only asks the chain passes on a dead client: on 2026-11-09 the chain carried the
exit on L1CoreMessaging while the app posted the pending-balance CLAIM there too, a contract
without that selector. So this checks three claims and requires all three to agree:

  1. the app's routing  - the function-to-contract map in src/lib/l1Targets.ts, compared to the
                          expected home of each write, with the hook required to use the map;
  2. the app's ABI      - every signature in src/lib/contract.ts, normalised to name(types);
  3. the chain          - each proxy's implementation, and which contract actually dispatches
                          each selector, scanned by opcode over the whole runtime.

Read-only: eth_getStorageAt, eth_getCode, eth_call, eth_blockNumber. No transaction is signed.

Usage:
  scripts/probe-l1-surface.py                        # routing + ABI + expected-home check
  scripts/probe-l1-surface.py --print-selectors      # also dump each dispatcher set
  scripts/probe-l1-surface.py --simulate-from 0x...  # replay cancelAllOrders/withdraw
  scripts/probe-l1-surface.py --history 80000        # walk both impl slots (needs archive state)
  scripts/probe-l1-surface.py --zk 0x.. --core 0x..  # probe candidates (app left uncertified)

Exit codes: 0 all three agree; 1 a mismatch; 2 incomplete (a requested check could not run).
Addresses are read from src/lib/config.ts and never printed in full.
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
WRITE_HOOK = os.path.join(REPO, "src", "hooks", "useL1Action.ts")
TARGETS_FILE = os.path.join(REPO, "src", "lib", "l1Targets.ts")
ABI_FILE = os.path.join(REPO, "src", "lib", "contract.ts")

# selector -> (normalised signature, the only contract that may carry it)
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

STATE = {"ok": True, "incomplete": False}


class RpcUnavailable(RuntimeError):
    """Every front refused the transport. Distinct from a node-answered refusal: reporting
    one as the other turns 'we could not ask' into 'the contract said no'."""


class RpcError(RuntimeError):
    """A node answered with an error object: a revert, a refused call, a bad parameter."""


def parse_error(err):
    if isinstance(err, dict):
        msg = str(err.get("message", "error"))
        data = err.get("data")
        return f"{msg} {data}" if data else msg
    return str(err)


def rpc(method, params):
    last = None
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for url in RPCS:
        try:
            req = urllib.request.Request(url, data=body, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                out = json.load(r)
        except urllib.error.HTTPError as exc:
            # A revert often arrives as HTTP 400 with the JSON-RPC error in the body, so a
            # blanket transport catch would relabel a refusal as an outage.
            try:
                parsed = json.loads(exc.read().decode(errors="replace"))
            except Exception:
                parsed = None
            if isinstance(parsed, dict) and "error" in parsed:
                raise RpcError(parse_error(parsed["error"])[:200])
            last = f"{url}: HTTP {exc.code}"
            continue
        except Exception as exc:
            last = f"{url}: {exc}"
            continue
        if not isinstance(out, dict):
            last = f"{url}: not a JSON-RPC response"
            continue
        if "error" in out:
            raise RpcError(parse_error(out["error"])[:200])
        if "result" not in out:
            last = f"{url}: no result"
            continue
        return out["result"]
    raise RpcUnavailable(f"all RPC fronts failed for {method} ({last})")


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}")


def pick_config(name, text=None):
    """The address a config constant ships, matched on the exact const name: 'export const
    ZKLIGHTER_LEGACY' also starts with 'export const ZKLIGHTER'."""
    text = read(CONFIG) if text is None else text
    m = re.search(r"export const " + re.escape(name) + r"\b\s*=(.{0,400})", text, re.S)
    if not m:
        raise SystemExit(f"{name} is not exported by {CONFIG}")
    a = re.search(r"(0x[0-9a-fA-F]{40})", m.group(1))
    if not a:
        raise SystemExit(f"no literal address found for {name} in {CONFIG}")
    return a.group(1)


def arg_value(flag):
    """Value of --flag VALUE, or a clean exit when the flag is last on the line."""
    argv = sys.argv
    if flag not in argv:
        return None
    i = argv.index(flag)
    if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
        raise SystemExit(f"{flag} needs a value")
    return argv[i + 1]


def slot_address(raw):
    """A 32-byte slot read as a 20-byte address, or None. A short or missing reply is not
    coerced: '0x' + '0x'[-40:] would print '0x0x' and compare as an address."""
    if not isinstance(raw, str) or len(raw) != 66:
        return None
    body = raw[2:].lower()
    if int(body, 16) == 0:
        return None
    return "0x" + body[-40:]


def impl_of(proxy):
    return slot_address(rpc("eth_getStorageAt", [proxy, SLOT, "latest"]))


def opcodes(code_hex, region=None):
    """Walk the runtime byte by byte, skipping PUSH data. A regex over the hex string is not
    a dispatcher test: it can match across a nibble boundary and inside PUSH32 constants
    (one real runtime carries 0xabf6a038 inside a PUSH32 at offset 10567)."""
    h = code_hex[2:] if code_hex.startswith(("0x", "0X")) else code_hex
    h = h.lower()
    end = len(h) if region is None else min(len(h), region * 2)
    i = 0
    while i + 2 <= end:
        op = int(h[i:i + 2], 16)
        if 0x60 <= op <= 0x7f:  # PUSH1..PUSH32
            size = op - 0x5f
            yield i // 2, op, h[i + 2:i + 2 + size * 2]
            i += 2 + size * 2
            continue
        yield i // 2, op, ""
        i += 2


def dispatched(code_hex, sel):
    """True when the runtime compares msg.sig against this selector: PUSH4 <sel> EQ.
    That is what `if (msg.sig == 0x...)` compiles to, and it is scanned over the whole
    runtime so a selector that moved past the dispatcher region is still found."""
    h = code_hex[2:] if code_hex.startswith(("0x", "0X")) else code_hex
    h = h.lower()
    n = len(h)
    i = 0
    while i + 12 <= n:
        op = int(h[i:i + 2], 16)
        if 0x60 <= op <= 0x7f:
            if op == 0x63 and h[i + 2:i + 10] == sel and h[i + 10:i + 12] == "14":
                return True
            i += 2 + (op - 0x5f) * 2
            continue
        i += 2
    return False


def dispatcher_selectors(code_hex, region=8192):
    """PUSH4 immediates in the dispatcher region, for the printed count only: it also picks
    up string data, so no absence is ever judged from it."""
    return {imm for _, op, imm in opcodes(code_hex, region=region) if op == 0x63 and imm}


def short(a):
    return f"{a[:10]}...{a[-4:]}" if a else "none"


def app_targets():
    """The app's function-to-contract map, read from l1Targets.ts rather than assumed."""
    text = read(TARGETS_FILE)
    i = text.find("export const L1_TARGETS")
    if i < 0:
        raise SystemExit(f"L1_TARGETS is not exported by {TARGETS_FILE}")
    body = text[i:]
    j = body.find("} as const")
    body = body[:j] if j >= 0 else body
    return dict(re.findall(r"(\w+):\s*(ZKLIGHTER|L1_CORE_MESSAGING)", body))


def abi_signatures():
    """Every `function name(types)` in contract.ts, normalised to name(types)."""
    text = read(ABI_FILE)
    out = {}
    for name, params in re.findall(r"'function\s+(\w+)\s*\(([^)]*)\)", text):
        types = []
        for part in params.split(","):
            part = part.strip()
            if not part:
                continue
            m = re.match(r"[a-z0-9\[\]]+", part)
            types.append(m.group(0) if m else part)
        out[name] = f"{name}({','.join(types)})"
    return out


# The app's map names the constants; the expected table names the contracts.
WRITE_LABEL = {"ZKLIGHTER": "ZkLighter", "L1_CORE_MESSAGING": "L1CoreMessaging"}
# Only these are writes. The views and the deposit path are chain-only in this probe: the repo's
# ABI does not encode them, so routing them would be a claim about code that is not here.
WRITES = {"withdrawPendingBalance", "withdraw", "cancelAllOrders", "createOrder", "burnShares", "changePubKey"}


def check_wiring():
    """The half the chain cannot answer: which contract each write is sent to."""
    ok = True
    targets = {name: WRITE_LABEL.get(const, const) for name, const in app_targets().items()}
    expected_by_name = {sig.split("(")[0]: (sig, home) for sig, home in EXPECTED.values()}

    print("shipped wiring")
    for name in sorted(WRITES):
        sig, home = expected_by_name[name]
        got = targets.get(name)
        if got != home:
            ok = False
        print(f"{'OK ' if got == home else 'BAD'} {sig:46} {home:17} {got or 'NOT ROUTED'}")
    for name in targets:
        if name not in WRITES:
            ok = False
            print(f"BAD {name:46} {'UNKNOWN':17} routed with no expected home")

    hook = read(WRITE_HOOK)
    uses_map = "address: l1Target(" in hook
    hardcoded = "address: L1_CORE_MESSAGING" in hook or "address: ZKLIGHTER" in hook
    if not uses_map or hardcoded:
        ok = False
    print(f"{'OK ' if uses_map and not hardcoded else 'BAD'} {os.path.relpath(WRITE_HOOK, REPO):46} "
          f"sends every write through l1Target()")

    abi = abi_signatures()
    for name, sig in sorted(abi.items()):
        if name in expected_by_name and sig != expected_by_name[name][0]:
            ok = False
            print(f"BAD {os.path.relpath(ABI_FILE, REPO):46} {sig} != {expected_by_name[name][0]}")
    missing = [n for n in targets if n not in abi]
    if missing:
        ok = False
        print(f"BAD {os.path.relpath(ABI_FILE, REPO):46} routed but absent from the ABI: {', '.join(missing)}")
    if ok:
        print(f"OK  {os.path.relpath(ABI_FILE, REPO):46} {len(abi)} signatures match the expected table")
    return ok


def main():
    zk_config = pick_config("ZKLIGHTER")
    core_config = pick_config("L1_CORE_MESSAGING")
    zk = arg_value("--zk") or zk_config
    core = arg_value("--core") or core_config
    for flag, addr in (("--zk", zk), ("--core", core)):
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", addr):
            raise SystemExit(f"{flag} needs a 20-byte hex address")
    if zk.lower() != zk_config.lower() or core.lower() != core_config.lower():
        print("NOTE: probing override addresses; the shipped app is NOT certified by this run")
        STATE["incomplete"] = True

    verbose = "--print-selectors" in sys.argv
    STATE["ok"] = check_wiring()

    carried = {}
    codes = {}
    print("\ncontracts")
    for name, proxy in (("ZkLighter", zk), ("L1CoreMessaging", core)):
        try:
            impl = impl_of(proxy)
        except RpcUnavailable as exc:
            print(f"BAD {name:16} proxy {short(proxy)}: no reading ({str(exc)[:60]})")
            return 2
        if not impl:
            print(f"BAD {name:16} proxy {short(proxy)}: EIP-1967 slot empty, not a proxy")
            return 1
        try:
            code = rpc("eth_getCode", [impl, "latest"])
        except RpcUnavailable as exc:
            print(f"BAD {name:16} proxy {short(proxy)}: no code readable ({str(exc)[:60]})")
            return 2
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
        if holders != [home]:
            STATE["ok"] = False
        print(f"{'OK ' if holders == [home] else 'BAD'} {sig:46} {home:17} {verdict}")
    for sel, note in DEAD.items():
        holders = [c for c in codes if dispatched(codes[c], sel)]
        if holders:
            STATE["ok"] = False
        print(f"{'BAD' if holders else 'OK '} {note:46} {'RETIRED':17} "
              f"{', '.join(holders) if holders else 'absent everywhere (good)'}")

    sender = arg_value("--simulate-from")
    if sender:
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", sender):
            raise SystemExit("--simulate-from needs a 20-byte hex address")
        print(f"\nsimulating from {sender[:10]}...")
        index = None
        try:
            raw = rpc("eth_call", [{"to": zk, "data": "0xabf6a038" + sender[2:].lower().rjust(64, "0")},
                                   "latest"])
            if not isinstance(raw, str) or len(raw) != 66:
                print("  the account-index read did not answer one 32-byte word; simulation skipped")
                STATE["incomplete"] = True
            else:
                index = int(raw, 16)
                if index >= 2 ** 48:
                    print("  the account index exceeds uint48; simulation skipped")
                    index = None
                    STATE["incomplete"] = True
        except RpcUnavailable:
            print("  no RPC front answered the account-index read; simulation skipped")
            STATE["incomplete"] = True
        except RpcError as exc:
            print(f"  the account-index read was refused ({str(exc)[:70]}); simulation skipped")
            STATE["incomplete"] = True
        if index == 0:
            print("  this address has no Lighter account index; a simulated call would only prove "
                  "an authorization failure, so it is skipped")
            STATE["incomplete"] = True
        elif index:
            def word(v):
                return f"{v:064x}"

            calls = [
                ("cancelAllOrders", "0xa4b6f756" + word(index)),
                ("withdraw(1,0,1)", "0xd20191bd" + word(index) + word(1) + word(0) + word(1)),
                ("withdraw(1,0,0)", "0xd20191bd" + word(index) + word(1) + word(0) + word(0)),
            ]
            for call, calldata in calls:
                for name, proxy in (("L1CoreMessaging", core), ("ZkLighter", zk)):
                    try:
                        out = rpc("eth_call", [{"from": sender, "to": proxy, "data": calldata}, "latest"])
                        kind = "accepted"
                        detail = ", no return data" if not out or out == "0x" else f", {len(out) // 2 - 1} bytes"
                        result = "accepted" + detail
                    except RpcUnavailable:
                        kind, result = "unknown", "no answer (RPC unavailable)"
                        STATE["incomplete"] = True
                    except RpcError as exc:
                        message = str(exc)
                        has_data = bool(re.search(r"0x[0-9a-fA-F]{8,}", message))
                        kind = "refused-with-data" if has_data else "refused-empty"
                        result = (f"refused with revert data (dispatched) [{message[:40]}]"
                                  if has_data else
                                  f"refused with empty revert (no such function) [{message[:40]}]")
                    print(f"  {call:24} on {name:16} {result}")
                    # The contract that should carry the selector must not look like it lacks it.
                    if name == "L1CoreMessaging" and kind == "refused-empty":
                        STATE["ok"] = False

    span_raw = arg_value("--history")
    if span_raw is not None:
        try:
            span = int(span_raw)
        except ValueError:
            raise SystemExit("--history needs a block count, for example --history 14000")
        if span <= 0:
            raise SystemExit("--history needs a positive block count")
        try:
            head = int(rpc("eth_blockNumber", []), 16)
        except RpcUnavailable:
            print("\nno RPC front answered eth_blockNumber; history skipped")
            STATE["incomplete"] = True
            head = None
        if head is not None:
            step = 2000
            lowest = max(0, head - span)
            points = list(range(head, lowest - 1, -step))
            print(f"\nwalking both impl slots from block {head} back to {lowest}: {len(points)} samples, "
                  f"stride {step}; changes are dated between samples only")
            for name, proxy in (("ZkLighter", zk), ("L1CoreMessaging", core)):
                prev = None
                changes = 0
                samples = 0
                last_b = None
                try:
                    for b in points:
                        impl = slot_address(rpc("eth_getStorageAt", [proxy, SLOT, hex(b)]))
                        last_b = b
                        samples += 1
                        if prev is not None and impl != prev:
                            changes += 1
                            print(f"  {name:16} changed between block {b} and {b + step}: "
                                  f"{short(impl)} -> {short(prev)}")
                        prev = impl
                except (RpcUnavailable, RpcError) as exc:
                    print(f"  {name:16} stopped at block {last_b}: {str(exc)[:70]} "
                          f"({samples} samples read before it)")
                    STATE["incomplete"] = True
                    continue
                if changes == 0:
                    print(f"  {name:16} no change across {samples} samples")

    if not STATE["ok"]:
        print("\nVERDICT: a claim does not match: the app's routing, its ABI, or the chain")
        return 1
    if STATE["incomplete"]:
        print("\nVERDICT: INCOMPLETE: a requested check did not run (see the lines above)")
        return 2
    print("\nVERDICT: routing, ABI and chain agree with the expected split")
    return 0


if __name__ == "__main__":
    sys.exit(main())
