import { describe, expect, it } from 'vitest'

import { L1_CORE_MESSAGING, ZKLIGHTER } from '../src/lib/config'
import { lighterAbi } from '../src/lib/contract'
import { L1_TARGETS, l1Target } from '../src/lib/l1Targets'

// The 2026-11-08 split put two contracts under one write hook, and the defect this pins is
// invisible to the type system: a claim sent to L1CoreMessaging encodes perfectly and reverts
// on mainnet, because that selector is not there. It shipped that way for a day.
describe('L1 write routing', () => {
  // stateMutability is a literal union per entry here, so read it through a widened view:
  // comparing the narrowed type against 'pure' is a compile error, not a runtime question.
  const mutability = (entry: (typeof lighterAbi)[number]) =>
    (entry as { stateMutability?: string }).stateMutability
  const writes = lighterAbi
    .filter(
      (entry) =>
        entry.type === 'function' && mutability(entry) !== 'view' && mutability(entry) !== 'pure',
    )
    .map((entry) => entry.name)

  it('routes every write the ABI declares, so none can fall through to a default', () => {
    expect([...writes].sort()).toEqual(Object.keys(L1_TARGETS).sort())
  })

  it('sends the pending-balance claim to ZkLighter, where its selector lives', () => {
    expect(l1Target('withdrawPendingBalance')).toBe(ZKLIGHTER)
  })

  it('sends the priority transactions to L1CoreMessaging', () => {
    for (const fn of ['withdraw', 'cancelAllOrders', 'createOrder', 'burnShares', 'changePubKey']) {
      expect(l1Target(fn)).toBe(L1_CORE_MESSAGING)
    }
  })

  it('refuses an unknown write instead of guessing a contract', () => {
    expect(() => l1Target('deposit')).toThrow(/no L1 target/)
  })
})
