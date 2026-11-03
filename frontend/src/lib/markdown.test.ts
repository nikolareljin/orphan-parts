import { describe, expect, it } from 'vitest'
import { blocks } from './markdown'

describe('a build pack read in place', () => {
  it('splits headings, lists, numbered steps, tables and paragraphs', () => {
    const md = [
      '# Homework desk',
      '',
      'A quiet desk with a **24 inch** screen,',
      'once a laptop is added.',
      '',
      '## Still needed',
      '- A working laptop',
      '- A cable',
      '',
      '1. Clean it',
      '2. Plug it in',
      '',
      '| Item | Cost |',
      '|---|---|',
      '| cable | 10 USD |',
    ].join('\n')
    expect(blocks(md)).toEqual([
      { kind: 'heading', level: 1, text: 'Homework desk' },
      { kind: 'paragraph', text: 'A quiet desk with a **24 inch** screen, once a laptop is added.' },
      { kind: 'heading', level: 2, text: 'Still needed' },
      { kind: 'list', ordered: false, items: ['A working laptop', 'A cable'] },
      { kind: 'list', ordered: true, items: ['Clean it', 'Plug it in'] },
      { kind: 'table', rows: [['Item', 'Cost'], ['cable', '10 USD']] },
    ])
  })

  it('keeps markup as text', () => {
    expect(blocks('<img src=x onerror=alert(1)>')).toEqual([{ kind: 'paragraph', text: '<img src=x onerror=alert(1)>' }])
  })
})
