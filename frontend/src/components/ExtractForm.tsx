import { useState, type ChangeEvent, type FormEvent } from 'react'
import { api, type Extraction } from '../lib/api'
import EvidenceTable from './EvidenceTable'

export const MAX_PHOTOS = 4

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'done'; result: Extraction }
  | { kind: 'error'; message: string }

export default function ExtractForm() {
  const [files, setFiles] = useState<File[]>([])
  const [state, setState] = useState<State>({ kind: 'idle' })

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(event.target.files ?? []).slice(0, MAX_PHOTOS)
    setFiles(picked)
    setState({ kind: 'idle' })
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (files.length === 0) return
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
          {files.map((f) => (
            <li key={f.name}>{f.name}</li>
          ))}
        </ul>
      )}
      <p className="hint">Up to {MAX_PHOTOS} photos. Sharp, straight on, the whole label in frame.</p>
      <button type="submit" disabled={files.length === 0 || state.kind === 'loading'}>
        {state.kind === 'loading' ? 'Reading…' : 'Read the label'}
      </button>

      {state.kind === 'error' && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {state.kind === 'done' && <EvidenceTable result={state.result} />}
    </form>
  )
}
