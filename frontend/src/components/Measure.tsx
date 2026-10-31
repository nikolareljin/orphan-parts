import { useEffect, useRef, useState, type ChangeEvent, type MouseEvent } from 'react'
import { api, type Item, type Measurement, type MeasureResult, type Point, type ProfileFeature } from '../lib/api'
import { whenText } from '../lib/inventory'
import {
  buildRequest,
  defaultFeatureKey,
  fitScale,
  formatMm,
  markLabel,
  marksNeeded,
  methodLabel,
  nextInstruction,
  toPhoto,
  type ReferenceKind,
  type ReferenceSpec,
} from '../lib/measure'

const CANVAS_MAX_WIDTH = 640
const COLOURS = { reference: '#2d6cdf', feature: '#eb5757' }

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// A dimension from a photo: mark the reference and the feature, the geometry does the rest.
export default function Measure({ item, onMeasured }: { item: Item; onMeasured: () => void }) {
  const [features, setFeatures] = useState<ProfileFeature[]>([])
  const [featureKey, setFeatureKey] = useState('')
  const [customKey, setCustomKey] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  const [marks, setMarks] = useState<Point[]>([])
  const [spec, setSpec] = useState<ReferenceSpec>({
    kind: 'two_point',
    length_mm: 100,
    width_mm: 85.6,
    height_mm: 53.98,
    tolerance_mm: 0.5,
  })
  const [straightOn, setStraightOn] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<MeasureResult | null>(null)
  const [history, setHistory] = useState<Measurement[] | null>(null)
  const [error, setError] = useState('')
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    let cancelled = false
    if (!item.profile) {
      setFeatures([])
      setFeatureKey('__other')
      return
    }
    api.profiles
      .features(item.profile)
      .then((list) => {
        if (cancelled) return
        setFeatures(list)
        setFeatureKey(defaultFeatureKey(list))
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err))
      })
    return () => {
      cancelled = true
    }
  }, [item.profile])

  useEffect(() => {
    let cancelled = false
    api.items
      .measurements(item.id)
      .then((list) => {
        if (!cancelled) setHistory(list)
      })
      .catch(() => {
        if (!cancelled) setHistory([])
      })
    return () => {
      cancelled = true
    }
  }, [item.id, item.version])

  const scale = image ? fitScale(image.naturalWidth, CANVAS_MAX_WIDTH) : 1

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !image) return
    canvas.width = Math.round(image.naturalWidth * scale)
    canvas.height = Math.round(image.naturalHeight * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
    const refCount = spec.kind === 'two_point' ? 2 : 4
    ctx.lineWidth = 2
    ctx.font = '13px system-ui, sans-serif'
    marks.forEach((m, i) => {
      const colour = i < refCount ? COLOURS.reference : COLOURS.feature
      const x = m.x * scale
      const y = m.y * scale
      ctx.strokeStyle = colour
      ctx.beginPath()
      ctx.moveTo(x - 8, y)
      ctx.lineTo(x + 8, y)
      ctx.moveTo(x, y - 8)
      ctx.lineTo(x, y + 8)
      ctx.stroke()
      ctx.fillStyle = colour
      ctx.fillText(markLabel(i, spec.kind), x + 6, y - 6)
    })
    const line = (a: Point, b: Point, colour: string) => {
      ctx.strokeStyle = colour
      ctx.beginPath()
      ctx.moveTo(a.x * scale, a.y * scale)
      ctx.lineTo(b.x * scale, b.y * scale)
      ctx.stroke()
    }
    if (spec.kind === 'two_point' && marks.length >= 2) line(marks[0], marks[1], COLOURS.reference)
    if (spec.kind === 'rectangle' && marks.length >= 4) {
      for (let i = 0; i < 4; i++) line(marks[i], marks[(i + 1) % 4], COLOURS.reference)
    }
    if (marks.length >= refCount + 2) line(marks[refCount], marks[refCount + 1], COLOURS.feature)
  }, [image, marks, scale, spec.kind])

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    setPhoto(file)
    setMarks([])
    setResult(null)
    setError('')
    if (!file) {
      setImage(null)
      return
    }
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      setImage(img)
      URL.revokeObjectURL(url)
    }
    img.src = url
  }

  function onCanvasClick(event: MouseEvent<HTMLCanvasElement>) {
    if (!image || marks.length >= marksNeeded(spec.kind)) return
    const rect = event.currentTarget.getBoundingClientRect()
    const p = toPhoto({ x: event.clientX - rect.left, y: event.clientY - rect.top }, scale)
    setMarks([...marks, { x: Math.round(p.x * 10) / 10, y: Math.round(p.y * 10) / 10 }])
    setResult(null)
  }

  function changeKind(kind: ReferenceKind) {
    setSpec({ ...spec, kind, tolerance_mm: kind === 'two_point' ? 0.5 : 0.2 })
    setMarks([])
    setResult(null)
  }

  const feature = featureKey === '__other' ? customKey.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_') : featureKey
  const chosen = features.find((f) => f.key === featureKey)
  const request =
    image && feature
      ? buildRequest(
          marks,
          spec,
          feature,
          item.profile || null,
          { width: image.naturalWidth, height: image.naturalHeight },
          straightOn,
        )
      : null

  async function measure() {
    if (!photo || !request) return
    setBusy(true)
    setError('')
    try {
      const stored = await api.items.measure(item.id, photo, request)
      setResult(stored)
      onMeasured()
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="measure" aria-label="Measure a feature">
      <h4>Measure a feature</h4>
      {!item.profile && (
        <p className="muted">Set a profile under Facts to list what can be measured, or name the feature yourself.</p>
      )}
      <div className="row">
        <label>
          <span>Feature</span>
          <select value={featureKey} onChange={(e) => setFeatureKey(e.target.value)}>
            {features.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label} (±{f.tolerance_mm} mm)
              </option>
            ))}
            <option value="__other">Other…</option>
          </select>
        </label>
        {featureKey === '__other' && (
          <label>
            <span>Feature name</span>
            <input value={customKey} onChange={(e) => setCustomKey(e.target.value)} placeholder="spout_diameter" />
          </label>
        )}
        <label>
          <span>Photo with a ruler or card in it</span>
          <input type="file" accept="image/*" onChange={onPick} />
        </label>
      </div>
      {chosen && <p className="hint">{chosen.how}</p>}

      <div className="row">
        <fieldset className="kind">
          <legend>Size reference in the photo</legend>
          <label>
            <input type="radio" name="kind" checked={spec.kind === 'two_point'} onChange={() => changeKind('two_point')} />
            <span>Two points on a ruler</span>
          </label>
          <label>
            <input type="radio" name="kind" checked={spec.kind === 'rectangle'} onChange={() => changeKind('rectangle')} />
            <span>Four corners of a card or other known rectangle</span>
          </label>
        </fieldset>
        {spec.kind === 'two_point' ? (
          <label>
            <span>Known length (mm)</span>
            <input
              type="number"
              min={1}
              step={0.1}
              value={spec.length_mm}
              onChange={(e) => setSpec({ ...spec, length_mm: Number(e.target.value) })}
            />
          </label>
        ) : (
          <>
            <label>
              <span>Width (mm)</span>
              <input
                type="number"
                min={1}
                step={0.01}
                value={spec.width_mm}
                onChange={(e) => setSpec({ ...spec, width_mm: Number(e.target.value) })}
              />
            </label>
            <label>
              <span>Height (mm)</span>
              <input
                type="number"
                min={1}
                step={0.01}
                value={spec.height_mm}
                onChange={(e) => setSpec({ ...spec, height_mm: Number(e.target.value) })}
              />
            </label>
          </>
        )}
        <label>
          <span>Reference accuracy (± mm)</span>
          <input
            type="number"
            min={0}
            step={0.1}
            value={spec.tolerance_mm}
            onChange={(e) => setSpec({ ...spec, tolerance_mm: Number(e.target.value) })}
          />
        </label>
      </div>
      {spec.kind === 'two_point' && (
        <label className="check">
          <input type="checkbox" checked={straightOn} onChange={(e) => setStraightOn(e.target.checked)} />
          <span>Taken straight on, with the ruler in the same plane as what is measured (touching it)</span>
        </label>
      )}

      {image && (
        <div className="marking">
          <p className="hint" aria-live="polite">
            {nextInstruction(marks.length, spec.kind)}
            {marks.length > 0 && (
              <>
                {' '}
                <button type="button" className="link" onClick={() => setMarks([])}>
                  Clear marks
                </button>
              </>
            )}
          </p>
          <canvas
            ref={canvasRef}
            role="img"
            aria-label="Photo to mark"
            onClick={onCanvasClick}
            style={{ cursor: marks.length < marksNeeded(spec.kind) ? 'crosshair' : 'default' }}
          />
        </div>
      )}

      <div className="row">
        <button type="button" disabled={!request || busy} onClick={() => void measure()}>
          {busy ? 'Measuring…' : 'Measure'}
        </button>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && <ResultCard result={result} />}

      {history && history.length > 0 && (
        <details className="history">
          <summary>Past measurements ({history.length})</summary>
          <table className="evidence" aria-label="Past measurements">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Feature</th>
                <th scope="col">Result</th>
                <th scope="col">Method</th>
              </tr>
            </thead>
            <tbody>
              {history.map((m) => (
                <tr key={m.id}>
                  <td>{whenText(m.at)}</td>
                  <td>{m.feature}</td>
                  <td>{m.accepted ? formatMm(m) : `refused: ${m.redo}`}</td>
                  <td>{methodLabel(m.method)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </section>
  )
}

function ResultCard({ result }: { result: MeasureResult }) {
  return (
    <div className={result.accepted ? 'measured' : 'measured refused'} role="status">
      {result.accepted ? (
        <>
          <p className="value">
            {formatMm(result)} <span className="muted">({methodLabel(result.method)})</span>
          </p>
          <p className="meta">
            Added to the item as a value to confirm; accept it under Fields above. Basis: {result.basis}.
          </p>
          {result.needs_direct_reading && (
            <p className="meta">
              The profile needs ±{result.tolerance_mm} mm, but this photo gives ±{result.uncertainty_mm?.toFixed(2)} mm: measure it with a
              caliper or ruler and enter it under &quot;Add what you know&quot; (known from: tested).
            </p>
          )}
        </>
      ) : (
        <p className="value">Could not measure: {result.redo}</p>
      )}
      <ul className="checks">
        {result.checks.map((c) => (
          <li key={c.name} className={c.passed ? 'pass' : 'fail'}>
            <strong>{c.passed ? 'pass' : c.blocking ? 'fail' : 'note'}</strong> {c.name}: {c.detail}
          </li>
        ))}
      </ul>
    </div>
  )
}
