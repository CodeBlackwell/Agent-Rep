const messages = document.getElementById('messages');
const form = document.getElementById('chat-form');
const input = document.getElementById('chat-input');

let sessionId = null;

function renderMarkdown(text) {
  return text
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '\n');
}

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `msg msg-${role}`;
  if (role === 'assistant') {
    div.innerHTML = renderMarkdown(content);
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

  const source = new EventSource(url);

  source.addEventListener('session', event => {
    sessionId = JSON.parse(event.data).session_id;
  });

  source.addEventListener('graph', event => {
    window.updateGraph(JSON.parse(event.data));
  });

  source.addEventListener('status', event => {
    const data = JSON.parse(event.data);
    if (data.phase === 'tool') {
      toolCount++;
      addStep(toolLabel(data.tool, data.args || {}));
    } else if (data.phase === 'curating') {
      addStep('Curating evidence…');
    } else if (data.phase === 'answering') {
      addStep('Composing answer…');
    }
    messages.scrollTop = messages.scrollHeight;
  });

  source.onmessage = event => {
    if (event.data === '[DONE]') {
      collapseStatus();
      source.close();
      input.disabled = false;
      input.focus();
      return;
    }
    if (loader.parentNode) loader.remove();
    collapseStatus();
    if (!assistantDiv) {
      assistantDiv = addMessage('assistant', event.data);
    } else {
      assistantDiv.innerHTML = renderMarkdown(event.data);
    }
    messages.scrollTop = messages.scrollHeight;
  };

  source.onerror = () => {
    source.close();
    if (elapsedTimer) clearInterval(elapsedTimer);
    if (loader.parentNode) loader.remove();
    if (!assistantDiv) addMessage('assistant', 'Connection lost. Please try again.');
    input.disabled = false;
    input.focus();
  };
});
