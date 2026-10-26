import { Link } from 'react-router-dom'
import { radar, type TimingOpp } from '../api'
import { useAsync } from '../hooks'
import { fmtDate } from './OppCardView'
import { ErrorState, Loading } from './StateViews'

const day = (d: string | null) => (d ? fmtDate(d.slice(0, 10)) : null)

function OppLine({ o, what }: { o: TimingOpp; what: 'opened' | 'closed' | 'open' | 'forecast' | 'recorded' }) {
  const deadline = o.deadline ? day(o.deadline) : o.deadline_text
  return (
    <li>
      <Link to={`/radar/${o.id}`}>{o.title}</Link>
      <span className="muted small">
        {what === 'opened' && o.posted_date && <> · posted {day(o.posted_date)}</>}
        {what === 'recorded' && <> · first seen by the Radar {day(o.first_seen_at)}</>}
        {(what === 'open' || what === 'opened') && deadline && <> · deadline {deadline}</>}
        {what === 'forecast' && <>{o.posted_date && <> · forecast posted {day(o.posted_date)}</>}{deadline && <> · estimated deadline {deadline}</>}</>}
        {what === 'closed' && deadline && <> · closed {deadline}</>}
      </span>
    </li>
  )
}

/** Feedback for a selected funder: what is open, what is forecasted, and when it last opened/closed, from recorded dates only. */
export function FunderTimingPanel({ slug }: { slug: string }) {
  const [t, retry] = useAsync(() => radar.funderTiming(slug), [slug])
  if (t.status === 'loading') return <div className="ftime"><Loading label="Checking this funder’s history…" /></div>
  if (t.status === 'error') return <div className="ftime"><ErrorState message={t.error} onRetry={retry} /></div>
  const d = t.data
  const checked = d.watch.map(w => w.last_checked_at).filter(Boolean).sort().at(-1) ?? null
  const pending = d.watch.some(w => w.page_change_pending)
  const manual = d.watch.length > 0 && d.watch.every(w => w.access_method === 'manual')
  return (
    <section className="ftime" aria-live="polite" aria-label={`Funding timing for ${d.funder.name}`}>
      <p className="eyebrow">Funder timing</p>
      <h2>{d.funder.name}</h2>
      <p className="ftime__headline">{d.headline}</p>
      <div className="ftime__grid">
        <div className="ftime__cell">
          <span className="osf-label">Last opened</span>
          {d.last_opened ? <ul className="plain"><OppLine o={d.last_opened} what="opened" /></ul>
            : d.first_recorded ? <><p className="small">This funder does not publish posting dates. Most recent call on record:</p>
                <ul className="plain"><OppLine o={d.first_recorded} what="recorded" /></ul></>
            : <p className="muted small">No call recorded yet.</p>}
          {d.last_closed && <><span className="osf-label mt-s">Most recent close</span><ul className="plain"><OppLine o={d.last_closed} what="closed" /></ul></>}
        </div>
        <div className="ftime__cell ftime__cell--next">
          <span className="osf-label">Opening again</span>
          {d.open_now.length > 0 && <><p className="small"><strong>Open now:</strong></p><ul className="plain">{d.open_now.slice(0, 3).map(o => <OppLine key={o.id} o={o} what="open" />)}</ul></>}
          {d.forecasted.length > 0 ? <><p className="small"><strong>Forecasted by the funder:</strong></p><ul className="plain">{d.forecasted.slice(0, 3).map(o => <OppLine key={o.id} o={o} what="forecast" />)}</ul></>
            : d.open_now.length === 0 && <p className="small">No next round has been announced in the sources the Radar checks.
                {pending && <> The funder’s page <strong>changed recently</strong>; the change is waiting for review and may be a new call.</>}</p>}
        </div>
        <div className="ftime__cell">
          <span className="osf-label">How we watch this funder</span>
          {d.watch.length === 0 ? <p className="muted small">Found through Grants.gov searches rather than watched directly.</p> : (
            <ul className="plain small">{d.watch.map(w => (
              <li key={w.name}><a href={w.official_url} target="_blank" rel="noreferrer">{w.name} ↗</a>
                <span className="muted"> · {w.access_method === 'manual' ? 'checked by hand (site blocks automated access)' : w.access_method === 'page_monitor' ? 'page checked weekly for changes' : 'collected weekly'}</span></li>))}</ul>
          )}
          {d.watch.length > 0 && <p className="muted small">{checked ? `Last checked ${day(checked)}.` : manual ? 'Check the funder’s site directly.' : 'Not checked yet.'}</p>}
        </div>
      </div>
      <p className="muted small ftime__note">{d.note}</p>
    </section>
  )
}
