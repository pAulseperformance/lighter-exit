// Follows one L1 transaction from the Lighter contract all the way to L2:
// polls /txFromL1TxHash until Lighter picks it up, prints the execution
// result and the L2 error (event_info.ae) if it was rejected.
//
// Usage:  node scripts/watch-l1-tx.mjs 0x<l1txhash> [timeoutSeconds]
// Zero dependencies, mainnet Lighter API. Exits 0 on executed, 1 on
// rejected/timeout so it can be chained in scripts.
const API = (process.env.LIGHTER_API_URL ?? 'https://mainnet.zklighter.elliot.ai').replace(/\/+$/, '')
const hash = process.argv[2]
const timeoutMs = (Number(process.argv[3] ?? 15 * 60) || 900) * 1000
const POLL_MS = 8_000

if (!hash || !/^0x[0-9a-fA-F]{64}$/.test(hash)) {
  console.error('usage: node scripts/watch-l1-tx.mjs 0x<l1txhash> [timeoutSeconds]')
  process.exit(2)
}

function l2Error(tx) {
  if (!tx?.event_info) return null
  try {
    const info = JSON.parse(tx.event_info)
    if (!info.ae) return null
    try {
      const inner = JSON.parse(info.ae)
      return inner.message ? `${inner.message}${inner.code ? ` (code ${inner.code})` : ''}` : info.ae
    } catch {
      return info.ae
    }
  } catch {
    return null
  }
}

const started = Date.now()
const startedAt = new Date().toISOString()
console.log(`watching ${hash}  (started ${startedAt}, timeout ${timeoutMs / 1000}s)`)

let last
while (Date.now() - started < timeoutMs) {
  let tx = null
  try {
    const res = await fetch(`${API}/api/v1/txFromL1TxHash?hash=${hash}`, {
      headers: { accept: 'application/json' },
    })
    const body = await res.json().catch(() => null)
    const code = typeof body?.code === 'number' ? body.code : res.status
    if (code !== 200 && code !== 0) {
      if (code !== 21500) console.log(`  api says: ${body?.message ?? `HTTP ${res.status}`} (code ${code})`)
    } else {
      tx = body
    }
  } catch (err) {
    console.log(`  api unreachable (${err.message}), retrying`)
  }

  if (tx) {
    const executed = (tx.executed_at ?? 0) > 0 || (tx.status ?? 0) >= 3
    const state = JSON.stringify({
      type: tx.type,
      status: tx.status,
      queued_at: tx.queued_at,
      executed_at: tx.executed_at,
    })
    if (state !== last) {
      console.log(`  l2 record: ${state}`)
      last = state
    }
    if (executed) {
      const err = l2Error(tx)
      if (err) {
        console.log(`REJECTED by Lighter: ${err}`)
        console.log(`  raw event_info: ${tx.event_info}`)
        process.exit(1)
      }
      console.log('EXECUTED on L2. Full record:')
      console.log(JSON.stringify(tx, null, 2))
      process.exit(0)
    }
  } else {
    console.log('  not picked up yet…')
  }
  await new Promise((r) => setTimeout(r, POLL_MS))
}

console.log('TIMEOUT: confirmed on Ethereum but Lighter has not executed/reported it within the window.')
process.exit(1)
