import { expect, openItem, section, test } from './lib'

// Sell or give away: the listing details, the draft the demo set wrote for the Sun monitor in
// Marketplace's own fields, its photos to download, Open Marketplace (pointed at, never opened),
// the checklist and what happened after posting; then the give-away of the older ThinkPad.

const SUN = 'Sun flat panel monitor'
const THINKPAD = 'Older ThinkPad, type 9461'

test('sell: details, the draft, the handoff', async ({ shots, page }) => {
  const item = await openItem(page, SUN)
  await section(item, 'Sell or give away')
  const listing = item.getByRole('region', { name: 'Prepare to sell or give away' })
  await shots.show(listing)
  await shots.take('01-listing-details')
  const draft = listing.getByRole('region', { name: 'Marketplace handoff' })
  await expect(draft).toBeVisible()
  await shots.show(draft)
  await shots.take('02-draft')
  await shots.show(draft.getByLabel('Fields to paste'))
  await shots.take('03-fields-to-paste')
  await shots.show(draft.getByRole('link', { name: 'Open Marketplace' }), 'center')
  await shots.take('04-open-marketplace')
  const after = draft.getByLabel('After posting')
  if (await after.count()) {
    await shots.show(after, 'center')
    await shots.take('05-after-posting')
  }
})

test('give away: free, worded for pickup, the data steps', async ({ shots, page }) => {
  const item = await openItem(page, THINKPAD)
  await section(item, 'Sell or give away')
  const draft = item.getByRole('region', { name: 'Prepare to sell or give away' }).getByRole('region', { name: 'Marketplace handoff' })
  await expect(draft).toBeVisible()
  await shots.show(draft)
  await shots.take('06-give-away')
  const wipe = draft.getByText('Wipe your data')
  if (await wipe.count()) {
    await shots.show(wipe.first(), 'center')
    await shots.take('07-wipe-your-data')
  }
})
