import type { Readiness } from './api'

export const ACCESS_REQUIRED = 'opl-access-required'

// One line about the gate for the service card: nothing when there is no gate.
export function demoText(ready: Readiness): string {
  const d = ready.demo
  if (!d.gated && !d.paused) return ''
  const parts: string[] = []
  if (d.gated) parts.push(`demo: ${d.daily_used} of ${d.daily_cap} calls today, ${d.visitor_cap_per_hour} per visitor and hour`)
  if (d.paused) parts.push('paused by the operator')
  return parts.join('; ')
}

// Whether a failed request means the session is gone, so the code is asked for again.
export function accessLost(status: number): boolean {
  return status === 401
}
