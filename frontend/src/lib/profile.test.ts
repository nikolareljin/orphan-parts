import { describe, expect, it } from 'vitest'
import { STARTER_SKILLS, customProblem, isStarter, skillRows, skillsLine, skillsToSave } from './profile'

describe('skillRows', () => {
  it('shows every starter skill, rated or not, then the custom ones', () => {
    const rows = skillRows([
      { skill: 'Woodworking', level: 'some' },
      { skill: 'bike repair', level: 'confident' },
    ])
    expect(rows).toHaveLength(STARTER_SKILLS.length + 1)
    expect(rows[0]).toEqual({ skill: 'software', level: 'none' })
    expect(rows.find((r) => r.skill === 'woodworking')?.level).toBe('some')
    expect(rows[rows.length - 1]).toEqual({ skill: 'bike repair', level: 'confident' })
    expect(isStarter(' 3d  printing ')).toBe(true)
    expect(isStarter('bike repair')).toBe(false)
  })
})

describe('skillsToSave', () => {
  it('trims, drops blank names and keeps a name once', () => {
    expect(
      skillsToSave([
        { skill: '  bike   repair ', level: 'some' },
        { skill: '   ', level: 'pro' },
        { skill: 'Bike repair', level: 'pro' },
      ]),
    ).toEqual([{ skill: 'bike repair', level: 'some' }])
  })
})

describe('customProblem', () => {
  it('refuses a blank name and one already listed', () => {
    const rows = skillRows([])
    expect(customProblem(' ', rows)).toBe('Name the skill first.')
    expect(customProblem('Plumbing', rows)).toBe('That skill is on the list already.')
    expect(customProblem('bike repair', rows)).toBeNull()
  })
})

describe('skillsLine', () => {
  it('names the rated skills, the strongest first, and leaves out none', () => {
    expect(
      skillsLine([
        { skill: 'woodworking', level: 'some' },
        { skill: 'plumbing', level: 'none' },
        { skill: 'software', level: 'pro' },
      ]),
    ).toBe('software: pro, woodworking: some')
    expect(skillsLine([{ skill: 'plumbing', level: 'none' }])).toBe('no skills rated')
  })
})
