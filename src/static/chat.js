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

form.addEventListener('submit', e => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  input.disabled = true;

  addMessage('user', q);
  const loader = addLoading();
  let assistantDiv = null;

  let url = `/api/chat?q=${encodeURIComponent(q)}`;
  if (sessionId) {
    url += `&session_id=${encodeURIComponent(sessionId)}`;
  }
  if (window.__fp) {
    url += `&fp=${encodeURIComponent(window.__fp)}`;
  }

  if (window.resetGraph) window.resetGraph();
  const source = new EventSource(url);

  source.addEventListener('session', event => {
    const data = JSON.parse(event.data);
    sessionId = data.session_id;
  });

  source.addEventListener('graph', event => {
    window.updateGraph(JSON.parse(event.data));
  });

  source.onmessage = event => {
    if (event.data === '[DONE]') {
      source.close();
      input.disabled = false;
      input.focus();
      return;
    }
    if (loader.parentNode) loader.remove();
    if (!assistantDiv) {
      assistantDiv = addMessage('assistant', event.data);
    } else {
      assistantDiv.innerHTML = renderMarkdown(event.data);
    }
    messages.scrollTop = messages.scrollHeight;
  };

  source.onerror = () => {
    source.close();
    if (loader.parentNode) loader.remove();
    if (!assistantDiv) addMessage('assistant', 'Connection lost. Please try again.');
    input.disabled = false;
    input.focus();
  };
});
