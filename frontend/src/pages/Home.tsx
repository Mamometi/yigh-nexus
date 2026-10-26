import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { radar } from '../api'
import { Deadline } from '../components/OppCardView'
import { ErrorState, Loading } from '../components/StateViews'
import { PRIORITY_COLORS } from '../components/Tags'
import { useAsync } from '../hooks'

interface Named { name: string; text: string }
interface HomeData {
  profile: {
    plan_source: string; tagline: { text: string }; subtagline: string; intro: string; history: string
    mission: { text: string }; vision: string
    values: (Named & { letter: string })[]
    approach: { intro: string; items: Named[] }
    priorities_intro: string; priorities: { slug: string; name: string; letter: string; summary: string; text: string }[]
    pillars_intro: string; pillars: Named[]; tools_link: string
    figures: { value: string; label: string; detail: string }[]; figures_source: string
    newsletter_url: string
  }
  live: {
    faculty: { total: number }
    opportunities: { open: number; verified_open: number }
    partners: { organizations: number }
    priorities: Record<string, { faculty: number; open_opportunities: number }>
    watchlist: { automated: number }
  }
  news: { title: string; url: string; summary: string; date: string | null; image: string | null; image_alt: string | null }[]
  news_source: string
}

const getHome = async (): Promise<HomeData> => {
  const r = await fetch('/api/home')
  if (!r.ok) throw new Error(`Request failed (${r.status})`)
  return r.json()
}
const newsDate = (d: string | null) => {
  const t = d ? new Date(d.replace(/\s+Z$/, ' GMT')) : null
  return t && !isNaN(t.getTime()) ? t.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }) : ''
}

export function Home() {
  const [state, retry] = useAsync(getHome, [])
  const [brief] = useAsync(radar.brief, [])
  useHomeMotion(state.status === 'success', brief.status)
  if (state.status === 'loading') return <Loading label="Loading…" />
  if (state.status === 'error') return <ErrorState message={state.error} onRetry={retry} />
  const { profile: p, live, news } = state.data

  return (
    <div className="home">
      <Hero p={p} />
      <div className="home__body">
        <section className="home-sec home-about">
          <p className="eyebrow">About YIGH</p>
          <p className="home-about__lead">{p.intro}</p>
          <div className="mv">
            <div><h3>Mission</h3><p>{p.mission.text}</p></div>
            <div><h3>Vision</h3><p>{p.vision}</p></div>
          </div>
          <p className="home-about__history">{p.history}</p>
          <div className="figures">
            {p.figures.map(f => <div key={f.label} className="figure"><span className="figure__v">{f.value}</span><span className="figure__l">{f.label}</span><span className="figure__d">{f.detail}</span></div>)}
          </div>
        </section>

        <section className="home-sec">
          <p className="eyebrow">Our values</p>
          <h2 className="home-sec__title">How we work</h2>
          <div className="values">
            {p.values.map(v => (
              <article key={v.name} className="value"><span className="value__letter" aria-hidden>{v.letter}</span><h3>{v.name}</h3><p>{v.text}</p></article>
            ))}
          </div>
        </section>

        <section className="home-sec">
          <p className="eyebrow">Strategic priorities</p>
          <h2 className="home-sec__title">Where Yale brings distinctive expertise</h2>
          <p className="home-sec__lede">{p.priorities_intro}</p>
          <div className="prio-grid">{p.priorities.map(pr => <PriorityCard key={pr.slug} pr={pr} live={live.priorities[pr.name]} />)}</div>
        </section>
        <section className="home-sec">
          <p className="eyebrow">Institutional pillars</p>
          <h2 className="home-sec__title">Partners. Leaders. Innovators. Scholars.</h2>
          <p className="home-sec__lede">{p.pillars_intro}</p>
          <Temple pillars={p.pillars} />
        </section>

      </div>

      <section className="home-approach home-tools">
        <div className="home-approach__inner">
          <p className="eyebrow eyebrow--light">Tools on this site</p>
          <h2>Funding intelligence and collaborator matchmaking</h2>
          <p className="home-approach__intro">{p.tools_link}</p>
          <div className="tool-grid">
            <Link to="/radar" className="tool-card"><h3>Opportunity Radar</h3>
              <p>Find grants that fit your work. We check funders every week, so you can see what’s open now and what’s coming up.</p><span className="tool-card__go">Browse opportunities →</span></Link>
            <Link to="/directory" className="tool-card"><h3>Faculty Directory</h3>
              <p>Meet Yale faculty working in global health. See what they study, where they work, and who might make a good collaborator.</p><span className="tool-card__go">Find faculty →</span></Link>
            <Link to="/launchpad" className="tool-card"><h3>Team Launchpad</h3>
              <p>Found a grant you like? Get ideas for who to team up with at Yale and beyond, plus a one-page outline to get started.</p><span className="tool-card__go">Open the Launchpad →</span></Link>
          </div>
        </div>
      </section>

      <div className="home__body">

        <section className="home-sec">
          <div className="home-sec__head"><h2>Funding closing soon</h2><Link to="/radar">See all opportunities →</Link></div>
          {brief.status === 'success' && (
            <div className="opps-strip">
              {(brief.data.closing_soon.length ? brief.data.closing_soon : brief.data.highlights).slice(0, 3).map(o => (
                <Link key={o.id} to={`/radar/${o.id}`} className="opp-mini"><span className="opp-mini__funder">{o.funder}</span><h3>{o.title}</h3><Deadline o={o} /></Link>
              ))}
            </div>
          )}
        </section>

        <section className="home-sec">
          <div className="home-sec__head"><h2>Latest from YIGH</h2><a href={state.data.news_source} target="_blank" rel="noreferrer">See all news →</a></div>
          <div className="news-grid">
            {news.map(n => (
              <a key={n.url} className="news-card" href={n.url} target="_blank" rel="noreferrer">
                {n.image ? <img src={n.image} alt={n.image_alt ?? ''} loading="lazy" /> : <div className="news-card__ph" />}
                <div className="news-card__body">
                  {newsDate(n.date) && <span className="news-card__date">{newsDate(n.date)}</span>}
                  <h3>{n.title}</h3><p>{n.summary}</p><span className="news-card__more">Read more</span>
                </div>
              </a>
            ))}
          </div>
        </section>

        <p className="muted small home__source">Institutional text: {p.plan_source}. Figures: <a href="https://medicine.yale.edu/yigh/" target="_blank" rel="noreferrer">YIGH website</a>.</p>
      </div>

      <section className="home-news">
        <svg className="wave wave--top" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden><path d="M0,40 C360,-10 1080,90 1440,40 L1440,0 L0,0 Z" /></svg>
        <div className="home-news__inner">
          <h2>Stay connected</h2>
          <p>Receive YIGH’s monthly Global Health Update with news, events and opportunities.</p>
          <a className="btn btn--lg btn--light" href={p.newsletter_url} target="_blank" rel="noreferrer">Subscribe to the Global Health Update ↗</a>
        </div>
      </section>
    </div>
  )
}

function Hero({ p }: { p: HomeData['profile'] }) {
  return (
    <section className="home-hero">
      <svg className="home-hero__stars" viewBox="0 0 600 400" aria-hidden>
        <g stroke="#b4e7f8" strokeOpacity=".35"><line x1="80" y1="300" x2="190" y2="140" /><line x1="190" y1="140" x2="330" y2="190" />
          <line x1="330" y1="190" x2="460" y2="90" /><line x1="330" y1="190" x2="400" y2="320" /><line x1="460" y1="90" x2="540" y2="210" /></g>
        <g fill="#fff">{[[80, 300, 4], [190, 140, 6], [330, 190, 5], [460, 90, 4], [400, 320, 3], [540, 210, 4]].map(([x, y, r]) => <circle key={x} cx={x} cy={y} r={r} />)}</g>
      </svg>
      <div className="home-hero__inner">
        <p className="eyebrow eyebrow--light">Yale Institute for Global Health</p>
        <h1>{p.tagline.text}</h1>
        <p className="home-hero__sub">{p.subtagline}</p>
      </div>
      <svg className="wave" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden><path d="M0,40 C360,90 1080,-10 1440,40 L1440,80 L0,80 Z" /></svg>
    </section>
  )
}

function PriorityCard({ pr, live }: { pr: HomeData['profile']['priorities'][number]; live?: { faculty: number; open_opportunities: number } }) {
  const [open, setOpen] = useState(false)
  return (
    <article className="prio-card" style={{ '--c': PRIORITY_COLORS[pr.slug] } as React.CSSProperties}>
      <span className="prio-card__letter" aria-hidden>{pr.letter}</span>
      <h3>{pr.name}</h3>
      <p>{open ? pr.text : pr.summary}</p>
      <button className="link-btn small" aria-expanded={open} onClick={() => setOpen(o => !o)}>{open ? 'Show less' : 'Read more'}</button>
      <div className="prio-card__links">
        <Link to={`/directory?priority=${pr.slug}`}><strong>{live?.faculty ?? 0}</strong> faculty</Link>
        <Link to={`/radar?priority=${pr.slug}`}><strong>{live?.open_opportunities ?? 0}</strong> open opportunities</Link>
      </div>
    </article>
  )
}

const PILLAR_ICONS: Record<string, ReactNode> = {
  Partners: <path d="M2 12l4-4 4 2 2-1 3 2 3-2 4 3M6 8l-4 4 6 6 2-1M18 9l4 3-6 6-2-1m-6-1 2 2m0-4 3 3m-1-5 3 3" />,
  Leaders: <><circle cx="12" cy="7" r="3" /><circle cx="5" cy="9" r="2.3" /><circle cx="19" cy="9" r="2.3" /><path d="M6 20a6 6 0 0 1 12 0M1 19a4 4 0 0 1 5-4M23 19a4 4 0 0 0-5-4" /></>,
  Innovators: <><path d="M9 17h6M10 20h4M8.5 14a5 5 0 1 1 7 0c-.8.8-1.5 1.7-1.5 3h-4c0-1.3-.7-2.2-1.5-3z" /><path d="M12 1v2M3 9H1m22 0h-2M5 3l1.5 1.5M19 3l-1.5 1.5" /></>,
  Scholars: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18M5 7h14M5 17h14" /></>,
}

function Temple({ pillars }: { pillars: Named[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (!('IntersectionObserver' in window)) { setShown(true); return }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setShown(true); io.disconnect() } }, { threshold: 0.25 })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <div ref={ref} className={`temple ${shown ? 'is-in' : ''}`} role="list" aria-label="Institutional pillars">
      <div className="temple__roof" aria-hidden>
        <div className="temple__pediment"><span className="temple__t1">Yale Institute for</span><span className="temple__t2">Global Health</span></div>
        <div className="temple__beam" />
      </div>
      <div className="temple__cols">
        {pillars.map((pl, i) => (
          <article key={pl.name} className="column" role="listitem" style={{ '--i': i } as React.CSSProperties}>
            <div className="column__capital" aria-hidden><span /><span /></div>
            <div className="column__shaft">
              <span className="column__n">{i + 1}</span>
              <svg className="column__icon" viewBox="0 0 24 24" aria-hidden>{PILLAR_ICONS[pl.name] ?? <circle cx="12" cy="12" r="8" />}</svg>
              <h3>{pl.name}</h3>
              <p>{pl.text}</p>
            </div>
            <div className="column__base" aria-hidden><span /><span /></div>
          </article>
        ))}
      </div>
      <div className="temple__floor" aria-hidden />
    </div>
  )
}

const REVEAL = ['.home-sec__head', '.home-sec > .eyebrow', '.home-sec__title', '.home-sec__lede', '.home-about__lead', '.mv > div', '.home-about__history',
  '.figure', '.value', '.prio-card', '.home-approach__inner > *:not(.tool-grid)', '.tool-card', '.opp-mini', '.news-card', '.home-news__inner > *', '.home__source']

/** Scroll-triggered reveals (staggered within each group) and count-up numbers for the Home page. */
function useHomeMotion(ready: boolean, extra: string) {
  useEffect(() => {
    if (!ready) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const els = Array.from(document.querySelectorAll<HTMLElement>(REVEAL.map(s => `.home ${s}`).join(','))).filter(e => !e.classList.contains('is-in'))
    els.forEach(el => {
      if (el.classList.contains('reveal')) return
      const sibs = Array.from(el.parentElement?.children ?? []).filter(c => c.matches(REVEAL.join(',')))
      el.style.setProperty('--d', `${Math.min(sibs.indexOf(el), 6) * 90}ms`)
      el.classList.add('reveal')
    })
    const nums = Array.from(document.querySelectorAll<HTMLElement>('.home .figure__v, .home .tool-card__num')).filter(n => !n.dataset.counted)
    if (reduce || !('IntersectionObserver' in window)) { els.forEach(e => e.classList.add('is-in')); return }
    const countUp = (n: HTMLElement) => {
      const m = n.textContent?.match(/^(\d[\d,]*)(.*)$/)
      if (!m || n.dataset.counted) return
      n.dataset.counted = '1'
      const target = Number(m[1].replace(/,/g, '')), suffix = m[2], t0 = performance.now(), dur = 1200
      if (target >= 1900 && target <= 2100) return // years stay as-is
      const step = (t: number) => {
        const k = Math.min(1, (t - t0) / dur), v = Math.round(target * (1 - Math.pow(1 - k, 3)))
        n.textContent = `${v.toLocaleString()}${suffix}`
        if (k < 1) requestAnimationFrame(step)
      }
      requestAnimationFrame(step)
    }
    const io = new IntersectionObserver(entries => entries.forEach(e => {
      if (!e.isIntersecting && e.boundingClientRect.top > 0) return
      e.target.classList.add('is-in')
      e.target.querySelectorAll<HTMLElement>('.figure__v, .tool-card__num').forEach(countUp)
      if ((e.target as HTMLElement).matches('.figure__v, .tool-card__num')) countUp(e.target as HTMLElement)
      io.unobserve(e.target)
    }), { threshold: 0.15, rootMargin: '0px 0px -40px 0px' })
    els.forEach(e => io.observe(e))
    nums.forEach(n => io.observe(n))
    // Jumping down the page (End key, a big scroll, a link) skips the observer: reveal everything already above the fold's bottom.
    let raf = 0
    const sweep = () => {
      raf = 0
      document.querySelectorAll<HTMLElement>('.home .reveal:not(.is-in)').forEach(el => {
        if (el.getBoundingClientRect().top < window.innerHeight) {
          el.classList.add('is-in')
          el.querySelectorAll<HTMLElement>('.figure__v, .tool-card__num').forEach(countUp)
          io.unobserve(el)
        }
      })
    }
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(sweep) }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => { io.disconnect(); window.removeEventListener('scroll', onScroll); cancelAnimationFrame(raf) }
  }, [ready, extra])
}
