# data/online_learning.py
import numpy as np
from sklearn.linear_model import SGDClassifier
import joblib

class OnlineLearner:
    def __init__(self, model_path: str = "models/online_model.pkl"):
        self.model_path = model_path
        try:
            self.model = joblib.load(model_path)
        except:
            self.model = SGDClassifier(loss="log_loss", max_iter=5)
        print("✅ Online learner initialized.")

    def partial_train(self, X, y):
        """Yeni verilerle modeli adım adım günceller."""
        self.model.partial_fit(X, y, classes=np.unique(y))
        joblib.dump(self.model, self.model_path)
        print("📈 Model online olarak güncellendi.")

    def predict(self, X):
        return self.model.predict_proba(X)[:, 1]
