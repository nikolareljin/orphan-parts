import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { Item, SampleCatalog } from '../lib/api'
import { DEFAULT_LIMITS } from '../lib/photos'
import { SIGN_IN_LINE } from '../lib/sample'
import ExtractForm from './ExtractForm'
import Find from './Find'
import Listing from './Listing'
import Measure from './Measure'
import SampleGallery from './SampleGallery'
import SendCapture from './SendCapture'

// What each upload surface renders, first paint, for the demo visitor and for the owner.
const item = {
  id: 1,
  name: 'Agitator',
  item_type: 'blender agitator',
  profile: '',
  version: 1,
  fields: {},
  assertions: [],
} as unknown as Item

const catalog: SampleCatalog = {
  title: 'a drawer',
  items: [
    {
      key: 'gpu',
      name: 'Graphics card',
      item_type: 'graphics card',
      photos: [
        { id: 'gpu-front', file: 'gpu-front.jpg', item_key: 'gpu', item_name: 'Graphics card' },
        { id: 'gpu-back', file: 'gpu-back.jpg', item_key: 'gpu', item_name: 'Graphics card' },
      ],
    },
    { key: 'mon', name: 'Monitor', item_type: 'monitor', photos: [{ id: 'mon', file: 'mon.jpg', item_key: 'mon', item_name: 'Monitor' }] },
  ],
  listings: [],
  notes: [],
}

const noop = () => undefined
const html = (el: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(el)

describe('the demo visitor gets no file input', () => {
  it('on Read a label, Inbox, Listing, Measure and Find', () => {
    const pages = [
      html(createElement(ExtractForm, { demo: true })),
      html(createElement(SendCapture, { limits: DEFAULT_LIMITS, demo: true, onSent: noop })),
      html(createElement(Listing, { item, demo: true, onChanged: noop })),
      html(createElement(Measure, { item, demo: true, onMeasured: noop })),
      html(createElement(Find, { demo: true })),
    ]
    for (const page of pages) expect(page).not.toContain('type="file"')
    // where no sample stands in, one line says what opens it
    expect(pages[1]).toContain(SIGN_IN_LINE)
    expect(pages[2]).toContain(SIGN_IN_LINE)
    expect(pages[4]).toContain(SIGN_IN_LINE)
  })

  it('and the owner gets them back', () => {
    expect(html(createElement(ExtractForm, { demo: false }))).toContain('type="file"')
    expect(html(createElement(SendCapture, { limits: DEFAULT_LIMITS, demo: false, onSent: noop }))).toContain('type="file"')
    expect(html(createElement(Listing, { item, onChanged: noop }))).toContain('type="file"')
    expect(html(createElement(Measure, { item, onMeasured: noop }))).toContain('type="file"')
  })
})

describe('the sample gallery', () => {
  it('shows each photo with a checkbox, grouped by item, with a whole-item button', () => {
    const page = html(createElement(SampleGallery, { catalog, selected: ['gpu-back'], onChange: noop }))
    expect(page.match(/type="checkbox"/g)).toHaveLength(3)
    expect(page).toContain('/api/samples/gpu-front/thumb')
    expect(page).toContain('alt="Graphics card, photo 2 of 2"')
    // only an item with more than one photo has the button
    expect(page.match(/Select all photos of this item/g)).toHaveLength(1)
    expect(page.match(/checked=""/g)).toHaveLength(1)
  })

  it('offers radio buttons when one photo is picked', () => {
    const page = html(createElement(SampleGallery, { catalog, selected: ['mon'], onChange: noop, multiple: false }))
    expect(page.match(/type="radio"/g)).toHaveLength(3)
    expect(page).not.toContain('Select all photos')
  })
})
