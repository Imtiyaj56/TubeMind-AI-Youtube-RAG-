/* ═══════════════════════════════════════════════════════════
   TubeMind AI — App Logic (ES6+ Vanilla JS)
   Features:
     • Video load + processing with animated progress
     • Multi-video session sidebar
     • SSE streaming with token-by-token display
     • Markdown rendering
     • Keyboard shortcuts
     • Auto-resize textarea
     • Session management (switch / delete)
═══════════════════════════════════════════════════════════ */

'use strict';

// ── State ─────────────────────────────────────────────────
const state = {
  activeVideoId: null,
  isStreaming: false,
  sessions: {},           // videoId → { title, channel, thumbnail }
  abortController: null,  // for cancelling SSE
};

// ── DOM refs ───────────────────────────────────────────────
const $ = id => document.getElementById(id);

const dom = {
  // Sidebar
  sidebar:          $('sidebar'),
  sidebarOverlay:   $('sidebarOverlay'),
  sidebarToggle:    $('sidebarToggle'),
  sidebarClose:     $('sidebarClose'),
  sessionsList:     $('sessionsList'),
  emptySessionsMsg: $('emptySessionsMsg'),
  newVideoBtn:      $('newVideoBtn'),

  // Header
  headerPlaceholder:   $('headerPlaceholder'),
  headerVideoDetails:  $('headerVideoDetails'),
  headerThumb:         $('headerThumb'),
  headerTitle:         $('headerTitle'),
  headerChannel:       $('headerChannel'),
  statusBadge:         $('statusBadge'),

  // Load panel
  loadPanel:       $('loadPanel'),
  videoIdInput:    $('videoIdInput'),
  processVideoBtn: $('processVideoBtn'),
  processBtnIcon:  $('processBtnIcon'),
  processBtnText:  $('processBtnText'),
  loadError:       $('loadError'),
  loadErrorText:   $('loadErrorText'),

  // Processing overlay
  processingOverlay: $('processingOverlay'),
  processingStep:    $('processingStep'),
  processingBar:     $('processingBar'),

  // Chat panel
  chatPanel:          $('chatPanel'),
  videoInfoBar:       $('videoInfoBar'),
  videoThumb:         $('videoThumb'),
  videoTitle:         $('videoTitle'),
  videoChannel:       $('videoChannel'),
  videoLink:          $('videoLink'),
  thumbLink:          $('thumbLink'),
  changeVideoBtn:     $('changeVideoBtn'),
  messagesContainer:  $('messagesContainer'),
  welcomeMessage:     $('welcomeMessage'),
  questionInput:      $('questionInput'),
  sendBtn:            $('sendBtn'),
  sendIcon:           $('sendIcon'),
};

// ── Markdown renderer (marked.js) ────────────────────────
function renderMarkdown(text) {
  if (!text) return '';
  if (typeof marked !== 'undefined') {
    return marked.parse(text);
  }
  return escapeHtml(text);
}

// ── Time helper ───────────────────────────────────────────
function timeNow() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ── Toast notifications ───────────────────────────────────
function showToast(message, type = 'info') {
  const colors = {
    info:    'bg-bg-secondary border-border-subtle text-text-primary',
    success: 'bg-green-500/10 border-green-500/30 text-green-400',
    error:   'bg-red-500/10 border-red-500/30 text-red-400',
  };
  const toast = document.createElement('div');
  toast.className = `fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl border shadow-2xl text-sm font-medium animate-slide-up ${colors[type]}`;
  toast.innerHTML = `<span>${message}</span>`;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 3500);
}

// ── Sidebar toggle (mobile) ───────────────────────────────
dom.sidebarToggle.addEventListener('click', () => {
  dom.sidebar.classList.add('open');
  dom.sidebarOverlay.classList.remove('hidden');
});
[dom.sidebarClose, dom.sidebarOverlay].forEach(el => {
  el.addEventListener('click', () => {
    dom.sidebar.classList.remove('open');
    dom.sidebarOverlay.classList.add('hidden');
  });
});

// ── New Video button → show load panel ───────────────────
dom.newVideoBtn.addEventListener('click', () => {
  showLoadPanel();
  dom.sidebar.classList.remove('open');
  dom.sidebarOverlay.classList.add('hidden');
});

// ── Change video button ───────────────────────────────────
dom.changeVideoBtn.addEventListener('click', showLoadPanel);

function showLoadPanel() {
  dom.loadPanel.classList.remove('hidden');
  dom.loadPanel.classList.add('flex');
  dom.chatPanel.classList.add('hidden');
  dom.chatPanel.classList.remove('flex');
  dom.headerPlaceholder.classList.remove('hidden');
  dom.headerVideoDetails.classList.add('hidden');
  dom.headerVideoDetails.classList.remove('flex');
  dom.statusBadge.classList.add('hidden');
  dom.statusBadge.classList.remove('flex');
  dom.videoIdInput.focus();
}

// ── Update header ─────────────────────────────────────────
function updateHeader(session) {
  dom.headerPlaceholder.classList.add('hidden');
  dom.headerVideoDetails.classList.remove('hidden');
  dom.headerVideoDetails.classList.add('flex');
  dom.headerThumb.src = session.thumbnail;
  dom.headerTitle.textContent = session.title;
  dom.headerChannel.textContent = session.channel;
  dom.statusBadge.classList.remove('hidden');
  dom.statusBadge.classList.add('flex');
}

// ── Session list rendering ────────────────────────────────
function renderSessions() {
  const ids = Object.keys(state.sessions);
  dom.emptySessionsMsg.style.display = ids.length === 0 ? 'flex' : 'none';

  // Remove old items (not the empty msg)
  dom.sessionsList.querySelectorAll('.session-item').forEach(el => el.remove());

  ids.forEach(vid => {
    const s = state.sessions[vid];
    const item = document.createElement('div');
    item.className = `session-item ${vid === state.activeVideoId ? 'active' : ''}`;
    item.dataset.videoid = vid;
    item.innerHTML = `
      <img class="session-thumb" src="${s.thumbnail}" alt="" onerror="this.src='https://img.youtube.com/vi/${vid}/default.jpg'"/>
      <div class="session-info">
        <div class="session-title" title="${s.title}">${s.title}</div>
        <div class="session-meta">${s.channel}</div>
      </div>
      <button class="session-delete" title="Remove session" data-vid="${vid}">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    `;
    item.addEventListener('click', (e) => {
      if (e.target.closest('.session-delete')) return;
      switchToSession(vid);
    });
    item.querySelector('.session-delete').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteSession(vid);
    });
    dom.sessionsList.appendChild(item);
  });
}

// ── Switch session ────────────────────────────────────────
async function switchToSession(videoId) {
  state.activeVideoId = videoId;
  const session = state.sessions[videoId];
  renderSessions();
  updateHeader(session);
  showChatPanel(session);

  // Load history from server
  try {
    const res = await fetch(`/api/history/${videoId}`);
    const data = await res.json();
    rebuildMessages(data.history || []);
  } catch (_) { /* ignore */ }

  dom.sidebar.classList.remove('open');
  dom.sidebarOverlay.classList.add('hidden');
}

function rebuildMessages(history) {
  // Clear except welcome
  const toRemove = dom.messagesContainer.querySelectorAll('.message-row');
  toRemove.forEach(el => el.remove());
  dom.welcomeMessage.style.display = history.length === 0 ? 'block' : 'none';
  history.forEach(msg => {
    appendMessage(msg.role === 'user' ? 'user' : 'ai', msg.content, false);
  });
  scrollToBottom();
}

// ── Delete session ────────────────────────────────────────
async function deleteSession(videoId) {
  try { await fetch(`/api/session/${videoId}`, { method: 'DELETE' }); } catch (_) {}
  delete state.sessions[videoId];
  if (state.activeVideoId === videoId) {
    state.activeVideoId = null;
    showLoadPanel();
  }
  renderSessions();
  showToast('Session removed.', 'info');
}

// ── Show chat panel ───────────────────────────────────────
function showChatPanel(session) {
  dom.loadPanel.classList.add('hidden');
  dom.loadPanel.classList.remove('flex');
  dom.chatPanel.classList.remove('hidden');
  dom.chatPanel.classList.add('flex');

  dom.videoThumb.src = session.thumbnail;
  dom.videoTitle.textContent = session.title;
  dom.videoChannel.textContent = session.channel;
  dom.videoLink.href = `https://www.youtube.com/watch?v=${state.activeVideoId}`;
  dom.thumbLink.onclick = () => window.open(`https://www.youtube.com/watch?v=${state.activeVideoId}`, '_blank');

  dom.welcomeMessage.style.display = 'block';
  dom.messagesContainer.querySelectorAll('.message-row').forEach(el => el.remove());
  dom.questionInput.focus();
}

// ── Processing overlay helpers ────────────────────────────
const processingSteps = [
  [10, 'Fetching transcript...'],
  [35, 'Splitting into chunks...'],
  [60, 'Generating embeddings...'],
  [80, 'Building FAISS index...'],
  [92, 'Creating retriever chain...'],
];

function runProcessingAnimation() {
  let i = 0;
  const interval = setInterval(() => {
    if (i >= processingSteps.length) { clearInterval(interval); return; }
    const [pct, msg] = processingSteps[i++];
    dom.processingBar.style.width = pct + '%';
    dom.processingStep.textContent = msg;
  }, 1800);
  return interval;
}

// ── Process Video ─────────────────────────────────────────
dom.processVideoBtn.addEventListener('click', processVideo);
dom.videoIdInput.addEventListener('keydown', e => { if (e.key === 'Enter') processVideo(); });

async function processVideo() {
  const raw = dom.videoIdInput.value.trim();
  if (!raw) return;

  // Strip full YouTube URL to ID
  let videoId = raw;
  const urlMatch = raw.match(/(?:v=|youtu\.be\/)([A-Za-z0-9_\-]{11})/);
  if (urlMatch) videoId = urlMatch[1];

  // Basic validation
  if (!/^[A-Za-z0-9_\-]{11}$/.test(videoId)) {
    showError('Invalid video ID. It should be 11 characters (e.g. dQw4w9WgXcQ).');
    return;
  }

  hideError();
  dom.processVideoBtn.disabled = true;
  dom.processBtnText.textContent = 'Loading...';

  // Show overlay
  dom.processingBar.style.width = '5%';
  dom.processingStep.textContent = 'Connecting...';
  dom.processingOverlay.classList.remove('hidden');
  const animInterval = runProcessingAnimation();

  try {
    const res = await fetch('/api/process_video', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_id: videoId }),
    });

    clearInterval(animInterval);

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to process video.');
    }

    const data = await res.json();
    dom.processingBar.style.width = '100%';
    dom.processingStep.textContent = 'Done! Ready to chat ✓';
    await sleep(700);

    // Store session
    state.sessions[videoId] = {
      title:     data.title,
      channel:   data.channel,
      thumbnail: data.thumbnail,
    };
    state.activeVideoId = videoId;

    renderSessions();
    updateHeader(state.sessions[videoId]);
    showChatPanel(state.sessions[videoId]);
    dom.videoIdInput.value = '';
    showToast(`✅ "${data.title}" loaded!`, 'success');

  } catch (err) {
    clearInterval(animInterval);
    showError(err.message || 'Something went wrong. Please try again.');
  } finally {
    dom.processingOverlay.classList.add('hidden');
    dom.processingBar.style.width = '0%';
    dom.processVideoBtn.disabled = false;
    dom.processBtnText.textContent = 'Load Video';
  }
}

function showError(msg) {
  dom.loadError.classList.remove('hidden');
  dom.loadError.classList.add('flex');
  dom.loadErrorText.textContent = msg;
}
function hideError() {
  dom.loadError.classList.add('hidden');
  dom.loadError.classList.remove('flex');
}

// ── Textarea auto-resize & send enable ───────────────────
dom.questionInput.addEventListener('input', () => {
  dom.sendBtn.disabled = dom.questionInput.value.trim() === '' || state.isStreaming;
});

dom.questionInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!dom.sendBtn.disabled) sendMessage();
  }
});

dom.sendBtn.addEventListener('click', sendMessage);

// ── Send Message ──────────────────────────────────────────
async function sendMessage() {
  if (state.isStreaming || !state.activeVideoId) return;
  const question = dom.questionInput.value.trim();
  if (!question) return;

  dom.questionInput.value = '';
  dom.sendBtn.disabled = true;
  dom.welcomeMessage.style.display = 'none';

  // Show user message
  appendMessage('user', question, true);
  scrollToBottom();

  // Create AI bubble (streaming target)
  const { row, bubble } = createAIBubble();
  dom.messagesContainer.appendChild(row);
  scrollToBottom();

  state.isStreaming = true;
  setSendLoading(true);

  let fullText = '';
  const cursor = document.createElement('span');
  cursor.className = 'cursor-blink';
  bubble.appendChild(cursor);

  try {
    const response = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_id: state.activeVideoId, question }),
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to get response.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const payload = JSON.parse(line.slice(6));
          if (payload.done) {
            cursor.remove();
            bubble.innerHTML = renderMarkdown(fullText);
            break;
          }
          if (payload.token) {
            fullText += payload.token;
            // Render as raw text while streaming, final render is markdown
            bubble.innerHTML = escapeHtml(fullText);
            bubble.appendChild(cursor);
            scrollToBottom();
          }
        } catch (_) { /* skip malformed */ }
      }
    }
    cursor.remove();
    if (fullText) bubble.innerHTML = renderMarkdown(fullText);

  } catch (err) {
    cursor.remove();
    bubble.innerHTML = `<span class="text-red-400">⚠️ ${escapeHtml(err.message)}</span>`;
    showToast(err.message, 'error');
  } finally {
    state.isStreaming = false;
    setSendLoading(false);
    dom.sendBtn.disabled = dom.questionInput.value.trim() === '';
    scrollToBottom();

    // Add timestamp
    const meta = document.createElement('div');
    meta.className = 'bubble-meta';
    meta.textContent = timeNow();
    row.querySelector('.bubble-wrapper').appendChild(meta);
  }
}

// ── Message helpers ───────────────────────────────────────
function appendMessage(role, content, animate) {
  const isUser = role === 'user';
  const row = document.createElement('div');
  row.className = `message-row ${isUser ? 'user' : ''} ${animate ? 'animate-slide-up' : ''}`;

  const avatarHtml = isUser
    ? `<div class="avatar user-av">U</div>`
    : `<div class="avatar ai">
        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
          <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
        </svg>
       </div>`;

  row.innerHTML = `
    ${avatarHtml}
    <div class="bubble-wrapper flex flex-col ${isUser ? 'items-end' : 'items-start'} flex-1">
      <p class="text-xs font-semibold mb-1.5 px-1 ${isUser ? 'text-indigo-400 text-right' : 'text-yt-red'}">${isUser ? 'You' : 'TubeMind AI'}</p>
      <div class="bubble ${isUser ? 'user' : 'ai'}">${isUser ? escapeHtml(content) : renderMarkdown(content)}</div>
      <div class="bubble-meta">${timeNow()}</div>
    </div>
  `;
  dom.messagesContainer.appendChild(row);
  return row;
}

function createAIBubble() {
  const row = document.createElement('div');
  row.className = 'message-row animate-slide-up';
  row.innerHTML = `
    <div class="avatar ai">
      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
      </svg>
    </div>
    <div class="bubble-wrapper flex flex-col items-start flex-1">
      <p class="text-xs font-semibold mb-1.5 px-1 text-yt-red">TubeMind AI</p>
      <div class="bubble ai min-w-12"></div>
    </div>
  `;
  const bubble = row.querySelector('.bubble.ai');
  return { row, bubble };
}

// ── Scroll ────────────────────────────────────────────────
function scrollToBottom() {
  dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
}

// ── Send button loading state ─────────────────────────────
function setSendLoading(loading) {
  if (loading) {
    dom.sendIcon.innerHTML = `<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="28.3" stroke-dashoffset="0" class="animate-spin origin-center"/>`;
    dom.sendBtn.classList.add('animate-pulse-soft');
  } else {
    dom.sendIcon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>`;
    dom.sendBtn.classList.remove('animate-pulse-soft');
  }
}

// ── Utilities ─────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Init ──────────────────────────────────────────────────
(function init() {
  // Focus video input on load
  dom.videoIdInput.focus();
  renderSessions();

  // Paste handler — strip full YouTube URLs
  dom.videoIdInput.addEventListener('paste', (e) => {
    setTimeout(() => {
      const val = dom.videoIdInput.value.trim();
      const match = val.match(/(?:v=|youtu\.be\/)([A-Za-z0-9_\-]{11})/);
      if (match) {
        dom.videoIdInput.value = match[1];
        showToast('📎 Extracted Video ID from URL!', 'success');
      }
    }, 50);
  });
})();
