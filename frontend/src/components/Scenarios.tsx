import { useId, type ReactNode } from 'react'
import { api, type DecisionChoice, type Decided, type KeepFix, type ReuseScenario, type Scenarios as ScenarioSet, type SellCard, type Worth } from '../lib/api'
import {
  CARDS,
  cardFor,
  chosenCard,
  difficultyLabel,
  keepFix,
  recommendationLabel,
  worthLine,
  type ScenarioCard,
} from '../lib/decide'
import { usd } from '../lib/format'
import { whenText } from '../lib/inventory'
import Compatibility from './Compatibility'
import DrawIt from './DrawIt'
import { NeverRun } from './Saved'
import SignInLine from './SignInLine'

// What to do with it: one button asks Muse Spark for three cards written for this owner (keep
// and fix, reuse, sell or give away) and the one it recommends. Each card records its choice
// on the item through the decision route; nothing is decided by asking. Cards already written
// are shown as kept, with "Ask again" beside them; the demo visitor (readOnly) reads them and
// the pictures drawn of them, with no button that asks, draws or decides.
export default function Scenarios({
  scenarios,
  worth,
  last,
  busy,
  onAsk,
  onChoose,
  onPrice,
  demo = false,
  readOnly = demo,
}: {
  scenarios: ScenarioSet | null
  worth: Worth | null
  last: Decided | null
  // the panel's busy key: 'scenarios', 'price' or a choice while one is under way
  busy: string
  onAsk: () => void
  onChoose: (choice: DecisionChoice) => void
  onPrice: () => void
  // the demo visitor: no Draw it, the line to sign in in its place
  demo?: boolean
  // read the cards and the choice made, with no button that asks or decides
  readOnly?: boolean
}) {
  const lit = scenarios ? cardFor(scenarios.recommended) : null
  const hintId = useId()
  const fix = scenarios ? keepFix(scenarios) : null
  const chosen = last?.choice

  const titleOf = (id: ScenarioCard) => CARDS.find((c) => c.id === id)?.title ?? id

  function card(id: ScenarioCard, body: ReactNode, actions: ReactNode) {
    const title = titleOf(id)
    return (
      <article key={id} className={`scenario${lit === id ? ' recommended' : ''}`} aria-label={title}>
        <h5>
          {title}
          {lit === id && <span className="badge state fits">recommended</span>}
          {chosenCard(id, chosen) && <span className="badge">chosen</span>}
        </h5>
        <div className="scenario-body">{body}</div>
        <div className="scenario-actions">{actions}</div>
      </article>
    )
  }

  // A "Choose this" is named with its card, so a list of the page's buttons tells them apart;
  // the visible words lead the name.
  function choose(choice: DecisionChoice, label: string, id?: ScenarioCard, hint?: string) {
    if (readOnly) return null
    return (
      <button
        type="button"
        onClick={() => onChoose(choice)}
        disabled={busy !== ''}
        aria-label={id ? `${label}: ${titleOf(id)}` : undefined}
        aria-describedby={hint}
      >
        {busy === choice ? 'Working…' : label}
      </button>
    )
  }

  return (
    <section className="scenarios" aria-label="What to do with it">
      {readOnly ? (
        !scenarios && (
          <>
            <p className="muted">No cards were written for this item yet.</p>
            <SignInLine what="What should I do with it?" />
          </>
        )
      ) : (
        <>
          <div className="row ask">
            <button type="button" className="ask-scenarios" onClick={onAsk} disabled={busy !== ''}>
              {busy === 'scenarios' ? 'Working…' : scenarios ? 'Ask again' : 'What should I do with it?'}
            </button>
            {scenarios && <span className="muted">Asking again adds new cards; these stay under earlier cards.</span>}
          </div>
          {!scenarios && <NeverRun step="scenarios" />}
        </>
      )}
      {scenarios && (
        <>
          <p className="meta">
            The model's scenarios · version {scenarios.version} · {whenText(scenarios.at)} · {scenarios.model} · {usd(scenarios.cost_usd)}
            {scenarios.from_fixture && <span className="badge">recorded answer</span>}
            {scenarios.stale && <span className="badge">item changed since</span>}
          </p>
          {!scenarios.profiled && !readOnly && (
            <p className="hint" role="note">
              No profile yet, so these are general answers. <a href="#profile">Fill in your profile</a> for advice that fits
              you.
            </p>
          )}
          <p className="recommendation" role="status" aria-label="Recommendation">
            <strong>Recommended: {recommendationLabel(scenarios.recommended)}.</strong> {scenarios.reason}
          </p>
          <div className="scenario-cards">
            {card(
              'keep_fix',
              <KeepFixBody card={scenarios.keep_fix} />,
              <>
                {fix && choose('keep_fix', fix.label, 'keep_fix', fix.hint ? hintId : undefined)}
                {fix?.hint && (
                  <span id={hintId} className="hint">
                    {fix?.hint}
                  </span>
                )}
              </>,
            )}
            {card(
              'reuse',
              <ReuseBody set={scenarios} demo={demo} />,
              <>
                {choose('keep_build', 'Choose this', 'reuse')}
                {chosen === 'keep_build' && <a href="#build">Plan it in Build and reuse</a>}
              </>,
            )}
            {card(
              'sell',
              <SellBody card={scenarios.sell} worth={worth} busy={busy} onPrice={onPrice} readOnly={readOnly} />,
              <>
                {choose('sell', 'Sell it')}
                {choose('give', 'Give it away')}
              </>,
            )}
          </div>
        </>
      )}
    </section>
  )
}

function Lines({ label, lines }: { label: string; lines: string[] }) {
  if (lines.length === 0) return null
  return (
    <>
      <span className="label">{label}</span>
      <ul aria-label={label}>
        {lines.map((l, i) => (
          <li key={`${i}:${l}`}>{l}</li>
        ))}
      </ul>
    </>
  )
}

function Difficulty({ level, why }: { level: KeepFix['difficulty']; why: string }) {
  return (
    <p>
      <span className={`badge level ${level}`}>{difficultyLabel(level)}</span> {why}
    </p>
  )
}

function KeepFixBody({ card }: { card: KeepFix }) {
  return (
    <>
      <Lines label="Likely problem" lines={card.problems} />
      {card.worth_fixing ? (
        <>
          {card.steps.length > 0 && (
            <>
              <span className="label">Steps</span>
              <ol aria-label="Steps">
                {card.steps.map((s, i) => (
                  <li key={`${i}:${s}`}>{s}</li>
                ))}
              </ol>
            </>
          )}
          <Difficulty level={card.difficulty} why={card.why} />
          <Lines label="Parts" lines={card.parts} />
          <p className="muted">
            {card.cost} · {card.time}
          </p>
        </>
      ) : (
        <p>
          <strong>Not worth fixing.</strong> {card.why}
        </p>
      )}
    </>
  )
}

// Each reuse scenario with its own Draw it: how the finished project could look, drawn only on a
// click and kept with this set of cards.
function ReuseBody({ set, demo }: { set: ScenarioSet; demo: boolean }) {
  const scenarios: ReuseScenario[] = set.reuse
  if (scenarios.length === 0) return <p className="muted">No reuse ideas came back.</p>
  return (
    <ul className="reuse" aria-label="Reuse scenarios">
      {scenarios.map((r, i) => (
        <li key={`${i}:${r.title}`}>
          <strong>{r.title}</strong>
          <p>{r.what_it_does}</p>
          {r.with_items.length > 0 && <p className="muted">With what you have: {r.with_items.join(', ')}</p>}
          {(r.without ?? []).length > 0 && <p className="muted">Not with what you have: {(r.without ?? []).join(', ')} (does not fit)</p>}
          <Compatibility pairings={r.compatibility ?? []} label={`Compatibility of ${r.title}`} />
          <Difficulty level={r.difficulty} why={r.why} />
          {r.extra_parts.length > 0 && <p className="muted">Extra parts: {r.extra_parts.join('; ')}</p>}
          <p className="muted">
            {r.cost} · {r.time}
          </p>
          <DrawIt
            key={`${set.id}:${i}`}
            name={r.title}
            demo={demo}
            shownToDemo
            list={() => api.decide.cardPictures(set.item_id, set.id, i)}
            draw={() => api.decide.drawCard(set.item_id, set.id, i)}
            url={(n) => api.decide.cardPictureUrl(set.item_id, set.id, i, n)}
          />
        </li>
      ))}
    </ul>
  )
}

function SellBody({
  card,
  worth,
  busy,
  onPrice,
  readOnly,
}: {
  card: SellCard
  worth: Worth | null
  busy: string
  onPrice: () => void
  readOnly: boolean
}) {
  return (
    <>
      <Lines label="What sells it" lines={card.selling_points} />
      <p>
        <span className="label">Effort</span>
        {card.effort}
      </p>
      {card.note && <p className="muted">{card.note}</p>}
      <p>
        <span className="label">Price guidance</span>
        {worth || readOnly ? (
          worthLine(worth)
        ) : (
          <button type="button" className="link" onClick={onPrice} disabled={busy !== ''}>
            {busy === 'price' ? 'Working…' : 'Get price guidance'}
          </button>
        )}
      </p>
    </>
  )
}
