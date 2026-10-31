import { useEffect, useRef, useState, type FormEvent } from 'react'
import Build from './components/Build'
import ExtractForm from './components/ExtractForm'
import Find from './components/Find'
import Inbox from './components/Inbox'
import Inventory from './components/Inventory'
import Modal from './components/Modal'
import Profile from './components/Profile'
import { ACCESS_REQUIRED_EVENT, api, apiBase, type Access, type Readiness, type Version } from './lib/api'

import { pairingText, reachableFromAPhone, redrawAfterMs } from './lib/pairing'
import { DEFAULT_LIMITS } from './lib/photos'
import { demoText } from './lib/access'
import { SIGNED_IN, SIGNED_OUT, doorOf, isDemo, retryDelayMs, type AccessState, type KnownAccess } from './lib/door'
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
  // what the server said about the code, asked on its own; null until it answers
  const [access, setAccess] = useState<KnownAccess>(null)
  // how many times the footer's pairing code has been opened; 0 while it is closed
  const [pairOpened, setPairOpened] = useState(0)
  const [signIn, setSignIn] = useState(false)
  const [reloads, setReloads] = useState(0)
  // the footer goes while the API is out of reach and comes back with the code closed: so is
  // the count, or a closed code would go on drawing pairings
  if (status.kind !== 'ok' && pairOpened !== 0) setPairOpened(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.readiness(), api.version()])
      .then(([ready, version]) => {
        if (cancelled) return
        setStatus({ kind: 'ok', ready, version })
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

  // The door is asked about on its own, so a slow or failed /readyz or /api/version never
  // takes it out of the header. A failed check is tried again (1 s, 2 s, 4 s ... 30 s), and the
  // tab asks again whenever it comes back into view. Each check and each thing the person does
  // takes a number: an answer to an older question than what the tab now knows is dropped.
  const accessSeq = useRef(0)
  const accessRetry = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const checkAccess = useRef<() => void>(() => undefined)
  useEffect(() => {
    let failures = 0
    const check = () => {
      const seq = ++accessSeq.current
      clearTimeout(accessRetry.current)
      api.access
        .status()
        .then((answer) => {
          if (seq !== accessSeq.current) return
          failures = 0
          setAccess({ gated: answer.gated, granted: answer.granted })
        })
        .catch(() => {
          if (seq !== accessSeq.current) return
          failures += 1
          accessRetry.current = setTimeout(check, retryDelayMs(failures))
        })
    }
    checkAccess.current = check
    check()
    const visible = () => {
      if (document.visibilityState === 'visible') check()
    }
    window.addEventListener('focus', check)
    document.addEventListener('visibilitychange', visible)
    return () => {
      accessSeq.current += 1
      clearTimeout(accessRetry.current)
      window.removeEventListener('focus', check)
      document.removeEventListener('visibilitychange', visible)
    }
  }, [])

  // what the tab knows from what the person just did: shown at once, ahead of any answer
  // still on its way
  function knowAccess(next: AccessState) {
    accessSeq.current += 1
    clearTimeout(accessRetry.current)
    setAccess(next)
  }

  // a session that ended mid-visit: a 401, or a write refused as the demo visitor, brings
  // the way in back to the header; the pages stay, as they do for any visitor
  useEffect(() => {
    const lost = () => {
      accessSeq.current += 1
      clearTimeout(accessRetry.current)
      setAccess(SIGNED_OUT)
    }
    window.addEventListener(ACCESS_REQUIRED_EVENT, lost)
    return () => window.removeEventListener(ACCESS_REQUIRED_EVENT, lost)
  }, [])

  // the header's one door: Sign in with the code, Sign out, or the open server's note
  const door = doorOf(access)
  // the demo door: gated, and no session; the code opens the rest
  const demo = isDemo(access)
  // the dialog belongs to the way in: once the door turns (a check, a sign-in) it closes
  if (signIn && door !== 'sign-in') setSignIn(false)

  // opening the way in also asks again: a session opened in another tab shows up here
  function openSignIn() {
    setSignIn(true)
    checkAccess.current()
  }

  // the way out: the server clears the cookie, the tab drops its token, and the header turns
  // at once; the page loads again as whatever the browser is now
  async function signOut() {
    let answer: Access | undefined
    try {
      answer = await api.access.leave()
    } catch {
      // the token is gone either way; the server is asked where the browser stands
    }
    knowAccess(answer ? { gated: answer.gated, granted: answer.granted } : SIGNED_OUT)
    if (!answer) checkAccess.current()
    setReloads((n) => n + 1)
    setSaved((n) => n + 1)
  }

  return (
    <main className="shell">
      <header className="top">
        <div className="brand">
          <img src="/brand.svg" alt="" width="48" height="48" />
          <div>
            <h1>Orphan Parts Lens</h1>
            <p className="tagline">Show it, ask it, sell it, or find the one that fits.</p>
          </div>
        </div>
        {/* the door sits beside the pages, not among them: on a phone the pages scroll sideways
            and the door would scroll off with them */}
        <div className="header-end">
          <nav className="nav" aria-label="Pages">
            {VIEWS.map((v) => (
              <button key={v.id} type="button" aria-current={view === v.id ? 'page' : undefined} onClick={() => setView(v.id)}>
                {v.label}
              </button>
            ))}
          </nav>
          {door === 'sign-in' && (
            <button type="button" className="link door" onClick={openSignIn}>
              Sign in with the code
            </button>
          )}
          {door === 'sign-out' && (
            <button type="button" className="link door" onClick={() => void signOut()}>
              Sign out
            </button>
          )}
          {door === 'open' && <span className="door door-note">Open server (no code needed)</span>}
        </div>
      </header>

      {signIn && door === 'sign-in' && (
        <Modal title="Access code" onClose={() => setSignIn(false)}>
          <AccessGate
            onGranted={(opened) => {
              setSignIn(false)
              knowAccess(opened.gated ? SIGNED_IN : { gated: false, granted: true })
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
            demo={demo}
            liveModels={status.kind === 'ok' && status.ready.demo.live_models}
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

      {view === 'profile' && (
        <section className="card">
          <h2>Profile</h2>
          <Profile />
        </section>
      )}

      <footer className="service" role="contentinfo" aria-label="Service">
        {status.kind === 'loading' && <span>Connecting to the server…</span>}
        {status.kind === 'error' && (
          <span className="error">
            Cannot reach the server: {status.message}. Start it with <code>./dev up</code>.
          </span>
        )}
        {status.kind === 'ok' && (
          <>
            <span>Orphan Parts Lens {status.version.version}</span>
            <span>
              {status.ready.model_api === 'fixture'
                ? 'recorded answers only (nothing spent)'
                : `${status.ready.model_api} mode, spent $${status.ready.spend_usd.toFixed(2)} of $${status.ready.spend_cap_usd.toFixed(2)}`}
              {status.ready.paused ? ' (paused: spend cap reached)' : ''}
            </span>
            <span>{Object.values(status.version.models).join(', ')}</span>
            <span>{status.ready.data_dir_writable ? 'storage writable' : 'storage read-only'}</span>
            {demoText(status.ready, !demo) && <span>{demoText(status.ready, !demo)}</span>}
            <details className="pair" onToggle={(e) => setPairOpened(e.currentTarget.open ? (n) => n + 1 : 0)}>
              <summary>Pair the phone</summary>
              <p>
                In the app, on the Backend tab, tap <strong>Scan to pair</strong> and point it at this code.{' '}
                {pairingText(status.ready.demo.gated, !demo)}
              </p>
              {reachableFromAPhone(pairOrigin) ? (
                <>
                  {/* drawn only while open, anew on each opening, once the door is known and again when
                      it changes: a pairing is in it once signed in, and a pairing is a live session */}
                  {pairOpened > 0 && access !== null && (
                    <PairImage key={`${demo ? 'demo' : 'in'}-${pairOpened}`} door={demo ? 'demo' : 'in'} />
                  )}
                  <p className="muted">
                    Or type <code>{pairOrigin}</code> into the app.
                  </p>
                </>
              ) : (
                <p className="muted">
                  This code would contain <code>{pairOrigin}</code>, which the phone cannot reach (on the phone, localhost
                  means the phone itself). Open the web app at the computer's network address and pair from there, or run{' '}
                  <code>./dev phone</code>, which prints a code with that address.
                </p>
              )}
            </details>
          </>
        )}
      </footer>
    </main>
  )
}

// The code's door. A session is a cookie the browser keeps; nothing is stored here.
function AccessGate({ onGranted }: { onGranted: (access: Access) => void }) {
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
        onGranted(access)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="gate">
      <h3>Sign in with the access code</h3>
      <p className="muted">
        Without a code you are in the demo: look around and try recorded answers; nothing is saved. The access code unlocks
        saving, listing drafts, prices, projects, captures and, when the server has a key, the live models. Signing in sets one
        cookie and stores nothing else about you.
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
        <p className="muted gate-note">For now, signing in uses an access code only. Proper accounts come later.</p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  )
}


// The pairing code as an image, fetched with the session (across origins an <img> carries no
// bearer header) and shown as a data URL; without a session the backend draws the address
// alone. While it is shown it is drawn again before the pairing in it ends.
function PairImage({ door }: { door: string }) {
  const [src, setSrc] = useState('')
  const [round, setRound] = useState(0)
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    api.pair
      .svg(window.location.origin, door)
      .then(({ svg, expiresAt, expiresIn }) => {
        if (cancelled) return
        setSrc(`data:image/svg+xml;utf8,${encodeURIComponent(svg)}`)
        timer = setTimeout(() => setRound((n) => n + 1), redrawAfterMs(expiresAt, Date.now(), expiresIn))
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [door, round])
  if (!src) return null // on its way
  return <img src={src} alt="Pairing code for the phone" width="220" height="220" />
}
