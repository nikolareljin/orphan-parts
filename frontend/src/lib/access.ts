import type { Readiness } from './api'

export const ACCESS_REQUIRED = 'opl-access-required'

// One line about the gate for the service card: nothing when there is no gate. Without a
// session the visitor is the demo: recorded answers, and the code is the way to the rest.
export function demoText(ready: Readiness, granted = true): string {
  const d = ready.demo
  if (!d.gated && !d.paused) return ''
  const parts: string[] = []
  if (d.gated && !granted) {
    parts.push(d.live_models ? 'Demo: recorded answers only. Sign in to save and use the live models' : 'Demo: recorded answers only. Sign in to save')
  } else if (d.gated) {
    parts.push(`Live calls: ${d.daily_used} of ${d.daily_cap} used today (${d.visitor_cap_per_hour} per visitor per hour)`)
  }
  if (d.paused) parts.push('paused by the operator')
  return parts.join('; ')
}

// The line a refused write carries for the demo visitor.
export const DEMO_REFUSED = 'demo: the code unlocks saving, drafts, prices, projects and captures'

// Whether a failed request means the session is gone, so the code is asked for again: a 401,
// or a write refused as the demo visitor.
export function accessLost(status: number, detail = ''): boolean {
  return status === 401 || (status === 403 && detail.startsWith('demo:'))
}
