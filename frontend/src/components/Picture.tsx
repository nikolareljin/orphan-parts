import { useEffect, useState, type FormEvent } from 'react'
import { api, type Item, type Picture as Drawn } from '../lib/api'
import { pictureCaption } from '../lib/picture'
import GatedImage from './GatedImage'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// What the item could look like: a picture drawn by Muse Image only when the button is clicked
// (every click is a paid call), the last section of the dialog, labeled as drawn, never as a
// photo of the item. The server says whether it draws at all (PICTURE_ENABLED); while it does
// not, the section says so in one line and shows no controls. The demo visitor sees the
// pictures already drawn and no button; a list that cannot be read hides the section.
export default function Picture({ item, demo = false }: { item: Item; demo?: boolean }) {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [failed, setFailed] = useState(false)
  const [pictures, setPictures] = useState<Drawn[]>([])
  const [use, setUse] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api.items
      .pictures(item.id)
      .then((list) => {
        if (cancelled) return
        setFailed(false)
        setEnabled(list.enabled)
        setPictures(list.pictures)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [item.id])

  async function draw(event: FormEvent) {
    event.preventDefault()
    if (busy || !enabled || demo) return
    setBusy(true)
    setError('')
    try {
      const drawn = await api.items.drawPicture(item.id, use.trim())
      // in drawing order, as the list comes back
      setPictures((kept) => [...kept.filter((p) => p.n !== drawn.n), drawn])
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  const off = enabled === false
  if (failed || (demo && pictures.length === 0)) return null
  return (
    <section className="picture" aria-label="What it could look like">
      <h4>What it could look like</h4>
      {!demo && !off && (
        <>
          <form className="inline" onSubmit={(e) => void draw(e)}>
            <label>
              <span>Draw it as</span>
              <input value={use} onChange={(e) => setUse(e.target.value)} placeholder="a kitchen recipe display" maxLength={200} />
            </label>
            <button type="submit" disabled={busy || enabled === null}>
              {busy ? 'Drawing…' : 'Draw it'}
            </button>
          </form>
          <p className="hint">
            Draws what the item could become, or the item itself if left blank. Marked as drawn; never counted as evidence.
          </p>
        </>
      )}
      {off && !demo && <p className="muted">Drawing pictures is turned off on this server.</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {pictures.map((p) => (
        <figure key={p.n}>
          <GatedImage src={api.items.pictureUrl(item.id, p.n)} alt={`Illustrative picture ${p.n}: ${p.use}`} loading="lazy" />
          <figcaption>{pictureCaption(p)}</figcaption>
        </figure>
      ))}
    </section>
  )
}
