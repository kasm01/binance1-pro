# models/ensemble_model.py
import numpy as np
import joblib

class EnsembleModel:
    """
    Ensemble yapısı: LSTM + LightGBM + CatBoost çıktılarının ağırlıklı ortalaması.
    """
    def __init__(self, model_paths=None):
        if model_paths is None:
            model_paths = {
                "lstm": "models/lstm_model.h5",
                "lightgbm": "models/lightgbm.pkl",
                "catboost": "models/catboost.pkl"
            }
        self.model_paths = model_paths

    def predict(self, lstm_pred, lgb_pred, cat_pred, weights=(0.4, 0.35, 0.25)):
        """Her modelin çıktısını ağırlıklı ortalama ile birleştirir."""
        lstm_w, lgb_w, cat_w = weights
        ensemble_pred = (lstm_pred * lstm_w) + (lgb_pred * lgb_w) + (cat_pred * cat_w)
        return np.clip(ensemble_pred, 0, 1)
