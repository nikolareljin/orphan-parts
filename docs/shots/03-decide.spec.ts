import { expect, openItem, section, test } from './lib'

// Decide: the three cards written for the profile, the recommendation, and a card chosen.

const AGITATOR = 'Frappé maker agitator, worn'

test('the decide section, the cards, and Choose this', async ({ shots, page }) => {
  const item = await openItem(page, AGITATOR)
  const decide = item.getByRole('region', { name: 'Decide' })
  await section(item, 'Decide')
  await shots.show(decide)
  await shots.take('01-decide-section')
  await decide.getByRole('button', { name: 'What should I do with it?' }).click()
  const cards = decide.getByRole('region', { name: 'What to do with it' })
  const fix = cards.getByRole('article', { name: 'Keep and fix' })
  await expect(fix).toBeVisible({ timeout: 120_000 })
  await shots.show(cards)
  await shots.take('02-three-cards')
  // the cards sit side by side: one picture holds Reuse it and Sell or give away
  const reuse = cards.getByRole('article', { name: 'Reuse it' })
  if (await reuse.count()) {
    await shots.show(reuse)
    await shots.take('03-reuse-it')
  }
  await fix.getByRole('button', { name: 'Choose this: Keep and fix' }).click()
  const made = decide.getByRole('status', { name: 'Decision made' })
  await expect(made).toContainText('Keep and fix')
  await shots.show(made, 'center')
  await shots.take('05-decision-made')
})
