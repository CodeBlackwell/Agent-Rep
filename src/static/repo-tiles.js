/* ── Repo Tiles — interactive donut rings ─────────────── */

(function () {
  const CAROUSEL = document.getElementById('exhibits-carousel');
  const DOTS = document.getElementById('carousel-dots');
  const DETAIL = document.getElementById('repo-detail');
  const STRIP = document.getElementById('hero-exhibits');
  const hasDesktop = CAROUSEL && DETAIL;
  if (!STRIP && !hasDesktop) return;

  const FEATURED = ['PROVE', 'SPICE', 'PANEL', 'C.R.A.C.K.', 'veridatum'];
  const DISPLAY_OVERRIDES = { veridatum: 'Veridatum' };
  const PAGE_SIZE = 5;
  const snippetCache = new Map();

  const SIZE = 110;
  const OUTER = SIZE / 2 - 6;
  const INNER = OUTER - 14;
  const EXP_SIZE = 200;
  const EXP_OUTER = EXP_SIZE / 2 - 4;
  const EXP_INNER = EXP_OUTER - 22;

  const pie = d3.pie().sort(null).value(d => d.value);
  const arc = d3.arc().innerRadius(INNER).outerRadius(OUTER);
  const arcExploded = d3.arc().innerRadius(INNER + 2).outerRadius(OUTER + 3);
  const expArc = d3.arc().innerRadius(EXP_INNER).outerRadius(EXP_OUTER);

  let expanded = null;
  let activeRequest = 0;

  function allTiles() {
    return document.querySelectorAll('.exhibits-container .repo-tile');
  }

  /* ── Render a single tile ──────────────────────── */

  function renderTile(repo) {
    const tile = document.createElement('div');
    tile.className = 'repo-tile';
    tile.dataset.repo = repo.name;

    const data = repo.domains.map(d => ({
      name: d.domain, value: d.snippets || d.skill_count || 1
    }));

    if (data.length) {
      const svgNS = 'http://www.w3.org/2000/svg';
      const svg = document.createElementNS(svgNS, 'svg');
      svg.setAttribute('viewBox', `0 0 ${SIZE} ${SIZE}`);
      svg.setAttribute('class', 'repo-tile__ring');

      const g = document.createElementNS(svgNS, 'g');
      g.setAttribute('transform', `translate(${SIZE / 2},${SIZE / 2})`);

      const slices = pie(data);
      for (const slice of slices) {
        const path = document.createElementNS(svgNS, 'path');
        path.setAttribute('d', arc(slice));
        path.setAttribute('fill', window.domainColor ? window.domainColor(slice.data.name) : '#5a7a4f');
        path.setAttribute('opacity', '0.85');
        path.dataset.domain = slice.data.name;
        g.appendChild(path);
      }
      svg.appendChild(g);
      tile.appendChild(svg);
      tile._slices = slices;
    }

    const name = document.createElement('div');
    name.className = 'repo-tile__name';
    name.textContent = repo.display_name || repo.name;
    tile.appendChild(name);

    tile.addEventListener('mouseenter', () => {
      if (expanded) return;
      tile.classList.add('repo-tile--hover');
      const container = tile.closest('.exhibits-container');
      if (container) container.classList.add('repo-tiles--has-hover');
      explodeSegments(tile, true);
    });

    tile.addEventListener('mouseleave', () => {
      if (expanded) return;
      tile.classList.remove('repo-tile--hover');
      const container = tile.closest('.exhibits-container');
      if (container) container.classList.remove('repo-tiles--has-hover');
      explodeSegments(tile, false);
    });

    tile.addEventListener('click', () => {
      if (expanded === repo.name) return;
      expandRepo(repo);
    });

    return tile;
  }

  /* ── Hover: explode / collapse arc segments ──── */

  function explodeSegments(tile, out) {
    const paths = tile.querySelectorAll('path[data-domain]');
    if (!tile._slices) return;
    tile._slices.forEach((slice, i) => {
      if (!paths[i]) return;
      paths[i].setAttribute('d', (out ? arcExploded : arc)(slice));
    });
  }

  /* ── Click: expand repo to center detail view ── */

  function expandRepo(repo) {
    expanded = repo.name;

    DETAIL.innerHTML = '';
    DETAIL.classList.add('repo-detail--visible');

    const data = repo.domains.map(d => ({
      name: d.domain, value: d.snippets || d.skill_count || 1
    }));
    if (data.length) {
      const svgNS = 'http://www.w3.org/2000/svg';
      const svg = document.createElementNS(svgNS, 'svg');
      svg.setAttribute('viewBox', `0 0 ${EXP_SIZE} ${EXP_SIZE}`);
      svg.setAttribute('class', 'repo-detail__ring');
      const g = document.createElementNS(svgNS, 'g');
      g.setAttribute('transform', `translate(${EXP_SIZE / 2},${EXP_SIZE / 2})`);
      for (const slice of pie(data)) {
        const path = document.createElementNS(svgNS, 'path');
        path.setAttribute('d', expArc(slice));
        path.setAttribute('fill', window.domainColor ? window.domainColor(slice.data.name) : '#5a7a4f');
        path.setAttribute('opacity', '0.9');
        g.appendChild(path);
      }
      svg.appendChild(g);
      DETAIL.appendChild(svg);
    }

    const title = document.createElement('h3');
    title.className = 'repo-detail__title';
    title.textContent = repo.display_name || repo.name;
    DETAIL.appendChild(title);

    const body = document.createElement('div');
    body.className = 'repo-detail__body';
    body.innerHTML = '<p class="repo-detail__loading">Loading…</p>';
    DETAIL.appendChild(body);

    const reqId = ++activeRequest;
    fetch(`/api/repositories/${encodeURIComponent(repo.name)}`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(detail => { if (reqId === activeRequest) renderDetail(body, detail); })
      .catch(() => { if (reqId === activeRequest) body.innerHTML = '<p class="repo-detail__loading">Could not load details</p>'; });
  }

  /* ── Render breakdown + accordion skill list ─── */

  function renderDetail(container, detail) {
    container.innerHTML = '';
    const bd = detail.breakdown || {};

    if (bd.tagline || bd.summary) {
      const section = document.createElement('div');
      section.className = 'repo-detail__breakdown';

      if (bd.tagline) {
        const tag = document.createElement('p');
        tag.className = 'repo-detail__tagline';
        tag.textContent = bd.tagline;
        section.appendChild(tag);
      }
      if (bd.summary) {
        const desc = document.createElement('p');
        desc.className = 'repo-detail__summary';
        desc.textContent = bd.summary;
        section.appendChild(desc);
      }
      if (bd.stack && bd.stack.length) {
        const pills = document.createElement('div');
        pills.className = 'repo-detail__stack';
        for (const tech of bd.stack) {
          const pill = document.createElement('span');
          pill.className = 'repo-detail__pill';
          pill.textContent = tech;
          pills.appendChild(pill);
        }
        section.appendChild(pills);
      }
      if (bd.url) {
        const link = document.createElement('a');
        link.href = bd.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.className = 'repo-detail__url';
        link.textContent = bd.url.replace(/^https?:\/\//, '');
        section.appendChild(link);
      }
      container.appendChild(section);
    }

    for (const [domain, skills] of Object.entries(detail.domains)) {
      const group = document.createElement('details');
      group.className = 'repo-detail__accordion';

      const hdr = document.createElement('summary');
      hdr.className = 'repo-detail__domain';
      const dot = document.createElement('span');
      dot.className = 'repo-detail__dot';
      dot.style.background = window.domainColor ? window.domainColor(domain) : '#5a7a4f';
      hdr.appendChild(dot);
      const label = document.createElement('span');
      label.textContent = domain;
      hdr.appendChild(label);
      const badge = document.createElement('span');
      badge.className = 'repo-detail__badge';
      badge.textContent = skills.length;
      hdr.appendChild(badge);
      group.appendChild(hdr);

      const body = document.createElement('div');
      body.className = 'repo-detail__accordion-body';
      for (const sk of skills.slice(0, 10)) {
        const skillDetails = document.createElement('details');
        skillDetails.className = 'repo-detail__skill-accordion';

        const summary = document.createElement('summary');
        summary.className = 'repo-detail__skill';
        const nameSpan = document.createElement('span');
        nameSpan.textContent = sk.skill;
        summary.appendChild(nameSpan);
        const countSpan = document.createElement('span');
        countSpan.className = 'repo-detail__count';
        countSpan.textContent = sk.snippets;
        summary.appendChild(countSpan);
        skillDetails.appendChild(summary);

        const snippetBody = document.createElement('div');
        snippetBody.className = 'repo-detail__snippet-body';
        skillDetails.appendChild(snippetBody);

        let loaded = false;
        skillDetails.addEventListener('toggle', () => {
          if (!skillDetails.open || loaded) return;
          loaded = true;
          loadSnippets(detail.name, sk.skill, snippetBody);
        });

        body.appendChild(skillDetails);
      }
      group.appendChild(body);
      container.appendChild(group);
    }
  }

  /* ── Lazy-load snippets for a skill accordion ──── */

  function loadSnippets(repoName, skillName, container) {
    const key = repoName + ':' + skillName;
    if (snippetCache.has(key)) {
      renderSnippets(snippetCache.get(key), repoName, container);
      return;
    }
    container.innerHTML = '<p class="repo-detail__loading">Loading…</p>';
    fetch('/api/repositories/' + encodeURIComponent(repoName) + '/skills/' + encodeURIComponent(skillName) + '/snippets')
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(data => { snippetCache.set(key, data); renderSnippets(data, repoName, container); })
      .catch(() => { container.innerHTML = '<p class="repo-detail__loading">Could not load snippets</p>'; });
  }

  function renderSnippets(snippets, repoName, container) {
    container.innerHTML = '';
    const LANGS = { py: 'Python', js: 'JavaScript', ts: 'TypeScript', tsx: 'TypeScript', jsx: 'JavaScript', java: 'Java', go: 'Go', rs: 'Rust' };
    for (const s of snippets) {
      const div = document.createElement('div');
      div.className = 'repo-detail__snippet';

      const fileLine = document.createElement('div');
      fileLine.className = 'repo-detail__snippet-file';
      const a = document.createElement('a');
      a.href = s.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.className = 'repo-detail__link';
      a.textContent = s.path;
      fileLine.appendChild(a);
      const range = document.createElement('span');
      range.className = 'repo-detail__snippet-range';
      range.textContent = s.end_line > s.start_line ? 'L' + s.start_line + '–' + s.end_line : 'L' + s.start_line;
      fileLine.appendChild(range);
      if (s.language && LANGS[s.language]) {
        const lang = document.createElement('span');
        lang.className = 'repo-detail__snippet-lang';
        lang.textContent = LANGS[s.language];
        fileLine.appendChild(lang);
      }
      div.appendChild(fileLine);

      if (s.context) {
        const ctx = document.createElement('p');
        ctx.className = 'repo-detail__snippet-context';
        ctx.textContent = s.context;
        div.appendChild(ctx);
      }

      if (s.content) {
        const escaped = s.content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const lines = s.content.split('\n').length;
        const langCls = s.language ? ' class="language-' + s.language + '"' : '';
        const code = document.createElement('details');
        code.className = 'repo-detail__snippet-code';
        code.innerHTML = '<summary><span class="repo-detail__snippet-arrow">▸</span> ' + lines + ' line' + (lines !== 1 ? 's' : '') + '</summary>' +
          '<pre class="repo-detail__snippet-pre"><code' + langCls + '>' + escaped + '</code></pre>';
        code.addEventListener('toggle', function() {
          this.querySelector('.repo-detail__snippet-arrow').textContent = this.open ? '▾' : '▸';
          if (this.open && window.hljs) window.hljs.highlightElement(this.querySelector('code'));
        });
        div.appendChild(code);
      } else if (s.private) {
        const redacted = document.createElement('span');
        redacted.className = 'repo-detail__snippet-redacted';
        redacted.textContent = 'PRIVATE — CODE REDACTED';
        div.appendChild(redacted);
      }

      container.appendChild(div);
    }
  }

  /* ── Close detail view ─────────────────────────── */

  function closeDetail() {
    if (!expanded) return;
    const container = document.querySelector('.exhibits-container');
    if (container) container.classList.remove('repo-tiles--has-hover');
    allTiles().forEach(t => {
      t.classList.remove('repo-tile--hover');
      explodeSegments(t, false);
    });
    expanded = null;
    DETAIL.classList.remove('repo-detail--visible');
  }

  const graphPanel = document.getElementById('graph-panel');
  if (graphPanel) graphPanel.addEventListener('click', (e) => {
    if (!expanded) return;
    if (DETAIL && DETAIL.contains(e.target) || e.target.closest('.repo-tile')) return;
    closeDetail();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeDetail(); closeSheet(); }
  });

  /* ── Mobile strip: mini ring renderer ──────── */

  function renderMiniRing(data, size) {
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
    svg.setAttribute('class', 'hero-strip__ring');
    const g = document.createElementNS(svgNS, 'g');
    g.setAttribute('transform', `translate(${size / 2},${size / 2})`);
    const r = size / 2 - 4;
    const miniArc = d3.arc().innerRadius(r - size * 0.13).outerRadius(r);
    for (const slice of pie(data)) {
      const path = document.createElementNS(svgNS, 'path');
      path.setAttribute('d', miniArc(slice));
      path.setAttribute('fill', window.domainColor ? window.domainColor(slice.data.name) : '#5a7a4f');
      path.setAttribute('opacity', '0.85');
      g.appendChild(path);
    }
    svg.appendChild(g);
    return svg;
  }

  /* ── Mobile strip: init tiles ──────────────── */

  function initMobileStrip(repos) {
    for (const repo of repos) {
      const data = repo.domains.map(d => ({ name: d.domain, value: d.snippets || d.skill_count || 1 }));
      if (!data.length) continue;
      const tile = document.createElement('div');
      tile.className = 'hero-strip__tile';
      tile.appendChild(renderMiniRing(data, 50));
      const name = document.createElement('div');
      name.className = 'hero-strip__name';
      name.textContent = repo.display_name || repo.name;
      tile.appendChild(name);
      tile.addEventListener('click', () => openSheet(repo));
      STRIP.appendChild(tile);
    }
  }

  /* ── Bottom sheet ──────────────────────────── */

  let sheetEl = null;
  let sheetBody = null;
  let dragStartY = 0;

  function ensureSheet() {
    if (sheetEl) return;
    sheetEl = document.createElement('div');
    sheetEl.className = 'repo-sheet';
    sheetEl.innerHTML = '<div class="repo-sheet__backdrop"></div>' +
      '<div class="repo-sheet__panel">' +
        '<div class="repo-sheet__handle"></div>' +
        '<div class="repo-sheet__header"></div>' +
        '<div class="repo-sheet__body"></div>' +
      '</div>';
    document.body.appendChild(sheetEl);
    sheetBody = sheetEl.querySelector('.repo-sheet__body');
    sheetEl.querySelector('.repo-sheet__backdrop').addEventListener('click', closeSheet);
    const panel = sheetEl.querySelector('.repo-sheet__panel');
    panel.addEventListener('touchstart', (e) => { dragStartY = e.touches[0].clientY; }, { passive: true });
    panel.addEventListener('touchend', (e) => {
      if (e.changedTouches[0].clientY - dragStartY > 80) closeSheet();
    });
  }

  function openSheet(repo) {
    ensureSheet();
    const header = sheetEl.querySelector('.repo-sheet__header');
    header.innerHTML = '';
    const data = repo.domains.map(d => ({ name: d.domain, value: d.snippets || d.skill_count || 1 }));
    if (data.length) {
      const ring = renderMiniRing(data, 120);
      ring.removeAttribute('class');
      ring.style.width = '120px';
      ring.style.height = '120px';
      ring.style.flexShrink = '0';
      header.appendChild(ring);
    }
    const title = document.createElement('h3');
    title.className = 'repo-sheet__title';
    title.textContent = repo.display_name || repo.name;
    header.appendChild(title);
    sheetBody.innerHTML = '<p class="repo-detail__loading">Loading…</p>';
    sheetEl.classList.add('repo-sheet--open');
    const reqId = ++activeRequest;
    fetch(`/api/repositories/${encodeURIComponent(repo.name)}`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(detail => { if (reqId === activeRequest) renderDetail(sheetBody, detail); })
      .catch(() => { if (reqId === activeRequest) sheetBody.innerHTML = '<p class="repo-detail__loading">Could not load details</p>'; });
  }

  function closeSheet() {
    if (sheetEl) sheetEl.classList.remove('repo-sheet--open');
  }

  /* ── Carousel pagination ────────────────────────── */

  let currentPage = 0;
  let totalPages = 1;
  let allTilesArr = [];

  /** Gap between arrows and tiles: scales with carousel width, clamped for tiny/large viewports. */
  function scaledArrowGapPx(wrapWidth) {
    const w = wrapWidth > 0 ? wrapWidth : (typeof window !== 'undefined' ? window.innerWidth : 16);
    return Math.round(Math.min(24, Math.max(8, w * 0.022)));
  }

  function updateArrowPositions() {
    // Only the desktop exhibits carousel uses arrows.
    const wrap = CAROUSEL?.parentNode;
    if (!wrap) return;

    const prev = wrap.querySelector('.carousel-arrow--prev');
    const next = wrap.querySelector('.carousel-arrow--next');
    if (!prev || !next) return;

    // If the carousel is hidden (responsive), skip positioning.
    const wrapRect = wrap.getBoundingClientRect();
    if (!wrapRect.width) return;

    // showPage() controls visibility via `style.display = 'none'` for non-visible tiles.
    const visibleTiles = allTilesArr.filter(t => t.style.display !== 'none' && t.getClientRects().length);
    if (!visibleTiles.length) return;

    const firstRect = visibleTiles[0].getBoundingClientRect();
    const lastRect = visibleTiles[visibleTiles.length - 1].getBoundingClientRect();

    // Read arrow sizes from the DOM so we don't hardcode anything fragile.
    const prevRect = prev.getBoundingClientRect();
    const nextRect = next.getBoundingClientRect();
    const prevHalfW = prevRect.width ? prevRect.width / 2 : 14;
    const nextHalfW = nextRect.width ? nextRect.width / 2 : 14;

    const gap = scaledArrowGapPx(wrapRect.width);
    // Target: center arrow next to the right edge of the last visible tile, etc.
    const nextCenterX = lastRect.right + gap;
    const prevCenterX = firstRect.left - gap;

    let nextLeft = nextCenterX - nextHalfW - wrapRect.left;
    let prevLeft = prevCenterX - prevHalfW - wrapRect.left;

    // Clamp to wrapper bounds to avoid arrows spilling outside on small widths.
    const nextMaxLeft = wrapRect.width - nextRect.width;
    const prevMaxLeft = wrapRect.width - prevRect.width;
    nextLeft = Math.max(0, Math.min(nextMaxLeft, nextLeft));
    prevLeft = Math.max(0, Math.min(prevMaxLeft, prevLeft));

    // Override the CSS `left/right` defaults with inline positioning.
    next.style.right = 'auto';
    next.style.left = `${nextLeft}px`;
    prev.style.right = 'auto';
    prev.style.left = `${prevLeft}px`;
  }

  function showPage(page) {
    currentPage = Math.max(0, Math.min(totalPages - 1, page));
    const start = currentPage * PAGE_SIZE;
    allTilesArr.forEach((t, i) => {
      t.style.display = (i >= start && i < start + PAGE_SIZE) ? '' : 'none';
    });
    updateNav();
    updateArrowPositions();
  }

  /** Wrap to previous/next page (bidirectional carousel). */
  function navigateCarousel(delta) {
    if (totalPages <= 1) return;
    let target = currentPage + delta;
    if (target < 0) target = totalPages - 1;
    else if (target >= totalPages) target = 0;
    showPage(target);
  }

  function updateNav() {
    if (DOTS) {
      DOTS.querySelectorAll('.carousel-dot').forEach((d, i) => {
        d.classList.toggle('carousel-dot--active', i === currentPage);
      });
    }
    const prev = CAROUSEL.parentNode.querySelector('.carousel-arrow--prev');
    const next = CAROUSEL.parentNode.querySelector('.carousel-arrow--next');
    // Bidirectional: arrows always active when multiple pages exist.
    if (prev) prev.disabled = false;
    if (next) next.disabled = false;
  }

  function buildNav() {
    const wrap = CAROUSEL.parentNode;

    const prev = document.createElement('button');
    prev.className = 'carousel-arrow carousel-arrow--prev';
    prev.textContent = '\u2039';
    prev.addEventListener('click', () => navigateCarousel(-1));
    wrap.insertBefore(prev, CAROUSEL);

    const next = document.createElement('button');
    next.className = 'carousel-arrow carousel-arrow--next';
    next.textContent = '\u203A';
    next.addEventListener('click', () => navigateCarousel(1));
    wrap.appendChild(next);

    if (DOTS) {
      for (let i = 0; i < totalPages; i++) {
        const dot = document.createElement('button');
        dot.className = 'carousel-dot';
        dot.addEventListener('click', () => showPage(i));
        DOTS.appendChild(dot);
      }
    }
  }

  // Keep arrow placement in sync with layout changes.
  let resizeRaf = 0;
  window.addEventListener('resize', () => {
    if (resizeRaf) return;
    resizeRaf = window.requestAnimationFrame(() => {
      resizeRaf = 0;
      updateArrowPositions();
    });
  });

  /* ── Init: fetch and distribute tiles ──────────── */

  fetch('/api/repositories')
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(repos => {
      if (STRIP) initMobileStrip(repos);
      if (!hasDesktop) return;

      // Sort: featured first (in declared order), then the rest
      const featSet = new Set(FEATURED);
      const featured = [];
      const rest = [];
      for (const repo of repos) {
        if (featSet.has(repo.name)) featured.push(repo);
        else rest.push(repo);
      }
      featured.sort((a, b) => FEATURED.indexOf(a.name) - FEATURED.indexOf(b.name));
      const sorted = featured.concat(rest);

      for (const repo of sorted) {
        if (DISPLAY_OVERRIDES[repo.name]) repo.display_name = DISPLAY_OVERRIDES[repo.name];
        const tile = renderTile(repo);
        CAROUSEL.appendChild(tile);
        allTilesArr.push(tile);
      }

      totalPages = Math.ceil(allTilesArr.length / PAGE_SIZE);
      if (totalPages > 1) buildNav();
      showPage(0);

      if (window.buildExhibitsLegend) window.buildExhibitsLegend();
    })
    .catch(() => {});
})();
