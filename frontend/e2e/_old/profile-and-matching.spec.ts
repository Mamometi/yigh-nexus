import { expect, test } from '@playwright/test'
import { api, detail, norm, sourceText } from './helpers'

test.describe('Data integrity (all faculty)', () => {
  test('every generated tag quotes text that really appears in that person’s profile', async ({ request }) => {
    test.setTimeout(240_000)
    const all = await api<any[]>(request, '/faculty')
    const problems: string[] = []
    for (const f of all) {
      const d = await detail(request, f.id)
      const src = sourceText(d)
      const everything = Object.values(src).join(' \n ')
      for (const kind of ['priorities', 'keywords', 'regions'] as const) {
        for (const t of d.generated[kind]) {
          if (!t.explanation) problems.push(`${d.name}: ${kind} ${t.name} has no explanation`)
          if (!t.evidence.length) problems.push(`${d.name}: ${kind} ${t.name} has no evidence`)
          for (const e of t.evidence) {
            const snip = norm(e.snippet ?? '')
            const field = src[e.field] ?? everything
            if (!norm(field).includes(snip.slice(0, 120))) problems.push(`${d.name}: ${kind} "${t.name}" evidence not found in ${e.field}: "${snip.slice(0, 60)}"`)
            if (e.term && !snip.includes(e.term.toLowerCase())) problems.push(`${d.name}: ${kind} "${t.name}" term "${e.term}" not in its snippet`)
          }
        }
      }
      // card summary agrees with detail
      expect(f.priorities.map((p: any) => p.name).sort()).toEqual(d.generated.priorities.map((p: any) => p.name).sort())
    }
    expect(problems, problems.slice(0, 20).join('\n')).toEqual([])
  })
})

test.describe('Profile + Find collaborators', () => {
  test('profile shows the right person, source sections and tags', async ({ page, request }) => {
    const d = await detail(request, 4)
    await page.goto('/faculty/4')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(d.name)
    if (d.source.activities.length) await expect(page.getByRole('heading', { name: /International & research activities/ })).toBeVisible()
    if (d.source.yale_coauthors.length) await expect(page.locator('.chip--link', { hasText: d.source.yale_coauthors[0].name })).toBeVisible()
    for (const p of d.generated.priorities) await expect(page.locator('.tag-group').first()).toContainText(p.name)
    // clicking a tag shows its explanation
    const first = d.generated.keywords[0]
    await page.locator('.tag-btn', { hasText: first.name }).first().click()
    await expect(page.locator('.why')).toContainText(`Why “${first.name}”?`)
  })

  test('collaborators are ranked, scored and labelled consistently', async ({ page, request }) => {
    const all = await api<any[]>(request, '/faculty')
    // sample faculty across the list
    const sample = [all[3], all[40], all[90], all[150], all[220]].filter(Boolean)
    for (const f of sample) {
      const me = await detail(request, f.id)
      const res = await api(request, `/faculty/${f.id}/collaborators?limit=12`)
      const scores = res.matches.map((m: any) => m.score)
      expect([...scores].sort((a, b) => b - a), `${me.name} ranking`).toEqual(scores)
      res.matches.forEach((m: any, i: number) => {
        expect(m.rank).toBe(i + 1)
        expect(m.faculty.id).not.toBe(f.id)
        expect(m.score).toBeGreaterThanOrEqual(0.3)
        const sum = Object.values(m.breakdown).reduce((s: number, b: any) => s + b.contribution, 0)
        expect(Math.abs(sum - m.score)).toBeLessThan(0.01)
        // never recommended on school difference alone
        expect(m.reasons.some((r: any) => r.criterion !== 'cross_school')).toBe(true)
      })
      // co-author flag must match the profiles' Yale Co-Authors lists (either direction)
      for (const m of res.matches) {
        const other = await detail(request, m.faculty.id)
        const listed = me.source.yale_coauthors.some((c: any) => c.faculty_id === other.id)
          || other.source.yale_coauthors.some((c: any) => c.faculty_id === me.id)
        expect(m.already_coauthors, `${me.name} ↔ ${other.name}`).toBe(listed)
      }
    }
  })

  test('UI: Find collaborators, toggles and navigation', async ({ page, request }) => {
    const res = await api(request, '/faculty/4/collaborators?limit=12')
    await page.goto('/')
    await page.locator('.faculty-card', { hasText: 'Serap Aksoy' }).getByRole('link', { name: 'Find collaborators' }).click()
    await expect(page).toHaveURL(/\/faculty\/4\?collaborators=1/)
    const cards = page.locator('.match')
    await expect(cards).toHaveCount(res.matches.length)
    for (let i = 0; i < res.matches.length; i++) {
      const m = res.matches[i]
      await expect(cards.nth(i).locator('h3')).toHaveText(m.faculty.name)
      await expect(cards.nth(i).locator('.score__num')).toHaveText(String(Math.round(m.score * 100)))
      await expect(cards.nth(i).locator('.badge--coauthor')).toHaveCount(m.already_coauthors ? 1 : 0)
    }
    // evidence panel
    await cards.first().getByRole('button', { name: /See the evidence/ }).click()
    await expect(cards.first().locator('.bars li')).toHaveCount(5)
    // new connections only
    await page.getByLabel(/New connections only/).check()
    await expect(page.locator('.match .badge--coauthor')).toHaveCount(0)
    // cross-school only: every match from a different school than Aksoy (Public Health)
    await page.getByLabel(/New connections only/).uncheck()
    await page.getByLabel(/Only show people in other schools/).check()
    await expect(page.locator('.match').first()).toBeVisible()
    const schools = await page.locator('.match .match__head .muted').allTextContents()
    expect(schools.every(s => !s.startsWith('Public Health'))).toBe(true)
    // clicking a match opens their profile
    const firstName = await page.locator('.match h3').first().textContent()
    await page.locator('.match h3 a').first().click()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(firstName!)
  })

  test('error and not-found states', async ({ page }) => {
    await page.goto('/faculty/999999')
    await expect(page.getByText('Faculty member not found')).toBeVisible()
    await page.goto('/no-such-page')
    await expect(page.getByText('Page not found')).toBeVisible()
  })
})
