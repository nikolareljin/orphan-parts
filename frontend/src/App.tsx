import { useEffect, useState, type FormEvent } from 'react'
import Build from './components/Build'
import ExtractForm from './components/ExtractForm'
import Find from './components/Find'
import Inbox from './components/Inbox'
import Inventory from './components/Inventory'
import Modal from './components/Modal'
import { ACCESS_REQUIRED_EVENT, api, apiBase, type Readiness, type Version } from './lib/api'

import { reachableFromAPhone } from './lib/pairing'
import { DEFAULT_LIMITS } from './lib/photos'
import { demoText } from './lib/access'
import { VIEWS, hashFor, viewFromHash, type View } from './lib/nav'
import './App.css'

// what the pairing code carries: the API's origin when the web app is served elsewhere, else this page's
const pairOrigin = apiBase || (typeof window !== 'undefined' ? window.location.origin : '')

type Status = { kind: 'loading' } | { kind: 'ok'; ready: Readiness; version: Version } | { kind: 'error'; message: string }

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: 'loading' })
  const [view, setViewState] = useState<View>(() => viewFromHash(window.location.hash))
  const [saved, setSaved] = useState(0)
  const [openItem, setOpenItem] = useState<number | null>(null)
  const [granted, setGranted] = useState<boolean | null>(null)
  const [gated, setGated] = useState(false)
  const [signIn, setSignIn] = useState(false)
  const [reloads, setReloads] = useState(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.readiness(), api.version(), api.access.status()])
      .then(([ready, version, access]) => {
        if (cancelled) return
        setStatus({ kind: 'ok', ready, version })
        setGranted(access.granted)
        setGated(access.gated)
      })
      .catch((err: unknown) => {
        if (!cancelled) setStatus({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
      })
    return () => {
      cancelled = true
    }
  }, [reloads])

  // the page is the URL hash: reload and back land where the person was
  function setView(next: View) {
    setViewState(next)
    const wanted = hashFor(next)
    if (window.location.hash !== wanted) window.history.pushState(null, '', wanted || window.location.pathname)
  }
  useEffect(() => {
    const changed = () => setViewState(viewFromHash(window.location.hash))
    window.addEventListener('hashchange', changed)
    window.addEventListener('popstate', changed)
    return () => {
      window.removeEventListener('hashchange', changed)
      window.removeEventListener('popstate', changed)
    }
  }, [])

  // a session that ended mid-visit: a 401, or a write refused as the demo visitor, brings
  // the way in back to the header; the pages stay, as they do for any visitor
  useEffect(() => {
    const lost = () => {
      setGranted(false)
      setGated(true)
    }
    window.addEventListener(ACCESS_REQUIRED_EVENT, lost)
    return () => window.removeEventListener(ACCESS_REQUIRED_EVENT, lost)
  }, [])

  // the demo door: gated, and no session; the code opens the rest
  const demo = gated && granted === false

  return (
    <main className="shell">
      <header className="top">
        <div className="brand">
          <img src="/favicon.svg" alt="" width="48" height="48" />
          <div>
            <h1>Orphan Parts Lens</h1>
            <p className="tagline">Show it, ask it, sell it, or find the one that fits.</p>
          </div>
        </div>
        <nav className="nav" aria-label="Pages">
          {VIEWS.map((v) => (
            <button key={v.id} type="button" aria-current={view === v.id ? 'page' : undefined} onClick={() => setView(v.id)}>
              {v.label}
            </button>
          ))}
          {demo && (
            <button type="button" className="link door" onClick={() => setSignIn(true)}>
              Sign in with the code
            </button>
          )}
        </nav>
      </header>

      {demo && signIn && (
        <Modal title="Access code" onClose={() => setSignIn(false)}>
          <AccessGate
            onGranted={() => {
              setSignIn(false)
              setReloads((n) => n + 1)
              // the page under the dialog loads again through the door it now has
              setSaved((n) => n + 1)
            }}
          />
        </Modal>
      )}

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

      {view === 'inbox' && (
        <section className="card">
          <h2>Inbox</h2>
          <Inbox
            limits={status.kind === 'ok' ? status.version.limits : DEFAULT_LIMITS}
            demo={demo}
            onOpenItem={(id) => {
              setOpenItem(id)
              setSaved((n) => n + 1)
              setView('inventory')
            }}
          />
        </section>
      )}

      {view === 'inventory' && (
        <section className="card">
          <h2>My inventory</h2>
          <Inventory refresh={saved} openId={openItem} onOpened={() => setOpenItem(null)} demo={demo} />
        </section>
      )}

      {view === 'find' && (
        <section className="card">
          <h2>Find a part</h2>
          <Find />
        </section>
      )}

      {view === 'build' && (
        <section className="card">
          <h2>Build and reuse</h2>
          <Build />
        </section>
      )}

      <footer className="service" role="contentinfo" aria-label="Service">
        {status.kind === 'loading' && <span>Checking the API…</span>}
        {status.kind === 'error' && (
          <span className="error">
            API not reachable: {status.message}. Start it with <code>./dev up</code>.
          </span>
        )}
        {status.kind === 'ok' && (
          <>
            <span>Orphan Parts Lens {status.version.version}</span>
            <span>
              {status.ready.model_api === 'fixture'
                ? 'fixture mode (nothing spent)'
                : `${status.ready.model_api} mode, spent $${status.ready.spend_usd.toFixed(2)} of $${status.ready.spend_cap_usd.toFixed(2)}`}
              {status.ready.paused ? ' (paused: spend cap reached)' : ''}
            </span>
            <span>{Object.values(status.version.models).join(', ')}</span>
            <span>{status.ready.data_dir_writable ? 'storage writable' : 'storage read-only'}</span>
            {demoText(status.ready, !demo) && <span>{demoText(status.ready, !demo)}</span>}
            <details className="pair">
              <summary>Pair the phone</summary>
              {demo ? (
                <p className="muted">The phone pairs with a session of yours: sign in with the code first.</p>
              ) : (
              <>
              <p>
                In the app, on the Backend tab, tap <strong>Scan to pair</strong> and point it at this code. It carries this address
                {status.ready.demo.gated ? ' and a session of its own; the access code stays here.' : '.'}
              </p>
              {reachableFromAPhone(pairOrigin) ? (
                <>
                  <PairImage />
                  <p className="muted">
                    Or type <code>{pairOrigin}</code> into the app.
                  </p>
                </>
              ) : (
                <p className="muted">
                  The code would carry <code>{pairOrigin}</code>, which the phone cannot reach (on the phone, localhost is
                  the phone). Open the web app at the computer's network address and pair from there, or run{' '}
                  <code>./dev phone</code>, which prints a code with that address.
                </p>
              )}
              </>
              )}
            </details>
          </>
        )}
      </footer>
    </main>
  )
}

// The code's door. A session is a cookie the browser keeps; nothing is stored here.
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
    <section className="gate">
      <h3>The code opens the rest</h3>
      <p className="muted">
        Without it this is the demo: recorded answers to try, nothing kept. The code unlocks the inventory, saving, drafts, prices,
        projects and captures, and the live models when the host has a key. A session lasts a while and keeps nothing about you but
        the cookie.
      </p>
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


// The pairing code as an image. Across origins an <img> carries no bearer header, so the SVG
// is fetched with the session and shown as a data URL; same origin the cookie does it.
function PairImage() {
  // across origins the first source would be an unauthenticated fetch of the SVG: none until
  // the session's copy is in hand
  const [src, setSrc] = useState(apiBase ? '' : api.pair.svgUrl(window.location.origin))
  useEffect(() => {
    if (!apiBase) return
    let cancelled = false
    api.pair
      .svg(window.location.origin)
      .then((text) => {
        if (!cancelled) setSrc(`data:image/svg+xml;utf8,${encodeURIComponent(text)}`)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])
  if (!src) return null // the session's copy is on its way
  return <img src={src} alt="Pairing code for the phone" width="220" height="220" />
}
