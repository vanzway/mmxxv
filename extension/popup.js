let ws;
let sources = {};
let messageQueue = [];
let isConnecting = false;

// Message chunking implementation
class MessageChunker {
	constructor(maxChunkSize = 1024 * 64) { // 64KB default chunk size
		this.maxChunkSize = maxChunkSize;
		this.messageCounter = 0;
	}

	chunkMessage(message, type) {
		const messageId = `msg_${Date.now()}_${this.messageCounter++}`;
		const stringified = JSON.stringify(message);
		const totalLength = stringified.length;
		const chunks = [];

		// Send metadata chunk first
		const totalChunks = Math.ceil(totalLength / this.maxChunkSize);
		const metadataChunk = {
			messageId,
			chunkIndex: -1, // Metadata chunk indicator
			totalChunks,
			type
		};
		chunks.push(metadataChunk);

		// Split message into chunks
		for (let i = 0; i < totalLength; i += this.maxChunkSize) {
			const chunk = stringified.slice(i, i + this.maxChunkSize);
			const chunkObj = {
				messageId,
				chunkIndex: Math.floor(i / this.maxChunkSize),
				chunk
			};
			chunks.push(chunkObj);
		}

		return chunks;
	}
}

const messageChunker = new MessageChunker();

// Connect to WebSocket server
function connectWebSocket() {
	if (ws?.readyState === WebSocket.OPEN) {
		displayMessage("WebSocket already connected.", 'system');
		return;
	}

	if (isConnecting) {
		displayMessage("WebSocket connection already in progress.", 'system');
		return;
	}

	isConnecting = true;

	ws = new WebSocket("ws://localhost:8765");

	ws.onopen = () => {
		isConnecting = false;

		// Send any queued messages
		while (messageQueue.length > 0) {
			const queuedMessage = messageQueue.shift();
			ws.send(JSON.stringify(queuedMessage));
		}

		// Send new chat message to reset server state
		sendWebSocketMessage({ action: "new_chat" });
	};

	ws.onmessage = (event) => {
		try {
			const response = JSON.parse(event.data);
			if (response && response.response) {
				displayMessage(response.response, 'bot');
			} else if (response.error) {
				displayMessage(response.error, 'system');
			} else {
				displayMessage("No response received from server.", 'system');
			}
		} catch (error) {
			displayMessage("Error receiving response from server.", 'system');
		}
	};

	ws.onerror = (error) => {
		displayMessage("WebSocket error. Please try refreshing the popup.", 'system');
		isConnecting = false;
	};

	ws.onclose = () => {
		isConnecting = false;
	};
}

// Safe WebSocket send function
function sendWebSocketMessage(message) {
	if (!ws || ws.readyState === WebSocket.CONNECTING) {
		messageQueue.push(message);
		return;
	}

	if (ws.readyState !== WebSocket.OPEN) {
		messageQueue.push(message);
		connectWebSocket();
		return;
	}

	try {
		ws.send(JSON.stringify(message));
	} catch (error) {
		messageQueue.push(message);
		connectWebSocket();
	}
}

// Save chat state to chrome.storage.local
function saveChatState() {
	const chatMessages = Array.from(document.getElementsByClassName('message')).map(
		(message) => ({
			text: message.innerHTML,
			sender: message.classList.contains('user') ? 'user' :
				message.classList.contains('bot') ? 'bot' : 'system'
		})
	);
	chrome.storage.local.set({
		chatMessages: chatMessages,
		sources: sources
	}, () => {});
}

// Load chat state from chrome.storage.local
function loadChatState() {
	return new Promise((resolve) => {
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
			resolve();
		});
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
			displayMessage("Unable to retrieve tab URL.", 'system');
		}
	});
}

// Display the list of sources
function displaySources() {
	const chatBox = document.getElementById('chat-box');
	const sourceList = Object.keys(sources).map(url => `
		<div class="message system">
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

	if (!query) return;

	// Disable all input elements
	const elementsToDisable = [
		queryInput,
		sendQueryBtn,
		urlInput,
		addUrlBtn,
		getTabUrlBtn
	];

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

	// Chunk the message
	const chunks = messageChunker.chunkMessage(message, 'query');

	// Send all chunks
	chunks.forEach((chunk, index) => {
		sendWebSocketMessage(chunk);
	});

	// Re-enable handler is in ws.onmessage
}

// Handle new chat
function handleNewChat() {
	// Clear local storage
	chrome.storage.local.clear(() => {});

	// Reset sources and chat box
	sources = {};
	const chatBox = document.getElementById('chat-box');
	chatBox.innerHTML = '';

	// Close existing connection if any
	if (ws && ws.readyState === WebSocket.OPEN) {
		ws.close();
	}

	// Establish new connection
	connectWebSocket();
}

// Initialize popup
document.addEventListener('DOMContentLoaded', async () => {
	// First load the state
	await loadChatState();

	// Then establish WebSocket connection
	connectWebSocket();

	// Wait a short moment to ensure DOM is fully loaded
	setTimeout(() => {
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
	}, 100);
});
