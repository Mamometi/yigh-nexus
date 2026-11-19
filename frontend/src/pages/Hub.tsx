import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { HubIcon } from '../components/HubIcon'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { hub, type Topic } from '../hub'
import { useAsync, useDebounced } from '../hooks'
import { SaveButton } from '../components/SaveButton'
import { Stages } from './Start'

const WAVE = <svg className="wave" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden><path d="M0,40 C360,90 1080,-10 1440,40 L1440,80 L0,80 Z" /></svg>


/** /hub — the five lifecycle sections, search and tools */
export function HubHome() {
  const [state, retry] = useAsync(hub.sections, [])
  return (
    <div className="page osf hub">
      <header className="osf-head">
        <div className="osf-head__inner">
          <p className="eyebrow eyebrow--light">Pathways</p>
          <h1>Global health pathways at Yale</h1>
          <p className="lede">Step-by-step guides for global health research and projects at Yale: who to talk to, what to do first,
            and where to do it. Every guide links to the Yale office that owns the process.</p>
          <HubSearch />
        </div>
        {WAVE}
      </header>

      <section className="hub-life" aria-label="Project lifecycle">
        {state.status === 'loading' && <Loading />}
        {state.status === 'error' && <ErrorState message={state.error} onRetry={retry} />}
        {state.status === 'success' && <Stages sections={state.data} />}
      </section>

    </div>
  )
}

export function HubSearch() {
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
          <p className="eyebrow eyebrow--light"><Link to="/">Home</Link> › <Link to="/hub">Pathways</Link></p>
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
        {(s.links ?? []).map(l => (
          <Link key={l.path} to={l.path} className="hub-topic-card hub-topic-card--tool" style={{ '--c': s.color } as React.CSSProperties}>
            <h3>{l.title}</h3><p>A GRAPPH tool for this stage.</p><span className="hub-topic-card__go">Open the tool →</span>
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
      <nav className="crumbs small" aria-label="Breadcrumb"><Link to="/">Home</Link> › <Link to="/hub">Pathways</Link> › <Link to={`/hub/${s.slug}`}>{s.title}</Link> › <span>{t.title}</span></nav>
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
            <div className="topic__meta">
              {t.last_reviewed && <span className="muted small">Last reviewed: {new Date(t.last_reviewed + 'T12:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>}
              <span className="topic__acts">
                <button className="link-btn small" onClick={() => window.print()}>🖶 Print</button>
                <ShareButton title={t.title} />
                <SaveButton small item={{ kind: 'guide', id: t.slug, title: t.title, sub: s.title, url: `/hub/${s.slug}/${t.slug}` }} />
              </span>
            </div>
            <h1>{t.title}</h1>
            <p className="lede">{t.summary}</p>
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

function ShareButton({ title }: { title: string }) {
  const [done, setDone] = useState(false)
  const share = async () => {
    const url = window.location.href
    try {
      if (navigator.share) await navigator.share({ title, url })
      else { await navigator.clipboard.writeText(url); setDone(true); setTimeout(() => setDone(false), 2000) }
    } catch { /* the person closed the share sheet */ }
  }
  return <button className="link-btn small" onClick={share}>{done ? '✓ Link copied' : '⤴ Share'}</button>
}
