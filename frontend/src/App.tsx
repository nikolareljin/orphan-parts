import { useEffect, useState, type FormEvent } from 'react'
import Build from './components/Build'
import ExtractForm from './components/ExtractForm'
import Find from './components/Find'
import Inventory from './components/Inventory'
import { ACCESS_REQUIRED_EVENT, api, type Readiness, type Version } from './lib/api'
import { demoText } from './lib/access'
import './App.css'

type Status = { kind: 'loading' } | { kind: 'ok'; ready: Readiness; version: Version } | { kind: 'error'; message: string }
type View = 'read' | 'inventory' | 'find' | 'build'

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: 'loading' })
  const [view, setView] = useState<View>('read')
  const [saved, setSaved] = useState(0)
  const [granted, setGranted] = useState<boolean | null>(null)
  const [reloads, setReloads] = useState(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.readiness(), api.version(), api.access.status()])
      .then(([ready, version, access]) => {
        if (cancelled) return
        setStatus({ kind: 'ok', ready, version })
        setGranted(access.granted)
      })
      .catch((err: unknown) => {
        if (!cancelled) setStatus({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
      })
    return () => {
      cancelled = true
    }
  }, [reloads])

  // a session that ended mid-visit: any 401 brings the code form back
  useEffect(() => {
    const lost = () => setGranted(false)
    window.addEventListener(ACCESS_REQUIRED_EVENT, lost)
    return () => window.removeEventListener(ACCESS_REQUIRED_EVENT, lost)
  }, [])

  const open = granted !== false

  return (
    <main className="shell">
      <header>
        <h1>Orphan Parts Lens</h1>
        <p className="tagline">Show it, ask it, sell it, or find the one that fits.</p>
        {open && (
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
          <button type="button" aria-current={view === 'build' ? 'page' : undefined} onClick={() => setView('build')}>
            Build and reuse
          </button>
        </nav>
        )}
      </header>

      {granted === false && <AccessGate onGranted={() => setReloads((n) => n + 1)} />}

      {open && view === 'read' && (
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

      {open && view === 'inventory' && (
        <section className="card">
          <h2>My inventory</h2>
          <Inventory refresh={saved} />
        </section>
      )}

      {open && view === 'find' && (
        <section className="card">
          <h2>Find a part</h2>
          <Find />
        </section>
      )}

      {open && view === 'build' && (
        <section className="card">
          <h2>Build and reuse</h2>
          <Build />
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
            {demoText(status.ready) && (
              <>
                <dt>Demo</dt>
                <dd>{demoText(status.ready)}</dd>
              </>
            )}
          </dl>
        )}
      </section>
    </main>
  )
}

// The code the demo runs behind. A session is a cookie the browser keeps; nothing is stored here.
function AccessGate({ onGranted }: { onGranted: () => void }) {
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function enter(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const access = await api.access.grant(code)
      if (access.granted) {
        setCode('')
        onGranted()
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card gate">
      <h2>This demo runs behind an access code</h2>
      <p className="muted">Every call to the models costs money, so the demo is open to people with the code. A session lasts a while and keeps nothing about you but the cookie.</p>
      <form onSubmit={(e) => void enter(e)} aria-label="Access code">
        <div className="row">
          <label>
            <span>Access code</span>
            <input type="password" value={code} autoComplete="off" onChange={(e) => setCode(e.target.value)} />
          </label>
          <button type="submit" disabled={busy || !code}>
            {busy ? 'Checking…' : 'Enter'}
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  )
}
