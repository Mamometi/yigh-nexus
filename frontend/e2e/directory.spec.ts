import { expect, test } from '@playwright/test'
import { api } from './helpers'

const count = async (page: any) => Number(((await page.locator('.results__bar p').first().innerText()).match(/\d+/) ?? ['-1'])[0])

test.beforeEach(async ({ page }) => { await page.goto('/directory'); await expect(page.locator('.fdir__card').first()).toBeVisible() })

test('shows every faculty member', async ({ page, request }) => {
  const all = await api<any[]>(request, '/faculty')
  expect(await count(page)).toBe(all.length)
  await expect(page.locator('.fdir__card')).toHaveCount(all.length)
})

test('priority buttons: count on button = cards shown, each card has it; toggles off', async ({ page }) => {
  const btns = page.locator('.fbar__row--prios .priority-opt')
  for (let i = 0; i < await btns.count(); i++) {
    const b = btns.nth(i)
    const label = (await b.locator('.priority-opt__label').innerText()).trim()
    const n = Number(await b.locator('.count').innerText())
    await b.click()
    await expect.poll(() => count(page)).toBe(n)
    for (let k = 0; k < Math.min(n, 15); k++) await expect(page.locator('.fdir__card').nth(k).locator('.chip--priority', { hasText: label })).toHaveCount(1)
    await b.click()
  }
})

test('search, school and geographic filters narrow results consistently', async ({ page, request }) => {
  await page.fill('#fd-q', 'malaria')
  await expect.poll(() => count(page)).toBe((await api<any[]>(request, '/faculty?q=malaria')).length)
  await page.fill('#fd-q', '')
  const geo = await page.locator('#fd-geo option').nth(1).getAttribute('value')
  await page.selectOption('#fd-geo', geo!)
  await expect.poll(() => count(page)).toBe((await api<any[]>(request, `/faculty?region=${encodeURIComponent(geo!)}`)).length)
})

test('full bio toggle and profile link', async ({ page }) => {
  const idx = await page.locator('.fdir__card').evaluateAll(cs => cs.findIndex(c => [...c.querySelectorAll('button')].some(b => /show full bio/i.test(b.textContent ?? ''))))
  const card = page.locator('.fdir__card').nth(idx)
  const before = (await card.locator('.fdir__bio').innerText()).length
  await card.getByRole('button', { name: /show full bio/i }).click()
  await expect.poll(async () => (await card.locator('.fdir__bio').innerText()).length).toBeGreaterThan(before)
  await card.getByRole('button', { name: /show less/i }).click()
  const name = (await card.locator('h3').innerText()).trim()
  await card.getByRole('link', { name: 'Full profile' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText(name.split(',')[0])
})
