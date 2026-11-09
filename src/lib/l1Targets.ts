import { L1_CORE_MESSAGING, ZKLIGHTER } from './config'

/**
 * Which L1 contract carries which write, since the 2026-11-08 split.
 *
 * Deposits and the pending-balance claim stay on ZkLighter; the priority transactions
 * moved to L1CoreMessaging. A single write target is what broke the claim: it posted
 * `withdrawPendingBalance` to a contract that does not implement that selector, so the
 * claim reverted while the chain and the ABI both looked right.
 *
 * Every non-view entry in `lighterAbi` must appear here; a test pins that, so adding a
 * write without deciding its contract fails by name instead of failing on mainnet.
 */
export const L1_TARGETS = {
  withdrawPendingBalance: ZKLIGHTER,
  withdraw: L1_CORE_MESSAGING,
  cancelAllOrders: L1_CORE_MESSAGING,
  createOrder: L1_CORE_MESSAGING,
  burnShares: L1_CORE_MESSAGING,
  changePubKey: L1_CORE_MESSAGING,
} as const

export type L1WriteFn = keyof typeof L1_TARGETS

const TARGETS: Record<string, `0x${string}`> = L1_TARGETS

/** The contract a write must be sent to. Throws rather than guessing a default. */
export function l1Target(fn: string): `0x${string}` {
  const target = TARGETS[fn]
  if (!target) {
    throw new Error(
      `no L1 target for ${fn}: add it to L1_TARGETS, because a default would send it to the wrong contract`,
    )
  }
  return target
}
