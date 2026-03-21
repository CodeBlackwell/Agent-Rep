/* ── Graph State ─────────────────────────────────────────────── */

class GraphState {
  constructor() { this.clear(); }

  update(data) {
    for (const n of data.nodes) {
      if (!this.nodes.has(n.id)) this.nodes.set(n.id, n);
    }
    for (const e of data.edges) {
      const key = e.from + '→' + e.to;
      if (!this._edgeSet.has(key)) {
        this.edges.push({ ...e, _key: key });
        this._edgeSet.add(key);
      }
    }
  }

  clear() {
    this.nodes = new Map();
    this.edges = [];
    this._edgeSet = new Set();
  }

  get empty() { return this.nodes.size === 0; }
}

/* ── Data Transforms ────────────────────────────────────────── */

function buildHierarchyTree(state, addUnexplored) {
  const domains = new Map();   // domId -> {name, children: Map<catId, {name, children: []}>}
  const nodeOf = id => state.nodes.get(id);

  // Hierarchy edges: non-dashed, from dom/cat to cat/skill
  for (const e of state.edges) {
    if (e.dashes) continue;
    const src = nodeOf(e.from);
    const tgt = nodeOf(e.to);
    if (!src || !tgt) continue;
    const sm = src.meta || {};
    const tm = tgt.meta || {};

    if (sm.type === 'domain' && tm.type === 'category') {
      if (!domains.has(e.from)) domains.set(e.from, { name: src.label, children: new Map() });
      const dom = domains.get(e.from);
      if (!dom.children.has(e.to)) dom.children.set(e.to, { name: tgt.label, children: [] });
    }

    if (sm.type === 'category' && tm.type === 'skill') {
      // Find parent domain
      for (const [, dom] of domains) {
        const cat = dom.children.get(e.from);
        if (cat) {
          cat.children.push({
            name: tgt.label,
            id: tgt.id,
            evidence_count: (tm.evidence_count || 0),
            status: tm.status || 'demonstrated',
            color: tgt.color,
            proficiency: tm.proficiency || null,
          });
          break;
        }
      }
    }
  }

  // Also handle category→skill edges where category was placed by gap overlay
  // (category node might not have a dom→cat edge if it came from gap overlay)
  for (const e of state.edges) {
    if (e.dashes) continue;
    const src = nodeOf(e.from);
    const tgt = nodeOf(e.to);
    if (!src || !tgt) continue;
    if ((src.meta || {}).type === 'category' && (tgt.meta || {}).type === 'skill') {
      // Check if already added
      let found = false;
      for (const [, dom] of domains) {
        if (dom.children.has(e.from)) { found = true; break; }
      }
      if (!found) {
        // Find the domain for this category via dom→cat edge
        for (const de of state.edges) {
          const ds = nodeOf(de.from);
          if (ds && (ds.meta || {}).type === 'domain' && de.to === e.from) {
            if (!domains.has(de.from)) domains.set(de.from, { name: ds.label, children: new Map() });
            const dom = domains.get(de.from);
            if (!dom.children.has(e.from)) dom.children.set(e.from, { name: src.label, children: [] });
            dom.children.get(e.from).children.push({
              name: tgt.label, id: tgt.id,
              evidence_count: ((tgt.meta || {}).evidence_count || 0),
              status: (tgt.meta || {}).status || 'demonstrated',
              color: tgt.color,
              proficiency: (tgt.meta || {}).proficiency || null,
            });
            break;
          }
        }
      }
    }
  }

  // Handle floating skill nodes (no hierarchy edges — e.g., orphan claims, pure gaps)
  for (const [id, n] of state.nodes) {
    if ((n.meta || {}).type !== 'skill') continue;
    let placed = false;
    for (const [, dom] of domains) {
      for (const [, cat] of dom.children) {
        if (cat.children.some(c => c.id === id)) { placed = true; break; }
      }
      if (placed) break;
    }
    if (!placed) {
      // Put under a virtual "Other" domain/category
      if (!domains.has('dom:_other')) {
        domains.set('dom:_other', { name: 'Other', children: new Map() });
      }
      const dom = domains.get('dom:_other');
      if (!dom.children.has('cat:_other')) {
        dom.children.set('cat:_other', { name: 'Claims', children: [] });
      }
      dom.children.get('cat:_other').children.push({
        name: n.label, id: id,
        evidence_count: ((n.meta || {}).evidence_count || 0),
        status: (n.meta || {}).status || 'claimed_only',
        color: n.color,
        proficiency: (n.meta || {}).proficiency || null,
      });
    }
  }

  const rootChildren = [];
  for (const [, dom] of domains) {
    const cats = [];
    for (const [, cat] of dom.children) {
      if (cat.children.length > 0) cats.push({ name: cat.name, children: cat.children });
    }
    if (cats.length > 0) rootChildren.push({ name: dom.name, children: cats });
  }

  if (addUnexplored && rootChildren.length > 0) {
    const totalEvidence = rootChildren.reduce((s, d) =>
      s + d.children.reduce((s2, c) =>
        s2 + c.children.reduce((s3, sk) => s3 + (sk.evidence_count || 1), 0), 0), 0);
    rootChildren.push({
      name: '_unexplored',
      _unexplored: true,
      children: [{ name: '_pad', _unexplored: true, children: [
        { name: '_leaf', _unexplored: true, evidence_count: Math.max(totalEvidence * 0.4, 10) }
      ]}],
    });
  }

  return { name: 'root', children: rootChildren };
}

function buildCoOccurrence(state) {
  const repoSkills = new Map();
  for (const e of state.edges) {
    if (!e.dashes) continue;
    const src = state.nodes.get(e.from);
    if (!src || (src.meta || {}).type !== 'repository') continue;
    if (!e.to.startsWith('skill:')) continue;
    if (!repoSkills.has(e.from)) repoSkills.set(e.from, []);
    repoSkills.get(e.from).push(e.to);
  }
  const counts = new Map();
  for (const [, skills] of repoSkills) {
    for (let i = 0; i < skills.length; i++) {
      for (let j = i + 1; j < skills.length; j++) {
        const key = [skills[i], skills[j]].sort().join('|');
        counts.set(key, (counts.get(key) || 0) + 1);
      }
    }
  }
  return [...counts.entries()].map(([k, v]) => {
    const [source, target] = k.split('|');
    return { source, target, count: v };
  });
}

function getGapEdges(state) {
  const out = [];
  for (const e of state.edges) {
    if (!e.dashes) continue;
    if (e.from.startsWith('skill:') && e.to.startsWith('skill:')) {
      out.push(e);
    }
  }
  return out;
}

/* ── Tooltip ────────────────────────────────────────────────── */

let tooltip;
function ensureTooltip() {
  if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.className = 'viz-tooltip';
    document.getElementById('graph-panel').appendChild(tooltip);
  }
  return tooltip;
}

function showTooltip(evt, html) {
  const tt = ensureTooltip();
  tt.innerHTML = html;
  tt.classList.add('viz-tooltip--visible');
  const panel = document.getElementById('graph-panel').getBoundingClientRect();
  tt.style.left = (evt.clientX - panel.left + 12) + 'px';
  tt.style.top = (evt.clientY - panel.top - 8) + 'px';
}

function hideTooltip() {
  const tt = ensureTooltip();
  tt.classList.remove('viz-tooltip--visible');
}

function skillTooltipHtml(d) {
  const status = d.status || d.data?.status || '';
  const prof = d.proficiency || d.data?.proficiency || '';
  const ev = d.evidence_count ?? d.data?.evidence_count ?? 0;
  const name = d.name || d.data?.name || '';
  let lines = [`<strong>${name}</strong>`];
  if (prof) lines.push(`Proficiency: ${prof}`);
  if (ev > 0) lines.push(`Evidence: ${ev} snippets`);
  if (status === 'claimed_only') lines.push('Resume claim (no code evidence)');
  if (status === 'gap') lines.push('Gap — not demonstrated');
  return lines.join('<br>');
}

/* ── Bloom Renderer (Partial Sunburst) ──────────────────────── */

const BloomRenderer = {
  _root: null,

  init(svg, dims) {
    this._root = svg.append('g').attr('class', 'bloom-root');
  },

  render(state, dims) {
    const g = this._root;
    g.selectAll('*').remove();
    if (state.empty) return;

    const tree = buildHierarchyTree(state, true);
    const root = d3.hierarchy(tree)
      .sum(d => d.children ? 0 : (d.evidence_count || 1))
      .sort((a, b) => (b.value || 0) - (a.value || 0));

    const radius = Math.min(dims.width, dims.height) / 2 - 10;
    d3.partition().size([2 * Math.PI, radius]).padding(0.005)(root);

    g.attr('transform', `translate(${dims.width / 2},${dims.height / 2})`);

    const arc = d3.arc()
      .startAngle(d => d.x0)
      .endAngle(d => d.x1)
      .innerRadius(d => d.y0)
      .outerRadius(d => d.y1)
      .padAngle(0.008)
      .padRadius(radius / 3);

    const descendants = root.descendants().filter(d => d.depth > 0);

    g.selectAll('path')
      .data(descendants, d => d.data.name)
      .join(
        enter => enter.append('path')
          .attr('class', 'bloom-arc')
          .attr('d', arc)
          .style('fill', d => arcColor(d))
          .style('opacity', d => d.data._unexplored ? 0.06 : 0)
          .on('mouseover', (evt, d) => {
            if (d.data._unexplored) return;
            if (d.depth === 3) showTooltip(evt, skillTooltipHtml(d.data));
          })
          .on('mouseout', hideTooltip)
          .transition().duration(600).ease(d3.easeCubicOut)
          .style('opacity', d => d.data._unexplored ? 0.06 : 0.9),
        update => update.transition().duration(400).attr('d', arc)
      );

    // Labels on outer ring (skills)
    const labelNodes = descendants.filter(d => d.depth === 3 && !d.data._unexplored && (d.x1 - d.x0) > 0.08);
    g.selectAll('text.bloom-label')
      .data(labelNodes, d => d.data.name)
      .join('text')
      .attr('class', 'bloom-label')
      .attr('transform', d => {
        const angle = (d.x0 + d.x1) / 2;
        const r = (d.y0 + d.y1) / 2;
        const [x, y] = d3.pointRadial(angle, r);
        const rotate = (angle * 180 / Math.PI - 90);
        const flip = rotate > 90 ? rotate + 180 : rotate;
        return `translate(${x},${y}) rotate(${flip})`;
      })
      .attr('dy', '0.35em')
      .attr('text-anchor', d => {
        const angle = (d.x0 + d.x1) / 2;
        return (angle * 180 / Math.PI - 90) > 90 ? 'end' : 'start';
      })
      .text(d => d.data.name);
  },

  destroy() {
    if (this._root) this._root.remove();
    this._root = null;
  }
};

function arcColor(d) {
  if (d.data._unexplored) return '#2c2c2c';
  if (d.depth === 3) return d.data.color || '#7a8b6f';
  if (d.depth === 2) return '#b8805a';
  if (d.depth === 1) return '#8b7355';
  return '#d4cdc4';
}

/* ── Dendrite Renderer (Radial Tree) ────────────────────────── */

const DendriteRenderer = {
  _root: null,

  init(svg, dims) {
    this._root = svg.append('g').attr('class', 'dendrite-root');
  },

  render(state, dims) {
    const g = this._root;
    g.selectAll('*').remove();
    if (state.empty) return;

    const tree = buildHierarchyTree(state, false);
    const root = d3.hierarchy(tree);
    root.sum(d => d.evidence_count || 0);

    const radius = Math.min(dims.width, dims.height) / 2 - 50;
    d3.tree()
      .size([2 * Math.PI, radius])
      .separation((a, b) => (a.parent === b.parent ? 1 : 2) / Math.max(a.depth, 1))
      (root);

    g.attr('transform', `translate(${dims.width / 2},${dims.height / 2})`);

    const maxFlow = Math.max(...root.descendants().map(d => d.value || 1));
    const widthScale = d3.scaleLinear().domain([0, maxFlow]).range([1, 6]);

    // Links
    g.selectAll('path.dendrite-link')
      .data(root.links().filter(l => l.source.depth > 0))
      .join(
        enter => enter.append('path')
          .attr('class', 'dendrite-link')
          .attr('d', d3.linkRadial().angle(d => d.x).radius(d => d.y))
          .attr('stroke', d => linkColor(d.target))
          .attr('stroke-width', d => widthScale(d.target.value || 1))
          .attr('stroke-opacity', 0)
          .transition().duration(600).ease(d3.easeCubicOut)
          .attr('stroke-opacity', 0.6)
      );

    // Nodes
    const nodes = root.descendants().filter(d => d.depth > 0);
    g.selectAll('circle.dendrite-node')
      .data(nodes, d => d.data.name)
      .join(
        enter => enter.append('circle')
          .attr('class', 'dendrite-node')
          .attr('transform', d => `translate(${d3.pointRadial(d.x, d.y)})`)
          .attr('r', d => nodeRadius(d))
          .attr('fill', d => nodeColor(d))
          .attr('stroke', d => d.data.status === 'gap' ? '#c4756a' : 'none')
          .attr('stroke-dasharray', d => d.data.status === 'gap' ? '3 2' : 'none')
          .attr('stroke-width', 1.5)
          .attr('opacity', 0)
          .on('mouseover', (evt, d) => {
            if (d.depth === 3) showTooltip(evt, skillTooltipHtml(d.data));
          })
          .on('mouseout', hideTooltip)
          .transition().duration(600).ease(d3.easeCubicOut)
          .attr('opacity', 1)
      );

    // Labels for skill leaves
    const labelNodes = nodes.filter(d => d.depth === 3);
    g.selectAll('text.dendrite-label')
      .data(labelNodes, d => d.data.name)
      .join('text')
      .attr('class', 'dendrite-label')
      .attr('transform', d => {
        const [x, y] = d3.pointRadial(d.x, d.y);
        const angleDeg = d.x * 180 / Math.PI - 90;
        const flip = angleDeg > 90 ? angleDeg + 180 : angleDeg;
        return `translate(${x},${y}) rotate(${flip})`;
      })
      .attr('dx', d => {
        const angleDeg = d.x * 180 / Math.PI - 90;
        return angleDeg > 90 ? '-8' : '8';
      })
      .attr('dy', '0.35em')
      .attr('text-anchor', d => {
        const angleDeg = d.x * 180 / Math.PI - 90;
        return angleDeg > 90 ? 'end' : 'start';
      })
      .text(d => d.data.name);

    // Gap bridge edges (dashed arcs between skill leaves)
    const gapEdges = getGapEdges(state);
    const leafPos = new Map();
    labelNodes.forEach(d => { leafPos.set(d.data.id, d3.pointRadial(d.x, d.y)); });

    g.selectAll('path.dendrite-gap-link')
      .data(gapEdges.filter(e => leafPos.has(e.from) && leafPos.has(e.to)))
      .join('path')
      .attr('class', 'dendrite-link dendrite-gap-link')
      .attr('d', e => {
        const [x1, y1] = leafPos.get(e.from);
        const [x2, y2] = leafPos.get(e.to);
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        // Curve toward center
        const cx = mx * 0.5;
        const cy = my * 0.5;
        return `M${x1},${y1} Q${cx},${cy} ${x2},${y2}`;
      })
      .attr('stroke', '#c4756a')
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.5);
  },

  destroy() {
    if (this._root) this._root.remove();
    this._root = null;
  }
};

function nodeRadius(d) {
  if (d.depth === 3) {
    const ev = d.data.evidence_count || 0;
    return Math.max(4, Math.min(14, Math.sqrt(ev) * 0.6));
  }
  if (d.depth === 2) return 4;
  return 5;
}

function nodeColor(d) {
  if (d.depth === 3) return d.data.color || '#7a8b6f';
  if (d.depth === 2) return '#b8805a';
  return '#8b7355';
}

function linkColor(d) {
  if (d.depth === 3) return d.data.color || '#7a8b6f';
  if (d.depth === 2) return '#b8805a';
  return '#8b7355';
}

/* ── Ribbon Renderer (Arc Diagram) ──────────────────────────── */

const RibbonRenderer = {
  _root: null,

  init(svg, dims) {
    this._root = svg.append('g').attr('class', 'ribbon-root');
  },

  render(state, dims) {
    const g = this._root;
    g.selectAll('*').remove();
    if (state.empty) return;

    const skills = [...state.nodes.values()]
      .filter(n => (n.meta || {}).type === 'skill')
      .sort((a, b) => ((b.meta || {}).evidence_count || 0) - ((a.meta || {}).evidence_count || 0));

    if (skills.length === 0) return;

    const padding = 60;
    const baseline = dims.height * 0.58;
    const x = d3.scalePoint()
      .domain(skills.map(s => s.id))
      .range([padding, dims.width - padding])
      .padding(0.5);

    const maxEv = Math.max(1, ...skills.map(s => (s.meta || {}).evidence_count || 0));
    const rScale = d3.scaleSqrt().domain([0, maxEv]).range([5, 18]);

    // Co-occurrence arcs above baseline
    const coOcc = buildCoOccurrence(state);
    const maxCount = Math.max(1, ...coOcc.map(c => c.count));
    const arcWidth = d3.scaleLinear().domain([1, maxCount]).range([1.5, 5]);

    g.selectAll('path.ribbon-arc')
      .data(coOcc.filter(c => x(c.source) !== undefined && x(c.target) !== undefined))
      .join('path')
      .attr('class', 'ribbon-arc')
      .attr('d', c => {
        const x1 = x(c.source), x2 = x(c.target);
        const rx = Math.abs(x2 - x1) / 2;
        const ry = Math.min(rx * 0.6, baseline - 30);
        return `M${x1},${baseline} A${rx},${ry} 0 0,1 ${x2},${baseline}`;
      })
      .attr('stroke', '#8b7355')
      .attr('stroke-width', c => arcWidth(c.count))
      .attr('opacity', 0)
      .transition().duration(800).delay((d, i) => 300 + i * 100)
      .attr('opacity', 0.5);

    // Gap arcs below baseline
    const gapEdges = getGapEdges(state);
    g.selectAll('path.ribbon-arc--gap')
      .data(gapEdges.filter(e => x(e.from) !== undefined && x(e.to) !== undefined))
      .join('path')
      .attr('class', 'ribbon-arc ribbon-arc--gap')
      .attr('d', e => {
        const x1 = x(e.from), x2 = x(e.to);
        const rx = Math.abs(x2 - x1) / 2;
        const ry = Math.min(rx * 0.4, (dims.height - baseline) - 40);
        return `M${x1},${baseline} A${rx},${ry} 0 0,0 ${x2},${baseline}`;
      })
      .attr('stroke', '#c4756a')
      .attr('stroke-width', 1.5)
      .attr('opacity', 0)
      .transition().duration(600).delay(400)
      .attr('opacity', 0.5);

    // Skill nodes on baseline
    g.selectAll('circle.ribbon-node')
      .data(skills, d => d.id)
      .join(
        enter => enter.append('circle')
          .attr('class', 'ribbon-node')
          .attr('cx', d => x(d.id))
          .attr('cy', baseline)
          .attr('r', 0)
          .attr('fill', d => d.color || '#7a8b6f')
          .attr('stroke', d => (d.meta || {}).status === 'gap' ? '#c4756a' : '#fff')
          .attr('stroke-width', 1.5)
          .attr('stroke-dasharray', d => (d.meta || {}).status === 'gap' ? '3 2' : 'none')
          .on('mouseover', (evt, d) => showTooltip(evt, skillTooltipHtml({
            name: d.label, status: (d.meta || {}).status,
            proficiency: (d.meta || {}).proficiency,
            evidence_count: (d.meta || {}).evidence_count,
          })))
          .on('mouseout', hideTooltip)
          .transition().duration(500).ease(d3.easeCubicOut)
          .attr('r', d => rScale((d.meta || {}).evidence_count || 0))
      );

    // Labels below nodes
    g.selectAll('text.ribbon-label')
      .data(skills, d => d.id)
      .join('text')
      .attr('class', 'ribbon-label')
      .attr('x', d => x(d.id))
      .attr('y', d => baseline + rScale((d.meta || {}).evidence_count || 0) + 14)
      .text(d => d.label);
  },

  destroy() {
    if (this._root) this._root.remove();
    this._root = null;
  }
};

/* ── Legend ──────────────────────────────────────────────────── */

const LEGENDS = {
  bloom: `
    <span><i class="dot" style="background:#7a8b6f"></i> Demonstrated</span>
    <span><i class="dot" style="background:#a8a099"></i> Claimed</span>
    <span><i class="dot" style="background:#c4756a"></i> Gap</span>
    <span class="legend-note">Arc width = evidence · Dark = unexplored</span>
  `,
  dendrite: `
    <span><i class="dot" style="background:#7a8b6f"></i> Demonstrated</span>
    <span><i class="dot" style="background:#a8a099"></i> Claimed</span>
    <span><i class="dot" style="background:#c4756a"></i> Gap</span>
    <span class="legend-note">Branch width = evidence flow · Dashed = gap bridge</span>
  `,
  ribbon: `
    <span><i class="dot" style="background:#7a8b6f"></i> Demonstrated</span>
    <span><i class="dot" style="background:#a8a099"></i> Claimed</span>
    <span><i class="dot" style="background:#c4756a"></i> Gap</span>
    <span class="legend-note">Arc above = shared repos · Dashed below = gap</span>
  `,
};

function updateLegend(mode) {
  const el = document.getElementById('viz-legend');
  if (el) el.innerHTML = LEGENDS[mode] || '';
}

/* ── Orchestrator ───────────────────────────────────────────── */

const renderers = { bloom: BloomRenderer, dendrite: DendriteRenderer, ribbon: RibbonRenderer };
let activeMode = 'bloom';
const state = new GraphState();
let svg = null;
let dims = { width: 400, height: 400 };

function initSVG() {
  const container = document.getElementById('graph-container');
  d3.select(container).selectAll('svg').remove();
  svg = d3.select(container).append('svg').attr('id', 'viz-svg');
  measureDims();
}

function measureDims() {
  const container = document.getElementById('graph-container');
  const rect = container.getBoundingClientRect();
  dims = { width: rect.width || 400, height: rect.height || 400 };
  if (svg) svg.attr('viewBox', `0 0 ${dims.width} ${dims.height}`);
}

function switchMode(mode) {
  if (mode === activeMode && renderers[mode]._root) return;
  renderers[activeMode].destroy();
  activeMode = mode;
  // Update toggle buttons
  document.querySelectorAll('.viz-toggle__btn').forEach(btn => {
    btn.classList.toggle('viz-toggle__btn--active', btn.dataset.mode === mode);
  });
  updateLegend(mode);
  renderers[mode].init(svg, dims);
  if (!state.empty) renderers[mode].render(state, dims);
}

function renderCurrent() {
  if (!svg) return;
  measureDims();
  const r = renderers[activeMode];
  if (!r._root) r.init(svg, dims);
  r.render(state, dims);
}

// Toggle bar listeners
document.querySelectorAll('.viz-toggle__btn').forEach(btn => {
  btn.addEventListener('click', () => switchMode(btn.dataset.mode));
});

// Resize observer
const resizeObs = new ResizeObserver(() => {
  measureDims();
  if (!state.empty) renderCurrent();
});
resizeObs.observe(document.getElementById('graph-container'));

// Init
initSVG();
updateLegend(activeMode);
renderers[activeMode].init(svg, dims);

/* ── Public API ─────────────────────────────────────────────── */

window.updateGraph = function (data) {
  state.update(data);
  const empty = document.querySelector('.graph-empty');
  if (empty && !state.empty) empty.style.display = 'none';
  renderCurrent();
};

window.resetGraph = function () {
  state.clear();
  renderCurrent();
  const empty = document.querySelector('.graph-empty');
  if (empty) empty.style.display = '';
};
