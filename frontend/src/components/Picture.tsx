import { useEffect, useState, type FormEvent } from 'react'
import { api, type Item, type Picture as Drawn } from '../lib/api'
import { pictureCaption } from '../lib/picture'
import GatedImage from './GatedImage'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// What the item could look like: a picture drawn by Muse Image only when the button is clicked
// (every click is a paid call), shown under the photos and labeled as drawn, never as a
// photo of the item. The server says whether it draws at all (PICTURE_ENABLED).
export default function Picture({ item }: { item: Item }) {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [pictures, setPictures] = useState<Drawn[]>([])
  const [use, setUse] = useState(item.item_type)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api.items
      .pictures(item.id)
      .then((list) => {
        if (cancelled) return
        setEnabled(list.enabled)
        setPictures(list.pictures)
      })
      .catch(() => {
        if (!cancelled) setEnabled(null) // not known: the button waits
      })
    return () => {
      cancelled = true
    }
  }, [item.id])

  async function draw(event: FormEvent) {
    event.preventDefault()
    if (busy || !enabled) return
    setBusy(true)
    setError('')
    try {
      const drawn = await api.items.drawPicture(item.id, use.trim())
      setPictures((kept) => [drawn, ...kept.filter((p) => p.n !== drawn.n)])
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  const off = enabled === false
  return (
    <section className="picture" aria-label="What it could look like">
      <h4>What it could look like</h4>
      <form className="inline" onSubmit={(e) => void draw(e)}>
        <label>
          <span>as a…</span>
          <input value={use} onChange={(e) => setUse(e.target.value)} placeholder={item.item_type} maxLength={200} disabled={off} />
        </label>
        <button type="submit" disabled={off || busy || enabled === null}>
          {busy ? 'Drawing…' : 'Draw it'}
        </button>
      </form>
      {off && <p className="muted">pictures are off on this server (PICTURE_ENABLED)</p>}
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
