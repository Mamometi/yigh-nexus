import { expect, test } from '@playwright/test'
import { api, watchErrors } from './helpers'

test.beforeEach(async ({ page }) => { await page.goto('/'); await expect(page.locator('.home-hero h1')).toBeVisible() })

test('priority cards: counts match the pages they link to', async ({ page, request }) => {
  const cards = page.locator('.prio-card')
  await expect(cards).toHaveCount(4)
  for (let i = 0; i < 4; i++) {
    const card = page.locator('.prio-card').nth(i)
    await card.scrollIntoViewIfNeeded()
    const [facLink, oppLink] = [card.locator('.prio-card__links a').nth(0), card.locator('.prio-card__links a').nth(1)]
    const facN = Number((await facLink.innerText()).match(/\d+/)![0]), oppN = Number((await oppLink.innerText()).match(/\d+/)![0])
    await facLink.click()
    await expect(page.locator('.results__bar')).toContainText(`${facN} faculty`)
    await page.goBack()
    await page.locator('.prio-card').nth(i).locator('.prio-card__links a').nth(1).click()
    await expect(page.locator('.osf-count')).toContainText(`${oppN} Opportunit`)
    await page.goBack()
  }
})

test('read more expands and collapses the full priority text', async ({ page }) => {
  const card = page.locator('.prio-card').first()
  await card.scrollIntoViewIfNeeded()
  const before = (await card.innerText()).length
  await card.getByRole('button', { name: /read more/i }).click()
  expect((await card.innerText()).length).toBeGreaterThan(before)
  await card.getByRole('button', { name: /less/i }).click()
  expect((await card.innerText()).length).toBeLessThanOrEqual(before + 5)
})

test('tool cards go to the right pages', async ({ page }) => {
  for (const [name, url] of [['Opportunity Radar', /\/radar$/], ['Faculty Directory', /\/directory$/], ['Team Launchpad', /\/launchpad$/]]) {
    await page.locator('.tool-card', { hasText: name as string }).click()
    await expect(page).toHaveURL(url)
    await page.goBack()
  }
})

test('funding closing soon: open, within 30 days, soonest first', async ({ page }) => {
  const items = page.locator('.opp-mini')
  const n = await items.count()
  const today = new Date(new Date().toDateString()).getTime()
  let last = 0
  for (let i = 0; i < n; i++) {
    const href = await items.nth(i).getAttribute('href')
    const id = Number(href!.split('/').pop())
    const o = await (await page.request.get(`/api/radar/opportunities/${id}`)).json()
    expect(['open', 'forecasted']).toContain(o.status)
    const t = new Date(o.deadline + 'T00:00:00').getTime()
    expect(t).toBeGreaterThanOrEqual(today); expect(t - today).toBeLessThanOrEqual(31 * 864e5); expect(t).toBeGreaterThanOrEqual(last)
    last = t
  }
})

test('news cards have real dates and links; no console errors', async ({ page }) => {
  const errors = watchErrors(page)
  await page.reload()
  const news = page.locator('.news-card')
  await expect(news).toHaveCount(3)
  for (const d of await page.locator('.news-card__date').allInnerTexts()) expect(d).not.toMatch(/invalid/i)
  for (let i = 0; i < 3; i++) expect(await news.nth(i).getAttribute('href')).toMatch(/^https:\/\//)
  await page.mouse.wheel(0, 20000); await page.waitForTimeout(1500)
  expect(await page.locator('.reveal:not(.is-in)').count()).toBe(0)
  expect(errors).toEqual([])
})
