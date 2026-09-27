import { useEffect } from 'react'

import { LIGHTER_CONTRACT } from '../lib/config'
import { LABEL_CLASSNAME, LINK_CLASSNAME, PAGE_TITLE_CLASSNAME } from '../lib/recipes'

import { Section } from './Section'
import { Table } from './StepCard'

const CornerSpans = () => (
  <>
    <span className="pointer-events-none absolute top-px left-px size-1 border border-r-0 border-b-0 border-ink/15" />
    <span className="pointer-events-none absolute top-px right-px size-1 border border-b-0 border-l-0 border-ink/15" />
    <span className="pointer-events-none absolute right-px bottom-px size-1 border border-t-0 border-l-0 border-ink/15" />
    <span className="pointer-events-none absolute bottom-px left-px size-1 border border-t-0 border-r-0 border-ink/15" />
  </>
)

const P_CLASSNAME = 'max-w-[68ch] text-md leading-2xl text-dim'

export function ThreatModelPage() {
  useEffect(() => {
    const previous = document.title
    document.title = 'Threat model · Lighter exit'
    window.scrollTo(0, 0)
    return () => {
      document.title = previous
    }
  }, [])

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-[840px] flex-col px-5 pb-10">
      <header className="flex items-center justify-between gap-4 py-6">
        <a href="#/" className="text-sm text-muted transition-colors hover:text-ink">
          ← Back to the exit tool
        </a>
        <span className={LABEL_CLASSNAME}>Threat model</span>
      </header>
      <main className="flex flex-1 flex-col gap-10">
        <Section d={0}>
          <div className="relative flex w-full flex-col gap-4 border border-ink/5 bg-ink/5 p-5">
            <p className="text-2xs font-medium tracking-caps text-meta uppercase">lighter · threat model</p>
            <h1 className={PAGE_TITLE_CLASSNAME}>What can exit without Lighter</h1>
            <p className="max-w-[58ch] text-md leading-2xl text-dim">
              This tool exists for the worst case: you can no longer use the Lighter app, and the only way out is
              Ethereum. This page lists what that path can reach — and what it cannot. Every row has been exercised
              against mainnet; nothing here is inferred from documentation.
            </p>
            <CornerSpans />
          </div>
        </Section>

        <Section d={1}>
          <div className="flex flex-col gap-4">
            <span className={LABEL_CLASSNAME}>The short version</span>
            <ul className="flex max-w-[68ch] flex-col gap-3 text-md leading-2xl text-dim">
              <li>
                <span className="font-medium text-ink">The contract reaches everything — except one thing.</span>{' '}
                Balances, open positions, the margin behind orders, public pool shares and funds parked on Ethereum can
                all be exited through Ethereum alone. The single exception is an active LIT stake.
              </li>
              <li>
                <span className="font-medium text-ink">The contract records; Lighter executes.</span> Your exit request
                is a real Ethereum transaction, but Lighter&apos;s engine is what acts on it. That is ban resistance,
                not protocol-death resistance.
              </li>
              <li>
                <span className="font-medium text-ink">The contract can be upgraded — so it is watched.</span> A monitor
                checks its code hourly and alerts on any change, including which functions were added or removed.
              </li>
            </ul>
          </div>
        </Section>

        <Section d={2}>
          <div className="flex flex-col gap-4">
            <span className={LABEL_CLASSNAME}>Exit matrix</span>
            <Table
              head={
                <>
                  <th>Location</th>
                  <th>Route</th>
                  <th>Contract alone?</th>
                </>
              }
            >
              <tr>
                <td className="text-ink">Perp collateral (USDC)</td>
                <td className="font-mono text-dim">withdraw · route 0</td>
                <td className="text-success">✓ works</td>
              </tr>
              <tr>
                <td className="text-ink">Spot balances</td>
                <td className="font-mono text-dim">withdraw · route 1</td>
                <td className="text-success">✓ works</td>
              </tr>
              <tr>
                <td className="text-ink">Margin behind open orders</td>
                <td className="font-mono text-dim">cancel all → withdraw</td>
                <td className="text-success">✓ works</td>
              </tr>
              <tr>
                <td className="text-ink">Open perp positions</td>
                <td className="font-mono text-dim">reduce-only close → withdraw</td>
                <td className="text-success">✓ works</td>
              </tr>
              <tr>
                <td className="text-ink">Public pool shares (LLP &amp; trader pools)</td>
                <td className="font-mono text-dim">burnShares</td>
                <td className="text-success">✓ proven on mainnet</td>
              </tr>
              <tr>
                <td className="text-ink">Withdrawals past the timer</td>
                <td className="font-mono text-dim">timer completes → withdraw</td>
                <td className="text-success">✓ works</td>
              </tr>
              <tr>
                <td className="text-ink">Funds parked on Ethereum</td>
                <td className="font-mono text-dim">claim · pure L1</td>
                <td className="text-success">✓ no Lighter involvement</td>
              </tr>
              <tr>
                <td className="text-ink">Staked LIT</td>
                <td className="font-mono text-dim">UnstakeAssets — API only</td>
                <td className="text-down">✗ rejected on the contract path</td>
              </tr>
              <tr>
                <td className="text-ink">Pool freeze / operator actions</td>
                <td className="font-mono text-dim">API only</td>
                <td className="text-down">✗ no contract function exists</td>
              </tr>
            </Table>
            <p className="max-w-[68ch] text-sm leading-md text-faint">
              The share-burn path was tested both ways on mainnet: a public-pool burn executed end-to-end through the
              contract, while a staking-pool burn was cleanly rejected by Lighter&apos;s engine with an explicit error
              code — which is why unstaking stays on the API.
            </p>
          </div>
        </Section>

        <Section d={3}>
          <div className="flex flex-col gap-4">
            <span className={LABEL_CLASSNAME}>What the contract cannot reach</span>
            <ul className="flex max-w-[68ch] flex-col gap-3 text-md leading-2xl text-dim">
              <li>
                <span className="font-medium text-ink">Staked LIT.</span> The one money position with no contract
                route. The contract&apos;s burn function accepts public-pool indices only; a staking-pool burn is
                rejected. Unstaking exists on the Lighter API alone, with a 3-day unlock — size a stake as money you
                trust to the API for that long.
              </li>
              <li>
                <span className="font-medium text-ink">Pool management.</span> Freezing a pool and similar operator
                actions have no contract equivalents. They move no money, but a pool operator who loses API access
                cannot fully wind down a public pool.
              </li>
            </ul>
          </div>
        </Section>

        <Section d={4}>
          <div className="flex flex-col gap-4">
            <span className={LABEL_CLASSNAME}>Residual risks</span>
            <ul className="flex max-w-[68ch] flex-col gap-3 text-md leading-2xl text-dim">
              <li>
                <span className="font-medium text-ink">Engine cooperation.</span> Queued contract actions are executed
                by Lighter&apos;s engine, not by Ethereum. If enforcement were ever extended below the API — or the
                engine stopped running — exit requests would wait. What a restricted account&apos;s queued action gets
                is untestable without being banned; treat it as the residual unknown.
              </li>
              <li>
                <span className="font-medium text-ink">Contract upgrades.</span> The contract sits behind an
                upgradeable proxy. A malicious or careless upgrade could remove or weaken exit functions. This project
                watches the implementation hourly and alerts with a function-level diff when it changes.
              </li>
              <li>
                <span className="font-medium text-ink">Emergency machinery is operator-gated.</span> The protocol&apos;s
                failure-mode tooling requires operator participation; there is no user-facing force-exit. Plan for
                cooperation, not for a dead Lighter.
              </li>
            </ul>
          </div>
        </Section>

        <Section d={5}>
          <div className="flex flex-col gap-4">
            <span className={LABEL_CLASSNAME}>What public sources miss</span>
            <ul className="flex max-w-[68ch] flex-col gap-3 text-md leading-2xl text-dim">
              <li>
                <span className="font-medium text-ink">The staking gap.</span>{' '}
                <a
                  href="https://l2beat.com/layer2s/projects/lighter"
                  target="_blank"
                  rel="noreferrer"
                  className={LINK_CLASSNAME}
                >
                  L2Beat&apos;s Lighter page
                </a>{' '}
                and its{' '}
                <a
                  href="https://l2beat.com/publications/exchange-risk-and-how-lighter-escapes-it"
                  target="_blank"
                  rel="noreferrer"
                  className={LINK_CLASSNAME}
                >
                  exchange-risk publication
                </a>{' '}
                describe the L1 exit path, but not that an active stake has no contract exit.
              </li>
              <li>
                <span className="font-medium text-ink">The enforcement-layer question.</span> Public
                &quot;force-via-L1&quot; analysis concerns protocol-level sequencer failure — not a healthy sequencer
                refusing a specific account&apos;s queued action.
              </li>
              <li>
                <span className="font-medium text-ink">Per-user dependency.</span> Everyday exits depend on
                Lighter&apos;s engine executing what the contract records. Published ratings score the system, not the
                per-account refusal scenario.
              </li>
            </ul>
          </div>
        </Section>

        <Section d={6}>
          <div className="flex flex-col gap-4">
            <span className={LABEL_CLASSNAME}>How this was verified</span>
            <p className={P_CLASSNAME}>
              Full passes against Ethereum mainnet, most recently on 2026-09-27. Both working routes and refusal paths
              were exercised: a public-pool share burn executed, a contract withdrawal executed, and a staking-pool
              burn was rejected with an explicit error. The tool holds no keys and nothing moves without your
              signature — every step is a standard Ethereum transaction or a documented Lighter action you can check
              against the explorer.
            </p>
          </div>
        </Section>
      </main>
      <footer className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t-[0.5px] border-line pt-5 text-sm text-faint">
        <p>Last verified 2026-09-27 · Ethereum mainnet</p>
        <p>
          Contract{' '}
          <a
            href={`https://etherscan.io/address/${LIGHTER_CONTRACT}`}
            target="_blank"
            rel="noreferrer"
            className={`${LINK_CLASSNAME} font-mono`}
          >
            0x3B4D…5ca7
          </a>
        </p>
      </footer>
    </div>
  )
}
