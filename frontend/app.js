const appShell = document.getElementById("app-shell");
const menuToggle = document.getElementById("menu-toggle");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");
const settingsToggle = document.getElementById("settings-toggle");
const settingsMenu = document.getElementById("settings-menu");
const themeToggle = document.getElementById("theme-toggle");
const toolTogglesList = document.getElementById("tool-toggles-list");
const profileToggle = document.getElementById("profile-toggle");
const profileEmailNav = document.getElementById("profile-email-nav");
const connectionToggle = document.getElementById("connection-toggle");
const connectionLabel = document.getElementById("connection-label");
const newConversationButton = document.getElementById("new-conversation");
const calendarToggle = document.getElementById("calendar-toggle");
const acceptedActionsToggle = document.getElementById("accepted-actions-toggle");
const conversationHistoryToggle = document.getElementById("conversation-history-toggle");
const workspace = document.getElementById("workspace");
const homeView = document.getElementById("home-view");
const calendarView = document.getElementById("calendar-view");
const calendarGrid = document.getElementById("calendar-grid");
const calendarMonth = document.getElementById("calendar-month");
const calendarSelectedDate = document.getElementById("calendar-selected-date");
const calendarPrevious = document.getElementById("calendar-previous");
const calendarNext = document.getElementById("calendar-next");
const calendarToday = document.getElementById("calendar-today");
const calendarUseDate = document.getElementById("calendar-use-date");
const authView = document.getElementById("auth-view");
const authTitle = document.getElementById("auth-title");
const authDescription = document.getElementById("auth-description");
const authForm = document.getElementById("auth-form");
const authEmail = document.getElementById("auth-email");
const authPassword = document.getElementById("auth-password");
const authSubmit = document.getElementById("auth-submit");
const authError = document.getElementById("auth-error");
const authModeToggle = document.getElementById("auth-mode-toggle");
const profileView = document.getElementById("profile-view");
const profileEmail = document.getElementById("profile-email");
const profileCreatedAt = document.getElementById("profile-created-at");
const acceptedActionsView = document.getElementById("accepted-actions-view");
const acceptedActionsList = document.getElementById("accepted-actions-list");
const refreshActions = document.getElementById("refresh-actions");
const conversationHistoryView = document.getElementById("conversation-history-view");
const conversationHistoryList = document.getElementById("conversation-history-list");
const refreshConversations = document.getElementById("refresh-conversations");
const conversationView = document.getElementById("conversation-view");
const conversationLog = document.getElementById("conversation-log");
const form = document.getElementById("chat-form");
const messageInput = document.getElementById("message");
const sendButton = document.getElementById("send-button");
const requestStatus = document.getElementById("request-status");

const THEME_STORAGE_KEY = "le-bras-theme";
const CURRENT_PLAN_STORAGE_KEY = "le-bras-current-plan";
const today = new Date();
today.setHours(0, 0, 0, 0);
let currentCalendarMonth = new Date(today.getFullYear(), today.getMonth(), 1);
let selectedCalendarDate = new Date(today);
let currentUser = null;
let authMode = "login";

const monthFormatter = new Intl.DateTimeFormat("fr-FR", {
    month: "long",
    year: "numeric",
});
const fullDateFormatter = new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
});

const ACTION_TITLES = {
    create_issue: "Créer une tâche",
    send_message: "Envoyer un message",
    write_record: "Enregistrer une information",
    generate_document: "Générer un document",
    create_calendar_event: "Créer un événement",
    list_pending_actions: "Consulter les actions en attente",
    undo_last_action: "Annuler une action",
};

const FIELD_LABELS = {
    title: "Titre",
    description: "Description",
    assignee: "Assignée à",
    due_date: "Échéance",
    channel: "Canal",
    recipient: "Destinataire",
    content: "Message",
    record_type: "Type",
    subject: "Sujet",
    payload: "Informations",
    filename: "Fichier",
    start: "Début",
    duration_min: "Durée",
    attendees: "Participants",
    plan_id: "Plan",
    action_id: "Action",
};

function setSidebar(isOpen) {
    appShell.classList.toggle("sidebar-open", isOpen);
    menuToggle.setAttribute("aria-expanded", String(isOpen));
    menuToggle.setAttribute("aria-label", isOpen ? "Fermer le menu" : "Ouvrir le menu");
    menuToggle.title = isOpen ? "Fermer le menu" : "Ouvrir le menu";

    if (!isOpen) {
        setSettingsOpen(false);
    }
}

function toggleSidebar() {
    setSidebar(!appShell.classList.contains("sidebar-open"));
}

function setSettingsOpen(isOpen, restoreFocus = false) {
    settingsMenu.hidden = !isOpen;
    settingsToggle.setAttribute("aria-expanded", String(isOpen));

    if (!isOpen && restoreFocus) {
        settingsToggle.focus();
    }
}

function setTheme(theme) {
    const selectedTheme = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = selectedTheme;
    themeToggle.checked = selectedTheme === "dark";

    try {
        localStorage.setItem(THEME_STORAGE_KEY, selectedTheme);
    } catch (error) {
        console.warn("La préférence de thème ne peut pas être sauvegardée.", error);
    }
}

function initializeTheme() {
    let savedTheme = "light";
    try {
        savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || "light";
    } catch (error) {
        console.warn("La préférence de thème ne peut pas être lue.", error);
    }
    setTheme(savedTheme);
}

function dateKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

function isSameDate(firstDate, secondDate) {
    return dateKey(firstDate) === dateKey(secondDate);
}

function setActiveNavigation(activeButton) {
    [
        profileToggle,
        connectionToggle,
        newConversationButton,
        calendarToggle,
        acceptedActionsToggle,
        conversationHistoryToggle,
    ].forEach((button) => {
        const isActive = button === activeButton;
        button.classList.toggle("active", isActive);
        if (isActive) {
            button.setAttribute("aria-current", "page");
        } else {
            button.removeAttribute("aria-current");
        }
    });
}

function hideWorkspaceViews() {
    [
        homeView,
        calendarView,
        authView,
        profileView,
        acceptedActionsView,
        conversationHistoryView,
        conversationView,
    ].forEach((view) => {
        view.hidden = true;
    });
}

function showManagementView(view, activeButton) {
    workspace.classList.remove("is-conversation", "is-calendar");
    hideWorkspaceViews();
    view.hidden = false;
    form.hidden = true;
    setActiveNavigation(activeButton);

    if (window.matchMedia("(max-width: 760px)").matches) {
        setSidebar(false);
    }
}

function renderCalendar() {
    const year = currentCalendarMonth.getFullYear();
    const month = currentCalendarMonth.getMonth();
    const firstDay = new Date(year, month, 1);
    const mondayOffset = (firstDay.getDay() + 6) % 7;
    const gridStart = new Date(year, month, 1 - mondayOffset);

    calendarMonth.textContent = monthFormatter.format(currentCalendarMonth);
    calendarSelectedDate.textContent = fullDateFormatter.format(selectedCalendarDate);
    calendarGrid.replaceChildren();

    for (let index = 0; index < 42; index += 1) {
        const date = new Date(gridStart);
        date.setDate(gridStart.getDate() + index);

        const button = document.createElement("button");
        button.type = "button";
        button.className = "calendar-day";
        button.textContent = String(date.getDate());
        button.dataset.date = dateKey(date);
        button.setAttribute("role", "gridcell");
        button.setAttribute("aria-label", fullDateFormatter.format(date));

        if (date.getMonth() !== month) {
            button.classList.add("outside-month");
        }
        if (isSameDate(date, today)) {
            button.classList.add("today");
        }
        if (isSameDate(date, selectedCalendarDate)) {
            button.classList.add("selected");
            button.setAttribute("aria-selected", "true");
        } else {
            button.setAttribute("aria-selected", "false");
        }

        button.addEventListener("click", () => {
            selectedCalendarDate = new Date(date);
            if (date.getMonth() !== currentCalendarMonth.getMonth()
                || date.getFullYear() !== currentCalendarMonth.getFullYear()) {
                currentCalendarMonth = new Date(date.getFullYear(), date.getMonth(), 1);
            }
            renderCalendar();
        });

        calendarGrid.appendChild(button);
    }
}

function showCalendar() {
    workspace.classList.remove("is-conversation");
    workspace.classList.add("is-calendar");
    hideWorkspaceViews();
    calendarView.hidden = false;
    form.hidden = true;
    setActiveNavigation(calendarToggle);
    renderCalendar();

    if (window.matchMedia("(max-width: 760px)").matches) {
        setSidebar(false);
    }
}

function formatJson(value) {
    if (value === undefined) {
        return "Non disponible";
    }
    try {
        return JSON.stringify(value, null, 2);
    } catch (error) {
        return String(value);
    }
}

function formatDateTime(value) {
    if (!value) {
        return "Date inconnue";
    }
    return new Intl.DateTimeFormat("fr-FR", {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date(value));
}

function escapeHtml(text) {
    const element = document.createElement("div");
    element.textContent = String(text ?? "");
    return element.innerHTML;
}

function renderInline(text) {
    return escapeHtml(text)
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function isTableRow(line) {
    return /^\|.*\|$/.test(line);
}

function isTableSeparator(line) {
    return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/.test(line);
}

function renderTableRow(line, cellTag) {
    const cells = line.replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
    return `<tr>${cells.map((cell) => `<${cellTag}>${renderInline(cell)}</${cellTag}>`).join("")}</tr>`;
}

function renderMarkdown(text) {
    const lines = String(text ?? "").split("\n");
    let html = "";
    let listType = null;
    let tableLines = [];

    const closeList = () => {
        if (listType) {
            html += `</${listType}>`;
            listType = null;
        }
    };
    const flushTable = () => {
        if (tableLines.length === 0) {
            return;
        }
        const rows = tableLines.filter((line) => !isTableSeparator(line));
        html += "<table>";
        rows.forEach((row, index) => {
            html += renderTableRow(row, index === 0 ? "th" : "td");
        });
        html += "</table>";
        tableLines = [];
    };

    lines.forEach((rawLine) => {
        const line = rawLine.trim();
        if (isTableRow(line)) {
            closeList();
            tableLines.push(line);
            return;
        }
        flushTable();

        const numbered = line.match(/^(\d+)\.\s+(.*)$/);
        const bulleted = line.match(/^[-*]\s+(.*)$/);
        if (numbered || bulleted) {
            const nextListType = numbered ? "ol" : "ul";
            if (listType !== nextListType) {
                closeList();
                html += `<${nextListType}>`;
                listType = nextListType;
            }
            html += `<li>${renderInline((numbered || bulleted)[2] || bulleted[1])}</li>`;
            return;
        }

        closeList();
        html += line ? `<p>${renderInline(line)}</p>` : "<br>";
    });
    closeList();
    flushTable();
    return html;
}

function formatUsefulValue(value, fieldName) {
    if (fieldName === "duration_min") {
        return `${value} min`;
    }
    if (Array.isArray(value)) {
        return value.join(", ") || "Aucun";
    }
    if (value && typeof value === "object") {
        return Object.entries(value)
            .map(([key, item]) => `${key}: ${String(item)}`)
            .join(" · ");
    }
    return String(value ?? "Non disponible");
}

function normalizeStatus(step) {
    if (step.status === "pending") {
        return "pending";
    }
    if (step.status === "rejected") {
        return "rejected";
    }
    if (step.status === "executed" || step.status === "success") {
        return "success";
    }
    return step.ok ? "success" : "error";
}

function statusLabel(status) {
    return {
        pending: "En attente de validation",
        success: "Exécutée",
        executed: "Exécutée",
        rejected: "Refusée",
        error: "Erreur",
    }[status] || "Erreur";
}

function scrollConversationToBottom() {
    requestAnimationFrame(() => {
        conversationLog.scrollTo({top: conversationLog.scrollHeight, behavior: "smooth"});
    });
}

function resizeMessageInput() {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 130)}px`;
}

function showConversation() {
    workspace.classList.remove("is-calendar");
    workspace.classList.add("is-conversation");
    hideWorkspaceViews();
    conversationView.hidden = false;
    form.hidden = false;
    setActiveNavigation(newConversationButton);
    messageInput.placeholder = "Votre prochaine demande...";
}

function resetConversation() {
    localStorage.removeItem(CURRENT_PLAN_STORAGE_KEY);
    conversationLog.replaceChildren();
    workspace.classList.remove("is-conversation", "is-calendar");
    hideWorkspaceViews();
    homeView.hidden = false;
    form.hidden = false;
    setActiveNavigation(newConversationButton);
    messageInput.value = "";
    messageInput.placeholder = "exemple: Prépare l'arrivée du stagiaire";
    resizeMessageInput();
    requestStatus.textContent = "Nouvelle conversation";
    messageInput.focus();

    if (window.matchMedia("(max-width: 760px)").matches) {
        setSidebar(false);
    }
}

function renderUserMessage(message) {
    const row = document.createElement("div");
    row.className = "message-row user";

    const bubble = document.createElement("article");
    bubble.className = "message-bubble user-bubble";
    bubble.textContent = message;
    bubble.setAttribute("aria-label", "Votre demande");

    row.appendChild(bubble);
    conversationLog.appendChild(row);
}

function renderAgentMessage() {
    const row = document.createElement("div");
    row.className = "message-row agent";

    const bubble = document.createElement("article");
    bubble.className = "message-bubble agent-bubble thinking";
    bubble.setAttribute("aria-label", "Réponse de LE BRAS");

    const heading = document.createElement("div");
    heading.className = "agent-heading";

    const icon = document.createElement("span");
    icon.className = "agent-icon";
    icon.setAttribute("aria-hidden", "true");
    const iconSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const iconUse = document.createElementNS("http://www.w3.org/2000/svg", "use");
    iconUse.setAttribute("href", "#icon-spark");
    iconSvg.appendChild(iconUse);
    icon.appendChild(iconSvg);

    const title = document.createElement("span");
    title.textContent = "LE BRAS";
    heading.append(icon, title);

    const response = document.createElement("p");
    response.className = "agent-response thinking-dots";
    response.textContent = "L'agent réfléchit";

    bubble.append(heading, response);
    row.appendChild(bubble);
    conversationLog.appendChild(row);
    scrollConversationToBottom();

    return {bubble, response};
}

function appendTechnicalValue(container, label, value) {
    const labelElement = document.createElement("strong");
    labelElement.textContent = label;
    container.appendChild(labelElement);

    const valueElement = document.createElement("pre");
    valueElement.textContent = formatJson(value);
    container.appendChild(valueElement);
    return valueElement;
}

function renderMetrics(metrics) {
    const element = document.createElement("p");
    element.className = "request-metrics";

    if (!metrics) {
        element.textContent = "Métriques indisponibles.";
        return element;
    }

    element.textContent = [
        `Tokens : ${metrics.input_tokens} entrée / ${metrics.output_tokens} sortie`,
        `total ${metrics.total_tokens}`,
        `latence globale ${metrics.latency_ms} ms`,
        "coût non configuré",
    ].join(" | ");
    return element;
}

function renderTrace(trace, metrics) {
    const details = document.createElement("details");
    details.className = "technical-trace";

    const summary = document.createElement("summary");
    summary.textContent = "Voir la trace technique";
    details.append(summary, renderMetrics(metrics));

    const list = document.createElement("div");
    list.className = "trace-list";
    const stepViews = [];

    if (!Array.isArray(trace) || trace.length === 0) {
        const empty = document.createElement("p");
        empty.className = "request-metrics";
        empty.textContent = "Aucun outil utilisé.";
        list.appendChild(empty);
    } else {
        trace.forEach((step, index) => {
            const item = document.createElement("div");
            item.className = "trace-step";

            const title = document.createElement("p");
            title.className = "trace-step-title";
            const toolName = document.createElement("strong");
            toolName.textContent = `${index + 1}. ${step.tool}`;
            const status = document.createElement("span");
            status.textContent = ` : ${step.status || (step.ok ? "success" : "error")}`;
            title.append(toolName, status, ` (${step.latency_ms} ms)`);
            item.appendChild(title);

            appendTechnicalValue(item, "Arguments", step.input);
            const output = appendTechnicalValue(
                item,
                step.ok ? "Résultat" : "Erreur",
                step.ok ? step.output : step.error,
            );
            list.appendChild(item);
            stepViews.push({item, status, output});
        });
    }

    details.appendChild(list);
    return {element: details, stepViews};
}

function renderActionDetails(toolInput) {
    const list = document.createElement("dl");
    list.className = "action-details";

    Object.entries(toolInput || {}).forEach(([fieldName, value]) => {
        const row = document.createElement("div");
        row.className = "action-detail";

        const term = document.createElement("dt");
        term.textContent = FIELD_LABELS[fieldName] || fieldName;
        const description = document.createElement("dd");
        description.textContent = formatUsefulValue(value, fieldName);
        row.append(term, description);
        list.appendChild(row);
    });

    return list;
}

function readableResult(result) {
    if (result === undefined || result === null) {
        return "Action terminée.";
    }
    if (typeof result !== "object") {
        return String(result);
    }
    return Object.entries(result)
        .map(([key, value]) => `${FIELD_LABELS[key] || key}: ${formatUsefulValue(value, key)}`)
        .join(" · ");
}

async function submitActionDecision(actionId, decision, view) {
    if (view.inFlight || view.settled) {
        return;
    }

    view.inFlight = true;
    view.approveButton.disabled = true;
    view.rejectButton.disabled = true;
    view.errorElement.textContent = "";

    try {
        const response = await fetch(`/actions/${actionId}/${decision}`, {method: "POST"});
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Erreur du serveur");
        }

        view.settled = true;
        view.resultElement.hidden = false;

        if (decision === "approve") {
            view.card.className = "action-card success";
            view.statusElement.textContent = "Exécutée";
            view.resultElement.textContent = readableResult(data.result);
            view.technicalView.status.textContent = " : executed";
            view.technicalView.output.textContent = formatJson(data.result);
            requestStatus.textContent = `Action ${actionId} exécutée`;
        } else {
            view.card.className = "action-card rejected";
            view.statusElement.textContent = "Refusée";
            view.resultElement.textContent = "Action refusée";
            view.technicalView.status.textContent = " : rejected";
            view.technicalView.output.textContent = "Action refusée";
            requestStatus.textContent = `Action ${actionId} refusée`;
        }
    } catch (error) {
        view.errorElement.textContent = `Erreur : ${error.message}`;
        view.approveButton.disabled = false;
        view.rejectButton.disabled = false;
        requestStatus.textContent = `Erreur sur l'action ${actionId}`;
    } finally {
        view.inFlight = false;
    }
}

function renderActions(trace, technicalViews) {
    const section = document.createElement("section");
    section.className = "actions-section";
    section.setAttribute("aria-label", "Actions proposées par LE BRAS");

    trace.forEach((step, index) => {
        const status = normalizeStatus(step);
        const card = document.createElement("article");
        card.className = `action-card ${status}`;

        const header = document.createElement("header");
        header.className = "action-card-header";

        const headingGroup = document.createElement("div");
        const title = document.createElement("h3");
        title.textContent = ACTION_TITLES[step.tool] || "Action opérationnelle";
        const toolName = document.createElement("code");
        toolName.className = "tool-name";
        toolName.textContent = step.tool;
        headingGroup.append(title, toolName);

        const statusElement = document.createElement("span");
        statusElement.className = "status-badge";
        statusElement.textContent = statusLabel(status);
        header.append(headingGroup, statusElement);
        card.append(header, renderActionDetails(step.input));

        const resultElement = document.createElement("p");
        resultElement.className = "action-result";
        resultElement.hidden = status === "pending";
        if (status === "error") {
            resultElement.textContent = step.error || "L'action a échoué.";
        } else if (status === "rejected") {
            resultElement.textContent = "Action refusée";
        } else if (status === "success") {
            resultElement.textContent = readableResult(step.output);
        }
        card.appendChild(resultElement);

        const actionId = step.action_id || (step.output && step.output.action_id);
        if (status === "pending" && actionId) {
            const controls = document.createElement("div");
            controls.className = "action-controls";

            const approveButton = document.createElement("button");
            approveButton.type = "button";
            approveButton.className = "approve-action";
            approveButton.textContent = "Approuver";

            const rejectButton = document.createElement("button");
            rejectButton.type = "button";
            rejectButton.className = "reject-action";
            rejectButton.textContent = "Refuser";

            const errorElement = document.createElement("p");
            errorElement.className = "action-error";
            errorElement.setAttribute("role", "alert");

            const view = {
                card,
                statusElement,
                resultElement,
                approveButton,
                rejectButton,
                errorElement,
                technicalView: technicalViews[index],
                inFlight: false,
                settled: false,
            };

            approveButton.addEventListener("click", () => {
                submitActionDecision(actionId, "approve", view);
            });
            rejectButton.addEventListener("click", () => {
                submitActionDecision(actionId, "reject", view);
            });

            controls.append(approveButton, rejectButton);
            card.append(controls, errorElement);
        }

        section.appendChild(card);
    });

    return section;
}

function completeAgentMessage(agentView, data) {
    agentView.bubble.classList.remove("thinking");
    agentView.response.classList.remove("thinking-dots");
    agentView.response.innerHTML = renderMarkdown(data.response || "Aucune réponse reçue.");

    const trace = Array.isArray(data.trace) ? data.trace : [];
    const technicalTrace = renderTrace(trace, data.metrics);
    if (trace.length > 0) {
        agentView.bubble.appendChild(renderActions(trace, technicalTrace.stepViews));
    }
    agentView.bubble.appendChild(technicalTrace.element);
    scrollConversationToBottom();
}

function restoredPlanToAgentData(plan) {
    return {
        response: plan.response,
        metrics: plan.metrics,
        trace: (plan.actions || []).map((action) => ({
            tool: action.tool,
            input: action.input,
            action_index: action.action_index,
            action_id: action.action_id,
            ok: action.status !== "error",
            status: action.status,
            output: action.output,
            error: action.error,
            latency_ms: 0,
        })),
    };
}

async function restoreCurrentPlan() {
    const planId = localStorage.getItem(CURRENT_PLAN_STORAGE_KEY);
    if (!planId) {
        return;
    }

    try {
        const response = await fetch(`/plans/${encodeURIComponent(planId)}`);
        const plan = await response.json();
        if (!response.ok) {
            throw new Error(plan.detail || "Plan introuvable");
        }

        conversationLog.replaceChildren();
        showConversation();
        renderUserMessage(plan.user_request);
        const agentView = renderAgentMessage();
        completeAgentMessage(agentView, restoredPlanToAgentData(plan));
        requestStatus.textContent = "Plan restauré";
    } catch (error) {
        localStorage.removeItem(CURRENT_PLAN_STORAGE_KEY);
        console.warn("Impossible de restaurer le plan.", error);
    }
}

function failAgentMessage(agentView, error) {
    agentView.bubble.classList.remove("thinking");
    agentView.bubble.classList.add("error");
    agentView.response.classList.remove("thinking-dots");
    agentView.response.textContent = `Erreur : ${error.message}`;
    scrollConversationToBottom();
}

function renderToolToggles(tools) {
    toolTogglesList.replaceChildren();
    if (!Array.isArray(tools) || tools.length === 0) {
        toolTogglesList.textContent = "Aucun outil déclaré.";
        return;
    }

    tools.forEach((tool) => {
        const row = document.createElement("div");
        row.className = "tool-toggle-row";
        const label = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = tool.enabled;
        const name = document.createElement("span");
        name.className = "tool-toggle-name";
        name.textContent = tool.name;
        const errorElement = document.createElement("span");
        errorElement.className = "tool-toggle-error";
        label.append(checkbox, name);
        row.append(label, errorElement);

        checkbox.addEventListener("change", async () => {
            const enabled = checkbox.checked;
            checkbox.disabled = true;
            errorElement.textContent = "";
            try {
                const response = await fetch(`/tools/${encodeURIComponent(tool.name)}/toggle`, {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({enabled}),
                });
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.detail || "Erreur du serveur");
                }
            } catch (error) {
                checkbox.checked = !enabled;
                errorElement.textContent = error.message;
            } finally {
                checkbox.disabled = false;
            }
        });

        toolTogglesList.appendChild(row);
    });
}

async function loadToolToggles() {
    try {
        const response = await fetch("/tools");
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Erreur du serveur");
        }
        renderToolToggles(data.tools);
    } catch (error) {
        toolTogglesList.textContent = `Erreur : ${error.message}`;
    }
}

function updateAuthInterface(user) {
    currentUser = user;
    const isConnected = Boolean(user);
    profileToggle.hidden = !isConnected;
    connectionLabel.textContent = isConnected ? "Déconnexion" : "Connexion";
    connectionToggle.title = isConnected ? "Déconnexion" : "Connexion";
    connectionToggle.setAttribute("aria-label", connectionToggle.title);

    if (isConnected) {
        profileEmailNav.textContent = user.email;
        profileEmail.textContent = user.email;
        profileCreatedAt.textContent = `Compte créé le ${formatDateTime(user.created_at)}`;
    } else {
        profileEmailNav.textContent = "";
        profileEmail.textContent = "";
        profileCreatedAt.textContent = "";
    }
}

function setAuthMode(mode) {
    authMode = mode === "register" ? "register" : "login";
    const isRegistration = authMode === "register";
    authTitle.textContent = isRegistration ? "Créer un compte" : "Connexion";
    authDescription.textContent = isRegistration
        ? "Créez un compte local pour conserver vos conversations et actions."
        : "Connectez-vous pour retrouver vos conversations et actions acceptées.";
    authSubmit.textContent = isRegistration ? "Créer mon compte" : "Se connecter";
    authModeToggle.textContent = isRegistration
        ? "J’ai déjà un compte"
        : "Créer un compte";
    authPassword.autocomplete = isRegistration ? "new-password" : "current-password";
    authError.textContent = "";
}

function openAuthView(mode = "login") {
    setAuthMode(mode);
    showManagementView(authView, connectionToggle);
    authEmail.focus();
}

function openProfileView() {
    if (!currentUser) {
        openAuthView();
        return;
    }
    updateAuthInterface(currentUser);
    showManagementView(profileView, profileToggle);
}

async function loadCurrentUser() {
    try {
        const response = await fetch("/auth/me");
        if (!response.ok) {
            updateAuthInterface(null);
            return;
        }
        const data = await response.json();
        updateAuthInterface(data.user);
    } catch (error) {
        console.warn("Impossible de vérifier la session.", error);
        updateAuthInterface(null);
    }
}

function historyMessage(container, className, message) {
    container.replaceChildren();
    const element = document.createElement("p");
    element.className = className;
    element.textContent = message;
    container.appendChild(element);
}

function renderAcceptedActions(actions) {
    acceptedActionsList.replaceChildren();
    if (!Array.isArray(actions) || actions.length === 0) {
        historyMessage(acceptedActionsList, "history-empty", "Aucune action acceptée pour le moment.");
        return;
    }

    actions.forEach((action) => {
        const item = document.createElement("article");
        item.className = "history-item";
        const header = document.createElement("header");
        header.className = "history-item-header";
        const title = document.createElement("h2");
        title.textContent = ACTION_TITLES[action.tool_name] || action.tool_name;
        const date = document.createElement("time");
        date.className = "history-date";
        date.textContent = formatDateTime(action.updated_at);
        header.append(title, date);

        const description = document.createElement("p");
        description.textContent = Object.entries(action.input || {})
            .map(([key, value]) => `${FIELD_LABELS[key] || key} : ${formatUsefulValue(value, key)}`)
            .join("\n");
        const meta = document.createElement("div");
        meta.className = "history-meta";
        [action.tool_name, `Action #${action.id}`, "Exécutée"].forEach((value) => {
            const badge = document.createElement("span");
            badge.textContent = value;
            meta.appendChild(badge);
        });
        item.append(header, description, meta);
        acceptedActionsList.appendChild(item);
    });
}

function renderConversationHistory(conversations) {
    conversationHistoryList.replaceChildren();
    if (!Array.isArray(conversations) || conversations.length === 0) {
        historyMessage(
            conversationHistoryList,
            "history-empty",
            "Aucune conversation enregistrée pour le moment.",
        );
        return;
    }

    conversations.forEach((conversation) => {
        const item = document.createElement("article");
        item.className = "history-item";
        const header = document.createElement("header");
        header.className = "history-item-header";
        const title = document.createElement("h2");
        title.textContent = conversation.user_message;
        const date = document.createElement("time");
        date.className = "history-date";
        date.textContent = formatDateTime(conversation.created_at);
        header.append(title, date);
        const response = document.createElement("p");
        response.textContent = conversation.agent_response;
        const meta = document.createElement("div");
        meta.className = "history-meta";
        if (conversation.plan_id) {
            const plan = document.createElement("span");
            plan.textContent = `Plan ${conversation.plan_id.slice(0, 8)}`;
            meta.appendChild(plan);
        }
        item.append(header, response, meta);
        conversationHistoryList.appendChild(item);
    });
}

async function loadAcceptedActions() {
    if (!currentUser) {
        openAuthView();
        return;
    }
    historyMessage(acceptedActionsList, "history-loading", "Chargement de l’historique...");
    try {
        const response = await fetch("/history/accepted-actions");
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Erreur du serveur");
        }
        renderAcceptedActions(data.actions);
    } catch (error) {
        historyMessage(acceptedActionsList, "history-error", error.message);
    }
}

async function openAcceptedActions() {
    if (!currentUser) {
        openAuthView();
        return;
    }
    showManagementView(acceptedActionsView, acceptedActionsToggle);
    await loadAcceptedActions();
}

async function loadConversationHistory() {
    if (!currentUser) {
        openAuthView();
        return;
    }
    historyMessage(conversationHistoryList, "history-loading", "Chargement de l’historique...");
    try {
        const response = await fetch("/history/conversations");
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Erreur du serveur");
        }
        renderConversationHistory(data.conversations);
    } catch (error) {
        historyMessage(conversationHistoryList, "history-error", error.message);
    }
}

async function openConversationHistory() {
    if (!currentUser) {
        openAuthView();
        return;
    }
    showManagementView(conversationHistoryView, conversationHistoryToggle);
    await loadConversationHistory();
}

menuToggle.addEventListener("click", toggleSidebar);
sidebarBackdrop.addEventListener("click", () => setSidebar(false));

settingsToggle.addEventListener("click", (event) => {
    event.stopPropagation();
    setSettingsOpen(settingsMenu.hidden);
});

settingsMenu.addEventListener("click", (event) => event.stopPropagation());

document.addEventListener("click", () => {
    if (!settingsMenu.hidden) {
        setSettingsOpen(false);
    }
});

themeToggle.addEventListener("change", () => {
    setTheme(themeToggle.checked ? "dark" : "light");
});

profileToggle.addEventListener("click", openProfileView);

connectionToggle.addEventListener("click", async () => {
    if (!currentUser) {
        openAuthView();
        return;
    }
    try {
        const response = await fetch("/auth/logout", {method: "POST"});
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Déconnexion impossible");
        }
        updateAuthInterface(null);
        resetConversation();
        requestStatus.textContent = "Vous êtes déconnecté";
    } catch (error) {
        requestStatus.textContent = error.message;
    }
});

authModeToggle.addEventListener("click", () => {
    setAuthMode(authMode === "login" ? "register" : "login");
});

authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    authError.textContent = "";
    authSubmit.disabled = true;
    try {
        const response = await fetch(`/auth/${authMode}`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                email: authEmail.value.trim(),
                password: authPassword.value,
            }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Connexion impossible");
        }
        updateAuthInterface(data.user);
        authPassword.value = "";
        openProfileView();
    } catch (error) {
        authError.textContent = error.message;
    } finally {
        authSubmit.disabled = false;
    }
});

newConversationButton.addEventListener("click", resetConversation);
calendarToggle.addEventListener("click", showCalendar);
acceptedActionsToggle.addEventListener("click", openAcceptedActions);
conversationHistoryToggle.addEventListener("click", openConversationHistory);
refreshActions.addEventListener("click", loadAcceptedActions);
refreshConversations.addEventListener("click", loadConversationHistory);

calendarPrevious.addEventListener("click", () => {
    currentCalendarMonth = new Date(
        currentCalendarMonth.getFullYear(),
        currentCalendarMonth.getMonth() - 1,
        1,
    );
    renderCalendar();
});

calendarNext.addEventListener("click", () => {
    currentCalendarMonth = new Date(
        currentCalendarMonth.getFullYear(),
        currentCalendarMonth.getMonth() + 1,
        1,
    );
    renderCalendar();
});

calendarToday.addEventListener("click", () => {
    selectedCalendarDate = new Date(today);
    currentCalendarMonth = new Date(today.getFullYear(), today.getMonth(), 1);
    renderCalendar();
});

calendarUseDate.addEventListener("click", () => {
    const selectedDateText = fullDateFormatter.format(selectedCalendarDate);
    resetConversation();
    messageInput.value = `Planifie une action pour le ${selectedDateText} : `;
    resizeMessageInput();
    messageInput.focus();
    messageInput.setSelectionRange(messageInput.value.length, messageInput.value.length);
});

messageInput.addEventListener("input", resizeMessageInput);
messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
    }
});

document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
        return;
    }

    if (!settingsMenu.hidden) {
        setSettingsOpen(false, true);
    } else if (appShell.classList.contains("sidebar-open")) {
        setSidebar(false);
        menuToggle.focus();
    }
});

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = messageInput.value.trim();
    if (!message || sendButton.disabled) {
        return;
    }

    showConversation();
    renderUserMessage(message);
    const agentView = renderAgentMessage();
    messageInput.value = "";
    resizeMessageInput();
    sendButton.disabled = true;
    requestStatus.textContent = "LE BRAS prépare sa réponse";

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({message}),
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Erreur du serveur");
        }

        if (data.plan_id) {
            localStorage.setItem(CURRENT_PLAN_STORAGE_KEY, data.plan_id);
        }
        completeAgentMessage(agentView, data);
        requestStatus.textContent = "Réponse reçue";
    } catch (error) {
        failAgentMessage(agentView, error);
        requestStatus.textContent = "La demande a échoué";
    } finally {
        sendButton.disabled = false;
        messageInput.focus();
    }
});

initializeTheme();
setSidebar(false);
resizeMessageInput();
loadCurrentUser();
loadToolToggles();
restoreCurrentPlan();
