import { useEffect, useState, type FormEvent } from 'react'
import { api, type SampleCatalog, type SampleResult } from '../lib/api'
import { inCatalogOrder, readingTitle } from '../lib/sample'
import EvidenceTable from './EvidenceTable'
import SampleGallery from './SampleGallery'
import SampleNotice from './SampleNotice'
import SegmentView from './SegmentView'

type State =
  | { kind: 'idle' }
  | { kind: 'reading' }
  | { kind: 'done'; results: SampleResult[] }
  | { kind: 'error'; message: string }

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// The demo visitor's "Read a label": no upload, the demo set's photos to click instead. An
// item's every photo picked is one reading of them all; any other photo is read alone, and the
// readings are shown side by side, each the answer recorded for that very sample.
export default function SampleRead({ liveModels = false }: { liveModels?: boolean }) {
  const [catalog, setCatalog] = useState<SampleCatalog | null>(null)
  const [loadError, setLoadError] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [findFirst, setFindFirst] = useState(true)
  const [state, setState] = useState<State>({ kind: 'idle' })

  useEffect(() => {
    let cancelled = false
    api.samples
      .list()
      .then((c) => {
        if (!cancelled) setCatalog(c)
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(messageOf(err))
      })
    return () => {
      cancelled = true
    }
  }, [])

  const busy = state.kind === 'reading'

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!catalog || selected.length === 0 || busy) return
    setState({ kind: 'reading' })
    try {
      const read = await api.samples.read(inCatalogOrder(catalog, selected), findFirst)
      setState({ kind: 'done', results: read.results })
    } catch (err: unknown) {
      setState({ kind: 'error', message: messageOf(err) })
    }
  }

  if (loadError) {
    return (
      <p className="error" role="alert">
        {loadError}
      </p>
    )
  }
  if (catalog === null) return <p className="muted">Loading the sample photos…</p>
  if (catalog.items.length === 0) {
    return <p className="muted">This server has no sample photos. Sign in with the access code to read your own photos.</p>
  }

  return (
    <form className="extract fields" onSubmit={(e) => void onSubmit(e)} aria-label="Read sample photos">
      <p className="help">
        Pick one or more photos from the demo set. All photos of one item are read together; any other photo is read on its own.
        Sign in with the access code to read your own photos.
      </p>
      <SampleGallery
        catalog={catalog}
        selected={selected}
        onChange={(next) => {
          setSelected(next)
          if (state.kind !== 'reading') setState({ kind: 'idle' })
        }}
      />
      <div className="row">
        <label className="check">
          <input type="checkbox" checked={findFirst} onChange={(e) => setFindFirst(e.target.checked)} />
          <span>Find the label in the photo first (SAM 3.1; helps with busy photos)</span>
        </label>
      </div>
      <div className="row actions">
        <button type="submit" disabled={selected.length === 0 || busy}>
          {busy ? 'Reading…' : 'Read the label'}
        </button>
        <span className="meta">{selected.length === 0 ? 'No photo picked' : `${selected.length} picked`}</span>
        {selected.length > 0 && (
          <button type="button" className="link" onClick={() => setSelected([])}>
            Clear
          </button>
        )}
      </div>

      {state.kind === 'error' && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      <div aria-live="polite">
        {state.kind === 'done' && (
          <div className="sample-results">
            {state.results.map((r) => {
              const title = readingTitle(catalog, r.item_key, r.sample_ids, r.whole_item)
              return (
                <article key={r.sample_ids.join('+')} className="sample-result" aria-label={`Reading: ${title}`}>
                  <h3>{title}</h3>
                  <ul className="thumbs small">
                    {r.sample_ids.map((id) => (
                      <li key={id}>
                        <img src={api.samples.thumbUrl(id)} alt="" />
                      </li>
                    ))}
                  </ul>
                  {r.missing || !r.extraction ? (
                    <p className="hint" role="note">
                      {r.note || 'No recorded answer for this sample yet.'}
                    </p>
                  ) : (
                    <>
                      <SampleNotice fromFixture={r.extraction.from_fixture} demo liveModels={liveModels} />
                      {r.segmentation && <SegmentView result={r.segmentation} />}
                      <EvidenceTable result={r.extraction} />
                    </>
                  )}
                </article>
              )
            })}
          </div>
        )}
      </div>
    </form>
  )
}
