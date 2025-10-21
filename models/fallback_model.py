# models/fallback_model.py
import numpy as np
from sklearn.linear_model import LogisticRegression
import joblib

class FallbackModel:
    """
    Ana modeller çökerse veya veri anomalisi varsa,
    fallback model devreye girer (basit Logistic Regression tabanlı).
    """
    def __init__(self, model_path="models/fallback.pkl"):
        self.model_path = model_path
        try:
            self.model = joblib.load(model_path)
        except:
            self.model = LogisticRegression(max_iter=500)
        print("⚙️ Fallback model initialized.")

    def predict(self, X):
        try:
            return self.model.predict_proba(X)[:, 1]
        except Exception:
            print("❗Fallback fallback simple logic applied.")
            return np.array([0.5 if x.mean() > 0 else 0.3 for x in X])

    def train(self, X, y):
        self.model.fit(X, y)
        joblib.dump(self.model, self.model_path)
        print("✅ Fallback model trained and saved.")
