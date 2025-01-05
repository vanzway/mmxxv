import logging
import argparse
import asyncio
import websockets
import json
import chromadb
from bs4 import BeautifulSoup
import requests
from typing import List, Dict, Generator, Optional
from ollama import Client
from ollama._types import ResponseError
import textwrap

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

class ChunkedMessageHandler:
	def __init__(self):
		self.message_buffers = {}

	def process_chunk(self, data):
		message_id = data.get('messageId')
		if not message_id:
			return None

		if data.get('chunkIndex') == -1:  # Metadata
			self.message_buffers[message_id] = {
				'chunks': [''] * data['totalChunks'],
				'received': 0,
				'type': data['type']
			}
			return None

		buffer = self.message_buffers.get(message_id)
		if not buffer:
			return None

		chunk_index = data.get('chunkIndex')
		if chunk_index is not None:
			buffer['chunks'][chunk_index] = data['chunk']
			buffer['received'] += 1

			if buffer['received'] == len(buffer['chunks']):
				complete_message = ''.join(buffer['chunks'])
				del self.message_buffers[message_id]
				return {'type': buffer['type'], 'content': complete_message}

		return None

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
				logging.info("Generating embedding for text.")
				response = self.client.embeddings(model=self.model_name, prompt=text)
				embeddings.append(response['embedding'])
			except Exception as e:
				logging.error("Error generating embedding.", exc_info=True)
		return embeddings

class ChromaDBManager:
	def __init__(self, config: dict):
		"""Initialize ChromaDB manager."""
		self.client = chromadb.Client()
		self.collection_name = config['chromadb']['collection_name']
		self.metadata = config['chromadb']['metadata']
		self.reset_collection()

	def reset_collection(self):
		"""Reset ChromaDB collection to initial state."""
		try:
			# Delete existing collection if it exists
			self.client.delete_collection(self.collection_name)
		except Exception:
			pass  # Collection might not exist
		# Create fresh collection
		self.collection = self.client.create_collection(
			name=self.collection_name,
			metadata=self.metadata
		)

class OllamaEnhancer:
	def __init__(self, config: dict):
		self.config = config
		self.embedding_function = OllamaEmbeddingFunction(config)
		self.db_manager = ChromaDBManager(config)
		self.collection = self.db_manager.collection
		self.generation_model = config['ollama']['models']['generation']
		self.ollama_client = Client(host=config['ollama']['host'])
		self.max_chunk_length = config['content_processing']['max_chunk_length']
		self.batch_size = config['content_processing']['batch_size']

	def process_content(self, content: str, url: str) -> Generator[Dict[str, str], None, None]:
		"""Extract and structure content from HTML page."""
		try:
			soup = BeautifulSoup(content, 'html.parser')

			# Remove script and style elements
			for element in soup(["script", "style", "nav", "footer", "header"]):
				element.decompose()

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
						yield {
							'heading': heading.get_text().strip(),
							'content': ' '.join(filter(None, section_content)),
							'type': heading.name,
							'url': url
						}

			if not headings:
				paragraphs = main_content.find_all(['p', 'div', 'article'])
				content = ' '.join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
				if content:
					yield {
						'heading': 'Main Content',
						'content': content,
						'type': 'body',
						'url': url
					}

			if not headings and not paragraphs:
				content = main_content.get_text().strip()
				if content:
					yield {
						'heading': 'Page Content',
						'content': content,
						'type': 'body',
						'url': url
					}

			if not headings and not paragraphs and not content:
				logging.warning(f"No content extracted from URL: {url}")

		except requests.RequestException as e:
			logging.error(f"Failed to fetch URL: {url}")
			logging.exception(e)
		except Exception as e:
			logging.error(f"Error processing HTML from URL: {url}")
			logging.exception(e)

	def _extract_sections(self, content, url: str) -> List[Dict[str, str]]:
		"""Extract content sections from HTML or text."""
		sections = []
		headings = content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

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
					sections.append({
						'heading': heading.get_text().strip(),
						'content': ' '.join(filter(None, section_content)),
						'type': heading.name,
						'url': url
					})

		return sections

	def chunk_text(self, text: str) -> List[str]:
		"""Split text into chunks based on estimated token length."""
		return textwrap.wrap(text, width=self.max_chunk_length // 4)

	def add_content(self, sources: Dict[str, Optional[str]]) -> None:
		"""Process and add content from URLs to the vector database."""
		self.db_manager.reset_collection()
		self.collection = self.db_manager.collection

		logging.info("Adding content to database")
		all_documents = []
		all_metadatas = []
		all_ids = []

		for url, content in sources.items():
			try:
				if content is None:
					# Fetch content from URL
					response = requests.get(url)
					response.raise_for_status()
					content = response.text
				else:
					content = "<!DOCTYPE html>" + content

				# Process content
				for section_idx, section in enumerate(self.process_content(content, url)):
					content_chunks = self.chunk_text(section['content'])

					for chunk_idx, chunk in enumerate(content_chunks):
						doc_id = f"doc_{url}_{section_idx}_{chunk_idx}"
						all_documents.append(chunk)
						all_metadatas.append({
							"url": url,
							"heading": section['heading'],
							"type": section['type'],
							"chunk_idx": chunk_idx
						})
						all_ids.append(doc_id)

			except Exception as e:
				logging.error(f"Error processing source {url}: {str(e)}")

		# Add to ChromaDB in batches
		if all_documents:
			for i in range(0, len(all_documents), self.batch_size):
				self.collection.add(
					documents=all_documents[i:i+self.batch_size],
					metadatas=all_metadatas[i:i+self.batch_size],
					ids=all_ids[i:i+self.batch_size],
				)
			logging.info(f"Added {len(all_documents)} documents to ChromaDB")
		else:
			logging.warning("No content was added to the database")

	def enhance_query(self, query: str) -> str:
		"""Enhance a query using semantically relevant content from the database."""
		logging.info("Applying user query: %s", query)

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

		formatted_context = '\n---\n'.join(
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
			logging.info("LLM response generated.")
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
	"""Handle WebSocket connections and messages."""
	try:
		async for message in websocket:
			data = json.loads(message)

			if data.get("action") == "new_chat":
				enhancer.db_manager.reset_collection()
				await websocket.send(json.dumps({"response": "Chat reset successful"}))
				continue

			query = data.get("query")
			sources = data.get("sources")

			if not query or not sources:
				await websocket.send(json.dumps({"error": "Missing query or sources"}))
				continue

			# Add content to the database
			enhancer.add_content(sources)

			# Generate response
			response = enhancer.enhance_query(query)
			await websocket.send(json.dumps({"response": response}))

	except Exception as e:
		logging.error(f"Error in WebSocket handler: {str(e)}")
		await websocket.send(json.dumps({"error": str(e)}))

async def start_server(enhancer, config: dict):
	"""Start the WebSocket server."""
	host = config['server']['host']
	port = config['server']['port']
	async with websockets.serve(lambda ws: websocket_handler(enhancer, ws), host, port):
		logging.info("WebSocket server running on %s:%d", host, port)
		await asyncio.Future()

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
