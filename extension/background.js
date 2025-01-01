chrome.runtime.onInstalled.addListener(() => {
	console.log("WebSocket Chatbot extension installed.");
});

// Function to get the current tab's URL
chrome.action.onClicked.addListener((tab) => {
	chrome.scripting.executeScript({
		target: { tabId: tab.id },
		function: getTabUrl
	});
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
	if (message.action === "getUrl") {
		chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
			if (tabs && tabs[0]) {
				sendResponse({ url: tabs[0].url });
			} else {
				sendResponse({ url: null });
			}
		});
		// Required to indicate an asynchronous response
		return true;
	}
});
