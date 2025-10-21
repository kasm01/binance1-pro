# websocket/reconnect_manager.py
import threading
import time

class ReconnectManager:
    """
    WebSocket bağlantısı koparsa yeniden bağlanmayı yönetir
    """
    def __init__(self, ws_instance, reconnect_interval=5):
        self.ws_instance = ws_instance
        self.reconnect_interval = reconnect_interval
        self.reconnect_thread = None

    def schedule_reconnect(self):
        if self.reconnect_thread is None or not self.reconnect_thread.is_alive():
            self.reconnect_thread = threading.Thread(target=self._reconnect)
            self.reconnect_thread.start()

    def _reconnect(self):
        print(f"🔄 {self.reconnect_interval}s sonra websocket yeniden bağlanıyor...")
        time.sleep(self.reconnect_interval)
        self.ws_instance.start()
