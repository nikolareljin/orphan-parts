import type { Extraction } from '../lib/api'
import { fieldLabel, orderedFields, percent, usd, withUnit } from '../lib/format'

export default function EvidenceTable({ result }: { result: Extraction }) {
  const rows = orderedFields(result.fields)
  return (
    <section className="result">
      <h3>{result.item_type}</h3>
      <p className="meta">
        {result.model} · {result.photos} {result.photos === 1 ? 'photo' : 'photos'} · {usd(result.cost_usd)}
        {result.from_fixture && <span className="badge">recorded answer</span>}
      </p>

      {result.warnings.length > 0 && (
        <ul className="warnings">
          {result.warnings.map((w, i) => (
            <li key={`${i}-${w}`}>{w}</li>
          ))}
        </ul>
      )}

      {rows.length === 0 ? (
        <p className="muted">Nothing readable on these photos.</p>
      ) : (
        <table className="evidence" aria-label="Evidence">
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">Value</th>
              <th scope="col">Confidence</th>
              <th scope="col">Source</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, e]) => (
              <tr key={name}>
                <th scope="row">{fieldLabel(name)}</th>
                <td>
                  {withUnit(e)}
                  {e.raw && e.raw !== e.value && <span className="raw"> as printed: {e.raw}</span>}
                </td>
                <td>
                  <span className="bar" aria-hidden="true">
                    <span style={{ width: percent(e.confidence) }} />
                  </span>
                  {percent(e.confidence)}
                </td>
                <td>{e.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {result.label_text && (
        <details>
          <summary>Label text</summary>
          <pre>{result.label_text}</pre>
        </details>
      )}
    </section>
  )
}
