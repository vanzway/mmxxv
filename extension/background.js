chrome.runtime.onInstalled.addListener(() => {
	console.log("WebSocket Chatbot extension installed.");
});

// Open side panel when extension icon is clicked
chrome.action.onClicked.addListener((tab) => {
	chrome.sidePanel.open({ windowId: tab.windowId });
});

// Function to get the current tab's URL and DOM content
const getTabContent = () => {
	const htmlContent = document.documentElement.outerHTML;
	return htmlContent;
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
	if (message.action === "getUrl") {
		chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
			if (tabs && tabs[0]) {
				chrome.scripting.executeScript({
					target: { tabId: tabs[0].id },
					function: getTabContent
				}, (results) => {
					if (results && results[0]) {
						sendResponse({
						url: tabs[0].url,
						content: results[0].result
						});
					} else {
						sendResponse({ url: tabs[0].url, content: null });
					}
				});
			} else {
				sendResponse({ url: null, content: null });
			}
		});
		return true;
	}
});
