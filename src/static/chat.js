const messages = document.getElementById('messages');
const form = document.getElementById('chat-form');
const input = document.getElementById('chat-input');

let sessionId = null;
let heroFaded = false;
const isMobileChat = window.innerWidth < 768;

/* ── Mobile: content-driven chat height ───────────────────── */

function resizeChatPanel() {
  if (!isMobileChat) return;
  const leftCol = document.querySelector('.left-col');
  if (!leftCol) return;

  const hero = document.querySelector('.hero');
  const heroH = hero ? hero.getBoundingClientRect().height : 0;
  const formH = form ? form.getBoundingClientRect().height : 40;
  const msgsContent = messages ? messages.scrollHeight : 0;

  // Content height = hero + messages + form + padding
  const contentH = heroH + msgsContent + formH + 24;
  const maxH = window.innerHeight * 0.95;

  leftCol.style.maxHeight = Math.min(contentH, maxH) + 'px';
}

// Initial size on load
if (isMobileChat) {
  requestAnimationFrame(resizeChatPanel);
}

/* ── Rate-limit modal ──────────────────────────────────────── */

let rateModal = null;

function showRateLimitModal(retrySecs) {
  if (!rateModal) {
    rateModal = document.createElement('div');
    rateModal.className = 'rate-modal';
    rateModal.innerHTML =
      '<div class="rate-modal__backdrop"></div>' +
      '<div class="rate-modal__panel">' +
        '<h2 class="rate-modal__title">Taking a breather</h2>' +
        '<p class="rate-modal__text">You\u2019ve been asking great questions! ' +
          'To keep things running smoothly, there\u2019s a short cooldown in effect.</p>' +
        '<p class="rate-modal__timer"></p>' +
        '<button class="rate-modal__btn">Got it</button>' +
      '</div>';
    document.body.appendChild(rateModal);
    rateModal.querySelector('.rate-modal__backdrop').addEventListener('click', closeRateLimitModal);
    rateModal.querySelector('.rate-modal__btn').addEventListener('click', closeRateLimitModal);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeRateLimitModal(); });
  }
  const mins = Math.ceil((retrySecs || 3600) / 60);
  rateModal.querySelector('.rate-modal__timer').textContent =
    'Check back in about ' + mins + ' minute' + (mins !== 1 ? 's' : '') + '.';
  rateModal.classList.add('rate-modal--open');
}

function closeRateLimitModal() {
  if (rateModal) rateModal.classList.remove('rate-modal--open');
}

/* ── Markdown / messages ───────────────────────────────────── */

function _escChat(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function renderMarkdown(text) {
  // Escape HTML first, then apply markdown transforms
  return _escChat(text)
    .replace(/```mermaid\n([\s\S]*?)```/g, '<div class="mermaid">$1</div>')
    .replace(/```(\w*)\n([\s\S]*?)```/g, function(_, lang, code) {
      var cls = lang ? ' class="language-' + lang + '"' : '';
      return '<pre><code' + cls + '>' + code + '</code></pre>';
    })
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '\n');
}

function renderMermaidBlocks(container) {
  if (!window.mermaid) return;
  container.querySelectorAll('.mermaid:not([data-processed])').forEach(el => {
    el.setAttribute('data-processed', 'true');
    const code = el.textContent.trim();
    const id = 'mermaid-' + Math.random().toString(36).slice(2, 8);
    try {
      window.mermaid.render(id, code).then(({ svg }) => {
        el.innerHTML = svg;
        el.style.cursor = 'pointer';
        el.title = 'Click to expand';
        el.addEventListener('click', () => openMermaidLightbox(el));
      }).catch(() => {
        el.innerHTML = '<pre><code>' + code + '</code></pre>';
      });
    } catch (e) {
      el.innerHTML = '<pre><code>' + code + '</code></pre>';
    }
  });
}

/* ── Mermaid lightbox ──────────────────────────────────────── */

let mermaidLightbox = null;

function openMermaidLightbox(sourceEl) {
  if (!mermaidLightbox) {
    mermaidLightbox = document.createElement('div');
    mermaidLightbox.className = 'mermaid-lightbox';
    mermaidLightbox.innerHTML =
      '<div class="mermaid-lightbox__backdrop"></div>' +
      '<div class="mermaid-lightbox__content"></div>';
    document.body.appendChild(mermaidLightbox);
    mermaidLightbox.querySelector('.mermaid-lightbox__backdrop')
      .addEventListener('click', closeMermaidLightbox);
    mermaidLightbox.addEventListener('click', function(e) {
      if (e.target === mermaidLightbox) closeMermaidLightbox();
    });
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && mermaidLightbox.classList.contains('mermaid-lightbox--open'))
        closeMermaidLightbox();
    });
  }
  var content = mermaidLightbox.querySelector('.mermaid-lightbox__content');
  content.innerHTML = sourceEl.innerHTML;
  // Force reflow before adding class for transition
  void mermaidLightbox.offsetHeight;
  mermaidLightbox.classList.add('mermaid-lightbox--open');
}

function closeMermaidLightbox() {
  if (mermaidLightbox) mermaidLightbox.classList.remove('mermaid-lightbox--open');
}

/* ── Collapsible code blocks ──────────────────────────────── */

function highlightCode(container) {
  if (!window.hljs) return;
  container.querySelectorAll('pre code:not([data-highlighted])').forEach(el => {
    hljs.highlightElement(el);
  });
}

function wrapCodeBlocks(container) {
  highlightCode(container);
  const pres = container.querySelectorAll('pre');
  if (!pres.length) return;
  pres.forEach(pre => {
    if (pre.closest('.code-collapse')) return;           // already wrapped
    const code = pre.querySelector('code');
    const lines = (code || pre).textContent.split('\n').length;
    const details = document.createElement('details');
    details.className = 'code-collapse';
    details.open = false;
    const summary = document.createElement('summary');
    summary.className = 'code-collapse__toggle';
    summary.innerHTML = '<span class="code-collapse__arrow">▸</span> ' + lines + ' line' + (lines !== 1 ? 's' : '');
    details.addEventListener('toggle', function() {
      summary.querySelector('.code-collapse__arrow').textContent = details.open ? '▾' : '▸';
    });
    pre.parentNode.insertBefore(details, pre);
    details.appendChild(summary);
    details.appendChild(pre);
  });
}

/* ── Confidence → evidence panel ───────────────────────────── */

function wireConfidenceLink(container, evidenceData) {
  if (!evidenceData || !evidenceData.references || !evidenceData.references.length) return;
  // Find the last text node containing "Confidence:"
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (node.textContent.includes('Confidence:')) {
      const span = document.createElement('span');
      span.className = 'confidence-link';
      span.textContent = node.textContent.trim();
      span.title = 'Click to browse all evidence';
      span.addEventListener('click', function() { openEvidencePanel(evidenceData); });
      node.parentNode.replaceChild(span, node);
      return;
    }
  }
}

function openEvidencePanel(data) {
  // Reuse the ref-modal from graph.js
  var m = window._ensureRefModal ? window._ensureRefModal() : null;
  if (!m) {
    // Fallback: create a minimal modal if graph.js hasn't loaded
    m = document.querySelector('.ref-modal');
    if (!m) return;
  }

  var header = m.querySelector('.ref-modal__header');
  var body = m.querySelector('.ref-modal__body');

  // Group by repo
  var byRepo = new Map();
  for (var ref of data.references) {
    var repo = ref.repo || 'unknown';
    if (!byRepo.has(repo)) byRepo.set(repo, []);
    byRepo.get(repo).push(ref);
  }
  var repoNames = [...byRepo.keys()];
  var owner = data.github_owner || 'codeblackwell';

  // Confidence badge class
  var confClass = data.confidence === 'Strong' ? 'tip-prof--extensive'
    : data.confidence === 'Partial' ? 'tip-prof--moderate' : 'tip-prof--minimal';

  header.innerHTML =
    '<h2>Evidence Overview</h2>' +
    '<div class="ref-modal__meta">' +
      '<span class="tip-prof ' + confClass + '">' + data.confidence + '</span>' +
      '<span class="ref-modal__stats">' + data.total +
        ' snippet' + (data.total !== 1 ? 's' : '') +
        ' across ' + repoNames.length +
        ' repo' + (repoNames.length !== 1 ? 's' : '') +
      '</span>' +
    '</div>';

  // Repo filter
  if (repoNames.length > 1) {
    var filterDiv = document.createElement('div');
    filterDiv.className = 'ref-filter';
    var allBtn = document.createElement('button');
    allBtn.className = 'ref-filter__btn ref-filter__btn--active';
    allBtn.textContent = 'All (' + data.references.length + ')';
    allBtn.dataset.repo = '';
    filterDiv.appendChild(allBtn);
    for (var rn of repoNames) {
      var btn = document.createElement('button');
      btn.className = 'ref-filter__btn';
      btn.textContent = rn + ' (' + byRepo.get(rn).length + ')';
      btn.dataset.repo = rn;
      filterDiv.appendChild(btn);
    }
    header.appendChild(filterDiv);
    filterDiv.addEventListener('click', function(e) {
      var b = e.target.closest('.ref-filter__btn');
      if (!b) return;
      filterDiv.querySelectorAll('.ref-filter__btn').forEach(function(x) { x.classList.remove('ref-filter__btn--active'); });
      b.classList.add('ref-filter__btn--active');
      _renderEvidenceList(body, byRepo, b.dataset.repo || null, owner);
    });
  }

  _renderEvidenceList(body, byRepo, null, owner);
  m.classList.add('ref-modal--open');
}

function _renderEvidenceList(body, byRepo, filterRepo, owner) {
  var html = '';
  var LANG_LABELS = { py: 'Python', js: 'JavaScript', ts: 'TypeScript', tsx: 'TypeScript', jsx: 'JavaScript', java: 'Java', go: 'Go', rs: 'Rust', rb: 'Ruby', cpp: 'C++', c: 'C' };
  var hasPrivate = false;

  for (var [repo, refs] of byRepo) {
    if (filterRepo && repo !== filterRepo) continue;
    var isPrivate = refs[0] && refs[0].private;
    if (isPrivate) hasPrivate = true;
    var repoUrl = 'https://github.com/' + owner + '/' + repo;
    var lock = isPrivate ? ' <span class="ref-repo__lock" title="Private repository">\u{1F512}</span>' : '';
    var redactedBadge = isPrivate ? ' <span class="ref-item__redacted">PRIVATE — REDACTED</span>' : '';
    html += '<div class="ref-repo">';
    html += '<h3 class="ref-repo__name"><a href="' + repoUrl + '" target="_blank">' + repo + '</a>' + lock + redactedBadge + '</h3>';

    for (var ref of refs) {
      var branch = 'main';
      var url = 'https://github.com/' + owner + '/' + ref.repo + '/blob/' + branch + '/' + ref.path + '#L' + ref.start_line;
      var langLabel = LANG_LABELS[ref.language] || ref.language || '';
      var lineRange = ref.end_line > ref.start_line
        ? 'L' + ref.start_line + '\u2013' + ref.end_line
        : 'L' + ref.start_line;

      html += '<div class="ref-item">';
      html += '<div class="ref-item__file">';
      html += '<a href="' + url + '" target="_blank" class="ref-item__link">' + ref.path + '</a>';
      html += '<span class="ref-item__line">' + lineRange + '</span>';
      if (langLabel) html += '<span class="ref-item__lang">' + langLabel + '</span>';
      if (ref.private) html += '<span class="ref-item__redacted">CODE REDACTED — PRIVATE REPO</span>';
      html += '</div>';
      if (ref.skill) html += '<div class="ref-item__name">' + ref.skill + '</div>';
      if (ref.context) html += '<div class="ref-item__context">' + ref.context + '</div>';
      if (ref.content) {
        var escaped = ref.content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        var lineCount = ref.content.split('\n').length;
        var langCls = ref.language ? ' class="language-' + ref.language + '"' : '';
        html += '<details class="ref-item__code-collapse">' +
          '<summary class="ref-item__code-toggle"><span class="ref-item__code-arrow">\u25B8</span> ' + lineCount + ' line' + (lineCount !== 1 ? 's' : '') + '</summary>' +
          '<pre class="ref-item__code-pre"><code' + langCls + '>' + escaped + '</code></pre>' +
          '</details>';
      }
      html += '</div>';
    }
    html += '</div>';
  }

  if (hasPrivate) {
    html += '<div class="ref-private-note">\u{1F512} Some code lives in a private repo. ' +
      'I\u2019d love to walk you through it \u2014 <a href="https://github.com/' + owner + '" target="_blank">reach out</a>!</div>';
  }

  body.innerHTML = html;
  // Highlight code in evidence snippets
  if (window.hljs) {
    body.querySelectorAll('.ref-item__code-pre code:not([data-highlighted])').forEach(function(el) {
      hljs.highlightElement(el);
    });
  }
}

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `msg msg-${role}`;
  if (role === 'assistant') {
    div.innerHTML = renderMarkdown(content);
    renderMermaidBlocks(div);
  } else {
    div.textContent = content;
  }
  messages.appendChild(div);
  resizeChatPanel();
  return div;
}

function addLoading() {
  const div = document.createElement('div');
  div.className = 'msg msg-assistant loading';
  div.innerHTML = '<span></span><span></span><span></span>';
  messages.appendChild(div);
  resizeChatPanel();
  return div;
}

/* ── Starter questions ─────────────────────────────────────── */

let starterDiv = null;

function showStarters() {
  starterDiv = document.createElement('div');
  starterDiv.className = 'starter-questions';

  const firstName = (window.__ENGINEER_NAME__ || 'Engineer').split(' ')[0];
  const buildQ = (repo) => 'How did ' + firstName + ' build ' + repo + '?';

  fetch('/api/repositories')
    .then(r => r.ok ? r.json() : [])
    .then(repos => {
      const names = repos.map(r => r.name);
      const pick = names.length ? names[Math.floor(Math.random() * names.length)] : 'PROVE';
      const questions = [
        { label: buildQ(pick), action: 'query', value: buildQ(pick) },
        { label: 'Strengths & weaknesses', action: 'query', value: "What are " + firstName + "'s strengths and weaknesses as an engineer?" },
        { label: 'Analyze a job description', action: 'jd' },
      ];
      if (!starterDiv) return;
      questions.forEach(sq => {
        const btn = document.createElement('button');
        btn.className = 'starter-btn';
        btn.textContent = sq.label;
        btn.addEventListener('click', () => {
          dismissStarters();
          if (sq.action === 'jd') {
            openJdModal();
          } else {
            input.value = sq.value;
            form.requestSubmit();
          }
        });
        starterDiv.appendChild(btn);
      });
    })
    .catch(() => {});

  messages.appendChild(starterDiv);
}

function dismissStarters() {
  if (starterDiv && starterDiv.parentNode) {
    starterDiv.remove();
    starterDiv = null;
  }
}

showStarters();

/* ── Tool call labels ──────────────────────────────────────── */

const TOOL_LABELS = {
  search_code: 'Searching code',
  get_evidence: 'Looking up evidence',
  search_resume: 'Searching resume',
  find_gaps: 'Analyzing skill gaps',
  get_repo_overview: 'Reviewing repository',
  get_connected_evidence: 'Tracing connections',
};

function toolLabel(tool, args) {
  const label = TOOL_LABELS[tool] || tool;
  const detail = args.query || args.skill_name || args.repo_name || args.skills_csv || '';
  if (detail) {
    const short = detail.length > 35 ? detail.slice(0, 32) + '…' : detail;
    return label + ' — ' + short;
  }
  return label;
}

/* ── Form handler ──────────────────────────────────────────── */

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

form.addEventListener('submit', e => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  input.disabled = true;

  dismissStarters();

  // Fade hero on first question — chat stretches to fill
  if (!heroFaded) {
    heroFaded = true;
    document.body.classList.add('hero-faded');
    // Dismiss the graph how-to overlay, reveal the empty-state text
    const howto = document.getElementById('graph-howto');
    if (howto) howto.classList.add('graph-howto--hidden');
    const empty = document.querySelector('.graph-empty');
    if (empty) empty.style.display = '';
    // Switch from exhibits to treemap
    if (window.switchVizMode) window.switchVizMode('treemap');
  }

  addMessage('user', q);
  const loader = addLoading();
  let assistantDiv = null;
  let pendingEvidence = null;

  // Status tracker state
  let statusDiv = null;
  let stepsEl = null;
  let elapsedEl = null;
  let startTime = null;
  let elapsedTimer = null;
  let toolCount = 0;
  let statusCollapsed = false;

  function ensureStatus() {
    if (statusDiv) return;
    if (loader.parentNode) loader.remove();
    statusDiv = document.createElement('div');
    statusDiv.className = 'msg msg-status';
    statusDiv.innerHTML =
      '<div class="status-steps"></div>' +
      '<div class="status-elapsed"></div>';
    stepsEl = statusDiv.querySelector('.status-steps');
    elapsedEl = statusDiv.querySelector('.status-elapsed');
    messages.appendChild(statusDiv);
    startTime = Date.now();
    elapsedTimer = setInterval(() => {
      elapsedEl.textContent = ((Date.now() - startTime) / 1000).toFixed(1) + 's';
    }, 100);
  }

  function addStep(text) {
    ensureStatus();
    const prev = stepsEl.querySelector('.status-step--active');
    if (prev) {
      prev.classList.remove('status-step--active');
      prev.classList.add('status-step--done');
      prev.querySelector('.status-icon').textContent = '✓';
    }
    const el = document.createElement('div');
    el.className = 'status-step status-step--active';
    el.innerHTML = '<span class="status-icon">●</span> ' + text;
    stepsEl.appendChild(el);
    resizeChatPanel();
  }

  function collapseStatus() {
    if (!statusDiv || statusCollapsed) return;
    statusCollapsed = true;
    clearInterval(elapsedTimer);
    const secs = ((Date.now() - startTime) / 1000).toFixed(1);
    const prev = stepsEl.querySelector('.status-step--active');
    if (prev) {
      prev.classList.remove('status-step--active');
      prev.classList.add('status-step--done');
      prev.querySelector('.status-icon').textContent = '✓';
    }
    statusDiv.classList.add('msg-status--done');
    statusDiv.innerHTML =
      '<span class="status-summary">' + toolCount +
      ' tool' + (toolCount !== 1 ? 's' : '') +
      ' · ' + secs + 's</span>';
  }

  let url = `/api/chat?q=${encodeURIComponent(q)}`;
  if (sessionId) url += `&session_id=${encodeURIComponent(sessionId)}`;
  if (window.__fp) url += `&fp=${encodeURIComponent(window.__fp)}`;

  function cleanup() {
    if (elapsedTimer) clearInterval(elapsedTimer);
    input.disabled = false;
    input.focus();
  }

  function dispatch(eventType, data) {
    if (eventType === 'session') {
      sessionId = JSON.parse(data).session_id;
    } else if (eventType === 'graph') {
      window.updateGraph(JSON.parse(data));
    } else if (eventType === 'evidence') {
      pendingEvidence = JSON.parse(data);
    } else if (eventType === 'status') {
      const d = JSON.parse(data);
      if (d.phase === 'tool') { toolCount++; addStep(toolLabel(d.tool, d.args || {})); }
      else if (d.phase === 'curating') addStep('Curating evidence\u2026');
      else if (d.phase === 'answering') addStep('Composing answer\u2026');
      /* no auto-scroll — let the user read at their own pace */
    } else {
      if (data === '[DONE]') {
        collapseStatus();
        if (assistantDiv) {
          wrapCodeBlocks(assistantDiv);
          wireConfidenceLink(assistantDiv, pendingEvidence);
        }
        cleanup();
        return;
      }
      if (loader.parentNode) loader.remove();
      collapseStatus();
      if (!assistantDiv) assistantDiv = addMessage('assistant', data);
      else { assistantDiv.innerHTML = renderMarkdown(data); renderMermaidBlocks(assistantDiv); resizeChatPanel(); }
      /* no auto-scroll — let the user read at their own pace */
    }
  }

  fetch(url).then(response => {
    if (response.status === 429) {
      if (loader.parentNode) loader.remove();
      return response.json().then(data => {
        showRateLimitModal(data.retry_after_seconds);
        cleanup();
      });
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    function processBlock(block) {
      let eventType = 'message';
      const dataLines = [];
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim();
        else if (line.startsWith('data: ')) dataLines.push(line.slice(6));
        else if (line === 'data:') dataLines.push('');
      }
      if (dataLines.length) dispatch(eventType, dataLines.join('\n'));
    }

    function pump() {
      return reader.read().then(({ done, value }) => {
        if (done) {
          if (buffer.trim()) processBlock(buffer);
          collapseStatus();
          cleanup();
          return;
        }
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();
        for (const part of parts) { if (part.trim()) processBlock(part); }
        return pump();
      });
    }

    return pump();
  }).catch(() => {
    if (loader.parentNode) loader.remove();
    if (!assistantDiv) addMessage('assistant', 'Connection lost. Please try again.');
    cleanup();
  });
});
