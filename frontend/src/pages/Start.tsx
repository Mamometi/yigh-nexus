import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { HubIcon } from '../components/HubIcon'
import { api, radar } from '../api'
import { hub, type Section } from '../hub'
import { useAsync } from '../hooks'
import { getHome } from './Home'

/** Home: start the Toolkit at your project's stage, search everything, browse the pathways, see what's closing soon. */

const STAGES = [
  { key: 'idea', label: 'Exploring an idea', text: 'Find people, partners and funding', icon: '💡', color: '#00356b' },
  { key: 'applying', label: 'Applying for a grant', text: 'Team, one-pager, letters, facilities', icon: '📝', color: '#0f4d92' },
  { key: 'awarded', label: 'Just won a grant', text: 'Upload your award letter', icon: '🏆', color: '#286dc0' },
  { key: 'implementing', label: 'Running the project', text: 'Pay, buy, ship and travel', icon: '⚙️', color: '#4f8fd8' },
  { key: 'sharing', label: 'Sharing results', text: 'Publish, share data, close out', icon: '📣', color: '#63aaff' },
]

export function Start() {
  const [q, setQ] = useState('')
  const nav = useNavigate()
  return (
    <div className="home4">
      <section className="home4__hero">
        <p className="kicker">GRAPPH · Yale Institute for Global Health</p>
        <h1>Where is your <em>project</em>?</h1>
        <p className="home4__lede">Pick a stage. We’ll match you with Yale collaborators, partner organizations and resources, and show the steps you’ll need at Yale.</p>
        <div className="home4__stages">
          {STAGES.map((s, i) => (
            <Link key={s.key} to={`/launchpad?stage=${s.key}&step=2`} className="home3__stage tile" style={{ '--c': s.color } as React.CSSProperties}>
              <span className="tile__n">0{i + 1}</span>
              <span className="tile__icon" aria-hidden>{s.icon}</span>
              <strong>{s.label}</strong><span className="tile__text">{s.text}</span>
              <em className="tile__go" aria-hidden>→</em></Link>
          ))}
        </div>
        <form className="home4__search" role="search" onSubmit={e => { e.preventDefault(); if (q.trim()) nav(`/search?q=${encodeURIComponent(q.trim())}`) }}>
          <input type="search" value={q} onChange={e => setQ(e.target.value)} aria-label="Search guides, funding and people"
                 placeholder="Or search guides, funding and people: malaria, Kenya, subawards…" />
          <button className="btn">Search</button>
        </form>
      </section>

      <HomeTools />
    </div>
  )
}

/** "Tools on this site" (moved here from About YIGH). */
function HomeTools() {
  const [home] = useAsync(getHome, [])
  return (
    <section className="home-approach home-tools home4__tools">
      <div className="home-approach__inner">
        <p className="eyebrow eyebrow--light">Tools on this site</p>
        <h2>Everything YIGH offers for global health work, in one place</h2>
        {home.status === 'success' && home.data.profile.tools_link && <p className="home-approach__intro">{home.data.profile.tools_link}</p>}
        <div className="tool-grid">
          <Link to="/hub" className="tool-card"><h3>Pathways</h3>
            <p>Step-by-step help with Yale processes: partner agreements, visitors, ethics, subawards, shipping, travel and publishing.</p><span className="tool-card__go">Open the pathways →</span></Link>
          <Link to="/radar" className="tool-card"><h3>Funding opportunities</h3>
            <p>Find grants that fit your work. We check funders every week, so you can see what’s open now and what’s coming up.</p><span className="tool-card__go">Browse funding →</span></Link>
          <Link to="/directory" className="tool-card"><h3>Faculty Directory</h3>
            <p>Meet Yale faculty working in global health. See what they study, where they work, and who might make a good collaborator.</p><span className="tool-card__go">Find faculty →</span></Link>
          <Link to="/launchpad" className="tool-card"><h3>Toolkit</h3>
            <p>Tell us your project’s stage and get collaborators, partners, Yale resources and the Yale steps you need, plus one-pagers and letters of support.</p><span className="tool-card__go">Open the Toolkit →</span></Link>
        </div>
      </div>
    </section>
  )
}

/** The six stages as columns, each listing its guides and tools. Shared with the Pathways page. */
export function Stages({ sections, compact = false }: { sections: Section[]; compact?: boolean }) {
  return (
    <ol className={`stages ${compact ? 'stages--compact' : ''}`} aria-label="Pathway stages">
      {sections.map((s, i) => (
        <li key={s.slug} className="stage" style={{ '--c': s.color } as React.CSSProperties}>
          <Link to={`/hub/${s.slug}`} className="stage__head">
            <span className="stage__icon"><HubIcon name={s.icon} size={34} /></span>
            <span className="stage__n">{i + 1}</span>
            <h2>{s.title}</h2>
            <span className="stage__short">{s.short ?? s.summary}</span>
          </Link>
          <ul className="stage__list">
            {(compact ? s.topics.slice(0, 4) : s.topics).map(t => <li key={t.slug}><Link to={`/hub/${s.slug}/${t.slug}`}>{t.title}</Link></li>)}
            {(compact ? [] : s.links ?? []).map(l => <li key={l.path} className="stage__tool"><Link to={l.path}>{l.title}</Link></li>)}
          </ul>
        </li>
      ))}
    </ol>
  )
}

export function SearchPage() {
  const [params] = useSearchParams()
  const q = (params.get('q') ?? '').trim()
  return (
    <div className="page osf">
      <nav className="crumbs small page-crumbs" aria-label="Breadcrumb"><Link to="/">Home</Link> › <span>Search</span></nav>
      <header className="search-head"><h1>Results for “{q}”</h1><p className="muted">Guides and tools, open funding and Yale faculty.</p></header>
      {q.length > 1 ? <Results q={q} /> : <p className="muted search-head">Type at least two letters in the search box above.</p>}
    </div>
  )
}

function Results({ q }: { q: string }) {
  const [guides] = useAsync(() => hub.search(q), [q])
  const [opps] = useAsync(() => radar.list({ q, status: 'open' }), [q])
  const [people] = useAsync(() => api.faculty({ q }), [q])
  const col = (title: string, more: string, empty: React.ReactNode, rows: { to: string; t: string; s?: string | null }[] | null) => (
    <div className="board__col"><h3>{title}</h3>
      {rows === null ? <p className="muted small">Searching…</p> : rows.length === 0 ? <p className="muted small">{empty}</p>
        : <ul>{rows.slice(0, 8).map(r => <li key={r.to}><Link to={r.to}>{r.t}</Link>{r.s && <span>{r.s}</span>}</li>)}</ul>}
      {rows && rows.length > 0 && <Link className="small" to={more}>See all →</Link>}
    </div>
  )
  return (
    <div className="board__results" role="region" aria-label="Search results">
      {col('Guides and tools', '/hub', <>No guides match. <Link to="/hub">Browse all guides</Link>.</>, guides.status === 'success' ? guides.data.map(g => ({ to: g.path, t: g.title })) : null)}
      {col('Open funding', `/radar?q=${encodeURIComponent(q)}`, <>No open calls match. <Link to="/radar?status=forecasted">See upcoming calls</Link>.</>, opps.status === 'success' ? opps.data.opportunities.map(o => ({ to: `/radar/${o.id}`, t: o.title, s: o.funder })) : null)}
      {col('Faculty', `/directory?q=${encodeURIComponent(q)}`, <>No faculty match. Try a broader word, or <button className="link-btn" onClick={() => window.dispatchEvent(new CustomEvent('open-nexi', { detail: q }))}>ask Nexi</button>.</>, people.status === 'success' ? people.data.map(f => ({ to: `/faculty/${f.id}`, t: f.name, s: f.school })) : null)}
    </div>
  )
}
