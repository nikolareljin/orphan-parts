import { useCallback, useEffect, useState } from 'react'
import { api, type Capture } from '../lib/api'
import { captureSummary, captureTone, statusLabel } from '../lib/captures'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// The clip as sent. A browser that cannot decode it (a codec it lacks) says so and offers
// the file instead of a blank player.
function Clip({ id }: { id: number }) {
  const [unplayable, setUnplayable] = useState(false)
  const url = api.captures.clipUrl(id)
  if (unplayable) {
    return (
      <p className="muted">
        This browser cannot play the clip of capture #{id} (a codec it lacks).{' '}
        <a href={url} download={`capture-${id}.mp4`}>
          Download it
        </a>
        .
      </p>
    )
  }
  return <video controls preload="metadata" src={url} aria-label={`Capture ${id} clip`} onError={() => setUnplayable(true)} />
}

// What the phone sent: photos, a clip, a spoken note, a line. Read into an item on request.
export default function Inbox({ onOpenItem }: { onOpenItem: (id: number) => void }) {
  const [captures, setCaptures] = useState<Capture[] | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setCaptures((await api.captures.list()).captures)
      setError('')
    } catch (err: unknown) {
      setError(message(err))
    }
  }, [])

  // loaded on arrival and every 15 s while the page is open: a capture sent from the phone
  // shows up without a click; Refresh is there for the impatient
  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), 15_000)
    return () => window.clearInterval(timer)
  }, [load])

  async function act(id: number, call: () => Promise<unknown>) {
    if (busyId !== null) return
    setBusyId(id)
    setError('')
    try {
      await call()
      await load()
    } catch (err: unknown) {
      setError(message(err))
      await load()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="inbox">
      <p className="muted">
        Captures arrive from the phone app: photos, a short clip, a spoken note and a line. <strong>Read it</strong> turns one into an item in your
        inventory, with every value marked as observed and the note kept as your words. Nothing here leaves this backend until you read it.{' '}
        <button type="button" className="link" onClick={() => void load()}>
          Refresh
        </button>
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {captures === null && !error && <p className="muted">Loading…</p>}
      {captures !== null && captures.length === 0 && <p className="muted">Nothing captured yet. Send one from the phone.</p>}
      {captures !== null && captures.length > 0 && (
        <ul className="captures" aria-label="Captures">
          {captures.map((c) => (
            <li key={c.id} className="capture">
              <div className="thumbs">
                {Array.from({ length: c.photos }, (_, i) => (
                  <img key={i} src={api.captures.photoUrl(c.id, i + 1)} alt={`Capture ${c.id}, photo ${i + 1}`} loading="lazy" />
                ))}
                {c.photos === 0 && <span className="no-photo muted">no photo</span>}
              </div>
              <div className="body">
                <div className="row">
                  <strong>Capture #{c.id}</strong>
                  <span className={`badge state ${captureTone(c.status)}`}>{statusLabel(c.status)}</span>
                  <span className="muted">{c.created_at.slice(0, 16).replace('T', ' ')}</span>
                </div>
                <p className="meta">{captureSummary(c)}</p>
                {c.note && <p>“{c.note}”</p>}
                {c.clip && <Clip id={c.id} />}
                {c.audio && <audio controls preload="metadata" src={api.captures.noteUrl(c.id)} aria-label={`Capture ${c.id} note`} />}
                {c.error && (
                  <p className={c.status === 'failed' ? 'error' : 'muted'} role={c.status === 'failed' ? 'alert' : undefined}>
                    {c.error}
                  </p>
                )}
                <div className="row actions">
                  {c.status !== 'processed' && (
                    <button type="button" disabled={busyId !== null} onClick={() => void act(c.id, () => api.captures.process(c.id))}>
                      {busyId === c.id ? 'Reading…' : c.status === 'failed' ? 'Try again' : 'Read it'}
                    </button>
                  )}
                  {c.status === 'processed' && c.item_id !== null && (
                    <button type="button" onClick={() => onOpenItem(c.item_id as number)}>
                      Open item #{c.item_id}
                    </button>
                  )}
                  <button type="button" className="link" disabled={busyId !== null} onClick={() => void act(c.id, () => api.captures.remove(c.id))}>
                    Delete
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
