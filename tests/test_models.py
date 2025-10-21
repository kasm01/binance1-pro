# tests/test_models.py
import unittest
from models.lstm_model import LSTMModel
from models.lightgbm_model import LightGBMModel

class TestModels(unittest.TestCase):

    def test_lstm_model_prediction(self):
        model = LSTMModel()
        sample_input = [[0.1, 0.2, 0.3]]
        pred = model.predict(sample_input)
        self.assertIsInstance(pred, list)

    def test_lightgbm_model_prediction(self):
        model = LightGBMModel()
        sample_input = [[0.1, 0.2, 0.3]]
        pred = model.predict(sample_input)
        self.assertIsInstance(pred, list)

if __name__ == "__main__":
    unittest.main()
