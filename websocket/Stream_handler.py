# websocket/stream_handler.py
class StreamHandler:
    """
    Gelen websocket verilerini işler ve bot modüllerine iletir.
    """
    def __init__(self):
        self.callbacks = []

    def register_callback(self, func):
        """
        Veri geldiğinde çalışacak fonksiyonları kaydeder
        """
        self.callbacks.append(func)

    def handle_message(self, message):
        """
        Gelen mesajları parse eder ve callback'lere iletir
        """
        data = self.parse_message(message)
        for callback in self.callbacks:
            callback(data)

    def parse_message(self, message):
        """
        Basit JSON parse işlemi, gerektiğinde geliştirilebilir
        """
        import json
        try:
            return json.loads(message)
        except Exception as e:
            print(f"❌ Mesaj parse hatası: {e}")
            return None
