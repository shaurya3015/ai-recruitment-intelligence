const API_BASE = "http://localhost:8000";

// --- STATE & DOM REFERENCES ---
let activeConversationId = null;
let conversationList, welcomeScreen, chatArea, chatMessages, chatForm, userInput;
let authToken = localStorage.getItem("resumeai_token") || "";
let authEmail = localStorage.getItem("resumeai_email") || "";

function authHeaders(extra = {}) {
    return authToken ? { ...extra, Authorization: `Bearer ${authToken}` } : extra;
}

function requireAuth() {
    if (authToken) return true;
    alert("Please sign in first.");
    return false;
}

// --- INITIALIZATION ---
// Use DOMContentLoaded to ensure all elements are ready before we start.
document.addEventListener('DOMContentLoaded', () => {
    // Assign references to our main DOM elements
    conversationList = document.getElementById('conversation-list');
    welcomeScreen = document.getElementById('welcome-screen');
    chatArea = document.getElementById('chat-area');
    chatMessages = document.getElementById('chatMessages');
    chatForm = document.getElementById('chatForm');
    userInput = document.getElementById('userInput');

    // Attach the main form submission listener
    chatForm.addEventListener('submit', handleSendMessage);
    document.getElementById('authForm').addEventListener('submit', handleAuthSubmit);
    document.getElementById('logoutBtn').addEventListener('click', handleLogout);

    // Hint pills — clicking a pill prefills the input
    document.querySelectorAll('.hint-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            userInput.value = pill.textContent.trim();
            userInput.focus();
        });
    });
    
    // --- THIS IS THE FIX: A SINGLE, DELEGATED EVENT LISTENER ---
    // This listener is attached to the whole document.
    document.addEventListener('click', (e) => {
        const target = e.target;
        
        // Case 1: A "New Chat" button was clicked
        if (target.closest('.js-new-chat')) {
            startNewChat();
        }

        // Case 2: A conversation item in the sidebar was clicked
        const conversationItem = target.closest('.conversation-item');
            if (conversationItem) {
            const id = conversationItem.dataset.id;
            
            // Sub-case A: The "rename" icon was clicked inside the item
            if (target.closest('.js-rename-btn')) {
                handleRename(id);
                return; // Stop further actions
            }
            // Sub-case B: The "delete" icon was clicked inside the item
            if (target.closest('.js-delete-btn')) {
                handleDelete(id);
                return; // Stop further actions
            }
            // Sub-case C: The conversation item itself was clicked
            selectConversation(id);
        }

        const sourceCard = target.closest('.source-card');
        if (sourceCard) {
            e.preventDefault();
            openResumeFile(sourceCard.dataset.resumeId, sourceCard.dataset.fileName);
        }
    });

    // Make the upload function available for the old-style onclick attribute
    window.handleUpload = handleUpload;

    // Load initial data
    updateAuthUI();
    if (authToken) loadConversations();
});

function updateAuthUI() {
    const authForm = document.getElementById('authForm');
    const authState = document.getElementById('authState');
    const authEmailEl = document.getElementById('authEmail');
    authForm.classList.toggle('hidden', Boolean(authToken));
    authState.classList.toggle('hidden', !authToken);
    authEmailEl.textContent = authEmail;
    if (!authToken) {
        conversationList.innerHTML = '<p class="px-3 py-2 text-xs text-gray-400">Sign in to load chats</p>';
    }
}

async function openResumeFile(resumeId, fileName) {
    if (!resumeId || !requireAuth()) return;
    try {
        const res = await fetch(`${API_BASE}/resumes/${resumeId}/file`, { headers: authHeaders() });
        if (!res.ok) throw new Error("Could not open resume.");
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.download = fileName || 'resume';
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (error) {
        alert(error.message);
    }
}

async function handleAuthSubmit(e) {
    e.preventDefault();
    const mode = e.submitter?.dataset.mode || 'login';
    const email = document.getElementById('authEmailInput').value.trim();
    const password = document.getElementById('authPasswordInput').value;
    const role = document.getElementById('authRoleInput').value;
    const body = mode === 'signup' ? { email, password, role } : { email, password };

    try {
        const res = await fetch(`${API_BASE}/auth/${mode}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || "Authentication failed");
        }
        const data = await res.json();
        authToken = data.access_token;
        authEmail = email;
        localStorage.setItem("resumeai_token", authToken);
        localStorage.setItem("resumeai_email", authEmail);
        updateAuthUI();
        await loadConversations();
    } catch (error) {
        alert(error.message);
    }
}

function handleLogout() {
    authToken = "";
    authEmail = "";
    activeConversationId = null;
    localStorage.removeItem("resumeai_token");
    localStorage.removeItem("resumeai_email");
    updateAuthUI();
    showWelcomeScreen();
}


// --- VIEW MANAGEMENT ---
function showWelcomeScreen() {
    welcomeScreen.classList.remove('hidden');
    chatArea.classList.add('hidden');
}

function showChatArea() {
    welcomeScreen.classList.add('hidden');
    chatArea.classList.remove('hidden');
}

// --- CORE LOGIC ---
async function loadConversations() {
    if (!requireAuth()) return;
    try {
        const res = await fetch(`${API_BASE}/conversations`, { headers: authHeaders() });
        if (!res.ok) throw new Error("Failed to load conversations.");
        const conversations = await res.json();
        renderConversationList(conversations);
    } catch (error) {
        console.error("Error loading conversations:", error);
    }
}

function renderConversationList(conversations) {
    conversationList.innerHTML = '';
    conversations.forEach(convo => {
        const convoItem = document.createElement('div');
        // Add data-id to the main item for easy selection
        convoItem.setAttribute('data-id', convo.id);
        convoItem.className = 'conversation-item group flex items-center justify-between p-3 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-200 cursor-pointer';
        
        // Use semantic classes for easier event delegation
        convoItem.innerHTML = `
            <span class="truncate">${convo.title}</span>
            <div class="actions flex items-center space-x-2">
                <i class="js-rename-btn fas fa-pen-to-square text-gray-500 hover:text-blue-600" title="Rename"></i>
                <i class="js-delete-btn fas fa-trash-can text-gray-500 hover:text-red-600" title="Delete"></i>
            </div>
        `;
        conversationList.appendChild(convoItem);
    });
    updateActiveConversationUI();
}

async function selectConversation(id) {
    if (!requireAuth()) return;
    if (activeConversationId === id && !welcomeScreen.classList.contains('hidden')) {
        showChatArea();
        return;
    }
    activeConversationId = id;
    showChatArea();
    updateActiveConversationUI();
    
    chatMessages.innerHTML = '<p class="text-center text-gray-500">Loading messages...</p>';
    
    try {
        const res = await fetch(`${API_BASE}/conversations/${id}`, { headers: authHeaders() });
        if (!res.ok) throw new Error("Failed to load messages.");
        const messages = await res.json();
        chatMessages.innerHTML = '';
        messages.forEach(msg => {
            if (msg.role === 'user') appendUserMessage(msg.content);
            else if (msg.role === 'assistant') appendBotMessage({ answer: msg.content, sources: msg.sources });
            else if (msg.role === 'file' && window.appendFileChip) {
                const meta = (msg.sources && msg.sources[0]) || { file_name: msg.content };
                appendFileChip(meta);
            }
        });
    } catch (error) {
        console.error("Error loading messages:", error);
        chatMessages.innerHTML = '<p class="text-center text-red-500">Failed to load chat history.</p>';
    }
}

async function startNewChat() {
    if (!requireAuth()) return;
    try {
        // Clear any pending file selection so nothing carries over into the new chat.
        const fileInput = document.getElementById('resumeInput');
        if (fileInput) fileInput.value = '';
        const fileNameLabel = document.getElementById('fileName');
        if (fileNameLabel) fileNameLabel.textContent = '';

        const res = await fetch(`${API_BASE}/conversations`, { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({}) });
        if (!res.ok) throw new Error("Failed to create new chat.");
        const newConvo = await res.json();
        await loadConversations();
        selectConversation(newConvo.id);
    } catch (error) {
        console.error("Error starting new chat:", error);
    }
}

async function handleRename(id) {
    const newTitle = prompt("Enter a new name for this chat:");
    if (!newTitle || !newTitle.trim()) return;
    try {
        await fetch(`${API_BASE}/conversations/${id}`, {
            method: 'PUT',
            headers: authHeaders({'Content-Type': 'application/json'}),
            body: JSON.stringify({new_title: newTitle.trim()})
        });
        loadConversations();
    } catch (error) {
        console.error("Failed to rename conversation:", error);
        alert("Error: Could not rename chat.");
    }
}

async function handleDelete(id) {
    if (!confirm("Are you sure you want to permanently delete this chat?")) return;
    try {
        await fetch(`${API_BASE}/conversations/${id}`, { method: 'DELETE', headers: authHeaders() });
        if (id == activeConversationId) {
            activeConversationId = null;
            showWelcomeScreen();
        }
        loadConversations();
    } catch (error) {
        console.error("Failed to delete conversation:", error);
        alert("Error: Could not delete chat.");
    }
}

function updateActiveConversationUI() {
    document.querySelectorAll('.conversation-item').forEach(item => {
        item.classList.toggle('active', item.getAttribute('data-id') == activeConversationId);
    });
}

function appendUserMessage(message) {
    const msgDiv = document.createElement("div");
    msgDiv.className = "flex justify-end";
    msgDiv.innerHTML = `<div class="text-white p-4 rounded-lg max-w-2xl shadow-md" style="background-color: var(--accent);">${message}</div>`;
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendBotMessage(data) {
    const msgContainer = document.createElement("div");
    msgContainer.className = "max-w-2xl space-y-3";
    const answerHtml = marked.parse(data.answer);
    const answerContainer = document.createElement('div');
    answerContainer.className = "inline-block bg-white text-gray-800 p-4 rounded-lg shadow-sm border";
    answerContainer.innerHTML = `<p class="font-semibold mb-2" style="color: var(--brand-blue);">AI Assistant</p><div class="markdown-content">${answerHtml}</div>`;
    msgContainer.appendChild(answerContainer);

    chatMessages.appendChild(msgContainer);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendThinkingIndicator() {
    const indicatorDiv = document.createElement("div");
    indicatorDiv.id = "thinking-indicator";
    indicatorDiv.innerHTML = `<div class="inline-block bg-white text-gray-500 p-4 rounded-lg shadow-sm border"><p class="font-semibold animate-pulse">AI is thinking...</p></div>`;
    chatMessages.appendChild(indicatorDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return indicatorDiv;
}

function appendErrorMessage(message) {
    const errorDiv = document.createElement("div");
    errorDiv.innerHTML = `<div class="inline-block bg-red-100 text-red-700 p-4 rounded-lg shadow-sm border border-red-200"><p class="font-semibold">Error</p><p>${message}</p></div>`;
    chatMessages.appendChild(errorDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function handleSendMessage(e) {
    e.preventDefault();
    const message = userInput.value.trim();
    if (!message || !activeConversationId) return;

    userInput.value = '';
    appendUserMessage(message);
    const indicator = appendThinkingIndicator();

    try {
        const res = await fetch(`${API_BASE}/chat/${activeConversationId}`, {
            method: 'POST',
            headers: authHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ message })
        });
        indicator.remove();
        if (!res.ok) throw new Error(`Server error: ${res.statusText}`);
        const data = await res.json();
        appendBotMessage({ answer: data.answer, sources: data.sources || [] });
        // Refresh sidebar title in case backend auto-renamed the chat
        loadConversations();
    } catch (error) {
        indicator.remove();
        console.error("Failed to send message:", error);
        appendErrorMessage("Could not reach the server. Is the backend running?");
    }
}

async function handleUpload() {
  if (!requireAuth()) return;
  const fileInput = document.getElementById("resumeInput");
  if (!fileInput.files.length) { alert("Please select a file to upload."); return; }
  // Capture the file first: starting a new chat clears the file input.
  const file = fileInput.files[0];
  // Make sure there's a conversation to attach this resume to, so the chat is
  // scoped to it instead of the whole collection.
  if (!activeConversationId) await startNewChat();
  const formData = new FormData();
  formData.append("file", file);
  if (activeConversationId) formData.append("conversation_id", activeConversationId);
  try {
    const res = await fetch(`${API_BASE}/upload/resume`, { method: "POST", headers: authHeaders(), body: formData });
    if (!res.ok) throw new Error(`Server error: ${res.statusText}`);
    const data = await res.json();
    // Show the uploaded file as a chip in the current chat thread.
    if (window.appendFileChip) appendFileChip(data);
    document.getElementById('fileName').textContent = '';
    fileInput.value = '';
  } catch (error) {
    console.error("Upload failed:", error);
    alert("Upload failed");
  }
}
