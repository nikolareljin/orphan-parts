import { useState, type ChangeEvent, type FormEvent } from 'react'
import { api, dataUrlToFile, type Extraction, type Limits, type Segmentation } from '../lib/api'
import { DEFAULT_LIMITS, oversized, takePhotos } from '../lib/photos'
import EvidenceTable from './EvidenceTable'
import SegmentView from './SegmentView'

type State =
  | { kind: 'idle' }
  | { kind: 'segmenting' }
  | { kind: 'reading'; segmentation?: Segmentation }
  | { kind: 'done'; segmentation?: Segmentation; result: Extraction }
  | { kind: 'error'; segmentation?: Segmentation; message: string }

export default function ExtractForm({ limits = DEFAULT_LIMITS }: { limits?: Limits }) {
  const [files, setFiles] = useState<File[]>([])
  const [dropped, setDropped] = useState(0)
  const [findFirst, setFindFirst] = useState(true)
  const [state, setState] = useState<State>({ kind: 'idle' })

  const busy = state.kind === 'segmenting' || state.kind === 'reading'
  const segmentation = 'segmentation' in state ? state.segmentation : undefined

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    const picked = takePhotos(Array.from(event.target.files ?? []), limits.max_photos)
    setFiles(picked.kept)
    setDropped(picked.dropped)
    setState({ kind: 'idle' })
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (files.length === 0 || busy) return
    const refused = oversized(files, limits.max_upload_mb)
    if (refused) {
      setState({ kind: 'error', message: refused })
      return
    }
    let segmentation: Segmentation | undefined
    try {
      if (findFirst) {
        setState({ kind: 'segmenting' })
        segmentation = await api.segment(files[0])
      }
      setState({ kind: 'reading', segmentation })
      const crops = (segmentation?.regions ?? [])
        .filter((r) => r.concept === 'label')
        .map((r, i) => dataUrlToFile(r.crop, `label-${i + 1}.jpg`))
      setState({ kind: 'done', segmentation, result: await api.extract(files, crops) })
    } catch (err: unknown) {
      setState({ kind: 'error', segmentation, message: err instanceof Error ? err.message : String(err) })
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
      <label className="check">
        <input type="checkbox" checked={findFirst} onChange={(e) => setFindFirst(e.target.checked)} />
        <span>Find the label first with SAM 3.1, then read the crop</span>
      </label>
      <button type="submit" disabled={files.length === 0 || busy}>
        {state.kind === 'segmenting' ? 'Finding…' : state.kind === 'reading' ? 'Reading…' : 'Read the label'}
      </button>

      {state.kind === 'error' && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {/* the live region stays mounted, so results landing in it are announced */}
      <div aria-live="polite">
        {segmentation && <SegmentView result={segmentation} />}
        {state.kind === 'done' && <EvidenceTable result={state.result} />}
      </div>
    </form>
  )
}
