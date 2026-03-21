/* ── JD Match Modal ─────────────────────────────────────────── */

let jdModal = null;
let jdFile = null;

const DAVINCI_SPINNER =
  '<svg class="jd-spinner" viewBox="0 0 100 100" width="48" height="48">' +
    '<circle cx="50" cy="50" r="38" fill="none" stroke="#c4b8a8" stroke-width="0.5"/>' +
    '<circle cx="50" cy="50" r="24" fill="none" stroke="#c4b8a8" stroke-width="0.5"/>' +
    '<circle cx="50" cy="50" r="14" fill="none" stroke="#c4b8a8" stroke-width="0.5"/>' +
    '<line x1="50" y1="12" x2="50" y2="88" stroke="#c4b8a8" stroke-width="0.5"/>' +
    '<line x1="12" y1="50" x2="88" y2="50" stroke="#c4b8a8" stroke-width="0.5"/>' +
    '<line x1="23" y1="23" x2="77" y2="77" stroke="#c4b8a8" stroke-width="0.4"/>' +
    '<line x1="77" y1="23" x2="23" y2="77" stroke="#c4b8a8" stroke-width="0.4"/>' +
    '<path d="M50 12 A38 38 0 0 1 88 50" fill="none" stroke="#6b4c2a" stroke-width="1.5" stroke-linecap="round" class="jd-spinner__arc"/>' +
    '<circle cx="50" cy="50" r="2.5" fill="#6b4c2a"/>' +
  '</svg>';

function _ensureJdModal() {
  if (jdModal) return jdModal;
  jdModal = document.createElement('div');
  jdModal.className = 'jd-modal';
  jdModal.innerHTML =
    '<div class="jd-modal__backdrop"></div>' +
    '<div class="jd-modal__panel">' +
      '<button class="jd-modal__close" aria-label="Close">&times;</button>' +
      '<h2 class="jd-modal__title">Analyze a Job Description</h2>' +
      '<p class="jd-modal__subtitle">Drop a file or paste the text to see how this portfolio matches.</p>' +
      '<div class="jd-drop" id="jd-drop">' +
        '<input type="file" id="jd-file" accept=".pdf,.docx,.md,.txt" hidden>' +
        '<div class="jd-drop__label">' +
          '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>' +
          '</svg>' +
          '<span>Drop PDF, DOCX, MD, or TXT here</span>' +
          '<span class="jd-drop__browse">or click to browse</span>' +
        '</div>' +
        '<div class="jd-drop__file" id="jd-drop-file" hidden></div>' +
      '</div>' +
      '<textarea class="jd-text" id="jd-text" placeholder="Or paste the job description text here\u2026" rows="5"></textarea>' +
      '<button class="jd-modal__analyze" id="jd-analyze" disabled>Analyze</button>' +
      '<div class="jd-loading" id="jd-loading" hidden></div>' +
      '<div class="jd-results" id="jd-results" hidden></div>' +
    '</div>';
  document.body.appendChild(jdModal);

  jdModal.querySelector('.jd-modal__backdrop').addEventListener('click', closeJdModal);
  jdModal.querySelector('.jd-modal__close').addEventListener('click', closeJdModal);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeJdModal(); });

  const drop = jdModal.querySelector('#jd-drop');
  const fileInput = jdModal.querySelector('#jd-file');
  const textArea = jdModal.querySelector('#jd-text');
  const analyzeBtn = jdModal.querySelector('#jd-analyze');

  drop.addEventListener('click', () => fileInput.click());
  drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('jd-drop--over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('jd-drop--over'));
  drop.addEventListener('drop', e => {
    e.preventDefault();
    drop.classList.remove('jd-drop--over');
    if (e.dataTransfer.files.length) _setFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', () => { if (fileInput.files.length) _setFile(fileInput.files[0]); });
  textArea.addEventListener('input', _updateAnalyzeState);
  analyzeBtn.addEventListener('click', _runAnalysis);

  return jdModal;
}

function _setFile(file) {
  jdFile = file;
  const label = jdModal.querySelector('.jd-drop__label');
  const fileEl = jdModal.querySelector('#jd-drop-file');
  label.hidden = true;
  fileEl.hidden = false;
  fileEl.innerHTML =
    '<span class="jd-drop__filename">' + file.name + '</span>' +
    '<button class="jd-drop__clear" type="button">&times;</button>';
  fileEl.querySelector('.jd-drop__clear').addEventListener('click', e => { e.stopPropagation(); _clearFile(); });
  _updateAnalyzeState();
}

function _clearFile() {
  jdFile = null;
  jdModal.querySelector('.jd-drop__label').hidden = false;
  jdModal.querySelector('#jd-drop-file').hidden = true;
  jdModal.querySelector('#jd-file').value = '';
  _updateAnalyzeState();
}

function _updateAnalyzeState() {
  const text = jdModal.querySelector('#jd-text').value.trim();
  jdModal.querySelector('#jd-analyze').disabled = !jdFile && !text;
}

function openJdModal() {
  const m = _ensureJdModal();
  jdFile = null;
  m.querySelector('#jd-text').value = '';
  m.querySelector('.jd-drop__label').hidden = false;
  m.querySelector('#jd-drop-file').hidden = true;
  m.querySelector('#jd-file').value = '';
  m.querySelector('#jd-analyze').disabled = true;
  m.querySelector('#jd-analyze').textContent = 'Analyze';
  m.querySelector('#jd-loading').hidden = true;
  m.querySelector('#jd-results').hidden = true;
  m.classList.add('jd-modal--open');
}

function closeJdModal() {
  if (jdModal) jdModal.classList.remove('jd-modal--open');
}

/* ── Loading state with Da Vinci spinner + live timer ──────── */

let _jdTimer = null;

function _showLoading() {
  const loading = jdModal.querySelector('#jd-loading');
  const btn = jdModal.querySelector('#jd-analyze');
  btn.hidden = true;
  loading.hidden = false;
  const start = Date.now();
  loading.innerHTML =
    '<div class="jd-loading__inner">' +
      DAVINCI_SPINNER +
      '<div class="jd-loading__text">Analyzing requirements\u2026</div>' +
      '<div class="jd-loading__timer">0.0s</div>' +
    '</div>';
  const timerEl = loading.querySelector('.jd-loading__timer');
  _jdTimer = setInterval(() => {
    timerEl.textContent = ((Date.now() - start) / 1000).toFixed(1) + 's';
  }, 100);
}

function _hideLoading() {
  if (_jdTimer) { clearInterval(_jdTimer); _jdTimer = null; }
  jdModal.querySelector('#jd-loading').hidden = true;
  jdModal.querySelector('#jd-analyze').hidden = false;
  jdModal.querySelector('#jd-analyze').textContent = 'Analyze';
  _updateAnalyzeState();
}

/* ── Run analysis ──────────────────────────────────────────── */

function _runAnalysis() {
  const results = jdModal.querySelector('#jd-results');
  results.hidden = true;
  _showLoading();

  const form = new FormData();
  if (jdFile) form.append('file', jdFile);
  else form.append('text', jdModal.querySelector('#jd-text').value);
  if (window.__fp) form.append('fp', window.__fp);

  fetch('/api/jd-match', { method: 'POST', body: form })
    .then(r => {
      if (r.status === 429) return r.json().then(d => { showRateLimitModal(d.retry_after_seconds); throw new Error('rate_limited'); });
      if (!r.ok) return r.json().then(d => { throw new Error(d.error || 'Analysis failed'); });
      return r.json();
    })
    .then(data => {
      _hideLoading();
      _renderResults(results, data);
      results.hidden = false;
    })
    .catch(err => {
      _hideLoading();
      if (err.message !== 'rate_limited') {
        results.innerHTML = '<p class="jd-results__error">' + err.message + '</p>';
        results.hidden = false;
      }
    });
}

/* ── Results rendering ─────────────────────────────────────── */

const CONF_CLASS = { Strong: 'jd-conf--strong', Partial: 'jd-conf--partial', None: 'jd-conf--none' };

function _ghUrl(repo, path, line) {
  var owner = window.__GITHUB_OWNER__ || 'codeblackwell';
  return 'https://github.com/' + owner + '/' + repo + '/blob/main/' + path + '#L' + line;
}

function _renderResults(el, data) {
  const pct = Math.round(data.match_percentage);
  const strong = data.requirements.filter(r => r.confidence === 'Strong').length;
  const partial = data.requirements.filter(r => r.confidence === 'Partial').length;
  const none = data.requirements.filter(r => r.confidence === 'None').length;
  const total = data.requirements.length;

  let html =
    '<div class="jd-results__header">' +
      '<div class="jd-results__pct">' + pct + '%</div>' +
      '<div class="jd-results__label">Match</div>' +
    '</div>' +
    '<p class="jd-results__summary">' + data.summary + '</p>';

  // Accordion: requirements breakdown
  html +=
    '<button class="jd-accordion" id="jd-acc-reqs">' +
      '<span class="jd-accordion__title">Requirements</span>' +
      '<span class="jd-accordion__meta">' +
        (strong ? '<span class="jd-conf jd-conf--strong">' + strong + ' strong</span> ' : '') +
        (partial ? '<span class="jd-conf jd-conf--partial">' + partial + ' partial</span> ' : '') +
        (none ? '<span class="jd-conf jd-conf--none">' + none + ' gap</span>' : '') +
      '</span>' +
      '<span class="jd-accordion__arrow">\u25B8</span>' +
    '</button>' +
    '<div class="jd-accordion__body" id="jd-acc-reqs-body" hidden>' +
      '<div class="jd-results__reqs">';

  for (let i = 0; i < total; i++) {
    const r = data.requirements[i];
    const cls = CONF_CLASS[r.confidence] || CONF_CLASS.None;
    const hasEvidence = r.evidence && r.evidence.length > 0;
    html +=
      '<div class="jd-req">' +
        '<div class="jd-req__row">' +
          '<span class="jd-req__name">' + r.requirement + '</span>' +
          '<span class="jd-conf ' + cls + '">' + r.confidence + '</span>' +
          (hasEvidence
            ? '<button class="jd-req__toggle" data-idx="' + i + '">' + r.evidence.length + ' snippet' + (r.evidence.length !== 1 ? 's' : '') + '</button>'
            : '') +
        '</div>';

    if (hasEvidence) {
      html += '<div class="jd-evidence" id="jd-ev-' + i + '" hidden>';
      for (const e of r.evidence) {
        const url = e.repo ? _ghUrl(e.repo, e.path, e.start_line) : '#';
        const shortPath = e.path ? e.path.split('/').pop() : '';
        const lineRange = e.end_line > e.start_line
          ? 'L' + e.start_line + '\u2013' + e.end_line
          : 'L' + e.start_line;
        const lock = e.private ? ' <span class="tip-lock" title="Private repo">\u{1F512}</span>' : '';
        html +=
          '<div class="jd-evidence__item">' +
            '<a href="' + url + '" target="_blank" class="jd-evidence__link">' +
              (e.repo || '') + '/' + shortPath + '#' + lineRange +
            '</a>' + lock +
            (e.context ? '<div class="jd-evidence__ctx">' + e.context + '</div>' : '') +
          '</div>';
      }
      html += '</div>';
    }

    html += '</div>';
  }

  html += '</div></div>';
  el.innerHTML = html;

  // Accordion toggle
  el.querySelector('#jd-acc-reqs').addEventListener('click', () => {
    const body = el.querySelector('#jd-acc-reqs-body');
    const btn = el.querySelector('#jd-acc-reqs');
    const open = !body.hidden;
    body.hidden = open;
    btn.classList.toggle('jd-accordion--open', !open);
  });

  // Evidence toggles
  el.querySelectorAll('.jd-req__toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const panel = el.querySelector('#jd-ev-' + btn.dataset.idx);
      const open = !panel.hidden;
      panel.hidden = open;
      btn.classList.toggle('jd-req__toggle--open', !open);
    });
  });
}

// Wire up the button
document.getElementById('jd-btn').addEventListener('click', openJdModal);
