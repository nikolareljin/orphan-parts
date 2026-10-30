import { useState, type ChangeEvent, type FormEvent } from 'react'
import { api, dataUrlToFile, type Extraction, type Item, type Limits, type Segmentation } from '../lib/api'
import { DEFAULT_LIMITS, oversized, takePhotos } from '../lib/photos'
import EvidenceTable from './EvidenceTable'
import SegmentView from './SegmentView'

type State =
  | { kind: 'idle' }
  | { kind: 'segmenting' }
  | { kind: 'reading'; segmentation?: Segmentation; note?: string }
  | { kind: 'done'; segmentation?: Segmentation; note?: string; result: Extraction; saved?: Item; saveError?: string }
  | { kind: 'error'; segmentation?: Segmentation; note?: string; message: string }

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export default function ExtractForm({
  limits = DEFAULT_LIMITS,
  onSaved,
}: {
  limits?: Limits
  onSaved?: (item: Item) => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const [dropped, setDropped] = useState(0)
  const [findFirst, setFindFirst] = useState(true)
  const [name, setName] = useState('')
  const [state, setState] = useState<State>({ kind: 'idle' })

  const busy = state.kind === 'segmenting' || state.kind === 'reading'
  const segmentation = 'segmentation' in state ? state.segmentation : undefined
  const note = 'note' in state ? state.note : undefined

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
    let note: string | undefined
    try {
      if (findFirst) {
        setState({ kind: 'segmenting' })
        try {
          segmentation = await api.segment(files[0])
        } catch (err: unknown) {
          // the photos are still readable whole; say what was skipped and why
          note = `The label could not be found first (${messageOf(err)}), so the photos were read whole.`
        }
      }
      setState({ kind: 'reading', segmentation, note })
      const crops = (segmentation?.regions ?? [])
        .filter((r) => r.concept === 'label')
        .slice(0, limits.max_photos)
        .map((r, i) => dataUrlToFile(r.crop, `label-${i + 1}.jpg`))
      setState({ kind: 'done', segmentation, note, result: await api.extract(files, crops) })
    } catch (err: unknown) {
      setState({ kind: 'error', segmentation, note, message: messageOf(err) })
    }
  }

  // The reading becomes a private record: observed fields, each still to confirm.
  // A failed save keeps the reading on the page: it was paid for, and can be saved again.
  async function save() {
    if (state.kind !== 'done' || state.saved) return
    try {
      const saved = await api.items.create({ extraction: state.result, name: name.trim() })
      // the photos the reading was made from stay with the item, beside the values to confirm;
      // the item is saved either way, and a refused photo is said rather than undoing the save
      let photoNote: string | undefined
      try {
        await api.items.addPhotos(saved.id, files)
      } catch (err: unknown) {
        photoNote = `The item is saved; its photos were not kept: ${messageOf(err)}`
      }
      setState({ ...state, saved, saveError: photoNote })
      onSaved?.(saved)
    } catch (err: unknown) {
      setState({ ...state, saveError: messageOf(err) })
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
        {note && <p className="hint">{note}</p>}
        {segmentation && <SegmentView result={segmentation} />}
        {state.kind === 'done' && (
          <>
            <EvidenceTable result={state.result} />
            <div className="save">
              {state.saved ? (
                <>
                  <p className="meta">
                    Saved privately as item #{state.saved.id}, {state.saved.name}. Nothing is published.
                  </p>
                  {state.saveError && (
                    <p className="error" role="alert">
                      {state.saveError}
                    </p>
                  )}
                </>
              ) : (
                <>
                  <label>
                    <span>Name</span>
                    <input value={name} onChange={(e) => setName(e.target.value)} placeholder={state.result.item_type} />
                  </label>
                  <button type="button" onClick={() => void save()}>
                    Save privately
                  </button>
                  {state.saveError && (
                    <p className="error" role="alert">
                      {state.saveError}
                    </p>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </div>
    </form>
  )
}
