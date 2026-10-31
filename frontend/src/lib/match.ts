import type { CheckStatus, ProfileRule, Side, Verdict } from './api'

// The ladder in plain words. CONFLICT is final; the two in the middle ask for evidence.
export function verdictLabel(verdict: Verdict): string {
  switch (verdict) {
    case 'EXACT_MATCH':
      return 'Exact match'
    case 'COMPATIBLE_LIKELY':
      return 'Likely compatible'
    case 'VISUALLY_SIMILAR':
      return 'Looks right, not proven'
    case 'CONFLICT':
      return 'Conflict: does not fit'
    case 'INSUFFICIENT_INFO':
      return 'Not enough evidence'
  }
}

// How the verdict box is coloured: fits, conflict, or still open.
export function verdictTone(verdict: Verdict): 'fits' | 'conflict' | 'unsure' {
  if (verdict === 'CONFLICT') return 'conflict'
  if (verdict === 'EXACT_MATCH' || verdict === 'COMPATIBLE_LIKELY') return 'fits'
  return 'unsure'
}

export function statusLabel(status: CheckStatus): string {
  return status === 'unknown' ? 'unknown' : status
}

// What the rule allows, as a short hint next to its name.
export function ruleHint(rule: ProfileRule): string {
  switch (rule.kind) {
    case 'equal':
      return rule.identity ? 'must match; confirms an exact match' : 'must match'
    case 'within':
      return slack(rule).map((s) => `±${s}`).join(' or ')
    case 'at_least':
      return slack(rule).length ? `at least (${slack(rule).join(' or ')} below is OK)` : 'at least'
    case 'at_most':
      return slack(rule).length ? `at most (${slack(rule).join(' or ')} over is OK)` : 'at most'
  }
}

// The allowances a numeric rule names; the larger of the two applies.
function slack(rule: ProfileRule): string[] {
  const unit = rule.unit ? ` ${rule.unit}` : ''
  const parts: string[] = []
  if (rule.tolerance) parts.push(`${rule.tolerance}${unit}`)
  if (rule.tolerance_pct) parts.push(`${rule.tolerance_pct}%`)
  return parts
}

// Which profile's rules decide: the needed item's when it has one, else this item's.
export function rulesNote(candidateProfile: string, needProfile: string | undefined): string {
  if (!needProfile || needProfile === candidateProfile) return ''
  return `The needed item's profile (${needProfile}) decides the rules, not this item's (${candidateProfile}).`
}

export function inputLabel(rule: ProfileRule): string {
  return rule.unit ? `${rule.label} (${rule.unit})` : rule.label
}

// The need as the API takes it: another item, or only the values that were written in.
export function needSide(needItemId: number | null, profile: string, values: Record<string, string>): Side {
  if (needItemId !== null) return { item_id: needItemId }
  const kept: Record<string, string> = {}
  for (const [key, value] of Object.entries(values)) {
    if (value.trim()) kept[key] = value.trim()
  }
  return { profile, values: kept }
}
