import { useState, type ChangeEvent, type FormEvent } from 'react'
import { api, type Extraction, type Limits } from '../lib/api'
import { DEFAULT_LIMITS, oversized, takePhotos } from '../lib/photos'
import EvidenceTable from './EvidenceTable'

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'done'; result: Extraction }
  | { kind: 'error'; message: string }

export default function ExtractForm({ limits = DEFAULT_LIMITS }: { limits?: Limits }) {
  const [files, setFiles] = useState<File[]>([])
  const [dropped, setDropped] = useState(0)
  const [state, setState] = useState<State>({ kind: 'idle' })

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    const picked = takePhotos(Array.from(event.target.files ?? []), limits.max_photos)
    setFiles(picked.kept)
    setDropped(picked.dropped)
    setState({ kind: 'idle' })
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (files.length === 0 || state.kind === 'loading') return
    const refused = oversized(files, limits.max_upload_mb)
    if (refused) {
      setState({ kind: 'error', message: refused })
      return
    }
    setState({ kind: 'loading' })
    try {
      setState({ kind: 'done', result: await api.extract(files) })
    } catch (err: unknown) {
      setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
    }
  }

  return (
    <form className="extract" onSubmit={onSubmit}>
      <label className="field">
        <span>Photos of the label</span>
        <input type="file" accept="image/*" multiple onChange={onPick} />
      </label>
      {files.length > 0 && (
        <ul className="files">
          {files.map((f, i) => (
            <li key={`${i}-${f.name}`}>{f.name}</li>
          ))}
        </ul>
      )}
      <p className="hint">
        Up to {limits.max_photos} photos, {limits.max_upload_mb} MB each. Sharp, straight on, the whole label in
        frame.
        {dropped > 0 && ` Only the first ${limits.max_photos} are used.`}
      </p>
      <button type="submit" disabled={files.length === 0 || state.kind === 'loading'}>
        {state.kind === 'loading' ? 'Reading…' : 'Read the label'}
      </button>

      {state.kind === 'error' && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {/* the live region stays mounted, so a result landing in it is announced */}
      <div aria-live="polite">{state.kind === 'done' && <EvidenceTable result={state.result} />}</div>
    </form>
  )
}
