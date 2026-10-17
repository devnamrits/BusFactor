const qs = (params) =>
  Object.entries(params || {})
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')

const unwrap = async (r) => {
  if (r.ok) return r.json()
  let detail = `HTTP ${r.status}`
  try {
    const body = await r.json()
    detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
  } catch {
    /* non-JSON error body */
  }
  throw new Error(detail)
}

const get = (path, params) =>
  fetch(path + (qs(params) ? `?${qs(params)}` : '')).then(unwrap)

const send = (method) => (path, body) =>
  fetch(path, {
    method,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }).then(unwrap)

const post = send('POST')
const put = send('PUT')

export const api = {
  health: (repo) => get('/api/health', { repo }),

  repos: () => get('/api/repos'),
  connect: (source, windowDays) =>
    post('/api/repos', { source, window_days: windowDays ?? null }),

  config: () => get('/api/config'),
  saveConfig: (values) => put('/api/config', values),

  overview: (repo) => get('/api/overview', { repo }),
  people: (repo) => get('/api/people', { repo }),
  timeline: (repo) => get('/api/timeline', { repo }),
  memory: (repo) => get('/api/memory', { repo }),
  findings: (repo, simId) => get('/api/findings', { repo, sim_id: simId || 'latest' }),
  graph: (world, repo) => get('/api/graph', { world, repo }),

  ask: (question, repo) => post('/api/ask', { question, repo }),
  drill: (person, repo) => post('/api/drill', { person, repo }),
  plan: (simId, repo, includeResilience = true) =>
    post('/api/plan', { sim_id: simId || null, repo, include_resilience: includeResilience }),
  heal: (planId, repo) => post('/api/heal', { plan_id: planId || null, repo }),
}
