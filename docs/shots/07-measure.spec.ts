import { expect, openItem, PHOTOS, section, test } from './lib'
import type { Locator } from '@playwright/test'

// Measure a feature on the agitator's photo with the tape measure beside it, the inch marks 1
// and 5 as the known length (101.6 mm): first the rod's length up to the edge of its disc,
// refused because that edge is too soft to mark, then the rod's diameter, accepted.

const AGITATOR = 'Frappé maker agitator, worn'
// points in the photo's own pixels (739 x 1600)
const W = 739
const H = 1600
const REFERENCE: [number, number][] = [
  [228, 405],
  [160, 1262],
]

async function mark(measure: Locator, feature: string, points: [number, number][]): Promise<void> {
  await measure.getByRole('combobox', { name: /^Feature/ }).selectOption(feature)
  await measure.getByLabel('Photo with a ruler or card in it').setInputFiles(`${PHOTOS}/agitator-ruler.jpg`)
  await measure.getByLabel('Known length (mm)').fill('101.6')
  await measure.getByLabel(/Taken straight on/).check()
  const canvas = measure.getByRole('img', { name: 'Photo to mark' })
  await expect(canvas).toBeVisible()
  await canvas.scrollIntoViewIfNeeded()
  const box = await canvas.boundingBox()
  if (!box) throw new Error('no canvas to mark')
  for (const [x, y] of [...REFERENCE, ...points]) {
    await canvas.click({ position: { x: (x / W) * box.width, y: (y / H) * box.height } })
  }
  await expect(measure.getByText('All marks placed')).toBeVisible()
}

test.describe.configure({ mode: 'serial' })

test('a capture refused, with the reason', async ({ shots, page }) => {
  const item = await openItem(page, AGITATOR)
  await section(item, 'Measure and fit')
  const measure = item.getByRole('region', { name: 'Measure a feature' })
  await measure.getByRole('combobox', { name: /^Feature/ }).selectOption('rod_length')
  await shots.show(measure)
  await shots.take('01-measure-section')
  await mark(measure, 'rod_length', [
    [465, 170],
    [398, 1425],
  ])
  await shots.show(measure.getByText('All marks placed'))
  await shots.take('02-marks-placed')
  await measure.getByRole('button', { name: 'Measure', exact: true }).click()
  const status = measure.getByRole('status')
  await expect(status).toContainText('Could not measure')
  await shots.show(status, 'center')
  await shots.take('03-refused')
})

test('a capture accepted, proposed on the item', async ({ shots, page }) => {
  const item = await openItem(page, AGITATOR)
  await section(item, 'Measure and fit')
  const measure = item.getByRole('region', { name: 'Measure a feature' })
  await mark(measure, 'rod_diameter', [
    [422, 700],
    [462, 700],
  ])
  await measure.getByRole('button', { name: 'Measure', exact: true }).click()
  const status = measure.getByRole('status')
  await expect(status).toContainText('±')
  await shots.show(status, 'center')
  await shots.take('04-measured')
})
