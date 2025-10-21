# tests/test_redis.py
import unittest
import redis

class TestRedis(unittest.TestCase):

    def setUp(self):
        self.client = redis.Redis(host='localhost', port=6379, db=0)

    def test_redis_set_get(self):
        self.client.set("test_key", "value")
        val = self.client.get("test_key").decode("utf-8")
        self.assertEqual(val, "value")

if __name__ == "__main__":
    unittest.main()
