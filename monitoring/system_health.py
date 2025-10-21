# monitoring/system_health.py
import psutil

class SystemHealth:
    """
    Sistem kaynaklarını (CPU, RAM, Disk) izler
    """
    def __init__(self):
        pass

    def get_status(self):
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        }

    def is_healthy(self, cpu_threshold=85, memory_threshold=85):
        status = self.get_status()
        return status["cpu_percent"] < cpu_threshold and status["memory_percent"] < memory_threshold
