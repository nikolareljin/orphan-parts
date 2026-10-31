import { describe, expect, it } from 'vitest'
import type { Evidence } from './api'
import { fieldLabel, orderedFields, percent, printedDiffers, usd, withUnit } from './format'

const ev = (value: string, unit = '', confidence = 0.9): Evidence => ({
  value,
  unit,
  confidence,
  source: 'photo',
  raw: value,
})

describe('orderedFields', () => {
  it('follows the field order, then alphabetical for the rest', () => {
    const names = orderedFields({
      zeta: ev('1'),
      output_voltage: ev('19.5', 'V'),
      alpha: ev('2'),
      brand: ev('Orbital'),
    }).map(([name]) => name)
    expect(names).toEqual(['brand', 'output_voltage', 'alpha', 'zeta'])
  })
})

describe('formatting', () => {
  it('turns a field name into a label', () => {
    expect(fieldLabel('output_voltage')).toBe('Output voltage')
    expect(fieldLabel('brand')).toBe('Brand')
  })

  it('joins value and unit only when there is a unit', () => {
    expect(withUnit(ev('19.5', 'V'))).toBe('19.5 V')
    expect(withUnit(ev('OP-65N'))).toBe('OP-65N')
  })

  it('renders confidence as a clamped percentage', () => {
    expect(percent(0.97)).toBe('97%')
    expect(percent(1.4)).toBe('100%')
    expect(percent(-1)).toBe('0%')
  })

  it('renders cost with four decimals, zero as a plain amount', () => {
    expect(usd(0)).toBe('$0.00')
    expect(usd(0.00412)).toBe('$0.0041')
  })
})

describe('printedDiffers', () => {
  it('is quiet when the label differs only in case, spacing or punctuation', () => {
    expect(printedDiffers('CULUS LISTED, CE, VCCI, FCC', 'cULus LISTED, CE, VCCI, FCC')).toBe(false)
    expect(printedDiffers('OP065-19-333', 'OP065 19 333')).toBe(false)
    expect(printedDiffers('19.5', undefined)).toBe(false)
  })
  it('speaks when the label says more', () => {
    expect(printedDiffers('19.5', '19.5V')).toBe(true)
    expect(printedDiffers('100-240', '100-240V~ 50/60Hz 1.5A')).toBe(true)
    expect(printedDiffers('OP065-19-333', 'P/N OP065-19-333')).toBe(true)
  })
})
