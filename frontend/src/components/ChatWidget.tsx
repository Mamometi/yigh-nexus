import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface Msg { role: 'user' | 'assistant'; content: string }

const STARTERS = ['Open grants on climate and health', 'Who works on malaria?', 'When does the Gates Foundation open again?', 'What are YIGH’s strategic priorities?']
const KEY = 'yigh-chat'

/** Small markdown subset: paragraphs, "- " lists, **bold**, [links](url). Internal links use the router. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*/g
  let last = 0, m: RegExpExecArray | null, k = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    if (m[1]) {
      const href = m[2]
      out.push(href.startsWith('/') ? <Link key={k++} to={href}>{m[1]}</Link>
        : /^https?:\/\//.test(href) ? <a key={k++} href={href} target="_blank" rel="noreferrer">{m[1]}</a> : m[1])
    } else out.push(<strong key={k++}>{m[3]}</strong>)
    last = re.lastIndex
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function Rich({ text }: { text: string }) {
  return <>{text.split(/\n{2,}/).map((block, i) => {
    const lines = block.split('\n')
    return lines.every(l => /^\s*[-*] /.test(l))
      ? <ul key={i}>{lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*[-*] /, ''))}</li>)}</ul>
      : <p key={i}>{lines.map((l, j) => <span key={j}>{j > 0 && <br />}{inline(l)}</span>)}</p>
  })}</>
}

export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>(() => { try { return JSON.parse(sessionStorage.getItem(KEY) ?? '[]') } catch { return [] } })
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { sessionStorage.setItem(KEY, JSON.stringify(msgs.slice(-40))) }, [msgs])
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs, busy, open])
  useEffect(() => { if (open) input.current?.focus() }, [open])

  const send = async (content: string) => {
    const q = content.trim()
    if (!q || busy) return
    const next = [...msgs, { role: 'user' as const, content: q }]
    setMsgs(next); setText(''); setBusy(true)
    try {
      const res = await fetch('/api/assistant/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
        body: JSON.stringify({ messages: next.slice(-20) }) })
      const d = await res.json().catch(() => null)
      setMsgs([...next, { role: 'assistant', content: res.ok && d?.reply ? d.reply : 'Oops, something went wrong on my end. Mind trying that again?' }])
    } catch {
      setMsgs([...next, { role: 'assistant', content: 'Oh no, I can’t reach the server right now. Give it a moment and try again?' }])
    } finally { setBusy(false) }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); send(text) }

  return (
    <>
      <button className={`chat-fab ${open ? 'is-open' : ''}`} onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="chat-panel"
              aria-label={open ? 'Close the assistant' : 'Ask the YIGH assistant'}>
        {open ? <svg viewBox="0 0 24 24" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
              : <><svg viewBox="0 0 24 24" aria-hidden><path d="M4 5h16v11H9l-5 4z" /></svg><span>Ask Nexi</span></>}
      </button>
      {open && (
        <section id="chat-panel" className="chat" role="dialog" aria-label="Nexi, the YIGH desk assistant">
          <header className="chat__head">
            <div><strong>Nexi · YIGH desk</strong><small>Here to help with funding, faculty and partners</small></div>
            {msgs.length > 0 && <button className="chat__clear" onClick={() => setMsgs([])}>New chat</button>}
          </header>
          <div className="chat__body" aria-live="polite">
            {msgs.length === 0 && (
              <div className="chat__hello">
                <p>Hi there, I’m Nexi! 👋 Welcome to the YIGH desk. Ask me about funding, Yale faculty, collaborators, teams or partners. What can I help you find today?</p>
                <div className="chat__starters">{STARTERS.map(s => <button key={s} onClick={() => send(s)}>{s}</button>)}</div>
              </div>
            )}
            {msgs.map((m, i) => <div key={i} className={`chat__msg chat__msg--${m.role}`}>{m.role === 'assistant' ? <Rich text={m.content} /> : m.content}</div>)}
            {busy && <div className="chat__msg chat__msg--assistant chat__typing" aria-label="Nexi is looking that up"><span /><span /><span /><em>Nexi is checking the directory and funding lists…</em></div>}
            <div ref={end} />
          </div>
          <form className="chat__form" onSubmit={submit}>
            <textarea ref={input} rows={1} value={text} placeholder="Ask Nexi about grants, faculty, partners…" aria-label="Your question"
                      onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(text) } }} />
            <button type="submit" disabled={busy || !text.trim()} aria-label="Send">
              <svg viewBox="0 0 24 24" aria-hidden><path d="M4 12l16-8-6 16-2-7z" /></svg>
            </button>
          </form>
          <p className="chat__foot">Answers come from this site. Check details with the funder before applying.</p>
        </section>
      )}
    </>
  )
}
