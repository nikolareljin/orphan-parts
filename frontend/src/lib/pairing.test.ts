import { describe, expect, it } from 'vitest'
import { reachableFromAPhone } from './pairing'

describe('reachableFromAPhone', () => {
  it('accepts a network address and a public origin', () => {
    expect(reachableFromAPhone('http://192.168.1.20:5173')).toBe(true)
    expect(reachableFromAPhone('https://orphan-parts.pages.dev')).toBe(true)
    expect(reachableFromAPhone('https://someone--orphan-parts-web.modal.run')).toBe(true)
  })
  it('refuses the loopback names a phone cannot reach, and junk', () => {
    expect(reachableFromAPhone('http://localhost:5183')).toBe(false)
    expect(reachableFromAPhone('http://127.0.0.1:8000')).toBe(false)
    expect(reachableFromAPhone('http://[::1]:8000')).toBe(false)
    expect(reachableFromAPhone('http://app.localhost')).toBe(false)
    expect(reachableFromAPhone('not a url')).toBe(false)
  })
})
