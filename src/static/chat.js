const messages = document.getElementById('messages');
const form = document.getElementById('chat-form');
const input = document.getElementById('chat-input');

let sessionId = null;
let heroFaded = false;

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

function renderMarkdown(text) {
  return text
    .replace(/```mermaid\n([\s\S]*?)```/g, '<div class="mermaid">$1</div>')
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
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
      }).catch(() => {
        el.innerHTML = '<pre><code>' + code + '</code></pre>';
      });
    } catch (e) {
      el.innerHTML = '<pre><code>' + code + '</code></pre>';
    }
  });
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
  return div;
}

function addLoading() {
  const div = document.createElement('div');
  div.className = 'msg msg-assistant loading';
  div.innerHTML = '<span></span><span></span><span></span>';
  messages.appendChild(div);
  return div;
}

/* ── Starter questions ─────────────────────────────────────── */

const REPOS = ['SPICE', 'C.R.A.C.K.', 'Flow-Ohana', 'Agent_Blackwell', 'PROVE', 'Architx', 'POI_Alchemist', 'A.U.R.A'];
const randomRepo = REPOS[Math.floor(Math.random() * REPOS.length)];

const STARTER_QUESTIONS = [
  { label: 'How did Le build ' + randomRepo + '?', action: 'query', value: 'How did Le build ' + randomRepo + '?' },
  { label: 'Strengths & weaknesses', action: 'query', value: "What are Le's strengths and weaknesses as an engineer?" },
  { label: 'Analyze a job description', action: 'jd' },
];

let starterDiv = null;

function showStarters() {
  starterDiv = document.createElement('div');
  starterDiv.className = 'starter-questions';
  STARTER_QUESTIONS.forEach(sq => {
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
  }

  addMessage('user', q);
  const loader = addLoading();
  let assistantDiv = null;

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
    } else if (eventType === 'status') {
      const d = JSON.parse(data);
      if (d.phase === 'tool') { toolCount++; addStep(toolLabel(d.tool, d.args || {})); }
      else if (d.phase === 'curating') addStep('Curating evidence\u2026');
      else if (d.phase === 'answering') addStep('Composing answer\u2026');
      /* no auto-scroll — let the user read at their own pace */
    } else {
      if (data === '[DONE]') { collapseStatus(); cleanup(); return; }
      if (loader.parentNode) loader.remove();
      collapseStatus();
      if (!assistantDiv) assistantDiv = addMessage('assistant', data);
      else { assistantDiv.innerHTML = renderMarkdown(data); renderMermaidBlocks(assistantDiv); }
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
