import type { RatedSkill, SkillLevel } from './api'

// The skills every profile form asks about, in this order; the owner adds their own below.
// The same list as backend/app/projects/skills.py.
export const STARTER_SKILLS: string[] = [
  'software',
  'electronics and soldering',
  'woodworking',
  'metalwork',
  'handcrafting and sewing',
  'plumbing',
  '3D printing',
  'arts and crafts',
  'car and mechanics',
  'home repair',
]

export const LEVELS: { value: SkillLevel; label: string }[] = [
  { value: 'none', label: 'none' },
  { value: 'some', label: 'some' },
  { value: 'confident', label: 'confident' },
  { value: 'pro', label: 'pro' },
]

export const SKILL_MAX = 200

function key(name: string): string {
  return name.trim().replace(/\s+/g, ' ').toLowerCase()
}

export function isStarter(name: string): boolean {
  return STARTER_SKILLS.some((s) => key(s) === key(name))
}

// The rows the form shows: every starter skill with its saved level (none when it was never
// rated), then the custom ones in the order they were saved.
export function skillRows(saved: RatedSkill[]): RatedSkill[] {
  const byKey = new Map(saved.map((s) => [key(s.skill), s.level]))
  const starters = STARTER_SKILLS.map((skill) => ({ skill, level: byKey.get(key(skill)) ?? ('none' as SkillLevel) }))
  const custom = saved.filter((s) => !isStarter(s.skill))
  return [...starters, ...custom]
}

// What is sent: names on one line, blank ones dropped, a name given twice kept once with its
// first rating.
export function skillsToSave(rows: RatedSkill[]): RatedSkill[] {
  const seen = new Set<string>()
  const out: RatedSkill[] = []
  for (const row of rows) {
    const skill = row.skill.trim().replace(/\s+/g, ' ').slice(0, SKILL_MAX)
    if (!skill || seen.has(key(skill))) continue
    seen.add(key(skill))
    out.push({ skill, level: row.level })
  }
  return out
}

// A new custom skill, or why it cannot be added.
export function customProblem(name: string, rows: RatedSkill[]): string | null {
  const wanted = key(name)
  if (!wanted) return 'Name the skill first.'
  if (rows.some((r) => key(r.skill) === wanted)) return 'That skill is on the list already.'
  return null
}

// The rated skills in one line, the strongest first; "none" is left out.
export function skillsLine(skills: RatedSkill[]): string {
  const order: SkillLevel[] = ['pro', 'confident', 'some']
  const rated = skills.filter((s) => s.level !== 'none').sort((a, b) => order.indexOf(a.level) - order.indexOf(b.level))
  if (rated.length === 0) return 'no skills rated'
  return rated.map((s) => `${s.skill}: ${s.level}`).join(', ')
}
