document.addEventListener('DOMContentLoaded', () => {
    // The URL of your Python backend API.
    // 127.0.0.1 (localhost) is correct because this script runs in your browser,
    // which is on the same machine as your Python server.
    const apiUrl = 'http://127.0.0.1:5001/ask';

    // The HTML structure for the entire widget.
    const chatWidgetHTML = `
        <div id="chat-bubble">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="white" width="32px" height="32px"><path d="M0 0h24v24H0z" fill="none"/><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
        </div>
        <div id="chat-popup" class="hidden">
            <div id="chat-header">
                <span>Analytics Chatbot</span>
                <button id="close-btn">&times;</button>
            </div>
            <div id="chat-messages"></div>
            <div id="chat-input-container">
                <input type="text" id="chat-input" placeholder="Ask a question..." autocomplete="off">
                <button id="send-btn">Send</button>
            </div>
        </div>
    `;

    // Create a container and inject the HTML into the page.
    const container = document.createElement('div');
    container.id = 'chat-widget-container';
    container.innerHTML = chatWidgetHTML;
    document.body.appendChild(container);

    // Get references to all the necessary DOM elements.
    const chatBubble = document.getElementById('chat-bubble');
    const chatPopup = document.getElementById('chat-popup');
    const closeBtn = document.getElementById('close-btn');
    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');

    // Toggle the chat window when the bubble or close button is clicked.
    chatBubble.addEventListener('click', () => {
        chatPopup.classList.toggle('hidden');
        chatBubble.classList.toggle('hidden');
    });

    closeBtn.addEventListener('click', () => {
        chatPopup.classList.toggle('hidden');
        chatBubble.classList.toggle('hidden');
    });

    // Function to send a message to the backend API.
    const sendMessage = async () => {
        const query = chatInput.value;
        if (!query.trim()) return;

        addMessage(query, 'user');
        chatInput.value = '';

        try {
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });
            const data = await response.json();
            addMessage(data.answer, 'bot');
        } catch (error) {
            console.error("Error fetching from API:", error);
            addMessage('Error: Could not connect to the backend.', 'bot');
        }
    };

    // Add event listeners for sending a message.
    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            sendMessage();
        }
    });

    // Helper function to add a new message to the chat window.
    function addMessage(text, sender) {
        const messageElement = document.createElement('div');
        messageElement.className = `message ${sender}-message`;
        messageElement.textContent = text;
        chatMessages.appendChild(messageElement);
        // Scroll to the bottom of the chat window.
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
});