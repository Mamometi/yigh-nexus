import { lazy, Suspense } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './auth'
import { ChatWidget } from './components/ChatWidget'
import { EmptyState, Loading } from './components/StateViews'
import { Home } from './pages/Home'
import { Profile } from './pages/Profile'

const Radar = lazy(() => import('./pages/Radar').then(m => ({ default: m.Radar })))
const OpportunityPage = lazy(() => import('./pages/OpportunityPage').then(m => ({ default: m.OpportunityPage })))
const Launchpad = lazy(() => import('./pages/Launchpad').then(m => ({ default: m.Launchpad })))
const SignIn = lazy(() => import('./pages/SignIn').then(m => ({ default: m.SignIn })))
const FacultyDirectory = lazy(() => import('./pages/FacultyDirectory').then(m => ({ default: m.FacultyDirectory })))

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand" aria-label="YIGH Nexus home">
          <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden>
            <g stroke="#b4e7f8" strokeOpacity=".8"><line x1="6" y1="22" x2="14" y2="9" /><line x1="14" y1="9" x2="25" y2="13" /><line x1="14" y1="9" x2="19" y2="25" /></g>
            <g fill="#ffffff"><circle cx="6" cy="22" r="2.2" /><circle cx="14" cy="9" r="3" /><circle cx="25" cy="13" r="2.2" /><circle cx="19" cy="25" r="2.2" /></g>
          </svg>
          <span><strong>YIGH Nexus</strong><small>Yale Institute for Global Health</small></span>
        </Link>
        <nav aria-label="Main">
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/radar">Opportunity Radar</NavLink>
          <NavLink to="/directory">Faculty Directory</NavLink>
          <NavLink to="/launchpad">Team Launchpad</NavLink>
          <AccountMenu />
        </nav>
      </header>
      <main>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/dashboard" element={<Navigate to="/" replace />} />
            <Route path="/radar" element={<Radar />} />
            <Route path="/radar/:id" element={<OpportunityPage />} />
            <Route path="/directory" element={<FacultyDirectory />} />
            <Route path="/constellation" element={<Navigate to="/directory" replace />} />
            <Route path="/faculty/:id" element={<Profile />} />
            <Route path="/signin" element={<SignIn />} />
            <Route path="/launchpad" element={<Launchpad />} />
            <Route path="/network" element={<Navigate to="/directory" replace />} />
            <Route path="*" element={<EmptyState title="Page not found" action={<Link className="btn" to="/">Go to the dashboard</Link>} />} />
          </Routes>
        </Suspense>
      </main>
      <ChatWidget />
      <footer className="site-footer">
        <div className="site-footer__inner">
          <div><strong className="site-footer__brand">Yale Institute for Global Health</strong>
            <p>PO Box 208034<br />New Haven, CT 06520-8034</p></div>
          <div><h4>Explore</h4><ul><li><Link to="/radar">Opportunity Radar</Link></li><li><Link to="/directory">Faculty Directory</Link></li><li><Link to="/launchpad">Team Launchpad</Link></li></ul></div>
          <div><h4>YIGH</h4><ul><li><a href="https://medicine.yale.edu/yigh/" target="_blank" rel="noreferrer">YIGH website ↗</a></li>
            <li><a href="https://medicine.yale.edu/yigh/news" target="_blank" rel="noreferrer">News ↗</a></li>
            <li><a href="https://medicine.yale.edu/about/contact-us/" target="_blank" rel="noreferrer">Contact ↗</a></li></ul></div>
        </div>
        <p className="site-footer__note">Data from public Yale faculty profiles, YIGH pages and official funder records. Tags, matches and team proposals are generated and should be verified.</p>
      </footer>
    </div>
  )
}

function AccountMenu() {
  const { user, ready, signOut } = useAuth()
  const loc = useLocation()
  if (!ready) return null
  if (!user) return loc.pathname === '/signin' ? null
    : <Link className="nav-signin" to={`/signin?next=${encodeURIComponent(loc.pathname + loc.search + loc.hash)}`}>Sign in</Link>
  return (
    <span className="nav-user">
      <span className="nav-user__name" title={user.email}>{user.name.split(' ')[0]}</span>
      <button className="nav-signout" onClick={signOut}>Sign out</button>
    </span>
  )
}
