import { expect, openItem, section, test } from './lib'

// What is it worth?: the price guidance the demo set keeps for the graphics card (four figures
// kept apart, comparables with their pages), and a sale you know of.

const GPU = 'EVGA GeForce 9800 GT graphics card'

test('price guidance and a sale you know of', async ({ shots, page }) => {
  const item = await openItem(page, GPU)
  await section(item, 'Value')
  const value = item.getByRole('region', { name: 'What is it worth?' })
  await shots.show(value)
  await shots.take('01-value-section')
  const guide = value.getByRole('status')
  if (await guide.count()) {
    const comparables = guide.getByRole('list', { name: 'Comparables' })
    if (await comparables.count()) {
      await shots.show(comparables, 'center')
      await shots.take('02-comparables')
    }
  }
  const sale = value.getByRole('form', { name: 'Add a sale you know of' })
  await sale.getByLabel(/^Price \(USD\)/).fill('20')
  await sale.getByLabel('Sold on').fill('2026-10-12')
  await sale.getByLabel('Note').fill('a friend')
  await sale.getByRole('button', { name: 'Add sale' }).click()
  await expect(value.getByRole('list', { name: 'Sales you reported' })).toContainText('20 USD')
  await shots.show(sale, 'center')
  await shots.take('03-sale-reported')
})
