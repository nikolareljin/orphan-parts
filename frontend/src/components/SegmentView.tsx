import type { Segmentation } from '../lib/api'
import { percent, usd } from '../lib/format'
import SampleNotice from './SampleNotice'

export default function SegmentView({ result, demo = false }: { result: Segmentation; demo?: boolean }) {
  return (
    <section className="segments">
      <SampleNotice fromFixture={result.from_fixture} demo={demo} />
      <p className="meta">
        {result.model} · {result.regions.length} {result.regions.length === 1 ? 'region' : 'regions'} ·{' '}
        {usd(result.cost_usd)}
        {result.from_fixture && <span className="badge">recorded answer</span>}
      </p>

      {result.warnings.length > 0 && (
        <ul className="warnings">
          {result.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      <img className="overlay" src={result.overlay} alt="Photo with the found regions drawn over it" />

      {result.regions.length > 0 && (
        <ul className="regions" aria-label="Regions">
          {result.regions.map((r) => (
            <li key={`${r.concept}-${r.object_id}`} className={`region region-${r.concept}`}>
              <img src={r.crop} alt={`${r.concept} crop`} />
              <div>
                <strong>{r.concept}</strong>
                <span className="muted">
                  {' '}
                  {r.box.right - r.box.left}×{r.box.bottom - r.box.top} px
                  {r.confidence !== null && ` · ${percent(r.confidence)}`}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
