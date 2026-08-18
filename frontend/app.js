const form = document.getElementById("chat-form");
const messageInput = document.getElementById("message");
const agentResponse = document.getElementById("agent-response");

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = messageInput.value.trim();

    if (!message) {
        return;
    }

    agentResponse.textContent = "L'agent réfléchit...";

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
    } catch (error) {
        agentResponse.textContent = `Erreur : ${error.message}`;
    }
});