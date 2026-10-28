import { describe, expect, it } from 'vitest'
import { apiUrl } from './api'

describe('apiUrl', () => {
  it('keeps same-origin paths relative when no base is set', () => {
    expect(apiUrl('/readyz')).toBe('/readyz')
  })

  it('adds the leading slash', () => {
    expect(apiUrl('api/version')).toBe('/api/version')
  })
})
