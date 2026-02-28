/* ==============================================
   ExamAI — Frontend Logic
   ============================================== */

(function () {
    'use strict';

    // ── Config ──
    const API_BASE = 'http://127.0.0.1:8000';

    // ── DOM Refs ──
    const uploadZone = document.getElementById('upload-zone');
    const uploadZoneInner = document.getElementById('upload-zone-inner');
    const fileInput = document.getElementById('file-input');
    const progressBar = document.getElementById('progress-bar');
    const documentCard = document.getElementById('document-card');
    const docTitle = document.getElementById('doc-title');
    const docFilename = document.getElementById('doc-filename');
    const statPages = document.getElementById('stat-pages');
    const statWords = document.getElementById('stat-words');
    const docTopics = document.getElementById('doc-topics');
    const topicsList = document.getElementById('topics-list');
    const recentQuestions = document.getElementById('recent-questions');
    const recentList = document.getElementById('recent-list');
    const chatMessages = document.getElementById('chat-messages');
    const chatEmpty = document.getElementById('chat-empty');
    const chatInput = document.getElementById('chat-input');
    const btnSend = document.getElementById('btn-send');
    const btnNewSession = document.getElementById('btn-new-session');
    const modeToggle = document.getElementById('mode-toggle');
    const modeTeachBtn = document.getElementById('mode-teach');
    const modePracticeBtn = document.getElementById('mode-practice');
    const modeTestBtn = document.getElementById('mode-test');

    // ── State ──
    let isDocumentReady = true;
    let isSending = false;
    let currentMode = 'teach';
    let currentSessionId = null;
    const recentQs = [];

    async function initializeSession() {
        try {
            const res = await fetch(`${API_BASE}/new-session`, { method: 'POST' });
            const data = await res.json();
            currentSessionId = data.session_id;
            localStorage.setItem('examai_session_id', currentSessionId);
            console.log('[SESSION] Initialized:', currentSessionId);
        } catch (err) {
            currentSessionId = 'fallback-' + Date.now();
            localStorage.setItem('examai_session_id', currentSessionId);
            console.warn('[SESSION] Backend unreachable, using fallback:', currentSessionId);
        }
    }

    let sessionReady = initializeSession();


    // ============================================
    // MODE TOGGLE
    // ============================================

    modeToggle.addEventListener('click', (e) => {
        const btn = e.target.closest('.mode-btn');
        if (!btn) return;
        const mode = btn.dataset.mode;
        if (mode === currentMode) return;

        currentMode = mode;
        modeTeachBtn.classList.toggle('active', mode === 'teach');
        modePracticeBtn.classList.toggle('active', mode === 'practice');
        modeTestBtn.classList.toggle('active', mode === 'test');
    });


    // ============================================
    // UPLOAD LOGIC
    // ============================================

    const SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg'];

    // Click to browse
    uploadZone.addEventListener('click', () => {
        if (uploadZone.classList.contains('uploading')) return;
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFiles(e.target.files);
        }
    });

    // Drag & drop
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragging');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragging');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragging');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFiles(files);
        }
    });

    function getFileExtension(filename) {
        return '.' + filename.split('.').pop().toLowerCase();
    }

    async function handleFiles(fileList) {
        const files = Array.from(fileList);

        // Validate all extensions
        for (const f of files) {
            const ext = getFileExtension(f.name);
            if (!SUPPORTED_EXTENSIONS.includes(ext)) {
                showSystemMessage(`Unsupported file: ${f.name}. Use PDF, DOCX, TXT, or images.`);
                return;
            }
        }

        // Visual upload state
        uploadZone.classList.add('uploading');
        progressBar.style.width = '0%';

        // Simulate progress
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += Math.random() * 12;
            if (progress > 90) progress = 90;
            progressBar.style.width = progress + '%';
        }, 200);

        // Build FormData with all files
        const formData = new FormData();
        for (const f of files) {
            formData.append('files', f);
        }
        formData.append('session_id', currentSessionId);

        try {
            const res = await fetch(`${API_BASE}/upload`, {
                method: 'POST',
                body: formData,
            });

            clearInterval(progressInterval);
            progressBar.style.width = '100%';

            if (!res.ok) {
                const errData = await res.json().catch(() => null);
                throw new Error(errData?.detail || 'Upload failed');
            }

            const data = await res.json();

            // Small delay for visual polish
            await delay(400);

            // Derive display info
            if (files.length === 1) {
                const name = files[0].name;
                const title = name
                    .replace(/\.\w+$/i, '')
                    .replace(/[-_]/g, ' ')
                    .replace(/\b\w/g, (c) => c.toUpperCase());
                docTitle.textContent = title;
                docFilename.textContent = name;
            } else {
                docTitle.textContent = `${files.length} Files Uploaded`;
                docFilename.textContent = files.map((f) => f.name).join(', ');
            }

            // Use real page count from backend, with word estimate
            const realPages = data.pages || Math.max(1, Math.round(files.reduce((s, f) => s + f.size, 0) / 1024 / 50));
            const estimatedWords = Math.round(realPages * 300);
            statPages.textContent = realPages;
            statWords.textContent = estimatedWords.toLocaleString();

            // Switch to document card
            uploadZone.classList.add('hidden');
            documentCard.classList.remove('hidden');

            // Render extracted topics
            if (data.topics && data.topics.length > 0) {
                topicsList.innerHTML = '';
                data.topics.forEach((topic) => {
                    const pill = document.createElement('span');
                    pill.className = 'topic-pill';
                    pill.textContent = topic;
                    topicsList.appendChild(pill);
                });
                docTopics.classList.remove('hidden');
            } else {
                docTopics.classList.add('hidden');
            }

            // Enable chat
            isDocumentReady = true;
            chatInput.disabled = false;
            chatInput.placeholder = 'Ask a follow-up question...';
            chatEmpty.querySelector('.empty-text').textContent =
                'Your documents are ready. Ask a question!';

            // Focus chat input
            chatInput.focus();
        } catch (err) {
            clearInterval(progressInterval);
            progressBar.style.width = '0%';
            uploadZone.classList.remove('uploading');
            showSystemMessage('Upload failed. Please try again.');
        }
    }


    // ============================================
    // CHAT LOGIC
    // ============================================

    // Send on Enter
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Send on button click
    btnSend.addEventListener('click', sendMessage);

    // Toggle send button strictly based on input text and sending state
    chatInput.addEventListener('input', () => {
        const hasText = chatInput.value.trim().length > 0;
        btnSend.disabled = !(hasText && !isSending);
    });


    async function sendMessage() {
        await sessionReady;
        const text = chatInput.value.trim();
        if (!text || isSending) return;

        isSending = true;
        btnSend.disabled = true;
        chatInput.value = '';

        // Hide empty state
        if (chatEmpty) chatEmpty.classList.add('hidden');

        // Add timestamp pill (on first message or after a gap)
        addTimestampPill();

        // Append user bubble
        appendMessage('user', text);

        // Track recent question
        addRecentQuestion(text);

        // Show typing indicator
        const typingEl = showTyping();

        try {
            const res = await fetch(`${API_BASE}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, mode: currentMode, session_id: currentSessionId }),
            });

            const data = await res.json();

            // Remove typing
            removeTyping(typingEl);

            if (data.error) {
                appendMessage('ai', data.error);
            } else {
                appendMessage('ai', data.answer);
            }
        } catch (err) {
            removeTyping(typingEl);
            appendMessage('ai', 'Something went wrong. Please try again.');
        }

        isSending = false;
        btnSend.disabled = chatInput.value.trim().length === 0;
    }


    // ── Append a chat message bubble ──
    function appendMessage(role, text) {
        const row = document.createElement('div');
        row.className = `message-row ${role}`;

        const avatarSvg =
            role === 'ai'
                ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
             <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
             <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
           </svg>`
                : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
             <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
             <circle cx="12" cy="7" r="4"/>
           </svg>`;

        const label =
            role === 'ai'
                ? `<div class="message-label">ExamAI <span class="online-dot"></span></div>`
                : '';

        const renderedText = role === 'ai' ? DOMPurify.sanitize(marked.parse(text)) : escapeHTML(text);

        row.innerHTML = `
      <div class="message-avatar">${avatarSvg}</div>
      <div class="message-bubble">
        ${label}
        <div class="message-text">${renderedText}</div>
      </div>
    `;

        chatMessages.appendChild(row);

        // Render LaTeX math using KaTeX (after DOM insertion)
        if (typeof renderMathInElement === 'function') {
            renderMathInElement(row, {
                delimiters: [
                    { left: "$$", right: "$$", display: true },
                    { left: "\\[", right: "\\]", display: true },
                    { left: "$", right: "$", display: false },
                    { left: "\\(", right: "\\)", display: false }
                ],
                throwOnError: false
            });
        }

        scrollToBottom();
    }


    // ── Typing indicator ──
    function showTyping() {
        const el = document.createElement('div');
        el.className = 'typing-indicator';
        el.innerHTML = `
      <div class="message-avatar" style="background:var(--bg-tertiary);border:1px solid var(--border-subtle);color:var(--text-secondary);display:flex;align-items:center;justify-content:center;width:32px;height:32px;min-width:32px;border-radius:9999px;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
        </svg>
      </div>
      <div class="typing-dots">
        <span></span><span></span><span></span>
      </div>
    `;
        chatMessages.appendChild(el);
        scrollToBottom();
        return el;
    }

    function removeTyping(el) {
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }


    // ── Timestamp pill ──
    let lastTimestamp = 0;
    function addTimestampPill() {
        const now = Date.now();
        if (now - lastTimestamp < 5 * 60 * 1000 && lastTimestamp !== 0) return;
        lastTimestamp = now;

        const pill = document.createElement('div');
        pill.className = 'timestamp-pill';
        const time = new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
        });
        const today = 'Today, ' + time;
        pill.innerHTML = `<span>${today}</span>`;
        chatMessages.appendChild(pill);
    }


    // ── System message (errors) ──
    function showSystemMessage(text) {
        if (chatEmpty) chatEmpty.classList.add('hidden');
        const el = document.createElement('div');
        el.className = 'timestamp-pill';
        el.innerHTML = `<span style="color:var(--text-secondary)">${escapeHTML(text)}</span>`;
        chatMessages.appendChild(el);
        scrollToBottom();
    }


    // ── Recent questions sidebar ──
    function addRecentQuestion(text) {
        recentQs.unshift({ text, time: new Date() });
        if (recentQs.length > 10) recentQs.pop();
        renderRecentQuestions();
    }

    function renderRecentQuestions() {
        recentQuestions.classList.remove('hidden');
        recentList.innerHTML = '';

        recentQs.forEach((q) => {
            const li = document.createElement('li');
            li.className = 'recent-item';
            const ago = timeAgo(q.time);
            li.innerHTML = `
        <div class="recent-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <div>
          <div class="recent-text">${escapeHTML(truncate(q.text, 60))}</div>
          <div class="recent-time">${ago}</div>
        </div>
      `;
            li.addEventListener('click', () => {
                chatInput.value = q.text;
                chatInput.focus();
                chatInput.dispatchEvent(new Event('input'));
            });
            recentList.appendChild(li);
        });
    }


    // ============================================
    // NEW SESSION
    // ============================================

    btnNewSession.addEventListener('click', async () => {
        sessionReady = initializeSession();
        await sessionReady;

        isDocumentReady = true;
        isSending = false;
        recentQs.length = 0;
        lastTimestamp = 0;

        currentMode = 'teach';
        modeTeachBtn.classList.add('active');
        modePracticeBtn.classList.remove('active');
        modeTestBtn.classList.remove('active');

        uploadZone.classList.remove('hidden', 'uploading');
        progressBar.style.width = '0%';
        fileInput.value = '';
        documentCard.classList.add('hidden');
        docTopics.classList.add('hidden');
        topicsList.innerHTML = '';

        chatMessages.innerHTML = '';
        const emptyState = document.createElement('div');
        emptyState.className = 'chat-empty';
        emptyState.id = 'chat-empty';
        emptyState.innerHTML = `
      <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" opacity="0.25">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
      <p class="empty-text">Ask anything, or upload a file for contextual answers</p>
    `;
        chatMessages.appendChild(emptyState);

        chatInput.disabled = false;
        chatInput.value = '';
        chatInput.placeholder = 'Ask anything...';
        btnSend.disabled = true;

        recentQuestions.classList.add('hidden');
        recentList.innerHTML = '';
    });


    // ============================================
    // UTILITY
    // ============================================

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        });
    }

    function escapeHTML(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // (Custom renderMarkdown removed in favor of marked.js)

    function truncate(str, len) {
        return str.length > len ? str.slice(0, len) + '…' : str;
    }

    function delay(ms) {
        return new Promise((r) => setTimeout(r, ms));
    }

    function timeAgo(date) {
        const seconds = Math.floor((Date.now() - date) / 1000);
        if (seconds < 60) return 'Just now';
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return minutes + ' min' + (minutes > 1 ? 's' : '') + ' ago';
        const hours = Math.floor(minutes / 60);
        return hours + ' hour' + (hours > 1 ? 's' : '') + ' ago';
    }

})();
