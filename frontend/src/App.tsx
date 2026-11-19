import { lazy, Suspense, useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './auth'
import { ChatWidget } from './components/ChatWidget'
import { EmptyState, PageSkeleton } from './components/StateViews'
import { Profile } from './pages/Profile'
import { Start } from './pages/Start'
import { Feedback } from './components/Feedback'

const About = lazy(() => import('./pages/Home').then(m => ({ default: m.Home })))
const Radar = lazy(() => import('./pages/Radar').then(m => ({ default: m.Radar })))
const OpportunityPage = lazy(() => import('./pages/OpportunityPage').then(m => ({ default: m.OpportunityPage })))
const Launchpad = lazy(() => import('./pages/Launchpad').then(m => ({ default: m.Launchpad })))
const PlanPage = lazy(() => import('./pages/Launchpad').then(m => ({ default: m.PlanPage })))
const SignIn = lazy(() => import('./pages/SignIn').then(m => ({ default: m.SignIn })))
const HubPages = () => import('./pages/Hub')
const HubHome = lazy(() => HubPages().then(m => ({ default: m.HubHome })))
const SectionPage = lazy(() => HubPages().then(m => ({ default: m.SectionPage })))
const TopicPage = lazy(() => HubPages().then(m => ({ default: m.TopicPage })))
const FacilitiesBuilder = lazy(() => import('./pages/HubTools').then(m => ({ default: m.FacilitiesBuilder })))
const Letters = lazy(() => import('./pages/HubTools').then(m => ({ default: m.Letters })))
const Expertise = lazy(() => import('./pages/Find').then(m => ({ default: m.Expertise })))
const News = lazy(() => import('./pages/Find').then(m => ({ default: m.News })))
const SearchPage = lazy(() => import('./pages/Start').then(m => ({ default: m.SearchPage })))
const Partners = lazy(() => import('./pages/Find').then(m => ({ default: m.Partners })))
const FacultyDirectory = lazy(() => import('./pages/FacultyDirectory').then(m => ({ default: m.FacultyDirectory })))

// Load a page's code when someone hovers or focuses its menu item, so the click feels instant.
const PRELOAD: Record<string, () => Promise<unknown>> = {
  '/hub': HubPages, '/launchpad': () => import('./pages/Launchpad'), '/expertise': () => import('./pages/Find'),
  '/news': () => import('./pages/Find'), '/about': () => import('./pages/Home'),
}

// Top menu, as in the GRAPPH mockups. `match` lists the paths that belong to each item.
const ICON = (d: string) => <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>
const NAV: { to: string; label: string; d: string; match: string[] }[] = [
  { to: '/', label: 'Home', d: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z', match: [] },
  { to: '/hub', label: 'Pathways', d: 'M6 18a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM12 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM7.5 14.5l3.5-6M13.5 5.5l3 1.5', match: ['/hub'] },
  { to: '/launchpad', label: 'Toolkit', d: 'M6 3h9l4 4v14H6zM9 9h6M9 13h6M9 17h4', match: ['/toolkit', '/launchpad', '/radar'] },
  { to: '/expertise', label: 'Expertise & Support', d: 'M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4 4-6 8-6s8 2 8 6', match: ['/expertise', '/directory', '/faculty', '/partners'] },
  { to: '/news', label: 'News & Updates', d: 'M4 5h13v14H6a2 2 0 0 1-2-2zM17 9h3v8a2 2 0 0 1-2 2M8 9h5M8 13h5', match: ['/news'] },
  { to: '/about', label: 'About YIGH', d: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5M12 8h.01', match: ['/about'] },
]

export default function App() {
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  const nav = useNavigate()
  const [q, setQ] = useState('')
  useEffect(() => { setOpen(false); window.scrollTo({ top: 0 }) }, [loc.pathname])
  const home = loc.pathname === '/'
  const search = (e: FormEvent) => { e.preventDefault(); if (q.trim()) nav(`/search?q=${encodeURIComponent(q.trim())}`) }
  return (
    <div className="app app--top">
      {home && <header className="gbanner">
        <Link to="/" className="gbanner__brand" aria-label="GRAPPH home">
          <svg viewBox="0 0 64 64" width="64" height="64" aria-hidden className="gbanner__logo">
            <g stroke="#fff" strokeWidth="2.2"><line x1="12" y1="40" x2="26" y2="14" /><line x1="26" y1="14" x2="48" y2="20" /><line x1="26" y1="14" x2="34" y2="44" /><line x1="12" y1="40" x2="34" y2="44" /><line x1="48" y1="20" x2="52" y2="46" /><line x1="34" y1="44" x2="52" y2="46" /></g>
            <g fill="#fff"><circle cx="12" cy="40" r="5" /><circle cx="26" cy="14" r="6" /><circle cx="34" cy="44" r="5" /></g>
            <circle cx="48" cy="20" r="5" fill="#ffffff" /><circle cx="52" cy="46" r="4.5" fill="#63aaff" />
          </svg>
          <span>
            <small className="gbanner__org">Yale Institute for Global Health</small>
            <strong className="gbanner__name">GRA<em>P</em>PH</strong>
            <span className="gbanner__full">Global Health Research and Projects Hub</span>
            <span className="gbanner__tag">Hub for Global Health at Yale</span>
          </span>
        </Link>
        <p className="gbanner__words" aria-hidden>People<br />Partnerships<br />Projects<br />Knowledge<span>A more equitable<br />healthier world</span></p>
      </header>}

      <div className={`topnav ${home ? '' : 'topnav--brand'}`}>
        {!home && <Link to="/" className="topnav__brand" aria-label="GRAPPH home" viewTransition>
          <svg viewBox="0 0 64 64" width="30" height="30" aria-hidden>
            <g stroke="#00356b" strokeWidth="3"><line x1="12" y1="40" x2="26" y2="14" /><line x1="26" y1="14" x2="48" y2="20" /><line x1="26" y1="14" x2="34" y2="44" /><line x1="12" y1="40" x2="34" y2="44" /></g>
            <g fill="#00356b"><circle cx="12" cy="40" r="6" /><circle cx="26" cy="14" r="7" /><circle cx="34" cy="44" r="6" /></g><circle cx="48" cy="20" r="6" fill="#1271e3" />
          </svg><strong>GRA<em>P</em>PH</strong></Link>}
        <button className="topnav__toggle" aria-expanded={open} aria-label="Menu" onClick={() => setOpen(o => !o)}>☰ Menu</button>
        <nav aria-label="Main" className={open ? 'is-open' : ''}>
          {NAV.map(n => {
            const on = n.to === '/' ? loc.pathname === '/' : n.match.some(m => loc.pathname.startsWith(m))
            return <NavLink key={n.to} to={n.to} end={n.to === '/'} className={on ? 'active' : ''} aria-current={on ? 'page' : undefined} viewTransition
              onMouseEnter={() => PRELOAD[n.to]?.()} onFocus={() => PRELOAD[n.to]?.()}>{ICON(n.d)}{n.label}</NavLink>
          })}
        </nav>
        <form className="topnav__search" role="search" onSubmit={search}>
          {ICON('M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-5-5')}
          <input type="search" value={q} onChange={e => setQ(e.target.value)} placeholder="Search GRAPPH…" aria-label="Search GRAPPH" />
        </form>
        <AccountMenu />
      </div>

      <div className="app__body">
        <main>
          <Suspense fallback={<PageSkeleton />}>
            <div key={loc.pathname} className="page-enter">
            <Routes>
              <Route path="/" element={<Start />} />
              <Route path="/about" element={<About />} />
              <Route path="/toolkit" element={<Navigate to="/launchpad" replace />} />
              <Route path="/expertise" element={<Expertise />} />
              <Route path="/news" element={<News />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/partners" element={<Partners />} />
              <Route path="/find" element={<Navigate to="/expertise" replace />} />
              <Route path="/plan" element={<Navigate to="/launchpad" replace />} />
              <Route path="/do" element={<Navigate to="/hub" replace />} />
              <Route path="/dashboard" element={<Navigate to="/" replace />} />
              <Route path="/hub" element={<HubHome />} />
              <Route path="/launchpad/facilities" element={<FacilitiesBuilder />} />
              <Route path="/launchpad/letters" element={<Letters />} />
              <Route path="/launchpad/plan" element={<PlanPage />} />
              <Route path="/hub/tools/facilities" element={<Navigate to="/launchpad/facilities" replace />} />
              <Route path="/hub/tools/letters" element={<Navigate to="/launchpad/letters" replace />} />
              <Route path="/hub/comply" element={<Navigate to="/hub/setup" replace />} />
              <Route path="/hub/:section" element={<SectionPage />} />
              <Route path="/hub/:section/:slug" element={<TopicPage />} />
              <Route path="/radar" element={<Radar />} />
              <Route path="/radar/:id" element={<OpportunityPage />} />
              <Route path="/directory" element={<FacultyDirectory />} />
              <Route path="/constellation" element={<Navigate to="/directory" replace />} />
              <Route path="/faculty/:id" element={<Profile />} />
              <Route path="/signin" element={<SignIn />} />
              <Route path="/launchpad" element={<Launchpad />} />
              <Route path="/network" element={<Navigate to="/directory" replace />} />
              <Route path="*" element={<EmptyState title="Page not found" action={<Link className="btn" to="/">Go to the home page</Link>} />} />
            </Routes>
            </div>
          </Suspense>
        </main>
        <footer className="site-footer">
          <div className="site-footer__inner">
            <div><strong className="site-footer__brand">Yale Institute for Global Health</strong>
              <p>PO Box 208034<br />New Haven, CT 06520-8034</p></div>
            <div><h4>Explore</h4><ul><li><Link to="/hub">Pathways</Link></li><li><Link to="/launchpad">Toolkit</Link></li><li><Link to="/radar">Funding</Link></li>
              <li><Link to="/directory">Faculty Directory</Link></li><li><Link to="/partners">Partners</Link></li><li><Link to="/launchpad">My project</Link></li>
              <li><Link to="/launchpad/facilities">Facilities builder</Link></li><li><Link to="/launchpad/letters">Letters of support</Link></li>
              <li><Link to="/about">About YIGH</Link></li></ul></div>
            <div><h4>YIGH</h4><ul><li><a href="https://medicine.yale.edu/yigh/" target="_blank" rel="noreferrer">YIGH website ↗</a></li>
              <li><a href="https://medicine.yale.edu/yigh/news" target="_blank" rel="noreferrer">News ↗</a></li>
              <li><a href="https://medicine.yale.edu/about/contact-us/" target="_blank" rel="noreferrer">Contact ↗</a></li></ul></div>
          </div>
          <p className="site-footer__note">Data from public Yale faculty profiles, YIGH pages, Yale office pages and official funder records. Tags, matches and team proposals are generated and should be verified.</p>
        </footer>
      </div>
      <Feedback />
      <ChatWidget />
    </div>
  )
}

function AccountMenu() {
  const { user, ready, signOut } = useAuth()
  const loc = useLocation()
  if (!ready) return null
  if (!user) return loc.pathname === '/signin' ? null
    : <Link className="nav-signin" to={`/signin?next=${encodeURIComponent(loc.pathname + loc.search + loc.hash)}`}>Sign in</Link>
  const initials = user.name.split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()
  return (
    <details className="avatar">
      <summary aria-label={`Account: ${user.name}`} title={user.email}>{initials}</summary>
      <div className="avatar__menu"><strong>{user.name}</strong><span className="muted small">{user.email}</span>
        <Link to="/launchpad">My project</Link>
        <button className="link-btn" onClick={signOut}>Sign out</button></div>
    </details>
  )
}
