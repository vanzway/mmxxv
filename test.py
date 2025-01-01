import asyncio
import websockets
import json

async def query_server():
	uri = "ws://localhost:8765"
	async with websockets.connect(uri, ping_interval=30, ping_timeout=600) as websocket:
		message = {
			"query": "What are the main points in the articles?",
			"urls": [
				"https://www.thehindu.com/news/international/south-korea-plane-crash-jeju-aircraft-muan-airport-live-updates-december-29/article69039217.ece",
				"https://www.thehindu.com/news/international/azerbaijan-accuses-russia-of-trying-to-hide-causes-of-plane-crash-says-the-plane-was-shot-from-russia/article69040088.ece"
			]
		}
		await websocket.send(json.dumps(message))
		response = await websocket.recv()
		print("Response from server:", json.loads(response))

asyncio.run(query_server())
