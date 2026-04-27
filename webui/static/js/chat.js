const STORAGE_KEYS = {
    userId: "agent_doc_system.user_id",
    username: "agent_doc_system.username",
    theme: "agent_doc_system.theme",
};

const state = {
    userId: null,
    username: "",
    currentChatId: null,
    chats: [],
    theme: "dark",
};

let activeChatEventSource = null;

const elements = {
    body: document.body,
    loginOverlay: document.getElementById("login-overlay"),
    loginForm: document.getElementById("login-form"),
    loginInput: document.getElementById("login-input"),
    loginSubmitBtn: document.getElementById("login-submit-btn"),
    loginError: document.getElementById("login-error"),
    userName: document.getElementById("user-name"),
    logoutBtn: document.getElementById("logout-btn"),
    themeToggleBtn: document.getElementById("theme-toggle-btn"),
    chatList: document.getElementById("chat-list"),
    newChatBtn: document.getElementById("new-chat-btn"),
    resetContextBtn: document.getElementById("reset-context-btn"),
    messagesContainer: document.getElementById("messages-container"),
    messageInput: document.getElementById("message-input"),
    sendBtn: document.getElementById("send-btn"),
    chatTitle: document.getElementById("chat-title"),
    chatSubtitle: document.getElementById("chat-subtitle"),
};

function isLoggedIn() {
    return Boolean(state.userId);
}

function getUserApiBase() {
    if (!state.userId) {
        throw new Error("Пользователь не авторизован.");
    }
    return `/api/users/${encodeURIComponent(state.userId)}`;
}

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

function applyTheme(theme, persist = true) {
    const normalized = theme === "light" ? "light" : "dark";
    state.theme = normalized;
    elements.body.dataset.theme = normalized;

    if (persist) {
        localStorage.setItem(STORAGE_KEYS.theme, normalized);
    }
}

function toggleTheme() {
    applyTheme(state.theme === "dark" ? "light" : "dark");
}

function setLoginError(message = "") {
    const normalized = String(message || "").trim();
    elements.loginError.hidden = !normalized;
    elements.loginError.textContent = normalized;
}

function showLoginOverlay() {
    elements.loginOverlay.classList.remove("login-overlay-hidden");
    elements.loginInput.focus();
}

function hideLoginOverlay() {
    elements.loginOverlay.classList.add("login-overlay-hidden");
}

function setUser(user) {
    state.userId = user?.user_id || null;
    state.username = user?.username || "";

    if (state.userId) {
        localStorage.setItem(STORAGE_KEYS.userId, state.userId);
        localStorage.setItem(STORAGE_KEYS.username, state.username);
    }

    elements.userName.textContent = state.username || "Не авторизован";
}

function clearUser() {
    state.userId = null;
    state.username = "";
    state.currentChatId = null;
    state.chats = [];

    localStorage.removeItem(STORAGE_KEYS.userId);
    localStorage.removeItem(STORAGE_KEYS.username);

    elements.userName.textContent = "Не авторизован";
}

function setChatControlsEnabled(enabled) {
    elements.newChatBtn.disabled = !enabled;
    elements.messageInput.disabled = !enabled || !state.currentChatId;
    elements.sendBtn.disabled = !enabled || !state.currentChatId;
    elements.resetContextBtn.disabled = !enabled || !state.currentChatId;
    elements.logoutBtn.disabled = !enabled;
}

function resetWorkspaceView() {
    stopActiveChatEvents();
    elements.chatList.innerHTML = "";
    elements.chatTitle.textContent = "Чат не выбран";
    elements.chatSubtitle.textContent = "Войдите и создайте новый чат, чтобы начать работу";
    elements.messageInput.value = "";
    elements.messageInput.disabled = true;
    elements.sendBtn.disabled = true;
    elements.resetContextBtn.disabled = true;

    elements.messagesContainer.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-title">Здесь появится переписка с агентом</div>
            <div class="empty-state-text">
                После входа вы сможете открыть свои прошлые чаты или создать новый и продолжить работу над документом.
            </div>
        </div>
    `;
}

async function login(username) {
    const normalized = String(username || "").trim();
    if (!normalized) {
        setLoginError("Введите логин пользователя.");
        return;
    }

    setLoginError("");
    elements.loginSubmitBtn.disabled = true;

    try {
        const user = await apiRequest("/api/session/login", {
            method: "POST",
            body: JSON.stringify({ username: normalized }),
        });

        setUser(user);
        hideLoginOverlay();
        setChatControlsEnabled(true);
        await loadChats();
    } catch (error) {
        setLoginError(error.message);
    } finally {
        elements.loginSubmitBtn.disabled = false;
    }
}

async function restoreLogin() {
    const savedTheme = localStorage.getItem(STORAGE_KEYS.theme);
    applyTheme(savedTheme || "dark", false);

    const savedUserId = localStorage.getItem(STORAGE_KEYS.userId);
    const savedUsername = localStorage.getItem(STORAGE_KEYS.username);

    if (!savedUserId) {
        clearUser();
        resetWorkspaceView();
        showLoginOverlay();
        return;
    }

    try {
        const user = await apiRequest(`/api/users/${encodeURIComponent(savedUserId)}`);
        setUser(user);
        if (!state.username && savedUsername) {
            state.username = savedUsername;
            elements.userName.textContent = savedUsername;
        }
        hideLoginOverlay();
        setChatControlsEnabled(true);
        await loadChats();
    } catch (_) {
        clearUser();
        resetWorkspaceView();
        showLoginOverlay();
    }
}

async function loadChats(preferredChatId = null) {
    if (!isLoggedIn()) {
        resetWorkspaceView();
        showLoginOverlay();
        return;
    }

    try {
        const data = await apiRequest(`${getUserApiBase()}/chats`);
        state.chats = data.items || [];
        renderChatList();

        if (!state.chats.length) {
            state.currentChatId = null;
            elements.chatTitle.textContent = "Новый рабочий диалог";
            elements.chatSubtitle.textContent = "У вас пока нет чатов. Создайте новый, чтобы начать работу.";
            elements.messageInput.disabled = true;
            elements.sendBtn.disabled = true;
            elements.resetContextBtn.disabled = true;
            showSystemMessage(
                "У этого пользователя пока нет чатов. Нажмите «Новый чат», чтобы начать новую сессию."
            );
            return;
        }

        const desiredChatId =
            preferredChatId ||
            (state.chats.some((chat) => chat.chat_id === state.currentChatId) ? state.currentChatId : null) ||
            state.chats[0].chat_id;

        if (desiredChatId) {
            await openChat(desiredChatId);
        }
    } catch (error) {
        showSystemMessage(`Не удалось загрузить список чатов: ${error.message}`);
    }
}

function renderChatList() {
    elements.chatList.innerHTML = "";

    if (!state.chats.length) {
        const empty = document.createElement("div");
        empty.className = "chat-list-empty";
        empty.textContent = "У пользователя пока нет чатов";
        elements.chatList.appendChild(empty);
        return;
    }

    for (const chat of state.chats) {
        const item = document.createElement("div");
        item.className = "chat-list-item";
        if (chat.chat_id === state.currentChatId) {
            item.classList.add("active");
        }

        const mainButton = document.createElement("button");
        mainButton.className = "chat-list-main";
        mainButton.type = "button";
        mainButton.innerHTML = `
            <div class="chat-list-item-title">${escapeHtml(chat.title)}</div>
            <div class="chat-list-item-date">${formatDate(chat.updated_at)}</div>
        `;
        mainButton.addEventListener("click", () => openChat(chat.chat_id));

        const deleteButton = document.createElement("button");
        deleteButton.className = "chat-list-delete";
        deleteButton.type = "button";
        deleteButton.setAttribute("aria-label", "Удалить чат");
        deleteButton.textContent = "×";
        deleteButton.addEventListener("click", async (event) => {
            event.stopPropagation();
            await deleteChat(chat.chat_id);
        });

        item.appendChild(mainButton);
        item.appendChild(deleteButton);
        elements.chatList.appendChild(item);
    }
}

async function createNewChat() {
    if (!isLoggedIn()) {
        showLoginOverlay();
        return;
    }

    try {
        const data = await apiRequest(`${getUserApiBase()}/chats`, {
            method: "POST",
            body: JSON.stringify({}),
        });

        await loadChats(data.chat_id);
    } catch (error) {
        showSystemMessage(`Не удалось создать чат: ${error.message}`);
    }
}

async function deleteChat(chatId) {
    if (!isLoggedIn()) {
        return;
    }

    const confirmed = window.confirm("Удалить этот чат и его сохраненный контекст?");
    if (!confirmed) {
        return;
    }

    try {
        await apiRequest(`${getUserApiBase()}/chats/${encodeURIComponent(chatId)}`, {
            method: "DELETE",
        });

        if (state.currentChatId === chatId) {
            state.currentChatId = null;
            resetWorkspaceView();
        }

        await loadChats();
    } catch (error) {
        showSystemMessage(`Не удалось удалить чат: ${error.message}`);
    }
}

async function openChat(chatId) {
    if (!isLoggedIn()) {
        showLoginOverlay();
        return;
    }

    try {
        stopActiveChatEvents();
        const data = await apiRequest(`${getUserApiBase()}/chats/${encodeURIComponent(chatId)}`);
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
        empty.innerHTML = `
            <div class="empty-state-title">В этом чате пока нет сообщений</div>
            <div class="empty-state-text">
                Опишите, какой документ нужно подготовить, исправить или дополнить данными из источников.
            </div>
        `;
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

function getRoleLabel(role) {
    if (role === "user") return "Вы";
    if (role === "system") return "Система";
    return "Агент";
}

function appendMessage(role, content) {
    const wrapper = document.createElement("div");
    wrapper.className = `message ${role === "user" ? "message-user" : "message-agent"}`;

    const roleLabel = document.createElement("div");
    roleLabel.className = "message-role";
    roleLabel.textContent = getRoleLabel(role);

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
    title.textContent = "Ход работы системы";

    const body = document.createElement("div");
    body.className = "processing-body";

    const steps = String(content || "")
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean);

    const normalizedSteps = steps.length ? steps : ["Анализирую запрос и подготавливаю следующий шаг..."];

    for (const step of normalizedSteps) {
        const line = document.createElement("div");
        line.className = "processing-step";
        line.textContent = step;
        body.appendChild(line);
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

    const normalizedSteps = steps.length ? steps : ["Анализирую запрос и подготавливаю следующий шаг..."];
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

    const eventSource = new EventSource(
        `${getUserApiBase()}/chats/${encodeURIComponent(chatId)}/events`
    );

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
        window.alert("Сначала создайте или выберите чат.");
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

        await apiRequest(`${getUserApiBase()}/chats/${encodeURIComponent(activeChatId)}/messages`, {
            method: "POST",
            body: JSON.stringify({ message }),
        });

        stopActiveChatEvents();

        if (thinkingPlaceholder.isConnected) {
            thinkingPlaceholder.remove();
        }

        await loadChats(activeChatId);
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
        await apiRequest(`${getUserApiBase()}/chats/${encodeURIComponent(state.currentChatId)}/reset`, {
            method: "POST",
            body: JSON.stringify({}),
        });

        await openChat(state.currentChatId);
    } catch (error) {
        appendMessage("agent", `Ошибка при сбросе контекста: ${error.message}`);
    }
}

function logout() {
    clearUser();
    stopActiveChatEvents();
    resetWorkspaceView();
    setChatControlsEnabled(false);
    showLoginOverlay();
}

function showSystemMessage(text) {
    elements.messagesContainer.innerHTML = "";
    const box = document.createElement("div");
    box.className = "empty-state";
    box.innerHTML = `
        <div class="empty-state-title">Системное сообщение</div>
        <div class="empty-state-text">${escapeHtml(text)}</div>
    `;
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

elements.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await login(elements.loginInput.value);
});

elements.themeToggleBtn.addEventListener("click", toggleTheme);
elements.newChatBtn.addEventListener("click", createNewChat);
elements.sendBtn.addEventListener("click", sendMessage);
elements.resetContextBtn.addEventListener("click", resetContext);
elements.logoutBtn.addEventListener("click", logout);

elements.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
});

window.addEventListener("load", async () => {
    setChatControlsEnabled(false);
    await restoreLogin();
});
