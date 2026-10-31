import { describe, expect, it } from 'vitest'
import { pairingText, reachableFromAPhone, redrawAfterMs } from './pairing'

describe('reachableFromAPhone', () => {
  it('accepts a network address and a public origin', () => {
    expect(reachableFromAPhone('http://192.168.1.20:5173')).toBe(true)
    expect(reachableFromAPhone('https://orphan-parts.pages.dev')).toBe(true)
    expect(reachableFromAPhone('https://someone--orphan-parts-web.modal.run')).toBe(true)
    expect(reachableFromAPhone('http://[2001:db8::1]:5173')).toBe(true)
  })
  it('refuses the loopback names a phone cannot reach, and junk', () => {
    expect(reachableFromAPhone('http://localhost:5183')).toBe(false)
    expect(reachableFromAPhone('http://127.0.0.1:8000')).toBe(false)
    expect(reachableFromAPhone('http://127.0.0.2:8000')).toBe(false)
    expect(reachableFromAPhone('http://[::ffff:127.0.0.1]:8000')).toBe(false)
    expect(reachableFromAPhone('http://0.0.0.0:8000')).toBe(false)
    expect(reachableFromAPhone('http://[::1]:8000')).toBe(false)
    expect(reachableFromAPhone('http://app.localhost')).toBe(false)
    expect(reachableFromAPhone('not a url')).toBe(false)
  })
})

describe('pairingText', () => {
  it('says what the code carries in each of the three states', () => {
    expect(pairingText(false, false)).toBe("It contains this server's address.")
    expect(pairingText(false, true)).toBe("It contains this server's address.")
    expect(pairingText(true, false)).toContain('the phone opens the demo')
    expect(pairingText(true, false)).toContain('Sign in here first')
    expect(pairingText(true, true)).toContain('its own access code')
    expect(pairingText(true, true)).toContain('never given to the phone')
    expect(pairingText(true, true)).toContain('anyone who scans it is signed in')
    expect(pairingText(true, false)).not.toContain('anyone who scans it is signed in')
  })
})

describe('redrawAfterMs', () => {
  it('draws the code again a minute before its pairing ends, and every 10 minutes without one', () => {
    const now = 1_000_000_000
    expect(redrawAfterMs(now / 1000 + 15 * 60, now)).toBe(14 * 60_000)
    expect(redrawAfterMs(now / 1000 + 60, now)).toBe(15_000)
    expect(redrawAfterMs(now / 1000 - 5, now)).toBe(15_000)
    expect(redrawAfterMs(0, now)).toBe(10 * 60_000)
  })
  it('goes by the seconds left when the server says them, whatever the page clock reads', () => {
    const now = 1_000_000_000
    // the page clock is an hour fast: the end in Unix seconds looks long past
    expect(redrawAfterMs(now / 1000 - 45 * 60, now, 15 * 60)).toBe(14 * 60_000)
    // an hour slow: the end looks far off
    expect(redrawAfterMs(now / 1000 + 75 * 60, now, 15 * 60)).toBe(14 * 60_000)
    expect(redrawAfterMs(now / 1000 + 15 * 60, now, 30)).toBe(15_000)
    expect(redrawAfterMs(now / 1000 + 15 * 60, now, 0)).toBe(15_000)
    // not said: the end against the page clock, then 10 minutes
    expect(redrawAfterMs(now / 1000 + 15 * 60, now, null)).toBe(14 * 60_000)
    expect(redrawAfterMs(0, now, null)).toBe(10 * 60_000)
  })
})
