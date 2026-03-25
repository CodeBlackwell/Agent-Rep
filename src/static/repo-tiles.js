/* ── Repo Tiles — interactive donut rings ─────────────── */

(function () {
  const LEFT = document.getElementById('exhibits-left');
  const RIGHT = document.getElementById('exhibits-right');
  const SHOWCASE = document.getElementById('exhibits-showcase');
  const DETAIL = document.getElementById('repo-detail');
  if (!LEFT || !RIGHT || !SHOWCASE || !DETAIL) return;

  const SHOWCASE_NAMES = ['PROVE', 'C.R.A.C.K.', 'PANEL', 'SPICE'];

  const SIZE = 72;
  const OUTER = SIZE / 2 - 2;
  const INNER = OUTER - 11;
  const EXP_SIZE = 200;
  const EXP_OUTER = EXP_SIZE / 2 - 4;
  const EXP_INNER = EXP_OUTER - 22;

  const pie = d3.pie().sort(null).value(d => d.value);
  const arc = d3.arc().innerRadius(INNER).outerRadius(OUTER);
  const arcExploded = d3.arc().innerRadius(INNER + 2).outerRadius(OUTER + 3);
  const expArc = d3.arc().innerRadius(EXP_INNER).outerRadius(EXP_OUTER);

  let expanded = null;

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
    name.textContent = repo.name;
    tile.appendChild(name);

    tile.addEventListener('mouseenter', () => {
      if (expanded) return;
      tile.classList.add('repo-tile--hover');
      allTiles().forEach(t => {
        if (t !== tile) t.classList.add('repo-tile--dimmed');
      });
      explodeSegments(tile, true);
    });

    tile.addEventListener('mouseleave', () => {
      if (expanded) return;
      tile.classList.remove('repo-tile--hover');
      document.querySelectorAll('.repo-tile--dimmed').forEach(t =>
        t.classList.remove('repo-tile--dimmed')
      );
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
    title.textContent = repo.name;
    DETAIL.appendChild(title);

    const body = document.createElement('div');
    body.className = 'repo-detail__body';
    body.innerHTML = '<p class="repo-detail__loading">Loading…</p>';
    DETAIL.appendChild(body);

    fetch(`/api/repositories/${encodeURIComponent(repo.name)}`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(detail => renderDetail(body, detail))
      .catch(() => { body.innerHTML = '<p class="repo-detail__loading">Could not load details</p>'; });
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
        const row = document.createElement('div');
        row.className = 'repo-detail__skill';

        const name = document.createElement('span');
        name.textContent = sk.skill;
        row.appendChild(name);

        const count = document.createElement('span');
        count.className = 'repo-detail__count';
        count.textContent = sk.snippets;
        row.appendChild(count);

        if (sk.files && sk.files.length) {
          const link = document.createElement('a');
          link.href = sk.files[0];
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.className = 'repo-detail__link';
          link.textContent = '↗';
          link.title = 'View on GitHub';
          row.appendChild(link);
        }
        body.appendChild(row);
      }
      group.appendChild(body);
      container.appendChild(group);
    }
  }

  /* ── Close detail view ─────────────────────────── */

  function closeDetail() {
    if (!expanded) return;
    expanded = null;
    DETAIL.classList.remove('repo-detail--visible');
    document.querySelectorAll('.repo-tile--dimmed').forEach(t =>
      t.classList.remove('repo-tile--dimmed')
    );
  }

  document.getElementById('graph-panel').addEventListener('click', (e) => {
    if (!expanded) return;
    if (DETAIL.contains(e.target) || e.target.closest('.repo-tile')) return;
    closeDetail();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDetail();
  });

  /* ── Init: fetch and distribute tiles ──────────── */

  fetch('/api/repositories')
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(repos => {
      const showcaseSet = new Set(SHOWCASE_NAMES);
      const showcase = [];
      const side = [];

      for (const repo of repos) {
        if (showcaseSet.has(repo.name)) showcase.push(repo);
        else side.push(repo);
      }

      // Sort showcase to match declared order
      showcase.sort((a, b) => SHOWCASE_NAMES.indexOf(a.name) - SHOWCASE_NAMES.indexOf(b.name));

      // Distribute side tiles: alternate left/right
      side.forEach((repo, i) => {
        const tile = renderTile(repo);
        (i % 2 === 0 ? LEFT : RIGHT).appendChild(tile);
      });

      // Showcase tiles into bottom row
      for (const repo of showcase) {
        SHOWCASE.appendChild(renderTile(repo));
      }

      // Build domain legend now that all domainColor() calls have fired
      if (window.buildExhibitsLegend) window.buildExhibitsLegend();
    })
    .catch(() => {});
})();
