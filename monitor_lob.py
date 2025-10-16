import asyncio
import websockets
import json
import random
from datetime import datetime
from typing import Dict, List
import time


class LOBDataServer:
    """WebSocket server that receives price feed and broadcasts to clients"""

    def __init__(self, host='localhost', port=8765):
        self.host = host
        self.port = port
        self.clients = set()
        self.running = False

        # Internal state for market data
        self.mid_price = 50000.0
        self.spread = 10.0
        self.market_orders = {'buy': 0.0, 'sell': 0.0}
        self.deribit_data = {}  # Will hold data from Deribit feed

    async def register_client(self, websocket):
        """Register new WebSocket client"""
        self.clients.add(websocket)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Client connected. Total: {len(self.clients)}")

    async def unregister_client(self, websocket):
        """Unregister WebSocket client"""
        self.clients.remove(websocket)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Client disconnected. Total: {len(self.clients)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if self.clients:
            json_msg = json.dumps(message)
            disconnected = set()

            for client in self.clients:
                try:
                    await client.send(json_msg)
                except Exception as e:
                    print(f"[ERROR] Broadcasting to client: {e}")
                    disconnected.add(client)

            # Remove disconnected clients
            for client in disconnected:
                self.clients.discard(client)

    async def price_feed_loop(self):
        """Main loop that broadcasts Deribit data"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Price feed loop started")

        last_log_time = time.time()

        while self.running:
            try:
                # Use Deribit data
                if self.deribit_data:
                    lob_data = self.format_deribit_data(self.deribit_data)

                    # Broadcast to all clients
                    if lob_data:
                        await self.broadcast(lob_data)

                        # Log less frequently
                        current_time = time.time()
                        if current_time - last_log_time >= 2:
                            print(
                                f"[{datetime.now().strftime('%H:%M:%S')}] Broadcasting to {len(self.clients)} client(s) - Bid: {lob_data['bestBid']}, Ask: {lob_data['bestAsk']}")
                            last_log_time = current_time
                else:
                    # Waiting for Deribit data
                    current_time = time.time()
                    if current_time - last_log_time >= 5:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting for Deribit data...")
                        last_log_time = current_time

                # Wait before next update (adjust frequency as needed)
                await asyncio.sleep(0.01)  # 100 updates per second

            except Exception as e:
                print(f"[ERROR] Price feed loop: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(1)

    def format_deribit_data(self, deribit_data: Dict) -> Dict:
        """Format Deribit data to match expected LOB format"""
        if not deribit_data.get('bids') or not deribit_data.get('asks'):
            print(deribit_data.keys())
            return None

        try:
            # Convert dict to sorted list
            bid_dict = deribit_data['bids']
            ask_dict = deribit_data['asks']

            # Sort bids descending (highest first)
            bid_prices = sorted(bid_dict.keys(), reverse=True)
            bids = [{"price": float(price), "volume": float(bid_dict[price])}
                    for price in bid_prices[:40]]

            # Sort asks ascending (lowest first)
            ask_prices = sorted(ask_dict.keys())
            asks = [{"price": float(price), "volume": float(ask_dict[price])}
                    for price in ask_prices[:40]]

            if not bids or not asks:
                return None

            best_bid = bids[0]['price']
            best_ask = asks[0]['price']

            # Calculate market order intensity
            market_orders = {
                'buy': self.market_orders['buy'],
                'sell': self.market_orders['sell']
            }

            result = {
                "timestamp": datetime.now().isoformat(),
                "bestBid": round(best_bid, 2),
                "bestAsk": round(best_ask, 2),
                "bids": bids,
                "asks": asks,
                "marketOrders": market_orders
            }

            return result

        except Exception as e:
            print(f"[ERROR] Formatting Deribit data: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def handle_client(self, websocket):
        """Handle individual WebSocket client connection"""
        await self.register_client(websocket)

        try:
            # Keep connection alive and handle incoming messages if needed
            async for message in websocket:
                # Handle client messages if needed
                try:
                    data = json.loads(message)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Received from client: {data}")
                except json.JSONDecodeError:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Invalid JSON from client")

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(websocket)

    async def start(self):
        """Start the WebSocket server"""
        self.running = True

        print(f"{'=' * 60}")
        print(f"LOB WebSocket Server Starting")
        print(f"{'=' * 60}")
        print(f"Host: {self.host}")
        print(f"Port: {self.port}")
        print(f"WebSocket URL: ws://{self.host}:{self.port}")
        print(f"{'=' * 60}\n")

        # Start the WebSocket server
        async with websockets.serve(self.handle_client, self.host, self.port):
            # Start the price feed loop
            await self.price_feed_loop()

    def stop(self):
        """Stop the server"""
        self.running = False
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Server stopping...")


# ============================================================================
# DERIBIT INTEGRATION
# ============================================================================

import websocket
import threading


class DeribitLOBServer(LOBDataServer):
    """WebSocket server with live Deribit feed integration"""

    def __init__(self, host='localhost', port=8765, instrument='BTC-PERPETUAL'):
        super().__init__(host, port)
        self.instrument = instrument
        self.deribit_ws = None

        # Maintain order book state as dicts: {price: volume}
        self.order_book = {
            'bids': {},
            'asks': {}
        }

        # Start Deribit connection
        self.connect_deribit()

    def apply_book_changes(self, changes, side):
        """Apply incremental changes to order book"""
        book = self.order_book[side]

        for change in changes:
            action = change[0]  # 'new', 'change', or 'delete'
            price = float(change[1])
            volume = float(change[2])

            if action == 'delete' or volume == 0:
                # Remove price level
                book.pop(price, None)
            else:
                # Add or update price level
                book[price] = volume

    def on_deribit_message(self, ws, message):
        """Handle incoming Deribit messages"""
        try:
            data = json.loads(message)

            # Handle subscription confirmation
            if 'result' in data:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Deribit subscription confirmed")
                return

            # Handle order book updates
            if 'params' in data and 'data' in data['params']:
                book_data = data['params']['data']

                # Check if this is a snapshot (initial state)
                # print(book_data)
                type_bd = type(book_data)
                if type_bd == dict:
                    if book_data.get('type') == 'snapshot':
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Received order book snapshot")
                        # For snapshot, data is [price, volume] format
                        self.order_book['bids'] = {float(b[1]): float(b[2]) for b in book_data.get('bids', [])}
                        self.order_book['asks'] = {float(a[1]): float(a[2]) for a in book_data.get('asks', [])}
                    else:
                        # For changes, data is ['action', price, volume] format
                        if 'bids' in book_data:
                            self.apply_book_changes(book_data['bids'], 'bids')
                        if 'asks' in book_data:
                            self.apply_book_changes(book_data['asks'], 'asks')

                    # Update deribit_data with current book state
                    self.deribit_data = {
                        'bids': self.order_book['bids'],
                        'asks': self.order_book['asks'],
                        'timestamp': book_data.get('timestamp', int(time.time() * 1000))
                    }

                elif type_bd == list:
                    for mo in book_data:
                        if mo.get('direction') == 'buy':
                            self.market_orders['buy'] = mo.get('price')
                        if mo.get('direction') == 'sell':
                            self.market_orders['sell'] = mo.get('price')

                # Only log periodically
                if not hasattr(self, '_message_count'):
                    self._message_count = 0

                self._message_count += 1
                if self._message_count <= 3 or self._message_count % 100 == 0:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Book update #{self._message_count}: {len(self.order_book['bids'])} bids, {len(self.order_book['asks'])} asks")

        except Exception as e:
            print(f"[ERROR] Processing Deribit message: {e}")
            import traceback
            traceback.print_exc()

    def on_deribit_error(self, ws, error):
        """Handle Deribit WebSocket errors"""
        print(f"[ERROR] Deribit WebSocket: {error}")

    def on_deribit_close(self, ws, close_status_code, close_msg):
        """Handle Deribit WebSocket close"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Deribit connection closed: {close_status_code} - {close_msg}")
        print("Attempting to reconnect in 5 seconds...")
        time.sleep(5)
        self.connect_deribit()

    def on_deribit_open(self, ws):
        """Handle Deribit WebSocket open"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Deribit connection established")

        # Subscribe to order book
        subscribe_msg = {
            "jsonrpc": "2.0",
            "method": "public/subscribe",
            "params": {
                "channels": [f"book.{self.instrument}.100ms",
                             f'trades.{self.instrument}.100ms',
                             f'ticker.{self.instrument}.100ms',
                             ]
            },
            "id": 1
        }
        ws.send(json.dumps(subscribe_msg))
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Subscribed to {self.instrument} order book")

    def connect_deribit(self):
        """Establish connection to Deribit WebSocket API"""
        ws_url = "wss://www.deribit.com/ws/api/v2"

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecting to Deribit...")

        self.deribit_ws = websocket.WebSocketApp(
            ws_url,
            on_message=self.on_deribit_message,
            on_error=self.on_deribit_error,
            on_close=self.on_deribit_close,
            on_open=self.on_deribit_open
        )

        # Run Deribit WebSocket in separate thread
        wst = threading.Thread(target=self.deribit_ws.run_forever, daemon=True)
        wst.start()

    def stop(self):
        """Stop the server and close Deribit connection"""
        super().stop()
        if self.deribit_ws:
            self.deribit_ws.close()


# ============================================================================
# Main execution
# ============================================================================

async def main():
    # Use DeribitLOBServer to connect to live Deribit feed
    server = DeribitLOBServer(host='localhost', port=8765, instrument='BTC-PERPETUAL')

    try:
        await server.start()
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
        server.stop()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("LOB Data WebSocket Server")
    print("=" * 60)
    print("\nPress Ctrl+C to stop the server\n")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nServer stopped.")