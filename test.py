import asyncio
import websockets
import json

async def query_server():
	uri = "ws://localhost:8765"
	async with websockets.connect(uri, ping_interval=30, ping_timeout=600) as websocket:
		message = {
			"query": "Tell me about this product",
			"urls": [
				"https://artcode.co.za/mmxxv",
				"https://github.com/vanzway/mmxxv"
			]
		}
		await websocket.send(json.dumps(message))
		response = await websocket.recv()
		print("Response from server:", json.loads(response))

asyncio.run(query_server())
