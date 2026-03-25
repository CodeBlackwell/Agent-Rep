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
  demonstrated: '#4a7856',
  claimed_only: '#9a9590',
  gap: '#b35a52',
};

function statusColor(status) {
  return STATUS_FILL[status] || STATUS_FILL.demonstrated;
}

/* ── Domain color palette ──────────────────────────────────── */

const DOMAIN_HUES = {};
const PALETTE = [
  '#4a7c55', '#4f6fa0', '#b57342', '#7a5982', '#48838f',
  '#9e4a50', '#6d8a4a', '#6a5a9a', '#7e7a42', '#96647e',
  '#4a8a72', '#8a7048',
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
  if (d.status === 'gap') return '#e6ccc6';
  if (d.status === 'claimed_only') return '#d6d2cc';
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
let _ttW = 280, _ttH = 100;
let _ttRaf = null;

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
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let x = evt.clientX + 14;
  let y = evt.clientY - _ttH - 10;
  if (x + _ttW > vw - 8) x = evt.clientX - _ttW - 10;
  if (y < 4) y = evt.clientY + 18;
  if (x < 4) x = 4;
  if (y + _ttH > vh - 4) y = vh - _ttH - 4;
  if (y < 4) y = 4;
  tt.style.transform = `translate(${x}px, ${y}px)`;
}

function showTooltip(evt, html) {
  const tt = ensureTooltip();
  tt.innerHTML = html;
  tt.classList.add('viz-tooltip--visible');
  _ttW = tt.offsetWidth || 280;
  _ttH = tt.offsetHeight || 100;
  _positionTooltip(evt);
}

function moveTooltip(evt) {
  if (_ttRaf) return;
  _ttRaf = requestAnimationFrame(() => {
    _ttRaf = null;
    _positionTooltip(evt);
  });
}

function hideTooltip() {
  if (_ttRaf) { cancelAnimationFrame(_ttRaf); _ttRaf = null; }
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

let _refHlObserver = null;

function _highlightRefCode(container) {
  if (!window.hljs) return;
  const els = container.querySelectorAll('.ref-item__code-pre code:not([data-highlighted])');
  if (window.IntersectionObserver) {
    if (!_refHlObserver) {
      _refHlObserver = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting || !window.hljs) continue;
          hljs.highlightElement(entry.target);
          _refHlObserver.unobserve(entry.target);
        }
      }, { rootMargin: '200px' });
    }
    els.forEach(el => _refHlObserver.observe(el));
  } else {
    els.forEach(el => hljs.highlightElement(el));
  }
}

/* ── Treemap Renderer ──────────────────────────────────────── */

const TreemapRenderer = {
  _root: null,

  init(svg, dims) {
    this._root = svg.append('g').attr('class', 'treemap-root');
  },

  render(state, dims) {
    const g = this._root;
    if (state.empty) { g.selectAll('*').remove(); return; }

    const tree = buildHierarchyTree(state);
    const root = d3.hierarchy(tree)
      .sum(d => {
        if (d.children) return 0;
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
    const T = 400;

    // Domain & category backgrounds — enter/update/exit
    gNode.selectAll('rect.treemap-group')
      .data(allNodes.filter(d => d.children), d => d.data.name)
      .join(
        enter => enter.append('rect')
          .attr('class', 'treemap-group')
          .attr('rx', 4)
          .style('fill', d => d.depth === 1 ? '#eae4dd' : '#efebe5')
          .style('stroke', '#d2cbc2')
          .style('stroke-width', d => d.depth === 1 ? 1 : 0.5)
          .style('opacity', 0)
          .attr('x', d => d.x0).attr('y', d => d.y0)
          .attr('width', d => Math.max(0, d.x1 - d.x0))
          .attr('height', d => Math.max(0, d.y1 - d.y0))
          .call(e => e.transition().duration(T).style('opacity', 1)),
        update => update.call(u => u.transition().duration(T)
          .attr('x', d => d.x0).attr('y', d => d.y0)
          .attr('width', d => Math.max(0, d.x1 - d.x0))
          .attr('height', d => Math.max(0, d.y1 - d.y0))),
        exit => exit.call(x => x.transition().duration(T).style('opacity', 0).remove())
      );

    // Domain & category labels — enter/update/exit
    function _groupLabelText(d) {
      const w = d.x1 - d.x0;
      const h = d.y1 - d.y0;
      if (w < 30 || h < (mobile ? 14 : 20)) return '';
      const charW = mobile ? 5.5 : 7;
      const maxChars = Math.floor(w / charW);
      return d.data.name.length > maxChars ? d.data.name.slice(0, maxChars - 1) + '\u2026' : d.data.name;
    }

    gNode.selectAll('text.treemap-group-label')
      .data(allNodes.filter(d => d.children), d => d.data.name)
      .join(
        enter => enter.append('text')
          .attr('class', 'treemap-group-label')
          .style('font-size', d => mobile
            ? (d.depth === 1 ? '0.58rem' : '0.5rem')
            : (d.depth === 1 ? '0.72rem' : '0.65rem'))
          .style('fill', '#8a8380')
          .style('font-weight', d => d.depth === 1 ? '400' : '300')
          .attr('x', d => d.x0 + (mobile ? 3 : 6))
          .attr('y', d => d.y0 + (mobile ? 12 : 15))
          .text(_groupLabelText),
        update => update.call(u => u.transition().duration(T)
          .attr('x', d => d.x0 + (mobile ? 3 : 6))
          .attr('y', d => d.y0 + (mobile ? 12 : 15)))
          .text(_groupLabelText),
        exit => exit.remove()
      );

    // Register all repo names for stable shade ordering
    const leaves = root.leaves();
    for (const leaf of leaves) {
      if (leaf.data.repo_breakdown) _ensureRepoOrder(leaf.data.repo_breakdown);
    }

    // Helper: rebuild leaf interior (stripes or solid rect) for a group element
    function _buildLeafInterior(el, d) {
      // Remove old interior except the hit rect
      el.selectAll(':not(.treemap-leaf-hit)').remove();
      const w = Math.max(0, d.x1 - d.x0);
      const h = Math.max(0, d.y1 - d.y0);
      const dom = d.parent && d.parent.parent ? d.parent.parent.data.name : '';
      const baseColor = domainColor(dom);
      const bd = d.data.repo_breakdown || [];

      if (d.data.status !== 'demonstrated' || bd.length <= 1) {
        el.insert('rect', '.treemap-leaf-hit')
          .attr('class', 'treemap-leaf')
          .attr('x', d.x0).attr('y', d.y0)
          .attr('width', w).attr('height', h)
          .attr('rx', 3)
          .style('fill', skillFill(d.data, dom))
          .style('stroke', d.data.status === 'gap' ? '#b35a52' : d.data.status === 'claimed_only' ? '#b0a898' : 'none')
          .style('stroke-width', d.data.status !== 'demonstrated' ? 1.5 : 0)
          .style('stroke-dasharray', d.data.status === 'gap' ? '3 2' : 'none');
      } else {
        const clipId = 'clip-' + d.data.name.replace(/[^a-zA-Z0-9]/g, '_') + '-' + Math.random().toString(36).slice(2, 6);
        el.insert('clipPath', '.treemap-leaf-hit').attr('id', clipId)
          .append('rect')
          .attr('x', d.x0).attr('y', d.y0)
          .attr('width', w).attr('height', h)
          .attr('rx', 3);
        const stripeG = el.insert('g', '.treemap-leaf-hit').attr('clip-path', 'url(#' + clipId + ')');
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
    }

    // Event handlers (shared between enter and update)
    function _bindLeafEvents(hit) {
      hit
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
    }

    // Skill tiles — enter/update/exit
    const leafGroups = gNode.selectAll('g.treemap-leaf-group')
      .data(leaves, d => d.data.name)
      .join(
        enter => {
          const eg = enter.append('g').attr('class', 'treemap-leaf-group');
          eg.each(function(d) { _buildLeafInterior(d3.select(this), d); });
          // Hit rect on top
          const hit = eg.append('rect').attr('class', 'treemap-leaf-hit')
            .attr('x', d => d.x0).attr('y', d => d.y0)
            .attr('width', d => Math.max(0, d.x1 - d.x0))
            .attr('height', d => Math.max(0, d.y1 - d.y0));
          _bindLeafEvents(hit);
          eg.style('opacity', 0)
            .transition().duration(500).ease(d3.easeCubicOut)
            .style('opacity', 0.88);
          return eg;
        },
        update => {
          // Rebuild interior with new positions, update hit rect
          update.each(function(d) { _buildLeafInterior(d3.select(this), d); });
          update.select('.treemap-leaf-hit')
            .attr('x', d => d.x0).attr('y', d => d.y0)
            .attr('width', d => Math.max(0, d.x1 - d.x0))
            .attr('height', d => Math.max(0, d.y1 - d.y0));
          return update;
        },
        exit => exit.call(x => x.transition().duration(T)
          .style('opacity', 0).remove())
      );

    // Touch support
    leafGroups.each(function(d) {
      if (!this._touchBound) {
        this._touchBound = true;
        this.addEventListener('touchend', (evt) => {
          evt.preventDefault();
          hideTooltip();
          if (d.data.status === 'demonstrated') openRefModal(d.data.name);
        }, { passive: false });
      }
    });

    // Skill labels — enter/update/exit
    function _leafLabelText(d) {
      const w = d.x1 - d.x0;
      const h = d.y1 - d.y0;
      const minH = mobile ? 12 : 16;
      const minW = mobile ? 24 : 30;
      if (w < minW || h < minH) return '';
      const charW = mobile ? 5 : 6.5;
      const maxChars = Math.floor(w / charW);
      return d.data.name.length > maxChars ? d.data.name.slice(0, maxChars - 1) + '\u2026' : d.data.name;
    }

    gNode.selectAll('text.treemap-label')
      .data(leaves, d => d.data.name)
      .join(
        enter => enter.append('text')
          .attr('class', 'treemap-label')
          .style('pointer-events', 'none')
          .style('fill', d => d.data.status === 'demonstrated' ? '#fff' : '#4a4a4a')
          .style('font-size', d => {
            const w = d.x1 - d.x0;
            if (mobile) return w > 60 ? '0.58rem' : '0.48rem';
            return w > 80 ? '0.72rem' : '0.6rem';
          })
          .attr('x', d => d.x0 + (mobile ? 3 : 4))
          .attr('y', d => d.y0 + (d.y1 - d.y0) / 2 + (mobile ? 3 : 4))
          .text(_leafLabelText),
        update => update
          .call(u => u.transition().duration(T)
            .attr('x', d => d.x0 + (mobile ? 3 : 4))
            .attr('y', d => d.y0 + (d.y1 - d.y0) / 2 + (mobile ? 3 : 4)))
          .style('font-size', d => {
            const w = d.x1 - d.x0;
            if (mobile) return w > 60 ? '0.58rem' : '0.48rem';
            return w > 80 ? '0.72rem' : '0.6rem';
          })
          .text(_leafLabelText),
        exit => exit.remove()
      );
  },

  destroy() {
    if (this._root) this._root.remove();
    this._root = null;
  }
};

/* ── Legend ──────────────────────────────────────────────────── */

const LEGENDS = {
  treemap: `
    <span><i class="dot" style="background:#4a7856"></i> Demonstrated</span>
    <span><i class="dot" style="background:#9a9590"></i> Claimed</span>
    <span><i class="dot" style="background:#b35a52"></i> Gap</span>
    <span class="legend-note">Tile size = evidence count</span>
  `,
  exhibits: null, // built dynamically by repo-tiles.js
};

function updateLegend(mode) {
  const el = document.getElementById('viz-legend');
  if (!el) return;
  const content = LEGENDS[mode];
  if (content === null) return; // managed externally
  el.innerHTML = content || '';
}

// Called by repo-tiles.js after domains are registered
window.buildExhibitsLegend = function () {
  const el = document.getElementById('exhibits-legend-slot');
  if (!el || activeMode !== 'exhibits') return;
  const entries = Object.entries(DOMAIN_HUES);
  if (!entries.length) return;
  let items = '';
  for (const [name, color] of entries) {
    items += `<span><i class="dot" style="background:${color}"></i>${name}</span>`;
  }
  el.innerHTML =
    '<div class="exhibits-legend">' +
      '<span class="exhibits-legend__label">Skill Domains</span>' +
      '<div class="exhibits-legend__items">' + items + '</div>' +
    '</div>';
};

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

const renderers = { treemap: TreemapRenderer };
const isMobile = window.innerWidth < 768;
let activeMode = isMobile ? 'chat' : 'exhibits';
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

  const exhibitsEl = document.getElementById('exhibits-container');
  const graphEl = document.getElementById('graph-container');
  const filterEl = document.getElementById('graph-filter');

  if (mode === 'exhibits') {
    if (exhibitsEl) exhibitsEl.classList.remove('exhibits-container--hidden');
    if (graphEl) graphEl.style.display = 'none';
    if (filterEl) filterEl.style.display = 'none';
    activeMode = mode;
    syncToggle(mode);
    if (window.buildExhibitsLegend) window.buildExhibitsLegend();
    return;
  }

  // Treemap (or any renderer mode)
  if (exhibitsEl) exhibitsEl.classList.add('exhibits-container--hidden');
  if (graphEl) graphEl.style.display = '';

  if (mode !== activeMode || !renderers[mode] || !renderers[mode]._root) {
    if (renderers[activeMode]) renderers[activeMode].destroy();
    activeMode = mode;
    if (renderers[mode]) renderers[mode].init(svg, dims);
  }
  syncToggle(mode);
  updateLegend(mode);
  measureDims();
  if (!state.empty && renderers[mode]) renderers[mode].render(getViewState(), dims);
}

function renderCurrent() {
  if (!svg || !renderers[activeMode]) return;
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
// On desktop, start in exhibits mode — hide graph-container, show exhibits
if (!isMobile) {
  document.getElementById('graph-container').style.display = 'none';
  document.getElementById('graph-filter').style.display = 'none';
}

/* ── Public API ─────────────────────────────────────────────── */

window.updateGraph = function (data) {
  const wasEmpty = state.empty;
  state.update(data);
  const empty = document.querySelector('.graph-empty');
  if (empty && !state.empty) empty.style.display = 'none';
  const howto = document.getElementById('graph-howto');
  if (howto && !state.empty) howto.classList.add('graph-howto--hidden');
  // Auto-switch to treemap on first graph data
  if (wasEmpty && !state.empty && activeMode === 'exhibits') {
    switchMode('treemap');
  }
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
