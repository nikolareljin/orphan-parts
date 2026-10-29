import { useEffect, useState } from 'react'
import ExtractForm from './components/ExtractForm'
import Find from './components/Find'
import Inventory from './components/Inventory'
import { api, type Readiness, type Version } from './lib/api'
import './App.css'

type Status = { kind: 'loading' } | { kind: 'ok'; ready: Readiness; version: Version } | { kind: 'error'; message: string }
type View = 'read' | 'inventory' | 'find'

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: 'loading' })
  const [view, setView] = useState<View>('read')
  const [saved, setSaved] = useState(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.readiness(), api.version()])
      .then(([ready, version]) => {
        if (!cancelled) setStatus({ kind: 'ok', ready, version })
      })
      .catch((err: unknown) => {
        if (!cancelled) setStatus({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="shell">
      <header>
        <h1>Orphan Parts Lens</h1>
        <p className="tagline">Show it, ask it, sell it, or find the one that fits.</p>
        <nav className="nav" aria-label="Pages">
          <button type="button" aria-current={view === 'read' ? 'page' : undefined} onClick={() => setView('read')}>
            Read a label
          </button>
          <button
            type="button"
            aria-current={view === 'inventory' ? 'page' : undefined}
            onClick={() => setView('inventory')}
          >
            My inventory
          </button>
          <button type="button" aria-current={view === 'find' ? 'page' : undefined} onClick={() => setView('find')}>
            Find a part
          </button>
        </nav>
      </header>

      {view === 'read' && (
        <section className="card">
          <h2>Read a label</h2>
          <ExtractForm
            limits={status.kind === 'ok' ? status.version.limits : undefined}
            onSaved={() => {
              setSaved((n) => n + 1)
              setView('inventory')
            }}
          />
        </section>
      )}

      {view === 'inventory' && (
        <section className="card">
          <h2>My inventory</h2>
          <Inventory refresh={saved} />
        </section>
      )}

      {view === 'find' && (
        <section className="card">
          <h2>Find a part</h2>
          <Find />
        </section>
      )}

      <section className="card">
        <h2>Service</h2>
        {status.kind === 'loading' && <p>Checking the API…</p>}
        {status.kind === 'error' && (
          <p className="error">
            API not reachable: {status.message}. Start it with <code>./dev up</code>.
          </p>
        )}
        {status.kind === 'ok' && (
          <dl>
            <dt>Version</dt>
            <dd>{status.version.version}</dd>
            <dt>Model API</dt>
            <dd>
              {status.ready.model_api === 'fixture'
                ? 'fixture mode (no key, recorded responses)'
                : `${status.ready.model_api}, spent $${status.ready.spend_usd.toFixed(2)} of $${status.ready.spend_cap_usd.toFixed(2)}`}
              {status.ready.paused ? ' (paused: spend cap reached)' : ''}
            </dd>
            <dt>Models</dt>
            <dd>{Object.values(status.version.models).join(', ')}</dd>
            <dt>Storage</dt>
            <dd>{status.ready.data_dir_writable ? 'writable' : 'read-only'}</dd>
          </dl>
        )}
      </section>
    </main>
  )
}
