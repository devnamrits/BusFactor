import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { useTheme } from './theme'
import GraphCanvas from './GraphCanvas.jsx'
import RepoBar from './RepoBar.jsx'
import {
  AskPanel,
  Filmstrip,
  FindingsPanel,
  Legend,
  MemoryPanel,
  ReposPanel,
  ScenarioPanel,
  SelectedCard,
} from './Panels.jsx'

const TABS = [
  ['ask', 'Ask'],
  ['scenario', 'Scenario'],
  ['findings', 'Findings'],
  ['memory', 'Memory'],
  ['repos', 'Repos'],
]

const TAB_ICONS = {
  ask: <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z" />,
  scenario: (
    <>
      <line x1="6" y1="3" x2="6" y2="15" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M18 9a9 9 0 0 1-9 9" />
    </>
  ),
  findings: <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />,
  memory: (
    <>
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </>
  ),
  repos: (
    <>
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
      <line x1="12" y1="22.08" x2="12" y2="12" />
    </>
  ),
}

function TabIcon({ id }) {
  return (
    <svg
      className="tabicon"
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {TAB_ICONS[id]}
    </svg>
  )
}

export default function App() {
  const [theme, toggleTheme] = useTheme()

  const [health, setHealth] = useState(null)
  const [repos, setRepos] = useState([])
  const [config, setConfig] = useState(null)
  const [repoSlug, setRepoSlug] = useState('main')
  const [people, setPeople] = useState([])
  const [overview, setOverview] = useState(null)
  const [timeline, setTimeline] = useState({ sims: [], plans: [] })
  const [memory, setMemory] = useState(null)
  const [graph, setGraph] = useState(null)
  const [world, setWorld] = useState('main')
  const [tab, setTab] = useState('ask')

  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [askResult, setAskResult] = useState(null)
  const [drill, setDrill] = useState(null)
  const [plan, setPlan] = useState(null)
  const [heal, setHeal] = useState(null)
  const [selected, setSelected] = useState(null)
  const [focus, setFocus] = useState(null)
  const [citedIds, setCitedIds] = useState([])
  const [searchIds, setSearchIds] = useState([])

  const repo = useMemo(
    () =>
      repos.find((r) => r.slug === repoSlug) || {
        slug: repoSlug,
        graph: repoSlug === 'main' ? 'main' : `repo:${repoSlug}`,
        status: 'ready',
      },
    [repos, repoSlug]
  )

  const guard = async (tag, fn) => {
    setBusy(tag)
    setError('')
    try {
      await fn()
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy('')
    }
  }

  const loadWorld = async (w) => {
    setSelected(null)
    setWorld(w)
    setGraph(await api.graph(w, repoSlug))
  }

  const refreshTimeline = async () => setTimeline(await api.timeline(repoSlug))
  const refreshOverview = async () => setOverview(await api.overview(repoSlug))
  const refreshMemory = async () => setMemory(await api.memory(repoSlug))
  const refreshRepos = async () => setRepos((await api.repos()).repos)

  const loadRepo = async (slug) => {
    const target = repos.find((r) => r.slug === slug)
    const g = target?.graph || (slug === 'main' ? 'main' : `repo:${slug}`)
    setRepoSlug(slug)
    setTab('ask')
    setSelected(null)
    setCitedIds([])
    setSearchIds([])
    setDrill(null)
    setPlan(null)
    setHeal(null)
    setAskResult(null)
    setWorld(g)
    const [p, o, t, h, m] = await Promise.all([
      api.people(slug),
      api.overview(slug),
      api.timeline(slug),
      api.health(slug),
      api.memory(slug),
    ])
    setPeople(p)
    setOverview(o)
    setTimeline(t)
    setHealth(h)
    setMemory(m)
    setGraph(await api.graph(g, slug))
  }

  useEffect(() => {
    ;(async () => {
      try {
        const [h, r, c] = await Promise.all([api.health(), api.repos(), api.config()])
        setHealth(h)
        setRepos(r.repos)
        setConfig(c)
        const first = r.repos.find((x) => x.slug === 'main') || r.repos[0]
        const target = first?.graph || 'main'
        const [p, o, t, m] = await Promise.all([
          api.people(first.slug),
          api.overview(first.slug),
          api.timeline(first.slug),
          api.memory(first.slug),
        ])
        setRepoSlug(first.slug)
        setPeople(p)
        setOverview(o)
        setTimeline(t)
        setMemory(m)
        setWorld(target)
        setGraph(await api.graph(target, first.slug))
      } catch (e) {
        setError(String(e.message || e))
      }
    })()
    // boot once — later loads go through loadRepo
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // the selected repo can disappear (removed after a failed index) — fall back
  // to a real one instead of querying a graph that no longer exists
  useEffect(() => {
    if (!repos.length || repos.some((r) => r.slug === repoSlug)) return
    const fallback = repos.find((r) => r.slug === 'main') || repos[0]
    guard('switch', () => loadRepo(fallback.slug))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repos, repoSlug])

  const selectRepo = (slug) => {
    if (slug === repoSlug || busy) return
    return guard('switch', () => loadRepo(slug))
  }

  // re-index straight from the Repos tab — optionally with a different window
  const indexRepo = (url, days) =>
    guard('index', async () => {
      await api.connect(url, days)
      await refreshRepos()
    })

  const selectWorld = (w) => guard('world', () => loadWorld(w))

  const runAsk = (question) => {
    const text = (question || '').trim()
    if (!text) return
    return guard('ask', async () => {
      const r = await api.ask(text, repoSlug)
      setAskResult(r)
      // point the map at the answer itself: glow every cited node
      // (person/module/doc/decision/pr) and fly to the first one
      const cited = [
        ...new Set(
          (r.citations || [])
            .filter(
              (c) =>
                ['person', 'module', 'doc', 'decision', 'pr'].includes(c.kind) &&
                c.id
            )
            .map((c) => c.id)
        ),
      ]
      setCitedIds(cited)
      if (cited.length) setFocus({ id: cited[0], nonce: Date.now() })
      await refreshMemory()
      const d = r.data || {}
      if (r.tool === 'simulate_departure' && d.world) {
        setDrill({ ...d, findings: d.findings || [] })
        setPlan(null)
        setHeal(null)
        setTab('scenario')
        await loadWorld(d.world)
        await refreshTimeline()
      } else if (r.tool === 'handover_plan' && d.plan_id) {
        setPlan(d)
        setTab('scenario')
      } else if (r.tool === 'heal_and_verify' && d.world) {
        setHeal(d)
        setTab('scenario')
        await loadWorld(d.world)
        await refreshTimeline()
        await refreshOverview()
      } else if (r.tool === 'critical_people') {
        await refreshOverview()
      }
    })
  }

  const runDrill = (person) =>
    guard('drill', async () => {
      setPlan(null)
      setHeal(null)
      const d = await api.drill(person, repoSlug)
      setDrill(d)
      await loadWorld(d.world)
      await refreshTimeline()
      await refreshMemory()
    })

  const runPlan = (includeResilience) =>
    guard('plan', async () => {
      setPlan(await api.plan(drill?.sim_id, repoSlug, includeResilience))
    })

  const runHeal = () =>
    guard('heal', async () => {
      const h = await api.heal(plan?.plan_id, repoSlug)
      setHeal(h)
      await loadWorld(h.world)
      await refreshTimeline()
      await refreshOverview()
      await refreshMemory()
    })

  // forget the drill → plan → heal arc for this repo: audit nodes and the
  // cloned worlds go; the indexed snapshot and the question log stay
  const clearRuns = () =>
    guard('clear', async () => {
      if (
        !window.confirm(
          "Forget this repo's drills, plans and throwaway worlds? The indexed snapshot is not touched."
        )
      ) {
        return
      }
      await api.clearRuns(repoSlug)
      setDrill(null)
      setPlan(null)
      setHeal(null)
      setCitedIds([])
      setSearchIds([])
      const g = repo.graph
      setWorld(g)
      const [t, m, o] = await Promise.all([
        api.timeline(repoSlug),
        api.memory(repoSlug),
        api.overview(repoSlug),
      ])
      setTimeline(t)
      setMemory(m)
      setOverview(o)
      setGraph(await api.graph(g, repoSlug))
    })

  // a finding names a module and often a person — point the map at both
  const focusFinding = (f) => {
    const nodes = graph?.nodes || []
    const ids = []
    if (f.module_id && nodes.some((n) => n.id === f.module_id)) ids.push(f.module_id)
    for (const n of nodes) {
      if (n.label === 'Person' && f.claim?.includes(n.name)) ids.push(n.id)
    }
    if (!ids.length) return
    setSearchIds(ids)
    const node = nodes.find((n) => n.id === ids[0])
    if (node) setSelected(node)
    setFocus({ id: ids[0], nonce: Date.now() })
  }

  const askAboutNode = (node) => {
    if (!node) return
    const q =
      node.label === 'Module'
        ? `who knows ${node.name}?`
        : node.label === 'Person'
          ? `what does ${node.name} carry?`
          : String(node.name)
    setTab('ask')
    return runAsk(q)
  }

  // a citation chip is a promise: click it and the map proves the claim
  const focusCite = (c) => {
    const nodes = graph?.nodes || []
    const node = nodes.find((n) => n.id === c.id) || nodes.find((n) => n.name === c.label)
    if (!node) return
    setSelected(node)
    setFocus({ id: node.id, nonce: Date.now() })
  }

  // search the graph by name: every substring match glows, the best is flown to
  const findOnGraph = (q) => {
    const query = (q || '').trim().toLowerCase()
    const nodes = graph?.nodes || []
    if (!query || !nodes.length) return
    const rankOf = (n) => {
      const s = String(n.name || '').toLowerCase()
      if (s === query) return 0
      if (s.startsWith(query)) return 1
      if (s.includes(query)) return 2
      return -1
    }
    const found = nodes
      .map((n) => ({ n, r: rankOf(n) }))
      .filter((x) => x.r >= 0)
      .sort((a, b) => a.r - b.r || (b.n.deg || 0) - (a.n.deg || 0))
    setSearchIds(found.slice(0, 40).map((x) => x.n.id))
    if (found[0]) {
      setSelected(found[0].n)
      setFocus({ id: found[0].n.id, nonce: Date.now() })
    }
  }

  const suggestions = useMemo(() => {
    const out = ['Who can we least afford to lose?', 'Where is knowledge stranded?']
    if (people[0]?.name) out.push(`What does ${people[0].name} carry?`)
    const firstModule = Object.values(overview?.coverage || {})[0]?.name
    if (firstModule) out.push(`Who knows ${firstModule}?`)
    out.push('What did we decide?')
    return out.slice(0, 5)
  }, [people, overview])

  const findings = drill && drill.world === world ? drill.findings || [] : graph?.findings || []

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark">BF</span>
          <b>BusFactor</b>
          <span className="tagline">know who your team can’t lose</span>
        </div>
        <div className="metrics">
          <span className={`dot ${health?.ok ? 'ok' : 'bad'}`} title={health?.ok ? 'FalkorDB up' : 'FalkorDB down'} />
          <span>
            {health?.nodes ?? '–'} nodes · {health?.edges ?? '–'} edges
          </span>
          {memory?.stats && (
            <span>
              memory {memory.stats.questions} · runs {memory.stats.runs}
            </span>
          )}
          <input
            className="gsearch"
            placeholder="find on graph…"
            onKeyDown={(e) => {
              if (e.key === 'Enter') findOnGraph(e.currentTarget.value)
            }}
          />
          <button className="btn ghost" onClick={toggleTheme} title="switch theme">
            {theme === 'dark' ? 'light mode' : 'dark mode'}
          </button>
        </div>
      </header>

      <RepoBar
        repos={repos}
        active={repoSlug}
        busy={busy}
        onSelect={selectRepo}
        onRefresh={refreshRepos}
        defaultWindow={config?.ingest?.window_days}
      />

      {error && <div className="errorbar">{error}</div>}

      <main>
        <section className="canvas-wrap">
          <GraphCanvas
            data={graph}
            theme={theme}
            selectedId={selected?.id}
            focus={focus}
            onSelect={setSelected}
            highlightIds={[...citedIds, ...searchIds]}
          />
          <Legend />
          <SelectedCard node={selected} onAskAbout={askAboutNode} />
        </section>

        <aside className="rail">
          <nav className="tabs">
            {TABS.map(([id, label]) => (
              <button
                key={id}
                className={`tab ${tab === id ? 'on' : ''}`}
                onClick={() => setTab(id)}
              >
                <TabIcon id={id} />
                <span>{label}</span>
                {id === 'findings' && findings.length > 0 && <em>{findings.length}</em>}
              </button>
            ))}
          </nav>
          <div className="rail-body">
            {tab === 'ask' && (
              <AskPanel
                result={askResult}
                busy={busy === 'ask'}
                suggestions={suggestions}
                onAsk={runAsk}
                onCite={focusCite}
              />
            )}
            {tab === 'scenario' && (
              <ScenarioPanel
                drill={drill}
                plan={plan}
                heal={heal}
                people={people}
                busy={busy}
                onDrill={runDrill}
                onPlan={runPlan}
                onHeal={runHeal}
                hasRuns={(timeline?.sims?.length || 0) > 0}
                onClear={clearRuns}
              />
            )}
            {tab === 'findings' && (
              <FindingsPanel findings={findings} onFocus={focusFinding} />
            )}
            {tab === 'memory' && (
              <MemoryPanel repo={repo} memory={memory} config={config} />
            )}
            {tab === 'repos' && (
              <ReposPanel
                repos={repos}
                active={repoSlug}
                busy={busy}
                onSelect={selectRepo}
                onIndex={indexRepo}
              />
            )}
          </div>
        </aside>
      </main>

      <Filmstrip
        repo={repo}
        overview={overview}
        timeline={timeline}
        world={world}
        onWorld={selectWorld}
        onClear={clearRuns}
        busy={busy}
      />
    </div>
  )
}
