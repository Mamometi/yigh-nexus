import { expect, test } from '@playwright/test'
import { api } from './helpers'

const COLORS: Record<string, string> = {
  'Climate & Health': '#5f9e3a', 'Digital Health & AI': '#3a8de8',
  'Health Diplomacy & Security': '#d0702a', 'Health Sovereignty': '#9265c4',
}

test.describe('Collaboration network', () => {
  test('API network is internally consistent for several filters', async ({ request }) => {
    for (const q of ['', '?size=30', '?keyword=HIV%2FAIDS', '?school=Public%20Health', '?priority=Climate%20%26%20Health']) {
      const n = await api(request, `/network${q}`)
      const ids = new Set(n.nodes.map((x: any) => x.id))
      expect(n.nodes.length).toBeLessThanOrEqual(q.includes('size=30') ? 30 : 25)
      for (const e of n.edges) {
        expect(ids.has(e.source) && ids.has(e.target), `edge ${e.id} endpoints`).toBe(true)
        expect(e.score).toBeGreaterThanOrEqual(0.3)
      }
      for (const node of n.nodes) {
        expect(node.degree).toBe(n.edges.filter((e: any) => e.source === node.id || e.target === node.id).length)
        if (q.includes('priority')) expect(node.priorities).toContain('Climate & Health')
        if (q.includes('school')) expect(node.school).toBe('Public Health')
        if (q.includes('keyword')) expect(node.keywords.length).toBeGreaterThan(0)
      }
    }
  })

  test('graph renders backend data; selecting a node highlights its 3 strongest links', async ({ page, request }) => {
    const n = await api(request, '/network')
    await page.goto('/network')
    await page.waitForFunction(() => (window as any).__cy?.nodes().length > 0)
    const graph = await page.evaluate(() => {
      const cy = (window as any).__cy
      return {
        nodes: cy.nodes().map((x: any) => ({ id: Number(x.id()), color: x.data('color') })),
        edges: cy.edges().map((x: any) => ({ id: x.id(), width: x.data('width'), score: x.data('score'), dashed: x.hasClass('coauthors') })),
      }
    })
    expect(graph.nodes.length).toBe(n.nodes.length)
    expect(graph.edges.length).toBe(n.edges.length)
    for (const node of n.nodes) {
      const g = graph.nodes.find(x => x.id === node.id)!
      expect(g.color).toBe(node.primary_priority ? COLORS[node.primary_priority.name] : '#8d949e')
    }
    for (const e of n.edges) expect(graph.edges.find(x => x.id === e.id)!.dashed).toBe(e.already_coauthors)
    // thicker line <=> higher score
    const sorted = [...graph.edges].sort((a, b) => a.score - b.score)
    for (let i = 1; i < sorted.length; i++) expect(sorted[i].width).toBeGreaterThanOrEqual(sorted[i - 1].width)

    // click the most connected node on the canvas
    const top = [...n.nodes].sort((a: any, b: any) => b.degree - a.degree)[0]
    const pos = await page.evaluate(id => (window as any).__cy.getElementById(String(id)).renderedPosition(), top.id)
    const box = (await page.locator('.net-canvas').boundingBox())!
    await page.mouse.click(box.x + pos.x, box.y + pos.y)
    await expect(page.locator('.net-panel__name')).toHaveText(top.name)
    const expectTop = n.edges.filter((e: any) => e.source === top.id || e.target === top.id)
      .sort((a: any, b: any) => b.score - a.score).slice(0, 3).map((e: any) => e.id).sort()
    const highlighted = await page.evaluate(() => (window as any).__cy.edges('.top').map((e: any) => e.id()).sort())
    expect(highlighted).toEqual(expectTop)
    await expect(page.locator('.net-links li.is-top')).toHaveCount(Math.min(3, top.degree))

    // clicking a link in the panel opens the explanation for that pair
    await page.locator('.net-links button').first().click()
    await expect(page.locator('.edge-details__title')).toContainText(top.name.split(',')[0])
  })

  test('filters, co-author toggle and accessible list view', async ({ page, request }) => {
    // Empty state: simulate a filter with too few connections (independent of live data).
    await page.route('**/api/network?school=Nursing*', r => r.fulfill({ json: { nodes: [], edges: [], candidates: 3, disclaimer: '' } }))
    await page.goto('/network')
    await page.selectOption('#n-school', 'Nursing')
    await expect(page.getByText('Not enough connections to draw a network')).toBeVisible()
    await expect(page.getByText(/3 faculty match these filters/)).toBeVisible()
    await page.getByRole('button', { name: 'Reset filters' }).click()
    await page.waitForFunction(() => (window as any).__cy?.nodes().length > 0)
    await page.getByLabel('Hide existing co-authors').click()
    await expect(page.getByLabel('Hide existing co-authors')).toBeChecked()
    await expect(page).toHaveURL(/new=1/)
    await page.waitForTimeout(1500)
    expect(await page.evaluate(() => (window as any).__cy.edges('.coauthors').length)).toBe(0)
    await page.getByLabel('Hide existing co-authors').click()
    await expect(page.getByLabel('Hide existing co-authors')).not.toBeChecked()
    const n = await api(request, '/network')
    await page.getByRole('tab', { name: 'List view' }).click()
    await expect(page.locator('.net-list__item')).toHaveCount(n.nodes.length)
    const firstLink = page.locator('.net-list__links .link-btn').first()
    await firstLink.click()
    await expect(firstLink).toHaveAttribute('aria-expanded', 'true')
    await expect(page.locator('.net-list .edge-details')).toHaveCount(1)
  })
})
