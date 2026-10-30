import { useState, type ChangeEvent, type FormEvent } from 'react'
import { api, type Limits } from '../lib/api'
import { clipProblem, oversized, takePhotos } from '../lib/photos'

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// A capture from this computer instead of the phone: photos, one short video, a name and a
// line, sent as one bundle to the same inbox the phone fills. The backend reads it on request.
export default function SendCapture({ limits, demo, onSent }: { limits: Limits; demo: boolean; onSent: () => void }) {
  const [photos, setPhotos] = useState<File[]>([])
  const [clip, setClip] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [note, setNote] = useState('')
  const [problem, setProblem] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState('')

  function onPhotos(e: ChangeEvent<HTMLInputElement>) {
    const { kept, dropped } = takePhotos(Array.from(e.target.files ?? []), limits.max_photos)
    setPhotos(kept)
    setProblem(dropped > 0 ? `Only the first ${limits.max_photos} photos are taken; ${dropped} left out.` : (oversized(kept, limits.max_upload_mb) ?? ''))
  }

  function onClip(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null
    setClip(file)
    setProblem(file ? (clipProblem(file, limits.max_clip_mb) ?? '') : '')
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy || demo) return
    if (photos.length === 0 && !clip && !note.trim()) {
      setProblem('A photo, a video or a line: at least one of them.')
      return
    }
    setBusy(true)
    setProblem('')
    setSent('')
    try {
      const made = await api.captures.send(photos, clip, { name: name.trim(), note: note.trim() })
      setSent(`Sent as capture #${made.id}. Read it below when you are ready.`)
      setPhotos([])
      setClip(null)
      setName('')
      setNote('')
      ;(e.target as HTMLFormElement).reset()
      onSent()
    } catch (err: unknown) {
      setProblem(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="send-capture" onSubmit={(e) => void onSubmit(e)} aria-label="Send a capture">
      <details>
        <summary>Send a capture from this computer</summary>
        <p className="muted">
          The same bundle the phone sends: up to {limits.max_photos} photos of the item and its label, one short video (MP4 or
          3GP, at most {limits.max_clip_mb} MB), a name and a line. It waits here until you read it.
        </p>
        {demo && <p className="muted">The code unlocks sending; the demo visitor can only look.</p>}
        <label className="field">
          <span>Photos</span>
          <input type="file" accept="image/*" multiple onChange={onPhotos} disabled={demo || busy} />
        </label>
        <label className="field">
          <span>A short video (optional)</span>
          <input type="file" accept="video/mp4,video/3gpp,.mp4,.3gp" onChange={onClip} disabled={demo || busy} />
        </label>
        <label className="field">
          <span>Name (optional)</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="the thing, in two words" disabled={demo || busy} />
        </label>
        <label className="field">
          <span>What you know (optional)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="where it came from, what works, what does not" disabled={demo || busy} />
        </label>
        <div className="row">
          <button type="submit" disabled={demo || busy}>
            {busy ? 'Sending…' : 'Send'}
          </button>
          {sent && <span className="meta">{sent}</span>}
        </div>
        {problem && (
          <p className="error" role="alert">
            {problem}
          </p>
        )}
      </details>
    </form>
  )
}
