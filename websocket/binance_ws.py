# websocket/binance_ws.py
import websocket
import threading
import time
from .reconnect_manager import ReconnectManager

class BinanceWebSocket:
    """
    Binance futures ve spot websocket bağlantısı
    """
    def __init__(self, stream_handler, url):
        self.stream_handler = stream_handler
        self.url = url
        self.ws = None
        self.reconnect_manager = ReconnectManager(self)
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run)
        self.thread.start()

    def _run(self):
        while True:
            try:
                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_message=self.stream_handler.handle_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                self.ws.run_forever()
            except Exception as e:
                print(f"❌ WebSocket hata: {e}")
                self.reconnect_manager.schedule_reconnect()
            time.sleep(5)

    def _on_error(self, ws, error):
        print(f"❌ WebSocket error: {error}")
        self.reconnect_manager.schedule_reconnect()

    def _on_close(self, ws, close_status_code, close_msg):
        print("⚠️ WebSocket kapandı")
        self.reconnect_manager.schedule_reconnect()

    def send(self, message):
        try:
            self.ws.send(message)
        except Exception as e:
            print(f"❌ WebSocket send hatası: {e}")
            self.reconnect_manager.schedule_reconnect()
