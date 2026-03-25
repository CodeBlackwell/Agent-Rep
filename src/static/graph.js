/* ── Graph State ─────────────────────────────────────────────── */

class GraphState {
  constructor() { this.clear(); }

  update(data) {
    this._queryCounter++;
    const qi = this._queryCounter;
    for (const n of data.nodes) {
      if (!this.nodes.has(n.id)) { n._query = qi; this.nodes.set(n.id, n); }
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
    this._queryCounter = 0;
  }

  get empty() { return this.nodes.size === 0; }

  getDomains() {
    const out = [];
    for (const [id, n] of this.nodes) {
      if ((n.meta || {}).type === 'domain') out.push({ id, name: n.label });
    }
    return out.sort((a, b) => a.name.localeCompare(b.name));
  }

  filteredView(domainIds) {
    if (!domainIds || domainIds.length === 0) return this;
    const domSet = new Set(domainIds);
    const keep = new Set(domainIds);
    // domain → category edges
    for (const e of this.edges) { if (domSet.has(e.from)) keep.add(e.to); }
    // category → skill edges
    const cats = new Set([...keep].filter(id => !domSet.has(id)));
    for (const e of this.edges) { if (cats.has(e.from)) keep.add(e.to); }
    const v = new GraphState();
    v._queryCounter = this._queryCounter;
    for (const [id, n] of this.nodes) { if (keep.has(id)) v.nodes.set(id, n); }
    for (const e of this.edges) {
      if (keep.has(e.from) && keep.has(e.to)) {
        v.edges.push(e);
        v._edgeSet.add(e._key || (e.from + '\u2192' + e.to));
      }
    }
    return v;
  }
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
            repo_breakdown: tm.repo_breakdown || [],
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
              repo_breakdown: ((tgt.meta || {}).repo_breakdown || []),
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
      repo_breakdown: (n.meta || {}).repo_breakdown || [],
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

/* ── Repo luminance variants ─────────────────────────────── */

// Stable repo ordering across all tiles so the same repo always gets the same shade
const REPO_ORDER = [];

function _ensureRepoOrder(repos) {
  for (const r of repos) {
    if (REPO_ORDER.indexOf(r.repo) === -1) REPO_ORDER.push(r.repo);
  }
}

function _hexToHSL(hex) {
  let r = parseInt(hex.slice(1, 3), 16) / 255;
  let g = parseInt(hex.slice(3, 5), 16) / 255;
  let b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0, l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
  }
  return [h * 360, s * 100, l * 100];
}

function _hslToHex(h, s, l) {
  s /= 100; l /= 100;
  const k = n => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  const toHex = x => Math.round(x * 255).toString(16).padStart(2, '0');
  return '#' + toHex(f(0)) + toHex(f(8)) + toHex(f(4));
}

function repoShade(baseHex, repoName) {
  const idx = REPO_ORDER.indexOf(repoName);
  const [h, s, l] = _hexToHSL(baseHex);
  // Spread repos across luminance: darkest first, then lighter
  // Range: base lightness ± 18%, capped to [20, 70]
  const steps = Math.max(REPO_ORDER.length, 1);
  const offset = (idx / steps) * 36 - 18;  // -18 to +18
  const newL = Math.max(20, Math.min(70, l + offset));
  // Slight saturation shift to add depth
  const newS = Math.max(15, Math.min(85, s - offset * 0.3));
  return _hslToHex(h, newS, newL);
}

/* ── Tooltip ────────────────────────────────────────────────── */

let tooltip;
function ensureTooltip() {
  if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.className = 'viz-tooltip';
    document.body.appendChild(tooltip);
  }
  return tooltip;
}

function _positionTooltip(evt) {
  const tt = ensureTooltip();
  const ttW = tt.offsetWidth || 280;
  const ttH = tt.offsetHeight || 100;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  // Default: right of cursor, above cursor
  let x = evt.clientX + 14;
  let y = evt.clientY - ttH - 10;
  // Flip right → left if overflowing right
  if (x + ttW > vw - 8) x = evt.clientX - ttW - 10;
  // Flip above → below if overflowing top
  if (y < 4) y = evt.clientY + 18;
  // Final clamp
  if (x < 4) x = 4;
  if (y + ttH > vh - 4) y = vh - ttH - 4;
  if (y < 4) y = 4;
  tt.style.transform = `translate(${x}px, ${y}px)`;
}

function showTooltip(evt, html) {
  const tt = ensureTooltip();
  tt.innerHTML = html;
  tt.classList.add('viz-tooltip--visible');
  _positionTooltip(evt);
}

function moveTooltip(evt) {
  _positionTooltip(evt);
}

function hideTooltip() {
  ensureTooltip().classList.remove('viz-tooltip--visible');
}

function _ghLink(repo, path, line, branch) {
  const b = branch || 'main';
  const owner = window.__GITHUB_OWNER__ || 'codeblackwell';
  return `https://github.com/${owner}/${repo}/blob/${b}/${path}#L${line}`;
}

function tipHtml(d, domBase) {
  const s = d.status || '';
  const p = d.proficiency || '';
  const ev = d.evidence_count ?? 0;
  const nm = d.name || '';
  const links = d.evidence_links || [];
  const bd = d.repo_breakdown || [];

  let h = `<strong>${nm}</strong>`;
  if (p) h += `<span class="tip-prof tip-prof--${p}">${p}</span>`;
  if (ev > 0) h += `<div class="tip-count">${ev} code snippets</div>`;
  if (s === 'claimed_only') h += `<div class="tip-status">Resume claim — no code evidence</div>`;
  if (s === 'gap') h += `<div class="tip-status tip-status--gap">Gap — not demonstrated</div>`;

  // Repo breakdown with color swatches
  if (bd.length > 1 && domBase) {
    h += '<div class="tip-repos">';
    for (const r of bd) {
      h += `<div class="tip-repo-row">` +
        `<span class="tip-repo-swatch" style="background:${repoShade(domBase, r.repo)}"></span>` +
        `<span class="tip-repo-name">${r.repo}</span>` +
        `<span class="tip-repo-count">${r.count}</span>` +
        `</div>`;
    }
    h += '</div>';
  }

  if (links.length > 0) {
    let hasPrivate = false;
    h += '<div class="tip-links">';
    for (const l of links) {
      const url = _ghLink(l.repo, l.path, l.line, l.branch);
      const short = l.repo + '/' + l.path.split('/').pop() + '#L' + l.line;
      const lock = l.private ? '<span class="tip-lock" title="Private repo">\u{1F512}</span> ' : '';
      h += `<a href="${url}" target="_blank" class="tip-link">${lock}${short}</a>`;
      if (l.private) hasPrivate = true;
    }
    if (hasPrivate) h += '<div class="tip-private">Private repo \u2014 happy to walk through it, reach out!</div>';
    h += '</div>';
  }

  return h;
}

/* ── Reference Index Modal ──────────────────────────────────── */

let refModal = null;

function _ensureModal() {
  if (refModal) return refModal;
  refModal = document.createElement('div');
  refModal.className = 'ref-modal';
  refModal.innerHTML =
    '<div class="ref-modal__backdrop"></div>' +
    '<div class="ref-modal__panel">' +
      '<button class="ref-modal__close" aria-label="Close">&times;</button>' +
      '<div class="ref-modal__header"></div>' +
      '<div class="ref-modal__body"></div>' +
    '</div>';
  document.body.appendChild(refModal);
  refModal.querySelector('.ref-modal__backdrop').addEventListener('click', closeRefModal);
  refModal.querySelector('.ref-modal__close').addEventListener('click', closeRefModal);
  return refModal;
}

// Expose for chat.js evidence panel reuse
window._ensureRefModal = _ensureModal;

function closeRefModal() {
  if (refModal) refModal.classList.remove('ref-modal--open');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeRefModal();
});

function openRefModal(skillName) {
  const m = _ensureModal();
  const header = m.querySelector('.ref-modal__header');
  const body = m.querySelector('.ref-modal__body');

  header.innerHTML = `<h2>${skillName}</h2><p class="ref-modal__loading">Loading references…</p>`;
  body.innerHTML = '';
  m.classList.add('ref-modal--open');

  fetch(`/api/skills/${encodeURIComponent(skillName)}/references`)
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(data => _renderRefModal(header, body, data))
    .catch(() => {
      header.querySelector('.ref-modal__loading').textContent = 'Could not load references.';
    });
}

const LANG_ICONS = { py: 'Python', js: 'JavaScript', ts: 'TypeScript', tsx: 'TypeScript', jsx: 'JavaScript', java: 'Java', go: 'Go', rs: 'Rust', rb: 'Ruby', cpp: 'C++', c: 'C' };

function _renderRefModal(header, body, data) {
  const profClass = data.proficiency ? `tip-prof tip-prof--${data.proficiency}` : '';

  // Group by repo
  const byRepo = new Map();
  for (const ref of data.references) {
    if (!byRepo.has(ref.repo)) byRepo.set(ref.repo, []);
    byRepo.get(ref.repo).push(ref);
  }
  const repoNames = [...byRepo.keys()];

  header.innerHTML =
    `<h2>${data.skill}</h2>` +
    `<div class="ref-modal__meta">` +
      `<span class="ref-modal__path">${data.domain} › ${data.category}</span>` +
      (data.proficiency ? `<span class="${profClass}">${data.proficiency}</span>` : '') +
    `</div>` +
    `<div class="ref-modal__stats">` +
      `${data.snippet_count} snippet${data.snippet_count !== 1 ? 's' : ''} across ` +
      `${data.repo_count} repo${data.repo_count !== 1 ? 's' : ''}` +
    `</div>`;

  // Repo filter (only show if more than one repo)
  if (repoNames.length > 1) {
    const filterDiv = document.createElement('div');
    filterDiv.className = 'ref-filter';
    const allBtn = document.createElement('button');
    allBtn.className = 'ref-filter__btn ref-filter__btn--active';
    allBtn.textContent = `All (${data.references.length})`;
    allBtn.dataset.repo = '';
    filterDiv.appendChild(allBtn);
    for (const repo of repoNames) {
      const btn = document.createElement('button');
      btn.className = 'ref-filter__btn';
      btn.textContent = `${repo} (${byRepo.get(repo).length})`;
      btn.dataset.repo = repo;
      filterDiv.appendChild(btn);
    }
    header.appendChild(filterDiv);

    filterDiv.addEventListener('click', e => {
      const btn = e.target.closest('.ref-filter__btn');
      if (!btn) return;
      filterDiv.querySelectorAll('.ref-filter__btn').forEach(b => b.classList.remove('ref-filter__btn--active'));
      btn.classList.add('ref-filter__btn--active');
      _renderRefList(body, byRepo, btn.dataset.repo || null);
    });
  }

  if (data.references.length === 0) {
    body.innerHTML = '<p class="ref-modal__empty">No code evidence found for this skill.</p>';
    return;
  }

  _renderRefList(body, byRepo, null);
}

function _renderRefList(body, byRepo, filterRepo) {
  let html = '';
  let hasPrivate = false;
  for (const [repo, refs] of byRepo) {
    if (filterRepo && repo !== filterRepo) continue;
    const isPrivate = refs[0] && refs[0].private;
    if (isPrivate) hasPrivate = true;
    const repoUrl = `https://github.com/${window.__GITHUB_OWNER__ || 'codeblackwell'}/${repo}`;
    const lock = isPrivate ? '<span class="ref-repo__lock" title="Private repository">\u{1F512}</span>' : '';
    html += `<div class="ref-repo">`;
    html += `<h3 class="ref-repo__name"><a href="${repoUrl}" target="_blank">${repo}</a> ${lock}</h3>`;

    for (const ref of refs) {
      const url = _ghLink(ref.repo, ref.path, ref.start_line, ref.branch);
      const langLabel = LANG_ICONS[ref.language] || ref.language || '';
      const lineRange = ref.end_line > ref.start_line
        ? `L${ref.start_line}\u2013${ref.end_line}`
        : `L${ref.start_line}`;
      const dates = ref.first_seen
        ? (ref.first_seen === ref.last_seen ? ref.first_seen : `${ref.first_seen} \u2192 ${ref.last_seen}`)
        : '';

      html += `<div class="ref-item">`;
      html += `<div class="ref-item__file">`;
      html += `<a href="${url}" target="_blank" class="ref-item__link">${ref.path}</a>`;
      html += `<span class="ref-item__line">${lineRange}</span>`;
      if (langLabel) html += `<span class="ref-item__lang">${langLabel}</span>`;
      html += `</div>`;
      html += `<div class="ref-item__name">${ref.snippet_name}</div>`;
      if (ref.context) html += `<div class="ref-item__context">${ref.context}</div>`;
      if (dates) html += `<div class="ref-item__dates">${dates}</div>`;
      if (ref.content) {
        const escaped = ref.content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const lineCount = ref.content.split('\n').length;
        const langCls = ref.language ? ` class="language-${ref.language}"` : '';
        html += `<details class="ref-item__code-collapse">` +
          `<summary class="ref-item__code-toggle"><span class="ref-item__code-arrow">\u25B8</span> ${lineCount} line${lineCount !== 1 ? 's' : ''}</summary>` +
          `<pre class="ref-item__code-pre"><code${langCls}>${escaped}</code></pre>` +
          `</details>`;
      }
      html += `</div>`;
    }

    html += `</div>`;
  }

  if (hasPrivate) {
    html += '<div class="ref-private-note">\u{1F512} Some code lives in a private repo. ' +
      'I\u2019d love to walk you through it \u2014 <a href="https://github.com/codeblackwell" target="_blank">reach out</a> and let\u2019s chat!</div>';
  }

  body.innerHTML = html;
  _highlightRefCode(body);
}

function _highlightRefCode(container) {
  if (!window.hljs) return;
  container.querySelectorAll('.ref-item__code-pre code:not([data-highlighted])').forEach(el => {
    hljs.highlightElement(el);
  });
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
        // Use log scale so high-volume skills (Testing: 10k) don't swallow
        // smaller but significant ones (FastAPI: 330). Min floor for gaps.
        const count = Math.max(d.evidence_count || 0, 20);
        return Math.log1p(count);
      })
      .sort((a, b) => (b.value || 0) - (a.value || 0));

    const mobile = dims.width < 400;
    const pad = mobile ? 4 : 14;
    d3.treemap()
      .size([dims.width - pad * 2, dims.height - pad * 2])
      .paddingOuter(mobile ? 2 : 6)
      .paddingTop(mobile ? 14 : 22)
      .paddingInner(mobile ? 2 : 3)
      .tile(d3.treemapSquarify.ratio(mobile ? 1.2 : 1.618))
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
      .attr('x', d => d.x0 + (mobile ? 3 : 6))
      .attr('y', d => d.y0 + (mobile ? 12 : 15))
      .style('font-size', d => mobile
        ? (d.depth === 1 ? '0.58rem' : '0.5rem')
        : (d.depth === 1 ? '0.72rem' : '0.65rem'))
      .style('fill', '#8a8380')
      .style('font-weight', d => d.depth === 1 ? '400' : '300')
      .text(d => {
        const w = d.x1 - d.x0;
        const h = d.y1 - d.y0;
        if (w < 30 || h < (mobile ? 14 : 20)) return '';
        const charW = mobile ? 5.5 : 7;
        const maxChars = Math.floor(w / charW);
        return d.data.name.length > maxChars ? d.data.name.slice(0, maxChars - 1) + '…' : d.data.name;
      });

    // Register all repo names for stable shade ordering
    const leaves = root.leaves();
    for (const leaf of leaves) {
      if (leaf.data.repo_breakdown) _ensureRepoOrder(leaf.data.repo_breakdown);
    }

    // Skill tiles — groups with repo stripes
    const leafGroups = gNode.selectAll('g.treemap-leaf-group')
      .data(leaves, d => d.data.name)
      .join(
        enter => {
          const g = enter.append('g').attr('class', 'treemap-leaf-group');

          // For each leaf, render either repo stripes or a solid rect
          g.each(function(d) {
            const el = d3.select(this);
            const w = Math.max(0, d.x1 - d.x0);
            const h = Math.max(0, d.y1 - d.y0);
            const dom = d.parent && d.parent.parent ? d.parent.parent.data.name : '';
            const baseColor = domainColor(dom);
            const bd = d.data.repo_breakdown || [];

            if (d.data.status !== 'demonstrated' || bd.length <= 1) {
              // Solid rect for gap/claimed/single-repo
              el.append('rect')
                .attr('class', 'treemap-leaf')
                .attr('x', d.x0).attr('y', d.y0)
                .attr('width', w).attr('height', h)
                .attr('rx', 3)
                .style('fill', skillFill(d.data, dom))
                .style('stroke', d.data.status === 'gap' ? '#c4756a' : d.data.status === 'claimed_only' ? '#b0a898' : 'none')
                .style('stroke-width', d.data.status !== 'demonstrated' ? 1.5 : 0)
                .style('stroke-dasharray', d.data.status === 'gap' ? '3 2' : 'none');
            } else {
              // Clip path for rounded corners
              const clipId = 'clip-' + d.data.name.replace(/[^a-zA-Z0-9]/g, '_') + '-' + Math.random().toString(36).slice(2, 6);
              el.append('clipPath').attr('id', clipId)
                .append('rect')
                .attr('x', d.x0).attr('y', d.y0)
                .attr('width', w).attr('height', h)
                .attr('rx', 3);

              const stripeG = el.append('g').attr('clip-path', 'url(#' + clipId + ')');
              const total = bd.reduce((s, r) => s + r.count, 0);
              let yOff = d.y0;
              for (const repo of bd) {
                const stripeH = (repo.count / total) * h;
                stripeG.append('rect')
                  .attr('class', 'treemap-stripe')
                  .attr('x', d.x0).attr('y', yOff)
                  .attr('width', w).attr('height', Math.max(0, stripeH))
                  .style('fill', repoShade(baseColor, repo.repo));
                yOff += stripeH;
              }
            }
          });

          // Invisible hit rect on top for events
          g.append('rect')
            .attr('class', 'treemap-leaf-hit')
            .attr('x', d => d.x0).attr('y', d => d.y0)
            .attr('width', d => Math.max(0, d.x1 - d.x0))
            .attr('height', d => Math.max(0, d.y1 - d.y0))
            .style('fill', 'transparent')
            .style('cursor', 'pointer')
            .on('mouseover', (evt, d) => {
              const dom = d.parent && d.parent.parent ? d.parent.parent.data.name : '';
              showTooltip(evt, tipHtml(d.data, domainColor(dom)));
              d3.select(evt.target.parentNode).style('opacity', 1);
            })
            .on('mousemove', (evt) => { moveTooltip(evt); })
            .on('mouseout', (evt) => {
              hideTooltip();
              d3.select(evt.target.parentNode).style('opacity', 0.88);
            })
            .on('click', (evt, d) => {
              evt.stopPropagation();
              hideTooltip();
              if (d.data.status === 'demonstrated') openRefModal(d.data.name);
            });

          g.style('opacity', 0)
            .transition().duration(500).ease(d3.easeCubicOut)
            .style('opacity', 0.88);

          return g;
        }
      );

    // Touch support for treemap tiles (SVG click unreliable on mobile)
    leafGroups.each(function(d) {
      this.addEventListener('touchend', (evt) => {
        evt.preventDefault();
        hideTooltip();
        if (d.data.status === 'demonstrated') openRefModal(d.data.name);
      }, { passive: false });
    });

    // Skill labels inside tiles
    gNode.selectAll('text.treemap-label')
      .data(leaves, d => d.data.name)
      .join('text')
      .attr('class', 'treemap-label')
      .attr('x', d => d.x0 + (mobile ? 3 : 4))
      .attr('y', d => d.y0 + (d.y1 - d.y0) / 2 + (mobile ? 3 : 4))
      .style('font-size', d => {
        const w = d.x1 - d.x0;
        if (mobile) return w > 60 ? '0.58rem' : '0.48rem';
        return w > 80 ? '0.72rem' : '0.6rem';
      })
      .style('fill', d => d.data.status === 'demonstrated' ? '#fff' : '#4a4a4a')
      .style('pointer-events', 'none')
      .text(d => {
        const w = d.x1 - d.x0;
        const h = d.y1 - d.y0;
        const minH = mobile ? 12 : 16;
        const minW = mobile ? 24 : 30;
        if (w < minW || h < minH) return '';
        const charW = mobile ? 5 : 6.5;
        const maxChars = Math.floor(w / charW);
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

    const mobile = dims.width < 400;
    const margin = mobile
      ? { top: 10, right: 12, bottom: 10, left: 6 }
      : { top: 16, right: 20, bottom: 16, left: 10 };
    const w = dims.width - margin.left - margin.right;
    const barH = Math.min(mobile ? 20 : 28, Math.max(mobile ? 14 : 18, (dims.height - margin.top - margin.bottom) / skills.length - (mobile ? 2 : 4)));
    const gap = mobile ? 2 : 4;
    const totalH = skills.length * (barH + gap);
    const labelW = Math.min(mobile ? 100 : 140, w * 0.35);
    const barW = w - labelW - 50; // reserve space for count label

    const maxEv = Math.max(1, ...skills.map(s => s.evidence_count));
    const x = d3.scaleLinear().domain([0, maxEv]).range([0, barW]);

    const gInner = g.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    skills.forEach((skill, i) => {
      const y = i * (barH + gap);
      const row = gInner.append('g')
        .attr('class', 'bar-row')
        .style('cursor', skill.status === 'demonstrated' ? 'pointer' : 'default');

      // Invisible hit area — full row width for easy tapping on mobile
      const hitArea = row.append('rect')
        .attr('x', 0)
        .attr('y', y)
        .attr('width', w)
        .attr('height', barH)
        .style('fill', 'transparent')
        .style('touch-action', 'none')
        .on('mouseover', (evt) => {
          showTooltip(evt, tipHtml(skill, skill.domain ? domainColor(skill.domain) : null));
          row.select('.bar-fill').style('opacity', 1);
        })
        .on('mousemove', (evt) => { moveTooltip(evt); })
        .on('mouseout', () => {
          hideTooltip();
          row.select('.bar-fill').style('opacity', 0.85);
        })
        .on('click', (evt) => {
          evt.stopPropagation();
          hideTooltip();
          if (skill.status === 'demonstrated') openRefModal(skill.name);
        });

      // Touch support — SVG click events are unreliable on mobile touch devices
      hitArea.node().addEventListener('touchend', (evt) => {
        evt.preventDefault();
        hideTooltip();
        if (skill.status === 'demonstrated') openRefModal(skill.name);
      }, { passive: false });

      // Skill name label
      row.append('text')
        .attr('x', labelW - 6)
        .attr('y', y + barH / 2 + 4)
        .attr('text-anchor', 'end')
        .style('font-size', mobile ? '0.6rem' : '0.75rem')
        .style('fill', skill.status === 'gap' ? '#b05a4f' : skill.status === 'claimed_only' ? '#8a8380' : '#3d3d3d')
        .style('pointer-events', 'none')
        .text(() => {
          const maxChars = Math.floor(labelW / 7);
          return skill.name.length > maxChars ? skill.name.slice(0, maxChars - 1) + '…' : skill.name;
        });

      // Bar
      const barX = labelW;
      const barWidth = skill.evidence_count > 0 ? x(skill.evidence_count) : barW * 0.04;

      row.append('rect')
        .attr('class', 'bar-fill')
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
        .style('pointer-events', 'none')
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

    // Always size the viewBox to fit content
    const neededH = totalH + margin.top + margin.bottom;
    svg.attr('viewBox', `0 0 ${dims.width} ${neededH}`);
    if (mobile) {
      document.getElementById('graph-container').style.height = neededH + 'px';
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

/* ── Domain Filter ─────────────────────────────────────────── */

let activeFilter = null; // null = all, Set<domainId> = filtered

function updateFilterBar() {
  const bar = document.getElementById('graph-filter');
  if (!bar) return;
  const domains = state.getDomains();
  if (domains.length < 2) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  bar.innerHTML = '';

  const allBtn = document.createElement('button');
  allBtn.className = 'filter-pill' + (!activeFilter ? ' filter-pill--active' : '');
  allBtn.dataset.domain = '';
  allBtn.textContent = 'All';
  bar.appendChild(allBtn);

  for (const d of domains) {
    const btn = document.createElement('button');
    btn.className = 'filter-pill' + (activeFilter && activeFilter.has(d.id) ? ' filter-pill--active' : '');
    btn.dataset.domain = d.id;
    const dot = document.createElement('span');
    dot.className = 'filter-dot';
    dot.style.background = domainColor(d.name);
    btn.appendChild(dot);
    btn.appendChild(document.createTextNode(d.name));
    bar.appendChild(btn);
  }
}

document.getElementById('graph-filter').addEventListener('click', e => {
  const btn = e.target.closest('.filter-pill');
  if (!btn) return;
  const did = btn.dataset.domain;
  if (!did) {
    activeFilter = null;
  } else {
    if (!activeFilter) activeFilter = new Set();
    if (activeFilter.has(did)) {
      activeFilter.delete(did);
      if (!activeFilter.size) activeFilter = null;
    } else {
      activeFilter.add(did);
    }
  }
  updateFilterBar();
  renderCurrent();
});

function getViewState() {
  if (!activeFilter) return state;
  return state.filteredView([...activeFilter]);
}

/* ── Orchestrator ───────────────────────────────────────────── */

const renderers = { treemap: TreemapRenderer, bars: BarRenderer };
const isMobile = window.innerWidth < 768;
let activeMode = isMobile ? 'bars' : 'treemap';
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

/* ── Mobile chat DOM relocation ─────────────────────────────── */

let mobileChat = null;

function ensureMobileChat() {
  if (mobileChat) return mobileChat;
  mobileChat = document.createElement('div');
  mobileChat.id = 'mobile-chat';
  const graphPanel = document.getElementById('graph-panel');
  const graphContainer = document.getElementById('graph-container');
  graphPanel.insertBefore(mobileChat, graphContainer);
  return mobileChat;
}

function showMobileChat() {
  const mc = ensureMobileChat();
  const msgs = document.getElementById('messages');
  const form = document.getElementById('chat-form');
  if (!mc.contains(msgs)) mc.appendChild(msgs);
  if (!mc.contains(form)) mc.appendChild(form);
  mc.style.display = 'flex';
  document.getElementById('graph-container').style.display = 'none';
  const filter = document.querySelector('.graph-filter');
  const empty = document.querySelector('.graph-empty');
  const legend = document.getElementById('viz-legend');
  if (filter) filter.style.display = 'none';
  if (empty) empty.style.display = 'none';
  if (legend) legend.style.display = 'none';
}

function hideMobileChat() {
  if (!mobileChat) return;
  const chatPanel = document.getElementById('chat-panel');
  const msgs = document.getElementById('messages');
  const form = document.getElementById('chat-form');
  if (mobileChat.contains(msgs)) chatPanel.appendChild(msgs);
  if (mobileChat.contains(form)) chatPanel.appendChild(form);
  mobileChat.style.display = 'none';
  document.getElementById('graph-container').style.display = '';
  const legend = document.getElementById('viz-legend');
  if (legend) legend.style.display = '';
  // graph-filter visibility managed by updateFilterBar
}

function syncToggle(mode) {
  document.querySelectorAll('.viz-toggle__btn').forEach(btn => {
    btn.classList.toggle('viz-toggle__btn--active', btn.dataset.mode === mode);
  });
}

/* ── Mode switching ────────────────────────────────────────── */

function switchMode(mode) {
  // Chat tab (mobile only — DOM relocation)
  if (mode === 'chat' && isMobile) {
    showMobileChat();
    syncToggle('chat');
    return;
  }

  // Leaving chat view — restore DOM
  if (isMobile) hideMobileChat();

  if (mode !== activeMode || !renderers[mode]._root) {
    renderers[activeMode].destroy();
    activeMode = mode;
    renderers[mode].init(svg, dims);
  }
  syncToggle(mode);
  updateLegend(mode);
  measureDims();
  if (!state.empty) renderers[mode].render(getViewState(), dims);
}

function renderCurrent() {
  if (!svg) return;
  measureDims();
  const viewState = getViewState();
  const r = renderers[activeMode];
  if (!r._root) r.init(svg, dims);
  r.render(viewState, dims);

}

document.querySelectorAll('.viz-toggle__btn').forEach(btn => {
  btn.addEventListener('click', () => switchMode(btn.dataset.mode));
});

new ResizeObserver(() => {
  measureDims();
  if (!state.empty) renderCurrent();
}).observe(document.getElementById('graph-container'));

initSVG();
syncToggle(isMobile ? 'chat' : activeMode);
updateLegend(activeMode);
renderers[activeMode].init(svg, dims);

/* ── Public API ─────────────────────────────────────────────── */

window.updateGraph = function (data) {
  state.update(data);
  const empty = document.querySelector('.graph-empty');
  if (empty && !state.empty) empty.style.display = 'none';
  const howto = document.getElementById('graph-howto');
  if (howto && !state.empty) howto.classList.add('graph-howto--hidden');
  updateFilterBar();
  renderCurrent();
};

window.switchVizMode = switchMode;

window.resetGraph = function () {
  state.clear();
  activeFilter = null;
  updateFilterBar();
  renderCurrent();
  const empty = document.querySelector('.graph-empty');
  if (empty) empty.style.display = '';
};

window.domainColor = domainColor;
