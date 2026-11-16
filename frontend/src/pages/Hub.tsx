import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { HubIcon } from '../components/HubIcon'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { hub, type Section, type Topic } from '../hub'
import { useAsync, useDebounced } from '../hooks'

const WAVE = <svg className="wave" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden><path d="M0,40 C360,90 1080,-10 1440,40 L1440,80 L0,80 Z" /></svg>

const TOOLS = [
  { to: '/radar', title: 'Opportunities', text: 'Open funding calls, checked against each funder’s own page.' },
  { to: '/directory', title: 'Faculty Directory', text: 'Find Yale faculty by topic, place or priority.' },
  { to: '/launchpad', title: 'Team Launchpad', text: 'Go from a funding call to a team and a one-page concept.' },
  { to: '/hub/tools/facilities', title: 'Facilities & Resources builder', text: 'Put together the Facilities section of a grant from Yale resources.' },
  { to: '/hub/tools/letters', title: 'Letters of support', text: 'Request a letter, and get templates and checklists.' },
]

/** /hub — the five lifecycle sections, search and tools */
export function HubHome() {
  const [state, retry] = useAsync(hub.sections, [])
  return (
    <div className="page osf hub">
      <header className="osf-head">
        <div className="osf-head__inner">
          <p className="eyebrow eyebrow--light">Guides</p>
          <h1>From idea to impact, the Yale way</h1>
          <p className="lede">Step-by-step guides for global health research and projects at Yale: who to talk to, what to do first,
            and where to do it. Every guide links to the Yale office that owns the process.</p>
          <HubSearch />
        </div>
        {WAVE}
      </header>

      <section className="hub-life" aria-label="Project lifecycle">
        {state.status === 'loading' && <Loading />}
        {state.status === 'error' && <ErrorState message={state.error} onRetry={retry} />}
        {state.status === 'success' && <ol className="hub-life__grid">
          {state.data.map((s, i) => <SectionCard key={s.slug} s={s} n={i + 1} />)}
        </ol>}
      </section>

      <section className="hub-tools">
        <h2 className="home-sec__title">Tools to get it done</h2>
        <div className="hub-tools__grid">
          {TOOLS.map(t => <Link key={t.to} to={t.to} className="hub-tool"><HubIcon name="tools" size={22} /><strong>{t.title}</strong><span>{t.text}</span></Link>)}
        </div>
      </section>
    </div>
  )
}

function SectionCard({ s, n }: { s: Section; n: number }) {
  return (
    <li className="hub-sec" style={{ '--c': s.color } as React.CSSProperties}>
      <Link to={`/hub/${s.slug}`} className="hub-sec__head">
        <span className="hub-sec__icon"><HubIcon name={s.icon} /></span>
        <span className="hub-sec__n">{n}</span>
        <h2>{s.title}</h2>
      </Link>
      <p>{s.summary}</p>
      <ul>{s.topics.slice(0, 6).map(t => <li key={t.slug}><Link to={`/hub/${s.slug}/${t.slug}`}>{t.title}</Link></li>)}</ul>
      {s.topics.length === 0 && <p className="muted small">Guides coming soon.</p>}
    </li>
  )
}

function HubSearch() {
  const [q, setQ] = useState('')
  const dq = useDebounced(q.trim(), 250)
  const [hits] = useAsync(() => dq.length > 2 ? hub.search(dq) : Promise.resolve([]), [dq])
  const nav = useNavigate()
  const list = hits.status === 'success' ? hits.data : []
  return (
    <div className="hub-search">
      <input type="search" className="input" placeholder="Search the guides (e.g. visitors, subaward, shipping samples)" aria-label="Search the guides"
             value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && list[0]) nav(list[0].path) }} />
      {dq.length > 2 && hits.status === 'success' && (
        <ul className="hub-search__results">
          {list.length ? list.map(h => <li key={h.path}><Link to={h.path}><strong>{h.title}</strong><span>{h.summary}</span></Link></li>)
            : <li className="muted small">No guides match. Try another word, or ask Nexi in the chat.</li>}
        </ul>
      )}
    </div>
  )
}

/** /hub/:section — one lifecycle section */
export function SectionPage() {
  const { section = '' } = useParams()
  const [state, retry] = useAsync(hub.sections, [])
  if (state.status === 'loading') return <Loading />
  if (state.status === 'error') return <ErrorState message={state.error} onRetry={retry} />
  const s = state.data.find(x => x.slug === section)
  if (!s) return <EmptyState title="Page not found" action={<Link className="btn" to="/hub">All guides</Link>} />
  return (
    <div className="page osf hub">
      <header className="osf-head">
        <div className="osf-head__inner">
          <p className="eyebrow eyebrow--light"><Link to="/hub">Guides</Link></p>
          <h1>{s.title}</h1>
          <p className="lede">{s.summary}</p>
        </div>
        {WAVE}
      </header>
      <div className="hub-topics">
        {s.topics.map(t => (
          <Link key={t.slug} to={`/hub/${s.slug}/${t.slug}`} className="hub-topic-card" style={{ '--c': s.color } as React.CSSProperties}>
            <h3>{t.title}</h3><p>{t.summary}</p><span className="hub-topic-card__go">Open the guide →</span>
          </Link>
        ))}
        {s.topics.length === 0 && <p className="muted">Guides for this section are coming soon.</p>}
      </div>
    </div>
  )
}

/** /hub/:section/:slug — a task page laid out like the GRAPPH mockups */
export function TopicPage() {
  const { section = '', slug = '' } = useParams()
  const [state, retry] = useAsync(() => hub.topic(section, slug), [section, slug])
  if (state.status === 'loading') return <Loading />
  if (state.status === 'error') return state.error.includes('404') || state.error.includes("doesn't exist")
    ? <EmptyState title="Page not found" action={<Link className="btn" to="/hub">All guides</Link>} />
    : <ErrorState message={state.error} onRetry={retry} />
  return <TopicView t={state.data} />
}

function TopicView({ t }: { t: Topic }) {
  const s = t.section_info
  return (
    <div className="page topic" style={{ '--c': s.color } as React.CSSProperties}>
      <nav className="crumbs small" aria-label="Breadcrumb"><Link to="/hub">Guides</Link> › <Link to={`/hub/${s.slug}`}>{s.title}</Link> › <span>{t.title}</span></nav>
      <div className="topic__layout">
        <aside className="topic__side">
          <Link to={`/hub/${s.slug}`} className="topic__sec"><span className="hub-sec__icon"><HubIcon name={s.icon} /></span><strong>{s.title}</strong></Link>
          <ol className="topic__nav">
            {t.siblings.map(x => <li key={x.slug} className={x.slug === t.slug ? 'is-on' : ''}><Link to={`/hub/${s.slug}/${x.slug}`}>{x.title}</Link></li>)}
          </ol>
          {t.office && (
            <div className="topic__help">
              <h3>Need help?</h3>
              <p className="small">This process is run by <strong>{t.office.name}</strong>.</p>
              {t.office.url && <a className="btn btn--ghost btn--sm" href={t.office.url} target="_blank" rel="noreferrer">Contact the office ↗</a>}
              {t.office.email && <p className="small"><a href={`mailto:${t.office.email}`}>{t.office.email}</a></p>}
            </div>
          )}
        </aside>

        <article className="topic__main">
          <header className="topic__head">
            <h1>{t.title}</h1>
            <p className="lede">{t.summary}</p>
            <p className="muted small">{t.last_reviewed && <>Last reviewed {new Date(t.last_reviewed + 'T12:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} · </>}
              <button className="link-btn small" onClick={() => window.print()}>Print</button></p>
          </header>

          {!!t.key_considerations?.length && (
            <section className="topic__box topic__box--key"><h2>Key considerations</h2><ul>{t.key_considerations.map(k => <li key={k}>{k}</li>)}</ul></section>
          )}

          {!!t.steps?.length && (
            <section><h2>Steps in the process</h2>
              <ol className="topic__steps">
                {t.steps.map((st, i) => (
                  <li key={st.title}><span className="topic__stepn">{i + 1}</span><strong>{st.title}</strong><p>{st.detail}</p>
                    {st.url && <a className="small" href={st.url} target="_blank" rel="noreferrer">Go there ↗</a>}</li>
                ))}
              </ol>
            </section>
          )}

          <div className="topic__cols">
            {!!t.resources?.length && (
              <section className="topic__box"><h2>Key resources</h2>
                <ul className="topic__links">{t.resources.map(r => <li key={r.url}><a href={r.url} target="_blank" rel="noreferrer">{r.title} ↗</a>{r.note && <span>{r.note}</span>}</li>)}</ul>
              </section>
            )}
            {t.related.length > 0 && (
              <section className="topic__box"><h2>Related topics</h2>
                <ul className="topic__links">{t.related.map(r => <li key={r.slug}><Link to={`/hub/${r.section}/${r.slug}`}>{r.title}</Link><span>{r.summary}</span></li>)}</ul>
              </section>
            )}
          </div>

          {!!t.good_to_know?.length && (
            <section className="topic__box topic__box--good"><h2>Good to know</h2><ul>{t.good_to_know.map(g => <li key={g}>{g}</li>)}</ul></section>
          )}
          {t.important && <section className="topic__box topic__box--warn"><h2>Important</h2><p>{t.important}</p></section>}

          {!!t.sources?.length && (
            <details className="topic__sources small"><summary>Where this information comes from</summary>
              <p className="muted">Summarized from these public Yale pages. Always check the office’s page for the latest rules.</p>
              <ul>{t.sources.map(u => <li key={u}><a href={u} target="_blank" rel="noreferrer">{u}</a></li>)}</ul>
            </details>
          )}
        </article>
      </div>
    </div>
  )
}
