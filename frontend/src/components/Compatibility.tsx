import type { Pairing } from '../lib/api'
import { marketplaceFor, pairingLabel, pairingTone, pairingWho } from '../lib/compat'

// The compatibility rules' answer for each pairing: fits, does not fit or unknown, why, and
// what to do about a failure (an item of yours that fits, or the part to search for).
export default function Compatibility({ pairings, label = 'Compatibility' }: { pairings: Pairing[]; label?: string }) {
  if (pairings.length === 0) return null
  return (
    <ul className="compat" aria-label={label}>
      {pairings.map((p, i) => (
        <li key={`${i}:${p.rule}:${p.part_id ?? ''}:${p.host_id ?? ''}`}>
          <span className={`badge state ${pairingTone(p.state)}`}>{pairingLabel(p.state)}</span> {pairingWho(p)}: {p.reason}
          {p.fix && <span className="muted"> · {p.fix}</span>}
          {p.search && (
            <>
              {' '}
              <a href={marketplaceFor(p.search)} target="_blank" rel="noopener noreferrer" aria-label={`Search Marketplace for ${p.search}`}>
                Search Marketplace
              </a>
            </>
          )}
        </li>
      ))}
    </ul>
  )
}
