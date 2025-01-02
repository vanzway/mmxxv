# MMXXV - Meaningful Model for Exploring Expert Views

MMXXV is a Chrome extension that enables contextual chat interactions with web content using local LLM capabilities through Ollama. The system uses ChromaDB for efficient vector storage and retrieval, allowing for enhanced responses based on the content of specified web pages.

## System Overview

The system consists of two main components:
1. A Python backend server that handles content processing and LLM interactions
2. A Chrome extension for the user interface

## Getting Started

### Clone the Repository

```bash
git clone https://github.com/vanzway/mmxxv.git
cd mmxxv
```

## Backend Server Setup

### Requirements

- Python 3.8+
- Ollama installed and running locally
- ChromaDB
- WebSocket support

### Installation Steps

1. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install required Python packages:
```bash
pip install websockets chromadb beautifulsoup4 requests ollama
```

3. Install required Ollama models:
```bash
ollama pull nomic-embed-text
ollama pull hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_0
```

### Server Configuration

Review and modify `mmxxv.json` as needed:
```json
{
  "server": {
    "host": "localhost",
    "port": 8765
  },
  "ollama": {
    "host": "http://localhost:11434",
    "models": {
      "generation": "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_0",
      "embedding": "nomic-embed-text"
    }
  }
}
```

### Starting the Server

1. Start the Ollama server:
```bash
ollama serve
```

2. Start the MMXXV server:
```bash
python mmxxv.py --server --config mmxxv.json
```

## Chrome Extension Setup

### Loading the Extension

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" using the toggle in the top right corner
3. Click "Load unpacked" button
4. Navigate to and select the `extension` directory in your project folder
5. The extension should now appear in your Chrome toolbar

### Using the Extension

1. Click the extension icon in your Chrome toolbar to open the interface
2. Add web pages to analyze:
   - Enter URLs manually and click "Add URL"
   - Use "Add Tab" to add the current tab's URL
3. Ask questions about the content:
   - Type your query in the input field
   - Press Enter or click "Send Query"
4. Start a new chat session:
   - Click the "+" button to clear history and start fresh

## Troubleshooting

### Server Issues

1. WebSocket Connection:
   - Ensure the server is running (`python mmxxv.py --server`)
   - Check if port 8765 is available
   - Verify WebSocket connection in browser console

2. Ollama Model Issues:
   - Confirm Ollama is running (`ollama serve`)
   - Verify models are installed using `ollama list`
   - Check model names in configuration match installed models

### Extension Issues

1. Extension Not Loading:
   - Verify all required files are present in the `extension` directory
   - Check for errors in Chrome's extension page (chrome://extensions/)
   - Look for error messages in Chrome's DevTools console

2. Interface Not Working:
   - Confirm the backend server is running
   - Check Chrome's console for connection errors
   - Verify WebSocket connection status

## Logging

Logs are written to `mmxxv.log` by default. Adjust logging settings in `mmxxv.json`:
```json
"logging": {
  "enabled": true,
  "level": "INFO",
  "format": "%(asctime)s - %(levelname)s - %(message)s"
}
```

## Security Notes

- The system runs locally and doesn't send data to external servers
- Web content is processed and stored in local ChromaDB
- Communication between extension and server uses WebSocket on localhost
- Review URLs before adding them to ensure they're trustworthy

## License

MIT License

Copyright (c) 2025 vanzway

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
