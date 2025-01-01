let ws;
let urls = [];

// Connect to WebSocket server
function connectWebSocket() {
  ws = new WebSocket("ws://localhost:8765");

  ws.onopen = () => {
    console.log("Connected to WebSocket server.");
  };

  ws.onmessage = (event) => {
    try {
      const response = JSON.parse(event.data);
      if (response && response.response) {
        displayMessage(response.response, 'bot');
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
    displayMessage("WebSocket connection closed.", 'bot');
  };
}

// Save chat state to chrome.storage.local
function saveChatState() {
  const chatMessages = Array.from(document.getElementsByClassName('message')).map(
    (message) => ({ text: message.textContent, sender: message.classList.contains('user') ? 'user' : 'bot' })
  );
  chrome.storage.local.set({ chatMessages: chatMessages }, () => {
    console.log("Chat state saved.");
  });
}

// Load chat state from chrome.storage.local
function loadChatState() {
  chrome.storage.local.get(['chatMessages'], (result) => {
    if (result.chatMessages) {
      const chatBox = document.getElementById('chat-box');
      chatBox.innerHTML = '';
      result.chatMessages.forEach((message) => {
        displayMessage(message.text, message.sender);
      });
    }
  });
}

// Save URL state to chrome.storage.local
function saveState() {
  chrome.storage.local.set({ urls: urls }, () => {
    console.log("State saved.");
  });
}

// Load URL state from chrome.storage.local
function loadState() {
  chrome.storage.local.get(['urls'], (result) => {
    if (result.urls) {
      urls = result.urls;
      displayUrls();
    }
  });
}

// Add a URL to the list
function addUrl() {
  const urlInput = document.getElementById('url-input');
  const url = urlInput.value.trim();

  if (url && !urls.includes(url)) {
    urls.push(url);
    saveState();
    urlInput.value = '';  // Clear input
    displayUrls();
  }
}

// Add current tab's URL
function getTabUrl() {
	chrome.runtime.sendMessage({ action: "getUrl" }, (response) => {
	  if (response && response.url) {
		urls.push(response.url);
		saveState();
		displayUrls();
	  } else {
		console.error("Unable to retrieve tab URL.");
	  }
	});
  }

// Display the list of URLs
function displayUrls() {
  const chatBox = document.getElementById('chat-box');
  const urlList = urls.map(url => `<div class="message bot">${url}</div>`).join('');
  chatBox.innerHTML = urlList;
}

// Display message in the chat box
function displayMessage(message, sender) {
  const chatBox = document.getElementById('chat-box');
  const messageDiv = document.createElement('div');
  messageDiv.classList.add('message', sender);
  messageDiv.textContent = message;
  chatBox.appendChild(messageDiv);
  chatBox.scrollTop = chatBox.scrollHeight; // Auto scroll
  saveChatState(); // Save after each message
}

// Handle text input and send query to WebSocket server
function handleKeydown(event) {
  if (event.key === 'Enter') {
    sendQuery();
  }
}

// Send the query to WebSocket server
function sendQuery() {
  const queryInput = document.getElementById('query-input');
  const query = queryInput.value.trim();

  if (query && ws.readyState === WebSocket.OPEN) {
    displayMessage(query, 'user');
    queryInput.value = ''; // Clear input

    const message = {
      query: query,
      urls: urls
    };

    ws.send(JSON.stringify(message));
  } else if (ws.readyState !== WebSocket.OPEN) {
    displayMessage("WebSocket is not connected. Please try again later.", 'bot');
  }
}

// Initialize WebSocket connection
connectWebSocket();

// Load state when the popup is opened
document.addEventListener('DOMContentLoaded', () => {
  loadState();
  loadChatState();
  connectWebSocket();
});

// Attach event listeners
document.getElementById('add-url-btn').addEventListener('click', addUrl);
document.getElementById('get-tab-url-btn').addEventListener('click', getTabUrl);
document.getElementById('send-query-btn').addEventListener('click', sendQuery);
document.getElementById('query-input').addEventListener('keydown', handleKeydown);

// Close popup explicitly
document.getElementById('close-popup-btn').addEventListener('click', () => {
  window.close();
});

// Handle new chat
document.getElementById('new-chat-btn').addEventListener('click', () => {
  // Clear local storage
  chrome.storage.local.clear(() => {
    console.log("Local storage cleared.");
  });

  // Reset URLs and chat box
  urls = [];
  const chatBox = document.getElementById('chat-box');
  chatBox.innerHTML = '';

  // Reconnect WebSocket
  if (ws) ws.close();
  connectWebSocket();

  console.log("New chat initialized.");
});
