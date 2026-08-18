const questionInput = document.getElementById("question");
const askButton = document.getElementById("askButton");
const statusEl = document.getElementById("status");
const chatEl = document.getElementById("chat");
const historyEl = document.getElementById("history");
const healthEl = document.getElementById("health");
const newChatButton = document.getElementById("newChat");
const clearHistoryButton = document.getElementById("clearHistory");
const menuButton = document.getElementById("menuButton");
const sidebar = document.getElementById("sidebar");

const STORAGE_KEY = "clinical-rag-day2-history-v1";
let chats = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
let activeChatId = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats.slice(0, 30)));
}

function createChat() {
  const chat = { id: crypto.randomUUID(), title: "New clinical question", messages: [], updated: Date.now() };
  chats.unshift(chat);
  activeChatId = chat.id;
  save();
  renderHistory();
  renderChat();
}

function getActiveChat() {
  return chats.find(c => c.id === activeChatId);
}

function renderHistory() {
  historyEl.innerHTML = chats.map(chat => `
    <button class="history-item ${chat.id === activeChatId ? "active" : ""}" data-id="${chat.id}">
      <span class="history-dot"></span>
      <span class="history-label">${escapeHtml(chat.title)}</span>
    </button>
  `).join("");
  historyEl.querySelectorAll(".history-item").forEach(btn => {
    btn.addEventListener("click", () => {
      activeChatId = btn.dataset.id;
      renderHistory();
      renderChat();
      sidebar.classList.remove("open");
    });
  });
}

function evidenceHtml(evidence) {
  return evidence.map(item => `
    <details class="evidence-card" ${item.rank === 1 ? "open" : ""}>
      <summary>
        <span><b>#${item.rank}</b> ${escapeHtml(item.document_name)}</span>
        <span class="score">${Number(item.similarity).toFixed(3)}</span>
      </summary>
      <div class="evidence-body">
        <div class="evidence-meta">
          <span>Page ${escapeHtml(item.page_number)}</span>
          <span>${escapeHtml(item.section)}</span>
          <span>${escapeHtml(item.chunk_id)}</span>
          <span>${escapeHtml(item.retrieval_method || "semantic")}</span>
        </div>
        <p>${escapeHtml(item.text)}</p>
        ${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">Open source ↗</a>` : ""}
      </div>
    </details>
  `).join("");
}

function messageHtml(message, index) {
  if (message.role === "user") {
    return `<article class="message user-message"><div class="bubble user-bubble">${escapeHtml(message.content)}</div></article>`;
  }
  return `
    <article class="message assistant-message">
      <div class="assistant-avatar">AI</div>
      <div class="assistant-body">
        <div class="assistant-bubble">${escapeHtml(message.content)}</div>
        ${message.evidence?.length ? `
          <div class="evidence-panel">
            <div class="evidence-heading"><span>Retrieved evidence</span><span>Top-${message.evidence.length}</span></div>
            ${evidenceHtml(message.evidence)}
          </div>` : ""}
        <div class="message-actions">
          <button data-action="copy" data-index="${index}" title="Copy answer">Copy</button>
          <button data-action="like" data-index="${index}" title="Helpful">♡ Helpful</button>
          <button data-action="dislike" data-index="${index}" title="Not helpful">Not helpful</button>
          <button data-action="reply" data-index="${index}" title="Reply">↩ Reply</button>
        </div>
      </div>
    </article>`;
}

function renderChat() {
  const chat = getActiveChat();
  if (!chat || !chat.messages.length) {
    chatEl.innerHTML = `
      <div class="welcome">
        <div class="welcome-icon">✦</div>
        <h2>Evidence first. Answers second.</h2>
        <p>Day 2 focuses on retrieval quality: the system shows the evidence, metadata, scores, and source before generating an answer.</p>
      </div>`;
    return;
  }
  chatEl.innerHTML = chat.messages.map(messageHtml).join("");
  chatEl.scrollTop = chatEl.scrollHeight;
  chatEl.querySelectorAll("[data-action]").forEach(button => {
    button.addEventListener("click", () => handleAction(button.dataset.action, Number(button.dataset.index)));
  });
}

async function handleAction(action, index) {
  const chat = getActiveChat();
  const message = chat?.messages[index];
  if (!message) return;
  if (action === "copy") {
    await navigator.clipboard.writeText(message.content);
    statusEl.textContent = "Answer copied.";
  } else if (action === "reply") {
    questionInput.value = `Follow up on this answer:\n\n${message.content}\n\nMy follow-up question: `;
    questionInput.focus();
  } else if (action === "like" || action === "dislike") {
    message.feedback = action;
    save();
    renderChat();
    statusEl.textContent = action === "like" ? "Marked helpful." : "Feedback saved.";
  }
}

async function ask() {
  const question = questionInput.value.trim();
  if (!question) return;
  if (!activeChatId) createChat();
  const chat = getActiveChat();
  chat.title = chat.messages.length ? chat.title : question.slice(0, 48);
  chat.updated = Date.now();
  chat.messages.push({ role: "user", content: question, created: Date.now() });
  renderChat();
  renderHistory();
  questionInput.value = "";
  askButton.disabled = true;
  statusEl.textContent = "Retrieving and ranking evidence…";

  try {
    const retrievalResponse = await fetch("/api/retrieve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: 5, strategy: "hybrid", config: "B_850_150", rerank: true })
    });
    const retrieval = await retrievalResponse.json();
    if (!retrievalResponse.ok) throw new Error(retrieval.detail || "Retrieval failed.");

    // Evidence is rendered immediately, before the LLM call.
    chat.messages.push({ role: "assistant", content: "", evidence: retrieval.evidence, pending: true, retrievalId: retrieval.retrieval_id, created: Date.now() });
    renderChat();
    statusEl.textContent = "Evidence ready. Generating a grounded answer…";

    const answerResponse = await fetch("/api/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ retrieval_id: retrieval.retrieval_id, question })
    });
    const answer = await answerResponse.json();
    if (!answerResponse.ok) throw new Error(answer.detail || "Answer generation failed.");

    const assistant = chat.messages[chat.messages.length - 1];
    assistant.content = answer.answer;
    assistant.pending = false;
    chat.updated = Date.now();
    save();
    renderChat();
    statusEl.textContent = "Answer ready · evidence verified first.";
  } catch (error) {
    const last = chat.messages[chat.messages.length - 1];
    if (last?.pending) {
      last.content = "The answer could not be generated. The retrieved evidence is still shown above for inspection.";
      last.pending = false;
    }
    save();
    renderChat();
    statusEl.textContent = error.message;
  } finally {
    askButton.disabled = false;
    questionInput.focus();
  }
}

askButton.addEventListener("click", ask);
questionInput.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") ask();
});

document.querySelectorAll(".example").forEach(button => {
  button.addEventListener("click", () => {
    questionInput.value = button.textContent;
    questionInput.focus();
  });
});

newChatButton.addEventListener("click", createChat);
clearHistoryButton.addEventListener("click", () => {
  chats = [];
  activeChatId = null;
  save();
  createChat();
});
menuButton.addEventListener("click", () => sidebar.classList.toggle("open"));

fetch("/api/health")
  .then(r => r.json())
  .then(data => {
    healthEl.textContent = data.index_ready ? "● Online" : "● Index needed";
    healthEl.classList.toggle("ready", data.index_ready);
  })
  .catch(() => { healthEl.textContent = "● Offline"; });

if (!chats.length) createChat();
else {
  activeChatId = chats[0].id;
  renderHistory();
  renderChat();
}
