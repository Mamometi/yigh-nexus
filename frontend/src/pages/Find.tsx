import { Link } from 'react-router-dom'
import { ErrorState, Loading } from '../components/StateViews'
import { hub } from '../hub'
import { useAsync } from '../hooks'
import { YighNews } from './Home'
import { PartnerSearch } from './Launchpad'

/** Toolkit, Expertise & Support, News & Updates and Partners: the top-menu pages from the GRAPPH mockups. */

const WAVE = <svg className="wave" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden><path d="M0,40 C360,90 1080,-10 1440,40 L1440,80 L0,80 Z" /></svg>

function Head({ crumb, title, lede }: { crumb: string; title: string; lede: React.ReactNode }) {
  return (
    <>
      <nav className="crumbs small page-crumbs" aria-label="Breadcrumb"><Link to="/">Home</Link> › <span>{crumb}</span></nav>
      <header className="osf-head"><div className="osf-head__inner"><h1>{title}</h1><p className="lede">{lede}</p></div>{WAVE}</header>
    </>
  )
}

const TOOLS: { to: string; title: string; text: string; tag: string }[] = [
  { to: '/launchpad', title: 'Toolkit (My project)', text: 'Tick what you need and get collaborators, partners, a one-pager and more in one place.', tag: 'Plan' },
  { to: '/launchpad/facilities', title: 'Facilities & Resources Builder', text: 'Create a grant-ready Facilities & Other Resources section from Yale resources.', tag: 'Write' },
  { to: '/launchpad/letters', title: 'Request a Letter of Support from YIGH', text: 'Guided request form, plus templates for partners and collaborators.', tag: 'Write' },
  { to: '/launchpad/letters', title: 'Templates & Checklists', text: 'Letter templates and checklists for proposals, travel and visitors.', tag: 'Write' },
  { to: '/launchpad?stage=applying&step=2', title: 'One-pager drafter', text: 'Turn a few bullet points into a concept for a specific funding call.', tag: 'Write' },
  { to: '/radar', title: 'Funding Opportunities', text: 'Open and upcoming global health calls, checked against each funder’s page.', tag: 'Find' },
]

export function Toolkit() {
  return (
    <div className="page osf">
      <Head crumb="Toolkit" title="Toolkit" lede="Tools, templates and checklists for planning and writing global health projects at Yale." />
      <section className="kit">
        {TOOLS.map(t => <Link key={t.title} to={t.to} className="kit__card"><span className="kit__tag">{t.tag}</span><strong>{t.title}</strong><span>{t.text}</span><em>Open →</em></Link>)}
      </section>
    </div>
  )
}

export function Expertise() {
  const [offices, retry] = useAsync(hub.offices, [])
  return (
    <div className="page osf">
      <Head crumb="Expertise & Support" title="Expertise & Support" lede="Find Yale faculty, partner organizations around the world, and the Yale office that runs each process." />
      <section className="kit">
        <Link to="/directory" className="kit__card"><span className="kit__tag">People</span><strong>Faculty Directory</strong><span>Yale faculty working in global health, by topic, place or priority.</span><em>Browse →</em></Link>
        <Link to="/partners" className="kit__card"><span className="kit__tag">Partners</span><strong>Partner organizations</strong><span>Universities, ministries and NGOs, and which already work with Yale.</span><em>Browse →</em></Link>
        <button className="kit__card" onClick={() => window.dispatchEvent(new CustomEvent('open-nexi'))}><span className="kit__tag">Ask</span><strong>Ask Nexi</strong><span>Not sure who to talk to? Our assistant searches the whole site for you.</span><em>Start a chat →</em></button>
      </section>
      <section className="offices">
        <h2>Yale offices</h2>
        <p className="muted">The offices named in our guides, and what they help with. Always check the office’s own page for the latest rules.</p>
        {offices.status === 'loading' && <Loading />}
        {offices.status === 'error' && <ErrorState message={offices.error} onRetry={retry} />}
        {offices.status === 'success' && <ul className="offices__list">{offices.data.map(o => (
          <li key={o.name}>
            <strong>{o.url ? <a href={o.url} target="_blank" rel="noreferrer">{o.name} ↗</a> : o.name}</strong>
            {o.email && <a className="small" href={`mailto:${o.email}`}>{o.email}</a>}
            <span className="small muted">Helps with: {o.topics.map((t, i) => <span key={t.slug}>{i > 0 && ', '}<Link to={`/hub/${t.section}/${t.slug}`}>{t.title}</Link></span>)}</span>
          </li>))}</ul>}
      </section>
    </div>
  )
}

export function News() {
  return (
    <div className="page osf">
      <Head crumb="News & Updates" title="News & Updates" lede="Stories and announcements from the Yale Institute for Global Health." />
      <div className="news-page"><YighNews /></div>
    </div>
  )
}

export function Partners() {
  return (
    <div className="page osf">
      <nav className="crumbs small page-crumbs" aria-label="Breadcrumb"><Link to="/">Home</Link> › <Link to="/expertise">Expertise & Support</Link> › <span>Partners</span></nav>
      <header className="osf-head"><div className="osf-head__inner"><h1>Partner organizations</h1>
        <p className="lede">Universities, ministries and NGOs around the world. “Works with Yale” means we found a public record of a link; otherwise it’s a suggestion only.</p></div>{WAVE}</header>
      <section className="launch__sec need__panel"><PartnerSearch /></section>
    </div>
  )
}
