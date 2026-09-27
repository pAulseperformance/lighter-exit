import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { WagmiProvider } from 'wagmi'

import { ExitPage } from './components/ExitPage'
import { ThreatModelPage } from './components/ThreatModelPage'
import { ActionsProvider } from './hooks/useActions'
import { SigningKeysProvider } from './hooks/useSigningKeys'
import { wagmiConfig } from './wagmi'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

/** Tiny hash router: '#/threat-model' renders the threat model page, everything else the exit tool. */
function useHashView(): string {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return hash.replace(/^#\/?/, '')
}

export default function App() {
  const view = useHashView()
  return (
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        <ActionsProvider>
          <SigningKeysProvider>
            {view === 'threat-model' ? <ThreatModelPage /> : <ExitPage />}
          </SigningKeysProvider>
        </ActionsProvider>
      </QueryClientProvider>
    </WagmiProvider>
  )
}
