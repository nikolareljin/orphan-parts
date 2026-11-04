import { describe, expect, it } from 'vitest'
import { marketplaceFor, pairingLabel, pairingSummary, pairingTone, pairingWho } from './compat'

describe('compatibility lines', () => {
  it('reads each state in its tone and words', () => {
    expect(pairingTone('pass')).toBe('fits')
    expect(pairingTone('fail')).toBe('conflict')
    expect(pairingTone('unknown')).toBe('unsure')
    expect(pairingLabel('fail')).toBe('does not fit')
    expect(pairingLabel('unknown')).toBe('unknown: check')
  })

  it('names the pair, or the item a missing part is for', () => {
    expect(pairingWho({ part: 'DDR4 stick', part_id: 3, host: 'ThinkPad T510' })).toBe('DDR4 stick with ThinkPad T510')
    expect(pairingWho({ part: 'M.2 drive', part_id: null, host: 'M.2 enclosure' })).toBe('M.2 enclosure')
  })

  it('counts the answers, failures first', () => {
    expect(pairingSummary([{ state: 'pass' }, { state: 'fail' }, { state: 'pass' }, { state: 'unknown' }])).toBe('1 does not fit, 1 to check, 2 fit')
    expect(pairingSummary([{ state: 'pass' }])).toBe('1 fits')
    expect(pairingSummary([])).toBe('')
  })

  it('searches Marketplace for the part a failure needs', () => {
    expect(marketplaceFor(' LGA1155 processor ')).toBe('https://www.facebook.com/marketplace/search/?query=LGA1155%20processor')
  })
})
