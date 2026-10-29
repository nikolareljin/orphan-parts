import { describe, expect, it } from 'vitest'
import type { Draft, Step } from './api'
import { draftText, groupLabel, modeLabel, remaining, stepsByGroup } from './listing'

const step = (key: string, group: Step['group'], done = false, required = true): Step => ({
  key,
  label: key,
  group,
  required,
  done,
})

describe('labels', () => {
  it('names the modes and the step groups', () => {
    expect(modeLabel('give')).toBe('Give away')
    expect(groupLabel('data')).toBe('Your data')
  })
})

describe('steps', () => {
  it('groups in the order they are done and counts what is left', () => {
    const steps = [step('photo_front', 'photos'), step('clean', 'prepare', true), step('reset', 'data', false, false)]
    expect(stepsByGroup(steps).map(([g, list]) => [g, list.map((s) => s.key)])).toEqual([
      ['prepare', ['clean']],
      ['photos', ['photo_front']],
      ['data', ['reset']],
    ])
    expect(stepsByGroup([step('a', 'photos')]).map(([g]) => g)).toEqual(['photos'])
    expect(remaining(steps)).toBe(1)
  })
})

describe('draftText', () => {
  it('is the title, a blank line and the text', () => {
    const draft = { title: 'Charger', description: 'Works.\n\nPrice: $5' } as Draft
    expect(draftText(draft)).toBe('Charger\n\nWorks.\n\nPrice: $5')
  })
})
