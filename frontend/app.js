const form = document.getElementById("chat-form");
const messageInput = document.getElementById("message");
const agentResponse = document.getElementById("agent-response");
const toolTraceList = document.getElementById("tool-trace-list");
const requestMetrics = document.getElementById("request-metrics");

function formatJson(value) {
    return JSON.stringify(value, null, 2);
}

function appendTraceValue(container, label, value) {
    const labelElement = document.createElement("strong");
    labelElement.textContent = label;
    container.appendChild(labelElement);

    const valueElement = document.createElement("pre");
    valueElement.textContent = formatJson(value);
    container.appendChild(valueElement);
    return valueElement;
}

async function submitActionDecision(actionId, decision, elements) {
    if (elements.inFlight || elements.settled) {
        return;
    }

    elements.inFlight = true;
    elements.approveButton.disabled = true;
    elements.rejectButton.disabled = true;
    elements.errorElement.textContent = "";

    try {
        const response = await fetch(`/actions/${actionId}/${decision}`, {method: "POST"});
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Erreur du serveur");
        }

        elements.settled = true;
        if (decision === "approve") {
            elements.item.className = "trace-step success";
            elements.statusElement.textContent = "Succès";
            elements.resultElement.textContent = formatJson(data.result);
        } else {
            elements.item.className = "trace-step rejected";
            elements.statusElement.textContent = "Action refusée";
            elements.resultElement.textContent = "Action refusée";
        }
    } catch (error) {
        elements.errorElement.textContent = `Erreur : ${error.message}`;
        elements.approveButton.disabled = false;
        elements.rejectButton.disabled = false;
    } finally {
        elements.inFlight = false;
    }
}

function renderTrace(trace) {
    toolTraceList.replaceChildren();

    if (!Array.isArray(trace) || trace.length === 0) {
        const emptyMessage = document.createElement("p");
        emptyMessage.textContent = "Aucun outil utilisé.";
        toolTraceList.appendChild(emptyMessage);
        return;
    }

    trace.forEach((step, index) => {
        const status = step.status === "pending"
            ? "pending"
            : (step.ok ? "success" : "error");
        const statusLabel = {
            pending: "En attente de validation",
            success: "Succès",
            error: "Erreur",
        }[status];

        const item = document.createElement("article");
        item.className = `trace-step ${status}`;

        const title = document.createElement("p");
        const toolName = document.createElement("strong");
        toolName.textContent = `${index + 1}. ${step.tool}`;
        title.appendChild(toolName);
        title.append(" — ");
        const statusElement = document.createElement("span");
        statusElement.textContent = statusLabel;
        title.appendChild(statusElement);
        title.append(` — ${step.latency_ms} ms`);
        item.appendChild(title);

        appendTraceValue(item, "Arguments", step.input);
        let resultElement;
        if (step.ok) {
            resultElement = appendTraceValue(item, "Résultat", step.output);
        } else {
            resultElement = appendTraceValue(item, "Erreur", step.error);
        }

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

            const elements = {
                item,
                statusElement,
                resultElement,
                approveButton,
                rejectButton,
                errorElement,
                inFlight: false,
                settled: false,
            };

            approveButton.addEventListener("click", () => {
                submitActionDecision(actionId, "approve", elements);
            });
            rejectButton.addEventListener("click", () => {
                submitActionDecision(actionId, "reject", elements);
            });

            controls.append(approveButton, rejectButton);
            item.append(controls, errorElement);
        }

        toolTraceList.appendChild(item);
    });
}

function renderMetrics(metrics) {
    if (!metrics) {
        requestMetrics.textContent = "Métriques indisponibles.";
        return;
    }

    requestMetrics.textContent = [
        `Tokens : ${metrics.input_tokens} entrée / ${metrics.output_tokens} sortie`,
        `total ${metrics.total_tokens}`,
        `latence globale ${metrics.latency_ms} ms`,
        "coût non configuré",
    ].join(" — ");
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = messageInput.value.trim();

    if (!message) {
        return;
    }

    agentResponse.textContent = "L'agent réfléchit...";
    renderTrace([]);
    renderMetrics(null);

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message: message,
            }),
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Erreur du serveur");
        }

        agentResponse.textContent = data.response;
        renderTrace(data.trace);
        renderMetrics(data.metrics);
    } catch (error) {
        agentResponse.textContent = `Erreur : ${error.message}`;
        renderTrace([]);
        renderMetrics(null);
    }
});
