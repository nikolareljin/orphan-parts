import { useId, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { api, dataUrlToFile, type Extraction, type Item, type Limits, type Segmentation } from '../lib/api'
import { asksForParent } from '../lib/inventory'
import { DEFAULT_LIMITS, oversized, takePhotos } from '../lib/photos'
import EvidenceTable from './EvidenceTable'
import ParentPrompt from './ParentPrompt'
import SampleRead from './SampleRead'
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

type FormProps = {
  limits?: Limits
  demo?: boolean
  liveModels?: boolean
  onSaved?: (item: Item) => void
}

// The demo visitor clicks the demo set's photos; signed in (or on a machine of your own),
// photos are uploaded and read live where the server has a key.
export default function ExtractForm(props: FormProps) {
  if (props.demo) return <SampleRead liveModels={props.liveModels} />
  return <UploadForm {...props} />
}

function UploadForm({ limits = DEFAULT_LIMITS, onSaved }: FormProps) {
  const [files, setFiles] = useState<File[]>([])
  const [dropped, setDropped] = useState(0)
  const [findFirst, setFindFirst] = useState(true)
  const [name, setName] = useState('')
  const [state, setState] = useState<State>({ kind: 'idle' })
  const ids = useId()

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
  const saving = useRef(false)
  async function save() {
    if (state.kind !== 'done' || state.saved || saving.current) return
    saving.current = true // one item per click, however long the save and the upload take
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
    } finally {
      saving.current = false
    }
  }

  // the device a saved part came from, answered right here; the item is replaced by the
  // server's answer and a refusal is said with the save's own line
  async function answer(action: () => Promise<Item>) {
    try {
      const saved = await action()
      setState((s) => (s.kind === 'done' ? { ...s, saved, saveError: undefined } : s))
    } catch (err: unknown) {
      setState((s) => (s.kind === 'done' ? { ...s, saveError: messageOf(err) } : s))
      throw err
    }
  }

  return (
    <form className="extract fields" onSubmit={onSubmit}>
      <div className="row">
        <div className="field">
          <label>
            <span>Photos of the label</span>
            <input type="file" accept="image/*" multiple onChange={onPick} aria-describedby={`${ids}-photos`} />
          </label>
          <p className="help" id={`${ids}-photos`}>
            Up to {limits.max_photos} photos, {limits.max_upload_mb} MB each. Sharp, straight on, the whole label in frame.
            {dropped > 0 && ` Only the first ${limits.max_photos} are used.`}
          </p>
        </div>
      </div>
      {files.length > 0 && (
        <ul className="files">
          {files.map((f, i) => (
            <li key={`${i}-${f.name}`}>{f.name}</li>
          ))}
        </ul>
      )}
      <div className="row">
        <label className="check">
          <input type="checkbox" checked={findFirst} onChange={(e) => setFindFirst(e.target.checked)} />
          <span>Find the label in the photo first (SAM 3.1; helps with busy photos)</span>
        </label>
      </div>
      <div className="row actions">
        <button type="submit" disabled={files.length === 0 || busy}>
          {state.kind === 'segmenting' ? 'Finding…' : state.kind === 'reading' ? 'Reading…' : 'Read the label'}
        </button>
      </div>

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
                    Saved to your inventory as item #{state.saved.id}, {state.saved.name}. It is private.
                  </p>
                  {asksForParent(state.saved) && <ParentPrompt item={state.saved} readOnly={false} save={answer} />}
                  {state.saveError && (
                    <p className="error" role="alert">
                      {state.saveError}
                    </p>
                  )}
                </>
              ) : (
                <>
                  <div className="row">
                    <label>
                      <span>Name</span>
                      <input value={name} onChange={(e) => setName(e.target.value)} placeholder={state.result.item_type} />
                    </label>
                  </div>
                  <div className="row actions">
                    <button type="button" onClick={() => void save()}>
                      Save privately
                    </button>
                  </div>
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
