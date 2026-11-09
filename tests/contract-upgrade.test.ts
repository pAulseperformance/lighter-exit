import { encodeFunctionData, parseAbi } from 'viem'
import { describe, expect, it } from 'vitest'

import { L1_CORE_MESSAGING, ZKLIGHTER } from '../src/lib/config'
import { lighterAbi } from '../src/lib/contract'

// The 2026-11-08 upgrade moved the L1 priority transactions to L1CoreMessaging and widened the
// createOrder market index from uint16 to uint64. Encoding is offline and deterministic, so it is
// the right layer to pin: a wrong width still compiles and only fails on-chain.
describe('post-upgrade contract wiring', () => {
  it('points priority transactions at L1CoreMessaging and keeps ZkLighter separate', () => {
    expect(L1_CORE_MESSAGING.toLowerCase()).toBe('0x183ef7195d443a3da7ec1d7003baca1ff490757d')
    expect(ZKLIGHTER.toLowerCase()).toBe('0x3b4d794a66304f130a4db8f2551b0070dfcf5ca7')
    expect(L1_CORE_MESSAGING).not.toBe(ZKLIGHTER)
  })

  it('encodes createOrder with the uint64 market index selector, not the retired uint16 one', () => {
    const data = encodeFunctionData({
      abi: lighterAbi,
      functionName: 'createOrder',
      args: [250552n, 111n, 0n, 0, 0, 3],
    })
    // keccak('createOrder(uint48,uint64,uint48,uint32,uint8,uint8)')[0:4]
    expect(data.slice(0, 10)).toBe('0x3873d062')
    expect(data.slice(0, 10)).not.toBe('0x3c40c676')
  })

  it('encodes the exit functions the emergency hatch needs', () => {
    const withdraw = encodeFunctionData({
      abi: lighterAbi,
      functionName: 'withdraw',
      args: [250552n, 1, 0, 1n],
    })
    expect(withdraw.slice(0, 10)).toBe('0xd20191bd')
    const cancel = encodeFunctionData({
      abi: lighterAbi,
      functionName: 'cancelAllOrders',
      args: [250552n],
    })
    expect(cancel.slice(0, 10)).toBe('0xa4b6f756')
    // the pending-balance claim stays on ZkLighter, and it must still encode
    const claim = encodeFunctionData({
      abi: parseAbi([
        'function withdrawPendingBalance(address _owner, uint16 _assetId, uint128 _amount)',
      ]),
      functionName: 'withdrawPendingBalance',
      args: ['0x0000000000000000000000000000000000000001', 0, 0n],
    })
    expect(claim.slice(0, 10)).toBe('0x2f25807e')
  })
})
