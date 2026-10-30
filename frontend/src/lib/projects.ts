import type { Budget, Conflict, Effort, Preferences, Project, ProjectStatus, Requirement } from './api'

export const EFFORTS: { value: Effort; label: string }[] = [
  { value: 'low', label: 'an hour or so' },
  { value: 'medium', label: 'an afternoon' },
  { value: 'high', label: 'a weekend or more' },
]

export const EMPTY_PREFERENCES: Preferences = {
  interests: '',
  effort: 'medium',
  skills: [],
  tools: '',
  opens_devices: false,
  budget: null,
  currency: 'USD',
  radius_km: null,
  purchase: 'used',
}

export function effortLabel(effort: Effort): string {
  return EFFORTS.find((e) => e.value === effort)?.label ?? effort
}

// Where a project stands, in plain words.
export function statusLabel(status: ProjectStatus): string {
  switch (status) {
    case 'proposed':
      return 'proposed'
    case 'shortlisted':
      return 'shortlisted'
    case 'selected':
      return 'selected: items committed'
    case 'building':
      return 'being built'
    case 'done':
      return 'done'
    case 'abandoned':
      return 'abandoned'
  }
}

export function statusTone(status: ProjectStatus): 'fits' | 'conflict' | 'unsure' | 'muted' {
  if (status === 'selected' || status === 'building' || status === 'done') return 'fits'
  if (status === 'abandoned') return 'muted'
  return 'unsure'
}

// The skills field is typed as one line; the API keeps a list.
export function skillsFromText(text: string): string[] {
  return text
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
}

export function skillsToText(skills: string[]): string {
  return skills.join(', ')
}

// A number field left blank means "not set", not zero.
export function numberOrNull(text: string): number | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const value = Number(trimmed)
  return Number.isFinite(value) && value >= 0 ? value : null
}

// What is wrong with a number field, or null: a blank is fine, anything that is not a number
// at or above zero is said rather than saved as "not set".
export function numberProblem(text: string, label: string): string | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const value = Number(trimmed)
  if (!Number.isFinite(value)) return `${label} must be a number`
  if (value < 0) return `${label} cannot be below 0`
  return null
}

export function money(amount: number, currency: string): string {
  const rounded = Number.isInteger(amount) ? String(amount) : amount.toFixed(2)
  return `${rounded} ${currency}`
}

// What the selected set spends against the budget, in one line.
export function budgetText(b: Budget): string {
  const spend = money(b.committed_spend, b.currency)
  if (b.budget === null) return `${b.selected} selected, expected spend ${spend}; no budget set`
  const left = b.remaining ?? 0
  if (left < 0) return `${b.selected} selected, expected spend ${spend} of ${money(b.budget, b.currency)}: over by ${money(-left, b.currency)}`
  return `${b.selected} selected, expected spend ${spend} of ${money(b.budget, b.currency)}; ${money(left, b.currency)} left`
}

// Requirements the inventory does not fill, blocking ones first.
export function missing(project: Pick<Project, 'requirements'>): Requirement[] {
  return project.requirements.filter((r) => r.state !== 'pass').sort((a, b) => Number(b.blocking) - Number(a.blocking))
}

export function canStart(project: Pick<Project, 'requirements'>): boolean {
  return project.requirements.every((r) => r.state === 'pass' || !r.blocking)
}

// The body of a 409 from select: which items another selected project holds.
export function conflictsOf(body: unknown): Conflict[] {
  const list = (body as { conflicts?: unknown } | undefined)?.conflicts
  if (!Array.isArray(list)) return []
  return list.filter(
    (c): c is Conflict =>
      typeof c === 'object' && c !== null && typeof (c as Conflict).item_name === 'string' && typeof (c as Conflict).project_id === 'number',
  )
}

export function conflictText(conflicts: Conflict[]): string {
  return conflicts.map((c) => `${c.item_name} is committed to "${c.project_title}"`).join('; ')
}
