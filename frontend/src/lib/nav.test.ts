import { describe, expect, it } from 'vitest'
import { VIEWS, hashFor, viewFromHash } from './nav'

describe('nav', () => {
  it('reads the page off the hash and falls back to the first page', () => {
    expect(viewFromHash('#inventory')).toBe('inventory')
    expect(viewFromHash('#build/7')).toBe('build')
    expect(viewFromHash('')).toBe('read')
    expect(viewFromHash('#nowhere')).toBe('read')
  })
  it('writes a hash for every page but the first', () => {
    expect(hashFor('read')).toBe('')
    expect(hashFor('find')).toBe('#find')
    expect(VIEWS.map((v) => v.id)).toEqual(['read', 'inbox', 'inventory', 'find', 'build', 'profile'])
    expect(viewFromHash('#profile')).toBe('profile')
  })
})
