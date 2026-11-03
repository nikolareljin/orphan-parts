import { expect, openItem, section, test } from './lib'

// Does it fit?: the agitator's profile rules against values typed in, decided by the rules
// with no model call.

const AGITATOR = 'Frappé maker agitator, worn'

test('values typed in, checked by the profile rules', async ({ shots, page }) => {
  const item = await openItem(page, AGITATOR)
  await section(item, 'Measure and fit')
  const assess = item.getByRole('region', { name: 'Does it fit?' })
  await shots.show(assess)
  await shots.take('01-does-it-fit')
  // what a replacement rod must measure, as the owner wrote it down: one value off, one missing
  for (const [label, value] of [
    [/^Rod diameter/, '4'],
    [/^Span across the two tabs/, '9'],
    [/^Coupling tab width/, '2.5'],
    [/^Rod length/, '160'],
    [/^Material/, 'metal'],
  ] as const) {
    await assess.getByLabel(label).fill(value)
  }
  await assess.getByRole('button', { name: 'Check fit' }).click()
  await expect(assess.getByRole('table', { name: 'Checks' })).toBeVisible()
  await shots.show(assess.getByRole('table', { name: 'Checks' }), 'center')
  await shots.take('02-checks')
})
