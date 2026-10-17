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
  ScenarioPanel,
  SelectedCard,
} from './Panels.jsx'

const TABS = [
  ['ask', 'Ask'],
  ['scenario', 'Scenario'],
  ['findings', 'Findings'],
  ['memory', 'Memory'],
]

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

  const selectRepo = (slug) => {
    if (slug === repoSlug || busy) return
    return guard('switch', () => loadRepo(slug))
  }

  const selectWorld = (w) => guard('world', () => loadWorld(w))

  const runAsk = (question) => {
    const text = (question || '').trim()
    if (!text) return
    return guard('ask', async () => {
      const r = await api.ask(text, repoSlug)
      setAskResult(r)
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

  const saveConfig = async (values) => setConfig(await api.saveConfig(values))

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
      />

      {error && <div className="errorbar">{error}</div>}

      <main>
        <section className="canvas-wrap">
          <GraphCanvas data={graph} theme={theme} selectedId={selected?.id} onSelect={setSelected} />
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
                {label}
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
              />
            )}
            {tab === 'findings' && <FindingsPanel findings={findings} />}
            {tab === 'memory' && (
              <MemoryPanel repo={repo} memory={memory} config={config} onSaveConfig={saveConfig} />
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
      />
    </div>
  )
}
