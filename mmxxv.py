import logging
import argparse
import asyncio
import websockets
import json
import chromadb
from bs4 import BeautifulSoup
import requests
from typing import List, Dict
from ollama import Client
from ollama._types import ResponseError

def load_config(config_path: str) -> dict:
	"""Load configuration from JSON file."""
	try:
		with open(config_path, 'r') as f:
			return json.load(f)
	except Exception as e:
		logging.error(f"Failed to load configuration from {config_path}: {e}")
		raise

def setup_logging(config: dict):
	"""Configure logging based on configuration."""
	logging_config = config['server']['logging']
	if logging_config['enabled']:
		handlers = []

		if logging_config['handlers']['file']['enabled']:
			handlers.append(logging.FileHandler(logging_config['handlers']['file']['filename']))

		if logging_config['handlers']['console']['enabled']:
			handlers.append(logging.StreamHandler())

		logging.basicConfig(
			level=getattr(logging, logging_config['level']),
			format=logging_config['format'],
			handlers=handlers
		)

class OllamaEmbeddingFunction:
	def __init__(self, config: dict):
		"""Initialize Ollama embedding function."""
		logging.info("Initializing OllamaEmbeddingFunction with model: %s",
					config['ollama']['models']['embedding'])
		self.client = Client(host=config['ollama']['host'])
		self.model_name = config['ollama']['models']['embedding']

	def __call__(self, input: List[str]) -> List[List[float]]:
		"""Generate embeddings for a list of texts."""
		embeddings = []
		for text in input:
			try:
				logging.debug("Generating embedding for text: %s", text)
				response = self.client.embeddings(model=self.model_name, prompt=text)
				embeddings.append(response['embedding'])
			except Exception as e:
				logging.error("Error generating embedding for text: %s", text)
				logging.exception(e)
		return embeddings

class OllamaEnhancer:
	def __init__(self, config: dict):
		"""Initialize the OllamaEnhancer with configuration."""
		logging.info("Initializing OllamaEnhancer with config")
		self.config = config
		self.embedding_function = OllamaEmbeddingFunction(config)
		self.client = chromadb.Client()
		self.collection = self.client.create_collection(
			name=config['chromadb']['collection_name'],
			embedding_function=self.embedding_function,
			metadata=config['chromadb']['metadata']
		)
		self.generation_model = config['ollama']['models']['generation']
		self.ollama_client = Client(host=config['ollama']['host'])
		self.max_chunk_length = config['content_processing']['max_chunk_length']
		self.batch_size = config['content_processing']['batch_size']

	def estimate_tokens(self, text: str) -> int:
		"""Estimate number of tokens in text using character count heuristic."""
		estimated_tokens = len(text) // 4
		logging.debug("Estimated tokens for text: %d", estimated_tokens)
		return estimated_tokens

	def process_html(self, url: str) -> List[Dict[str, str]]:
		"""Extract and structure content from HTML page."""
		try:
			logging.info("Processing HTML content from URL: %s", url)
			response = requests.get(url)
			soup = BeautifulSoup(response.content, 'html.parser')

			# Remove script and style elements
			for element in soup(["script", "style", "nav", "footer", "header"]):
				element.decompose()

			structured_content = []
			main_content = soup.find('main') or soup.find('article') or soup.find('body')

			if main_content is None:
				logging.warning(f"No main content found for URL: {url}")
				# Fall back to using the entire soup object
				main_content = soup

			# First try to extract content by headings
			headings = main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
			if headings:
				for heading in headings:
					section_content = []
					current = heading.next_sibling

					while current and not current.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
						if isinstance(current, str) and current.strip():
							section_content.append(current.strip())
						elif current and current.name in ['p', 'div', 'span', 'li', 'td', 'pre', 'code']:
							section_content.append(current.get_text().strip())
						current = current.next_sibling if current else None

					if section_content:
						structured_content.append({
							'heading': heading.get_text().strip(),
							'content': ' '.join(filter(None, section_content)),
							'type': heading.name,
							'url': url
						})

			# If no content found by headings, try paragraphs and divs
			if not structured_content:
				paragraphs = main_content.find_all(['p', 'div', 'article'])
				content = ' '.join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
				if content:
					structured_content.append({
						'heading': 'Main Content',
						'content': content,
						'type': 'body',
						'url': url
					})

			# If still no content, try getting all text
			if not structured_content:
				content = main_content.get_text().strip()
				if content:
					structured_content.append({
						'heading': 'Page Content',
						'content': content,
						'type': 'body',
						'url': url
					})

			if not structured_content:
				logging.warning(f"No content extracted from URL: {url}")
				return []

			return structured_content

		except requests.RequestException as e:
			logging.error(f"Failed to fetch URL: {url}")
			logging.exception(e)
			return []
		except Exception as e:
			logging.error(f"Error processing HTML from URL: {url}")
			logging.exception(e)
			return []

	def chunk_text(self, text: str) -> List[str]:
		"""Split text into chunks based on estimated token length."""
		chunks = []
		sentences = text.split('. ')
		current_chunk = []
		current_length = 0

		for sentence in sentences:
			sentence_length = self.estimate_tokens(sentence)

			if current_length + sentence_length > self.max_chunk_length:
				if current_chunk:
					chunks.append('. '.join(current_chunk) + '.')
				current_chunk = [sentence]
				current_length = sentence_length
			else:
				current_chunk.append(sentence)
				current_length += sentence_length

		if current_chunk:
			chunks.append('. '.join(current_chunk) + '.')

		return chunks

	def add_content(self, urls: List[str]) -> None:
		"""Process and add content from URLs to the vector database."""
		logging.info("Adding content from URLs: %s", urls)
		all_documents = []
		all_metadatas = []
		all_ids = []

		for url_idx, url in enumerate(urls):
			structured_content = self.process_html(url)

			for section_idx, section in enumerate(structured_content):
				content_chunks = self.chunk_text(section['content'])

				for chunk_idx, chunk in enumerate(content_chunks):
					doc_id = f"doc_{url_idx}{section_idx}{chunk_idx}"

					all_documents.append(chunk)
					all_metadatas.append({
						"url": url,
						"heading": section['heading'],
						"type": section['type'],
						"chunk_idx": chunk_idx
					})
					all_ids.append(doc_id)

		for i in range(0, len(all_documents), self.batch_size):
			batch_docs = all_documents[i:i+self.batch_size]
			batch_meta = all_metadatas[i:i+self.batch_size]
			batch_ids = all_ids[i:i+self.batch_size]

			self.collection.add(
				documents=batch_docs,
				metadatas=batch_meta,
				ids=batch_ids
			)

	def enhance_query(self, query: str) -> str:
		"""Enhance a query using semantically relevant content from the database."""
		logging.info("Enhancing query: %s", query)

		try:
			results = self.collection.query(
				query_texts=[query],
				n_results=self.config['query_enhancement']['max_results'],
				include=['documents', 'metadatas']
			)
		except Exception as e:
			logging.error("Error querying the vector database.")
			logging.exception(e)
			return "Error retrieving context from the database."

		documents = results.get('documents', [[]])[0]
		metadatas = results.get('metadatas', [[]])[0]

		if not documents:
			logging.warning("No relevant documents found for the query.")
			return "No relevant context found in the database."

		formatted_context = "\n---\n".join(
			f"[Source: {metadata['url']}, Section: {metadata.get('heading', 'Unknown')}]\n{doc}"
			for doc, metadata in zip(documents, metadatas)
		)

		prompt = f"""Based on the following relevant context:

	{formatted_context}

	Please answer this query: {query}

	Provide detailed responses and reference specific sources when possible."""

		try:
			response = self.ollama_client.chat(
				model=self.generation_model,
				messages=[{'role': 'user', 'content': prompt}]
			)
			answer = response.get('message', {}).get('content', "No response from the model.")
			logging.info("LLM response: %s", answer)
			return answer
		except ResponseError as e:
			if "not found" in str(e).lower():
				error_msg = f"The model '{self.generation_model}' is not available. Please install it using 'ollama pull {self.generation_model}'"
				logging.error(error_msg)
				return error_msg
			logging.error("Error interacting with the LLM: %s", str(e))
			return f"Error interacting with the LLM: {str(e)}"
		except Exception as e:
			logging.error("Unexpected error while generating response: %s", str(e))
			logging.exception(e)
			return "An unexpected error occurred while generating the response."

async def websocket_handler(enhancer, websocket):
	"""Handle WebSocket connections."""
	logging.info("New WebSocket connection established.")
	try:
		async for message in websocket:
			logging.info("Received message: %s", message)
			data = json.loads(message)

			query = data.get("query")
			urls = data.get("urls", [])

			if not query:
				await websocket.send(json.dumps({"error": "Missing 'query' in request"}))
				continue

			if not urls:
				await websocket.send(json.dumps({"error": "Missing 'urls' in request"}))
				continue

			try:
				logging.info("Adding content from URLs: %s", urls)
				enhancer.add_content(urls)
				response = enhancer.enhance_query(query)
				await websocket.send(json.dumps({"response": response}))
			except Exception as e:
				logging.error("Error processing request.")
				logging.exception(e)
				await websocket.send(json.dumps({"error": "An error occurred while processing your request."}))
	except websockets.exceptions.ConnectionClosedError as e:
		logging.error("WebSocket connection was closed: %s", e)
	except Exception as e:
		logging.error("Error in WebSocket handler.")
		logging.exception(e)
	finally:
		try:
			await websocket.close()
		except Exception as e:
			logging.error("Error while closing WebSocket: %s", e)
		logging.info("WebSocket connection closed.")

async def start_server(enhancer, config: dict):
	"""Start the WebSocket server."""
	host = config['server']['host']
	port = config['server']['port']
	async with websockets.serve(lambda ws: websocket_handler(enhancer, ws), host, port):
		logging.info("WebSocket server running on %s:%d", host, port)
		await asyncio.Future()  # Run forever

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Run the OllamaEnhancer script.")
	parser.add_argument("--config", default="mmxxv.json", help="Path to configuration file")
	parser.add_argument("--server", action="store_true", help="Run as WebSocket server")
	args = parser.parse_args()

	config = load_config(args.config)
	setup_logging(config)
	enhancer = OllamaEnhancer(config)

	if args.server:
		logging.info("Running in server mode.")
		try:
			asyncio.run(start_server(enhancer, config))
		except KeyboardInterrupt:
			logging.info("Server shutdown by user.")
	else:
		logging.info("Running in standalone mode.")
		urls = config['urls']
		enhancer.add_content(urls)

		query = "What are the key points discussed in these pages?"
		enhanced_response = enhancer.enhance_query(query)
		print(f"Enhanced response: {enhanced_response}")