import { useEffect, useRef, useState } from 'react'
import { api } from './api'

const PENDING = new Set(['queued', 'cloning', 'building', 'loading'])

export default function RepoBar({ repos, active, busy, onSelect, onRefresh }) {
  const [source, setSource] = useState('')
  const [formError, setFormError] = useState('')
  const [opening, setOpening] = useState(false)
  const wanted = useRef(null) // slug we just kicked off, to auto-switch when done

  const pending = (repos || []).filter((r) => PENDING.has(r.status))

  useEffect(() => {
    if (!pending.length) return
    const t = setInterval(onRefresh, 2000)
    return () => clearInterval(t)
  }, [pending.length, onRefresh])

  useEffect(() => {
    const done = (repos || []).find((r) => r.slug === wanted.current)
    if (done?.status === 'ready') {
      wanted.current = null
      onSelect(done.slug)
    }
    if (done?.status === 'error') wanted.current = null
  }, [repos, onSelect])

  const connect = async (e) => {
    e.preventDefault()
    const src = source.trim()
    if (!src) return
    setFormError('')
    try {
      const job = await api.connect(src)
      wanted.current = job.slug
      setSource('')
      setOpening(false)
      onRefresh()
    } catch (err) {
      setFormError(String(err.message || err))
    }
  }

  return (
    <>
      <div className="repobar">
        <label className="repolabel">repo</label>
        <select
          className="repo-select"
          value={active}
          disabled={!!busy}
          onChange={(e) => onSelect(e.target.value)}
        >
          {(repos || []).map((r) => (
            <option key={r.slug} value={r.slug}>
              {r.slug}
              {r.status === 'ready' ? '' : ` (${r.status})`}
            </option>
          ))}
        </select>
        {opening ? (
          <form className="connect-form" onSubmit={connect}>
            <input
              type="text"
              autoFocus
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="https://github.com/owner/name  ·  or /path/to/clone"
              spellCheck={false}
            />
            <button className="btn primary" type="submit">
              Index
            </button>
            <button className="btn ghost" type="button" onClick={() => setOpening(false)}>
              cancel
            </button>
          </form>
        ) : (
          <button className="btn" onClick={() => setOpening(true)}>
            + index a repo
          </button>
        )}
        {formError && <span className="formerror">{formError}</span>}
      </div>
      {pending.map((r) => (
        <div className="ingest-strip" key={r.slug}>
          <span className={`istate ${r.status}`}>{r.status}</span>
          <span className="isource">{r.url}</span>
          <span className="imessage">{r.message || '…'}</span>
        </div>
      ))}
    </>
  )
}
