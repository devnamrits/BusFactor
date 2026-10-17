import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const PALETTE = {
  dark: {
    Person: '#3ec6b4',
    Module: '#97a0ae',
    Doc: '#d9a036',
    Decision: '#a291f5',
    stranded: '#ef5350',
    departed: '#3b3e45',
    planEdge: 'rgba(224,161,44,0.9)',
    label: 'rgba(233,230,224,0.75)',
    link: {
      KNOWS: 'rgba(62,198,180,0.26)',
      OWNS: 'rgba(151,160,174,0.30)',
      DECIDED_BY: 'rgba(162,145,245,0.20)',
      AFFECTS: 'rgba(162,145,245,0.20)',
      WROTE: 'rgba(217,160,54,0.20)',
    },
  },
  light: {
    Person: '#0f766e',
    Module: '#5b6472',
    Doc: '#9a6700',
    Decision: '#6d5bd0',
    stranded: '#b91c1c',
    departed: '#bfb8a9',
    planEdge: 'rgba(180,83,9,0.85)',
    label: 'rgba(23,25,30,0.72)',
    link: {
      KNOWS: 'rgba(15,118,110,0.30)',
      OWNS: 'rgba(91,100,114,0.30)',
      DECIDED_BY: 'rgba(109,91,208,0.22)',
      AFFECTS: 'rgba(109,91,208,0.22)',
      WROTE: 'rgba(154,103,0,0.22)',
    },
  },
}

function radius(node) {
  if (node.label === 'Person') return 3.5 + Math.min(5.5, (node.deg || 0) * 0.45)
  if (node.label === 'Module') return 4 + Math.min(6, (node.criticality || 0) * 1.2)
  return 3
}

export default function GraphCanvas({ data, selectedId, focus, theme, onSelect }) {
  const wrap = useRef(null)
  const fg = useRef(null)
  const [size, setSize] = useState({ w: 900, h: 600 })
  const palette = PALETTE[theme] || PALETTE.dark

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight })
    measure()
    const obs = new ResizeObserver(measure)
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  const gdata = useMemo(() => {
    if (!data) return { nodes: [], links: [] }

    // a component with modules but no active person is a stranded island
    const comps = {}
    for (const n of data.nodes) {
      const c = (comps[n.component] = comps[n.component] || { active: false, module: false })
      if (n.label === 'Person' && n.status !== 'departed') c.active = true
      if (n.label === 'Module') c.module = true
    }
    const stranded = new Set(
      Object.entries(comps)
        .filter(([, v]) => v.module && !v.active)
        .map(([id]) => Number(id))
    )

    const degree = {}
    for (const l of data.links) {
      degree[l.source] = (degree[l.source] || 0) + 1
      degree[l.target] = (degree[l.target] || 0) + 1
    }

    return {
      nodes: data.nodes.map((n) => ({
        ...n,
        stranded: stranded.has(n.component),
        deg: degree[n.id] || 0,
      })),
      links: data.links.map((l) => ({ ...l })),
    }
  }, [data])

  useEffect(() => {
    const t = setTimeout(() => fg.current?.zoomToFit(600, 64), 400)
    return () => clearTimeout(t)
  }, [data?.world])

  // fly to a cited node (citation chips in the Ask panel)
  useEffect(() => {
    if (!focus?.id) return
    const n = gdata.nodes.find((x) => x.id === focus.id)
    const f = fg.current
    if (n && f && n.x != null) {
      f.centerAt(n.x, n.y, 500)
      f.zoom(2.4, 500)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce])

  useEffect(() => {
    const f = fg.current
    if (!f) return
    f.d3Force('charge')?.strength(-110)
    f.d3Force('link')?.distance((l) => (l.plan ? 28 : 62))
  }, [gdata])

  const drawNode = (node, ctx, scale) => {
    const r = radius(node)
    let fill = palette[node.label] || palette.Module

    if (node.label === 'Module' && node.severity === 3) fill = palette.stranded
    else if (node.label === 'Module' && node.severity === 1) fill = palette.Doc
    if (node.label === 'Module' && node.stranded) fill = palette.stranded
    if (node.label === 'Person' && node.status === 'departed') fill = palette.departed

    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = fill
    ctx.globalAlpha = node.label === 'Doc' || node.label === 'Decision' ? 0.8 : 1
    ctx.fill()
    ctx.globalAlpha = 1

    if (node.stranded || (node.label === 'Person' && node.status === 'departed')) {
      ctx.strokeStyle = palette.stranded
      ctx.lineWidth = 1.4 / scale
      if (node.label === 'Person' && node.status === 'departed') {
        ctx.setLineDash([2.5 / scale, 2 / scale])
      }
      ctx.beginPath()
      ctx.arc(node.x, node.y, r + 2.6 / scale, 0, 2 * Math.PI)
      ctx.stroke()
      ctx.setLineDash([])
    }

    if (node.id === selectedId) {
      ctx.strokeStyle = '#e2603c'
      ctx.lineWidth = 1.6 / scale
      ctx.beginPath()
      ctx.arc(node.x, node.y, r + 4.2 / scale, 0, 2 * Math.PI)
      ctx.stroke()
    }

    if (scale > 1.15) {
      ctx.font = `${Math.max(2.4, 11 / scale)}px ui-monospace, SFMono-Regular, Menlo, monospace`
      ctx.textAlign = 'center'
      ctx.fillStyle = palette.label
      ctx.fillText(node.name, node.x, node.y + r + 9 / scale)
    }
  }

  return (
    <div className="canvas" ref={wrap}>
      <ForceGraph2D
        ref={fg}
        graphData={gdata}
        width={size.w}
        height={size.h}
        backgroundColor="rgba(0,0,0,0)"
        nodeCanvasObject={drawNode}
        nodePointerAreaPaint={(node, color, ctx) => {
          const r = radius(node) + 4
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
          ctx.fill()
        }}
        linkColor={(l) => (l.plan ? palette.planEdge : palette.link[l.type] || 'rgba(100,116,139,0.15)')}
        linkWidth={(l) => (l.plan ? 1.8 : l.type === 'KNOWS' ? Math.max(0.5, (l.weight || 0.3) * 1.8) : 0.7)}
        onNodeClick={(n) => onSelect && onSelect(n)}
        onBackgroundClick={() => onSelect && onSelect(null)}
        cooldownTicks={140}
      />
    </div>
  )
}
