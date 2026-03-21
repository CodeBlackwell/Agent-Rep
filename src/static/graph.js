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

function buildHierarchyTree(state) {
  const domains = new Map();
  const nodeOf = id => state.nodes.get(id);

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
      for (const [, dom] of domains) {
        const cat = dom.children.get(e.from);
        if (cat) {
          cat.children.push({
            name: tgt.label, id: tgt.id,
            evidence_count: (tm.evidence_count || 0),
            status: tm.status || 'demonstrated',
            color: tgt.color,
            proficiency: tm.proficiency || null,
            evidence_links: tm.evidence_links || [],
          });
          break;
        }
      }
    }
  }

  // Handle gap-overlay edges
  for (const e of state.edges) {
    if (e.dashes) continue;
    const src = nodeOf(e.from);
    const tgt = nodeOf(e.to);
    if (!src || !tgt) continue;
    if ((src.meta || {}).type === 'category' && (tgt.meta || {}).type === 'skill') {
      let found = false;
      for (const [, dom] of domains) {
        if (dom.children.has(e.from)) { found = true; break; }
      }
      if (!found) {
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
              evidence_links: ((tgt.meta || {}).evidence_links || []),
            });
            break;
          }
        }
      }
    }
  }

  // Floating skill nodes → virtual "Claims" group
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
      if (!domains.has('dom:_other')) domains.set('dom:_other', { name: 'Claims', children: new Map() });
      const dom = domains.get('dom:_other');
      if (!dom.children.has('cat:_other')) dom.children.set('cat:_other', { name: 'Resume', children: [] });
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

  return { name: 'root', children: rootChildren };
}

/* ── Flat skill list from state ────────────────────────────── */

function getSkillList(state) {
  // Build skill→domain lookup from edges
  const skillDomain = new Map();
  for (const e of state.edges) {
    const src = state.nodes.get(e.from);
    const tgt = state.nodes.get(e.to);
    if (src && tgt && (src.meta || {}).type === 'category' && (tgt.meta || {}).type === 'skill') {
      // Find the domain for this category
      for (const e2 of state.edges) {
        const d = state.nodes.get(e2.from);
        if (d && (d.meta || {}).type === 'domain' && e2.to === e.from) {
          skillDomain.set(tgt.id, d.label);
          break;
        }
      }
    }
  }
  return [...state.nodes.values()]
    .filter(n => (n.meta || {}).type === 'skill')
    .map(n => ({
      name: n.label,
      id: n.id,
      evidence_count: (n.meta || {}).evidence_count || 0,
      status: (n.meta || {}).status || 'demonstrated',
      proficiency: (n.meta || {}).proficiency || null,
      evidence_links: (n.meta || {}).evidence_links || [],
      domain: skillDomain.get(n.id) || '',
    }))
    .sort((a, b) => b.evidence_count - a.evidence_count);
}

/* ── Status helpers ─────────────────────────────────────────── */

const STATUS_FILL = {
  demonstrated: '#5a7a4f',
  claimed_only: '#9e9890',
  gap: '#c4756a',
};

function statusColor(status) {
  return STATUS_FILL[status] || STATUS_FILL.demonstrated;
}

/* ── Domain color palette ──────────────────────────────────── */

const DOMAIN_HUES = {};
const PALETTE = [
  '#4a7c59', '#5b7fa5', '#8b6f47', '#7a5980', '#5a8a8a',
  '#8a6b5a', '#6b7a3a', '#6a5a9a', '#9a6a5a', '#4a8a6a',
];
let _hueIdx = 0;

function domainColor(domainName) {
  if (!DOMAIN_HUES[domainName]) {
    DOMAIN_HUES[domainName] = PALETTE[_hueIdx % PALETTE.length];
    _hueIdx++;
  }
  return DOMAIN_HUES[domainName];
}

function skillFill(d, domainName) {
  if (d.status === 'gap') return '#e8d0cc';
  if (d.status === 'claimed_only') return '#d4cec6';
  return domainColor(domainName);
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
  // Position within panel bounds
  let left = evt.clientX - panel.left + 14;
  let top = evt.clientY - panel.top - 10;
  // Clamp so tooltip doesn't overflow right/bottom
  const maxW = panel.width - 20;
  if (left + 280 > maxW) left = maxW - 280;
  if (left < 4) left = 4;
  tt.style.left = left + 'px';
  tt.style.top = top + 'px';
}

function hideTooltip() {
  ensureTooltip().classList.remove('viz-tooltip--visible');
}

function _ghLink(repo, path, line) {
  return `https://github.com/codeblackwell/${repo}/blob/main/${path}#L${line}`;
}

function tipHtml(d) {
  const s = d.status || '';
  const p = d.proficiency || '';
  const ev = d.evidence_count ?? 0;
  const nm = d.name || '';
  const links = d.evidence_links || [];

  let h = `<strong>${nm}</strong>`;
  if (p) h += `<span class="tip-prof tip-prof--${p}">${p}</span>`;
  if (ev > 0) h += `<div class="tip-count">${ev} code snippets</div>`;
  if (s === 'claimed_only') h += `<div class="tip-status">Resume claim — no code evidence</div>`;
  if (s === 'gap') h += `<div class="tip-status tip-status--gap">Gap — not demonstrated</div>`;

  if (links.length > 0) {
    h += '<div class="tip-links">';
    for (const l of links) {
      const url = _ghLink(l.repo, l.path, l.line);
      const short = l.repo + '/' + l.path.split('/').pop() + '#L' + l.line;
      h += `<a href="${url}" target="_blank" class="tip-link">${short}</a>`;
    }
    h += '</div>';
  }

  return h;
}

/* ── Treemap Renderer ──────────────────────────────────────── */

const TreemapRenderer = {
  _root: null,

  init(svg, dims) {
    this._root = svg.append('g').attr('class', 'treemap-root');
  },

  render(state, dims) {
    const g = this._root;
    g.selectAll('*').remove();
    if (state.empty) return;

    const tree = buildHierarchyTree(state);
    const root = d3.hierarchy(tree)
      .sum(d => {
        if (d.children) return 0;
        return Math.max(d.evidence_count || 0, 20); // min size for claimed/gap
      })
      .sort((a, b) => (b.value || 0) - (a.value || 0));

    const pad = 14;
    d3.treemap()
      .size([dims.width - pad * 2, dims.height - pad * 2])
      .paddingOuter(6)
      .paddingTop(22)
      .paddingInner(3)
      .round(true)
      (root);

    const allNodes = root.descendants().filter(d => d.depth > 0);
    const gNode = g.attr('transform', `translate(${pad},${pad})`);

    // Domain & category backgrounds
    gNode.selectAll('rect.treemap-group')
      .data(allNodes.filter(d => d.children), d => d.data.name)
      .join(
        enter => enter.append('rect')
          .attr('class', 'treemap-group')
          .attr('x', d => d.x0)
          .attr('y', d => d.y0)
          .attr('width', d => Math.max(0, d.x1 - d.x0))
          .attr('height', d => Math.max(0, d.y1 - d.y0))
          .attr('rx', 4)
          .style('fill', d => d.depth === 1 ? '#ebe6df' : '#f0ece6')
          .style('stroke', '#d4cdc4')
          .style('stroke-width', d => d.depth === 1 ? 1 : 0.5)
          .style('opacity', 0)
          .transition().duration(400)
          .style('opacity', 1)
      );

    // Domain & category labels
    gNode.selectAll('text.treemap-group-label')
      .data(allNodes.filter(d => d.children), d => d.data.name)
      .join('text')
      .attr('class', 'treemap-group-label')
      .attr('x', d => d.x0 + 6)
      .attr('y', d => d.y0 + 15)
      .style('font-size', d => d.depth === 1 ? '0.72rem' : '0.65rem')
      .style('fill', '#8a8380')
      .style('font-weight', d => d.depth === 1 ? '400' : '300')
      .text(d => {
        const w = d.x1 - d.x0;
        if (w < 40) return '';
        const maxChars = Math.floor(w / 7);
        return d.data.name.length > maxChars ? d.data.name.slice(0, maxChars - 1) + '…' : d.data.name;
      });

    // Skill tiles
    const leaves = root.leaves();
    gNode.selectAll('rect.treemap-leaf')
      .data(leaves, d => d.data.name)
      .join(
        enter => enter.append('rect')
          .attr('class', 'treemap-leaf')
          .attr('x', d => d.x0)
          .attr('y', d => d.y0)
          .attr('width', d => Math.max(0, d.x1 - d.x0))
          .attr('height', d => Math.max(0, d.y1 - d.y0))
          .attr('rx', 3)
          .style('fill', d => {
            if (d.data.status === 'gap') return '#e8d0cc';
            if (d.data.status === 'claimed_only') return '#d4cec6';
            const dom = d.parent && d.parent.parent ? d.parent.parent.data.name : '';
            return domainColor(dom);
          })
          .style('stroke', d => d.data.status === 'gap' ? '#c4756a' : d.data.status === 'claimed_only' ? '#b0a898' : 'none')
          .style('stroke-width', d => d.data.status !== 'demonstrated' ? 1.5 : 0)
          .style('stroke-dasharray', d => d.data.status === 'gap' ? '3 2' : 'none')
          .style('opacity', 0)
          .on('mouseover', (evt, d) => {
            showTooltip(evt, tipHtml(d.data));
            d3.select(evt.target).style('opacity', 1);
          })
          .on('mouseout', (evt, d) => {
            hideTooltip();
            d3.select(evt.target).style('opacity', 0.88);
          })
          .transition().duration(500).ease(d3.easeCubicOut)
          .style('opacity', 0.88)
      );

    // Skill labels inside tiles
    gNode.selectAll('text.treemap-label')
      .data(leaves, d => d.data.name)
      .join('text')
      .attr('class', 'treemap-label')
      .attr('x', d => d.x0 + 4)
      .attr('y', d => d.y0 + (d.y1 - d.y0) / 2 + 4)
      .style('font-size', d => {
        const w = d.x1 - d.x0;
        return w > 80 ? '0.72rem' : '0.6rem';
      })
      .style('fill', d => d.data.status === 'demonstrated' ? '#fff' : '#4a4a4a')
      .style('pointer-events', 'none')
      .text(d => {
        const w = d.x1 - d.x0;
        const h = d.y1 - d.y0;
        if (w < 30 || h < 16) return '';
        const maxChars = Math.floor(w / 6.5);
        return d.data.name.length > maxChars ? d.data.name.slice(0, maxChars - 1) + '…' : d.data.name;
      });
  },

  destroy() {
    if (this._root) this._root.remove();
    this._root = null;
  }
};

/* ── Bar Chart Renderer ────────────────────────────────────── */

const BarRenderer = {
  _root: null,

  init(svg, dims) {
    this._root = svg.append('g').attr('class', 'bar-root');
  },

  render(state, dims) {
    const g = this._root;
    g.selectAll('*').remove();
    if (state.empty) return;

    const skills = getSkillList(state);
    if (skills.length === 0) return;

    const margin = { top: 16, right: 20, bottom: 16, left: 10 };
    const w = dims.width - margin.left - margin.right;
    const barH = Math.min(28, Math.max(18, (dims.height - margin.top - margin.bottom) / skills.length - 4));
    const gap = 4;
    const totalH = skills.length * (barH + gap);
    const labelW = Math.min(140, w * 0.35);
    const barW = w - labelW - 50; // reserve space for count label

    const maxEv = Math.max(1, ...skills.map(s => s.evidence_count));
    const x = d3.scaleLinear().domain([0, maxEv]).range([0, barW]);

    const gInner = g.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    skills.forEach((skill, i) => {
      const y = i * (barH + gap);
      const row = gInner.append('g').attr('class', 'bar-row');

      // Skill name label
      row.append('text')
        .attr('x', labelW - 6)
        .attr('y', y + barH / 2 + 4)
        .attr('text-anchor', 'end')
        .style('font-size', '0.75rem')
        .style('fill', skill.status === 'gap' ? '#b05a4f' : skill.status === 'claimed_only' ? '#8a8380' : '#3d3d3d')
        .text(() => {
          const maxChars = Math.floor(labelW / 7);
          return skill.name.length > maxChars ? skill.name.slice(0, maxChars - 1) + '…' : skill.name;
        });

      // Bar
      const barX = labelW;
      const barWidth = skill.evidence_count > 0 ? x(skill.evidence_count) : barW * 0.04; // min visible width

      row.append('rect')
        .attr('x', barX)
        .attr('y', y)
        .attr('width', 0)
        .attr('height', barH)
        .attr('rx', 3)
        .style('fill', skill.status === 'demonstrated' ? domainColor(skill.domain) : statusColor(skill.status))
        .style('stroke', skill.status === 'gap' ? '#c4756a' : skill.status === 'claimed_only' ? '#b0a898' : 'none')
        .style('stroke-width', skill.status !== 'demonstrated' ? 1 : 0)
        .style('stroke-dasharray', skill.status === 'gap' ? '3 2' : 'none')
        .style('opacity', 0.85)
        .on('mouseover', (evt) => {
          showTooltip(evt, tipHtml(skill));
          d3.select(evt.target).style('opacity', 1);
        })
        .on('mouseout', (evt) => {
          hideTooltip();
          d3.select(evt.target).style('opacity', 0.85);
        })
        .transition().duration(500).delay(i * 60).ease(d3.easeCubicOut)
        .attr('width', barWidth);

      // Evidence count
      if (skill.evidence_count > 0) {
        row.append('text')
          .attr('x', barX + barWidth + 6)
          .attr('y', y + barH / 2 + 4)
          .style('font-size', '0.68rem')
          .style('fill', '#8a8380')
          .style('opacity', 0)
          .text(skill.evidence_count)
          .transition().duration(400).delay(i * 60 + 300)
          .style('opacity', 1);
      }
    });

    // Adjust viewBox if content exceeds panel height
    const neededH = totalH + margin.top + margin.bottom;
    if (neededH > dims.height) {
      svg.attr('viewBox', `0 0 ${dims.width} ${neededH}`);
    }
  },

  destroy() {
    if (this._root) this._root.remove();
    this._root = null;
  }
};

/* ── Legend ──────────────────────────────────────────────────── */

const LEGENDS = {
  treemap: `
    <span><i class="dot" style="background:#5a7a4f"></i> Demonstrated</span>
    <span><i class="dot" style="background:#9e9890"></i> Claimed</span>
    <span><i class="dot" style="background:#c4756a"></i> Gap</span>
    <span class="legend-note">Tile size = evidence count</span>
  `,
  bars: `
    <span><i class="dot" style="background:#5a7a4f"></i> Demonstrated</span>
    <span><i class="dot" style="background:#9e9890"></i> Claimed</span>
    <span><i class="dot" style="background:#c4756a"></i> Gap</span>
    <span class="legend-note">Bar length = evidence count</span>
  `,
};

function updateLegend(mode) {
  const el = document.getElementById('viz-legend');
  if (el) el.innerHTML = LEGENDS[mode] || '';
}

/* ── Orchestrator ───────────────────────────────────────────── */

const renderers = { treemap: TreemapRenderer, bars: BarRenderer };
let activeMode = 'treemap';
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

document.querySelectorAll('.viz-toggle__btn').forEach(btn => {
  btn.addEventListener('click', () => switchMode(btn.dataset.mode));
});

new ResizeObserver(() => {
  measureDims();
  if (!state.empty) renderCurrent();
}).observe(document.getElementById('graph-container'));

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
