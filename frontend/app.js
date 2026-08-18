const form = document.getElementById("chat-form");
const messageInput = document.getElementById("message");
const agentResponse = document.getElementById("agent-response");

form.addEventListener("submit", (event) => {
    event.preventDefault();

    const message = messageInput.value.trim();

    if (!message) {
        return;
    }

    agentResponse.textContent = "En attente de la réponse du backend...";
});