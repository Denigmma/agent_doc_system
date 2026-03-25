const state = {
    currentChatId: null,
    chats: [],
};

let activeChatEventSource = null;

const elements = {
    chatList: document.getElementById("chat-list"),
    newChatBtn: document.getElementById("new-chat-btn"),
    resetContextBtn: document.getElementById("reset-context-btn"),
    messagesContainer: document.getElementById("messages-container"),
    messageInput: document.getElementById("message-input"),
    sendBtn: document.getElementById("send-btn"),
    chatTitle: document.getElementById("chat-title"),
    chatSubtitle: document.getElementById("chat-subtitle"),
};

async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            "Content-Type": "application/json",
        },
        ...options,
    });

    if (!response.ok) {
        let detail = "Ошибка запроса";
        try {
            const data = await response.json();
            detail = data.detail || detail;
        } catch (_) {}
        throw new Error(detail);
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
        return await response.json();
    }

    return response;
}

async function loadChats() {
    try {
        const data = await apiRequest("/api/chats");
        state.chats = data.items || [];
        renderChatList();
    } catch (error) {
        showSystemMessage(`Не удалось загрузить список чатов: ${error.message}`);
    }
}

function renderChatList() {
    elements.chatList.innerHTML = "";

    if (!state.chats.length) {
        const empty = document.createElement("div");
        empty.className = "chat-list-empty";
        empty.textContent = "Чатов пока нет";
        elements.chatList.appendChild(empty);
        return;
    }

    for (const chat of state.chats) {
        const item = document.createElement("button");
        item.className = "chat-list-item";
        if (chat.chat_id === state.currentChatId) {
            item.classList.add("active");
        }

        item.innerHTML = `
            <div class="chat-list-item-title">${escapeHtml(chat.title)}</div>
            <div class="chat-list-item-date">${formatDate(chat.updated_at)}</div>
        `;

        item.addEventListener("click", () => openChat(chat.chat_id));
        elements.chatList.appendChild(item);
    }
}

async function createNewChat() {
    try {
        const data = await apiRequest("/api/chats", {
            method: "POST",
            body: JSON.stringify({}),
        });

        await loadChats();
        await openChat(data.chat_id);
    } catch (error) {
        showSystemMessage(`Не удалось создать чат: ${error.message}`);
    }
}

async function openChat(chatId) {
    try {
        stopActiveChatEvents();
        const data = await apiRequest(`/api/chats/${chatId}`);
        state.currentChatId = data.chat_id;

        elements.chatTitle.textContent = data.title || "Чат";
        elements.chatSubtitle.textContent = `Создан: ${formatDate(data.created_at)}`;

        elements.messageInput.disabled = false;
        elements.sendBtn.disabled = false;
        elements.resetContextBtn.disabled = false;

        renderChatList();
        renderMessages(data.messages || [], data.document_ready, data.document_url, data.version);
    } catch (error) {
        showSystemMessage(`Не удалось открыть чат: ${error.message}`);
    }
}

function renderMessages(messages, documentReady = false, documentUrl = null, version = null) {
    elements.messagesContainer.innerHTML = "";

    if (!messages.length) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.textContent = "В этом чате пока нет сообщений.";
        elements.messagesContainer.appendChild(empty);
    } else {
        for (const message of messages) {
            if (message.role === "processing") {
                appendProcessingMessage(message.content);
            } else {
                appendMessage(message.role, message.content);
            }
        }
    }

    if (documentReady && documentUrl) {
        appendDocumentCard(documentUrl, version);
    }

    scrollMessagesToBottom();
}

function appendMessage(role, content) {
    const wrapper = document.createElement("div");
    wrapper.className = `message ${role === "user" ? "message-user" : "message-agent"}`;

    const roleLabel = document.createElement("div");
    roleLabel.className = "message-role";
    roleLabel.textContent = role === "user" ? "Вы" : "Агент";

    const body = document.createElement("div");
    body.className = "message-body";
    body.textContent = content;

    wrapper.appendChild(roleLabel);
    wrapper.appendChild(body);
    elements.messagesContainer.appendChild(wrapper);
}

function appendProcessingMessage(content, isPlaceholder = false) {
    const wrapper = document.createElement("div");
    wrapper.className = "processing-block";
    if (isPlaceholder) {
        wrapper.classList.add("processing-block-pending");
    }

    const title = document.createElement("div");
    title.className = "processing-title";
    title.textContent = "Думает";

    const body = document.createElement("div");
    body.className = "processing-body";

    const steps = String(content || "")
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean);

    if (!steps.length) {
        const line = document.createElement("div");
        line.className = "processing-step";
        line.textContent = "Анализирую запрос...";
        body.appendChild(line);
    } else {
        for (const step of steps) {
            const line = document.createElement("div");
            line.className = "processing-step";
            line.textContent = step;
            body.appendChild(line);
        }
    }

    wrapper.appendChild(title);
    wrapper.appendChild(body);
    elements.messagesContainer.appendChild(wrapper);
    return wrapper;
}

function appendDocumentCard(documentUrl, version = null) {
    const card = document.createElement("div");
    card.className = "document-card";

    const title = document.createElement("div");
    title.className = "document-card-title";
    title.textContent = version ? `PDF документ (версия ${version})` : "PDF документ";

    const link = document.createElement("a");
    link.className = "document-card-link";
    link.href = documentUrl;
    link.textContent = "Скачать PDF";
    link.setAttribute("download", "");

    card.appendChild(title);
    card.appendChild(link);

    elements.messagesContainer.appendChild(card);
}

async function fetchChatSnapshot(chatId) {
    return await apiRequest(`/api/chats/${chatId}`);
}

function updateProcessingMessageElement(wrapper, content, isPending = false) {
    if (!wrapper) {
        return;
    }

    wrapper.classList.toggle("processing-block-pending", Boolean(isPending));
    const body = wrapper.querySelector(".processing-body");
    if (!body) {
        return;
    }

    body.innerHTML = "";

    const steps = String(content || "")
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean);

    const normalizedSteps = steps.length ? steps : ["Анализирую запрос..."];
    for (const step of normalizedSteps) {
        const line = document.createElement("div");
        line.className = "processing-step";
        line.textContent = step;
        body.appendChild(line);
    }
}

function stopActiveChatEvents() {
    if (activeChatEventSource) {
        activeChatEventSource.close();
        activeChatEventSource = null;
    }
}

function startChatEventStream(chatId, processingElement) {
    stopActiveChatEvents();

    const eventSource = new EventSource(`/api/chats/${chatId}/events`);

    eventSource.addEventListener("processing", (event) => {
        if (state.currentChatId !== chatId) {
            return;
        }

        try {
            const payload = JSON.parse(event.data);
            updateProcessingMessageElement(processingElement, payload.content || "", true);
            scrollMessagesToBottom();
        } catch (_) {}
    });

    eventSource.addEventListener("reset", () => {
        if (state.currentChatId !== chatId) {
            return;
        }
        stopActiveChatEvents();
    });

    eventSource.onerror = () => {
        if (activeChatEventSource === eventSource) {
            eventSource.close();
            activeChatEventSource = null;
        }
    };

    activeChatEventSource = eventSource;
    return eventSource;
}

async function sendMessage() {
    const message = elements.messageInput.value.trim();

    if (!state.currentChatId) {
        alert("Сначала создайте или выберите чат.");
        return;
    }

    if (!message) {
        return;
    }

    elements.sendBtn.disabled = true;
    elements.messageInput.disabled = true;

    appendMessage("user", message);
    const thinkingPlaceholder = appendProcessingMessage("Анализирую запрос...", true);
    scrollMessagesToBottom();

    elements.messageInput.value = "";

    try {
        const activeChatId = state.currentChatId;
        startChatEventStream(activeChatId, thinkingPlaceholder);

        await apiRequest(`/api/chats/${activeChatId}/messages`, {
            method: "POST",
            body: JSON.stringify({ message }),
        });

        stopActiveChatEvents();

        if (thinkingPlaceholder.isConnected) {
            thinkingPlaceholder.remove();
        }

        await openChat(activeChatId);
        await loadChats();
    } catch (error) {
        stopActiveChatEvents();
        if (thinkingPlaceholder.isConnected) {
            thinkingPlaceholder.remove();
        }
        appendMessage("agent", `Ошибка: ${error.message}`);
    } finally {
        elements.sendBtn.disabled = false;
        elements.messageInput.disabled = false;
        elements.messageInput.focus();
    }
}

async function resetContext() {
    if (!state.currentChatId) {
        return;
    }

    try {
        const data = await apiRequest(`/api/chats/${state.currentChatId}/reset`, {
            method: "POST",
            body: JSON.stringify({}),
        });

        await openChat(state.currentChatId);
    } catch (error) {
        appendMessage("agent", `Ошибка при сбросе контекста: ${error.message}`);
    }
}

function showSystemMessage(text) {
    elements.messagesContainer.innerHTML = "";
    const box = document.createElement("div");
    box.className = "empty-state";
    box.textContent = text;
    elements.messagesContainer.appendChild(box);
}

function scrollMessagesToBottom() {
    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
}

function formatDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("ru-RU");
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

elements.newChatBtn.addEventListener("click", createNewChat);
elements.sendBtn.addEventListener("click", sendMessage);
elements.resetContextBtn.addEventListener("click", resetContext);

elements.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
});

window.addEventListener("load", async () => {
    await loadChats();
});
