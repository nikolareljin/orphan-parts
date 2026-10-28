import { useEffect, useState } from 'react'
import { api, type Readiness, type Version } from './lib/api'
import './App.css'

type Status = { kind: 'loading' } | { kind: 'ok'; ready: Readiness; version: Version } | { kind: 'error'; message: string }

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: 'loading' })

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
      </header>

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
              {status.ready.model_api === 'live' ? 'live' : 'fixture mode (no key, recorded responses)'}
            </dd>
            <dt>Models</dt>
            <dd>{Object.values(status.version.models).join(', ')}</dd>
            <dt>Storage</dt>
            <dd>{status.ready.data_dir_writable ? 'writable' : 'read-only'}</dd>
          </dl>
        )}
      </section>

      <section className="card muted">
        <h2>Next</h2>
        <p>The five flows land here: identify, value, list, find and reuse. Photos or a listing in, an evidence-backed answer out.</p>
      </section>
    </main>
  )
}
