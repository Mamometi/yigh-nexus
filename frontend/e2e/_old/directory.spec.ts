import { expect, test } from '@playwright/test'
import { api, detail, PRIORITIES } from './helpers'

test.describe('Faculty directory', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.faculty-card').first()).toBeVisible()
  })

  test('shows every faculty record from the database', async ({ page, request }) => {
    const all = await api<any[]>(request, '/faculty')
    const filters = await api(request, '/filters')
    expect(all.length).toBe(filters.total_faculty)
    await expect(page.locator('.faculty-card')).toHaveCount(all.length)
    await expect(page.locator('.results__bar')).toContainText(`${all.length} faculty members`)
    // names on cards == names in DB
    const names = await page.locator('.faculty-card h3').allTextContents()
    expect(names.sort()).toEqual(all.map(f => f.name).sort())
  })

  for (const p of PRIORITIES) {
    test(`priority filter "${p}" shows exactly the faculty tagged with it`, async ({ page, request }) => {
      const opt = (await api(request, '/filters')).priorities.find((o: any) => o.label === p)
      await page.getByRole('button', { name: new RegExp(`^${p.replace(/[&]/g, '\\&')}`) }).click()
      await expect(page.locator('.results__bar')).toContainText(`${opt.count} faculty member`)
      await expect(page.locator('.faculty-card')).toHaveCount(opt.count)
      // every visible card carries that priority chip
      const cards = page.locator('.faculty-card')
      for (let i = 0; i < opt.count; i++) await expect(cards.nth(i).locator('.chip--priority', { hasText: p })).toHaveCount(1)
      await expect(page).toHaveURL(new RegExp(`priority=${opt.value}`))
    })
  }

  test('school filter shows only that school, with the advertised count', async ({ page, request }) => {
    const { schools } = await api(request, '/filters')
    for (const s of schools) {
      await page.selectOption('#f-school', s.value)
      await expect(page.locator('.faculty-card')).toHaveCount(s.count)
      const meta = await page.locator('.faculty-card .faculty-card__head .muted').allTextContents()
      expect(meta.every(m => m.startsWith(s.value))).toBe(true)
    }
  })

  test('research-area and region filters only return faculty actually tagged with them', async ({ page, request }) => {
    for (const [sel, param, value, key] of [
      ['#f-keyword', 'keyword', 'Malaria', 'keywords'],
      ['#f-keyword', 'keyword', 'HIV/AIDS', 'keywords'],
      ['#f-region', 'region', 'Kenya', 'regions'],
      ['#f-region', 'region', 'India', 'regions'],
    ] as const) {
      await page.goto('/')
      await page.selectOption(sel, value)
      const ids = (await api<any[]>(request, `/faculty?${param}=${encodeURIComponent(value)}`)).map(f => f.id)
      await expect(page.locator('.faculty-card')).toHaveCount(ids.length)
      expect(ids.length).toBeGreaterThan(0)
      for (const id of ids) {
        const d = await detail(request, id)
        expect(d.generated[key].map((t: any) => t.name), `${d.name} should have ${value}`).toContain(value)
      }
    }
  })

  test('combined filters are an AND of the individual filters', async ({ request }) => {
    const a = new Set((await api<any[]>(request, '/faculty?school=Public%20Health')).map(f => f.id))
    const b = new Set((await api<any[]>(request, '/faculty?priority=climate-health')).map(f => f.id))
    const both = (await api<any[]>(request, '/faculty?school=Public%20Health&priority=climate-health')).map(f => f.id)
    expect(both.sort()).toEqual([...a].filter(x => b.has(x)).sort())
  })

  test('search matches name/title/bio/interests and filters can be removed', async ({ page, request }) => {
    await page.getByRole('searchbox', { name: 'Search faculty' }).fill('malaria')
    await expect(page).toHaveURL(/q=malaria/)
    const res = await api<any[]>(request, '/faculty?q=malaria')
    await expect(page.locator('.faculty-card')).toHaveCount(res.length)
    for (const f of res) {
      const d = await detail(request, f.id)
      const hay = [d.name, d.title, d.source.bio, ...d.source.research_interests, ...d.generated.keywords.map((k: any) => k.name)].join(' ').toLowerCase()
      expect(hay, d.name).toContain('malaria')
    }
    await page.getByRole('button', { name: /Climate & Health/ }).click()
    await expect(page.getByRole('button', { name: /Remove filter/ })).toHaveCount(1)
    await page.getByRole('button', { name: /Remove filter/ }).click()
    await expect(page.locator('.faculty-card')).toHaveCount(res.length)
    await page.getByRole('searchbox', { name: 'Search faculty' }).fill('zzzz-no-such-person')
    await expect(page.getByText('No faculty match these filters')).toBeVisible()
    await page.getByRole('button', { name: 'Clear search and filters' }).click()
    await expect(page.locator('.faculty-card')).toHaveCount((await api<any[]>(request, '/faculty')).length)
  })

  test('"Show bio" expands the same card in place with that person’s bio', async ({ page, request }) => {
    const card = page.locator('.faculty-card', { hasText: 'Serap Aksoy' })
    const name = (await card.locator('h3').textContent())!
    const id = (await api<any[]>(request, `/faculty?q=${encodeURIComponent('Serap Aksoy')}`))[0].id
    const d = await detail(request, id)
    await card.getByRole('button', { name: /Show bio/ }).click()
    await expect(card.getByRole('button', { name: /Hide bio/ })).toHaveAttribute('aria-expanded', 'true')
    await expect(card.locator('.faculty-card__bio-text')).toHaveText(d.source.bio.trim())
    await expect(page).toHaveURL(/\/$/)                       // stayed on the directory
    await expect(page.locator('.faculty-card.is-open')).toHaveCount(1)
    expect(name).toBe(d.name)
    await card.getByRole('button', { name: /Hide bio/ }).click()
    await expect(card.locator('.faculty-card__bio')).toHaveCount(0)
  })
})
