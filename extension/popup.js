let ws;
let sources = {};  // Changed from urls array to sources object

// Connect to WebSocket server
function connectWebSocket() {
	ws = new WebSocket("ws://localhost:8765");

	ws.onopen = () => {
		console.log("Connected to WebSocket server.");
		// Send new chat message to reset server state
		ws.send(JSON.stringify({ action: "new_chat" }));
	};

	ws.onmessage = (event) => {
		try {
			const response = JSON.parse(event.data);
			if (response && response.response) {
				displayMessage(response.response, 'bot');
			} else if (response.error) {
				displayMessage(response.error, 'bot');
			} else {
				displayMessage("No response received from server.", 'bot');
			}
		} catch (error) {
			console.error("Error parsing WebSocket response:", error);
			displayMessage("Error receiving response from server.", 'bot');
		}
	};

	ws.onerror = (error) => {
		console.error("WebSocket error:", error);
		displayMessage("WebSocket error: " + error.message, 'bot');
	};

	ws.onclose = () => {
		console.log("WebSocket connection closed.");
	};
}

// Save chat state to chrome.storage.local
function saveChatState() {
	const chatMessages = Array.from(document.getElementsByClassName('message')).map(
		(message) => ({
			text: message.innerHTML,
			sender: message.classList.contains('user') ? 'user' : message.classList.contains('bot') ? 'bot' : null
		})
	);
	chrome.storage.local.set({
		chatMessages: chatMessages,
		sources: sources  // Save sources instead of urls
	}, () => {
		console.log("Chat state saved.");
	});
}

// Load chat state from chrome.storage.local
function loadChatState() {
	chrome.storage.local.get(['chatMessages', 'sources'], (result) => {
		if (result.sources) {
			sources = result.sources;
			displaySources();
		}
		if (result.chatMessages) {
			const chatBox = document.getElementById('chat-box');
			chatBox.innerHTML = '';
			result.chatMessages.forEach((message) => {
				const messageDiv = document.createElement('div');
				messageDiv.classList.add('message', message.sender);
				messageDiv.innerHTML = message.text;
				chatBox.appendChild(messageDiv);
			});
		}
	});
}

// Add a URL to the sources
function addUrl() {
	const urlInput = document.getElementById('url-input');
	const url = urlInput.value.trim();

	if (url && !(url in sources)) {
		sources[url] = null;  // null indicates content should be fetched from URL
		saveChatState();
		urlInput.value = '';  // Clear input
		displaySources();
	}
}

// Add current tab's URL
function getTabUrl() {
	chrome.runtime.sendMessage({ action: "getUrl" }, (response) => {
		if (response && response.url) {
			sources[response.url] = response.content;
			saveChatState();
			displaySources();
		} else {
			console.error("Unable to retrieve tab URL.");
		}
	});
}

// Display the list of sources
function displaySources() {
	const chatBox = document.getElementById('chat-box');
	const sourceList = Object.keys(sources).map(url => `
		<div class="message">
			<div class="source-container">
				<span>${url}</span>
				<button class="delete-btn" data-url="${url}">×</button>
			</div>
		</div>
	`).join('');
	chatBox.innerHTML = sourceList;

	// Add event listeners to delete buttons
	document.querySelectorAll('.delete-btn').forEach(button => {
		button.addEventListener('click', (e) => {
			const url = e.target.getAttribute('data-url');
			delete sources[url];
			saveChatState();
			displaySources();
		});
	});
}

// Display message in the chat box
function displayMessage(message, sender) {
	const chatBox = document.getElementById('chat-box');
	const messageDiv = document.createElement('div');
	messageDiv.classList.add('message', sender);

	// Convert markdown-style code blocks
	const formattedMessage = message.replace(
		/```(\w*)\n([\s\S]*?)```/g,
		(match, language, code) => {
			return `<pre class="code-block${language ? ' language-' + language : ''}"><code>${code.trim()}</code></pre>`;
		}
	);

	// Handle inline code
	const withInlineCode = formattedMessage.replace(
		/`([^`]+)`/g,
		'<code class="inline-code">$1</code>'
	);

	// Handle bold text
	const withBold = withInlineCode.replace(
		/\*\*([^*]+)\*\*/g,
		'<strong>$1</strong>'
	);

	messageDiv.innerHTML = withBold;
	chatBox.appendChild(messageDiv);
	chatBox.scrollTop = chatBox.scrollHeight;
	saveChatState();
}

// Send the query to WebSocket server
function sendQuery() {
	const queryInput = document.getElementById('query-input');
	const sendQueryBtn = document.getElementById('send-query-btn');
	const urlInput = document.getElementById('url-input');
	const addUrlBtn = document.getElementById('add-url-btn');
	const getTabUrlBtn = document.getElementById('get-tab-url-btn');
	const query = queryInput.value.trim();

	if (query && ws.readyState === WebSocket.OPEN) {
		// Disable all input elements
		const elementsToDisable = [
			queryInput,
			sendQueryBtn,
			urlInput,
			addUrlBtn,
			getTabUrlBtn
		];

		// Disable all elements
		elementsToDisable.forEach(element => {
			element.disabled = true;
			if (element.tagName.toLowerCase() === 'input') {
				element.classList.add('input-disabled');
			}
		});

		displayMessage(query, 'user');
		queryInput.value = ''; // Clear input

		const message = {
			query: query,
			sources: sources
		};

		ws.send(JSON.stringify(message));

		// Re-enable input and button after response is received
		ws.onmessage = (event) => {
			try {
				const response = JSON.parse(event.data);
				if (response && response.response) {
					displayMessage(response.response, 'bot');
				} else if (response.error) {
					displayMessage(response.error, 'bot');
				} else {
					displayMessage("No response received from server.", 'bot');
				}
			} catch (error) {
				console.error("Error parsing WebSocket response:", error);
				displayMessage("Error receiving response from server.", 'bot');
			} finally {
				// Re-enable all elements
				elementsToDisable.forEach(element => {
					element.disabled = false;
					if (element.tagName.toLowerCase() === 'input') {
						element.classList.remove('input-disabled');
					}
				});
			}
		};
	} else if (ws.readyState !== WebSocket.OPEN) {
		displayMessage("WebSocket is not connected. Please try again later.", 'bot');
	}
}

// Handle new chat
function handleNewChat() {
	// Clear local storage
	chrome.storage.local.clear(() => {
		console.log("Local storage cleared.");
	});

	// Reset sources and chat box
	sources = {};
	const chatBox = document.getElementById('chat-box');
	chatBox.innerHTML = '';

	// Reconnect WebSocket
	if (ws) ws.close();
	connectWebSocket();

	console.log("New chat initialized.");
}

// Initialize WebSocket connection
connectWebSocket();

// Load state when the popup is opened
document.addEventListener('DOMContentLoaded', () => {
	loadChatState();
	connectWebSocket();
});

// Attach event listeners
document.getElementById('add-url-btn').addEventListener('click', addUrl);
document.getElementById('get-tab-url-btn').addEventListener('click', getTabUrl);
document.getElementById('send-query-btn').addEventListener('click', sendQuery);
document.getElementById('query-input').addEventListener('keydown', (event) => {
	if (event.key === 'Enter') {
		sendQuery();
	}
});
document.getElementById('close-popup-btn').addEventListener('click', () => {
	window.close();
});
document.getElementById('new-chat-btn').addEventListener('click', handleNewChat);
