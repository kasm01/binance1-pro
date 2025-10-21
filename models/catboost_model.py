# models/catboost_model.py
from catboost import CatBoostClassifier
import joblib
from sklearn.metrics import accuracy_score

class CatBoostModel:
    def __init__(self, model_path="models/catboost.pkl"):
        self.model_path = model_path
        self.model = CatBoostClassifier(
            iterations=400,
            learning_rate=0.03,
            depth=8,
            loss_function="Logloss",
            verbose=False
        )

    def train(self, X_train, y_train):
        self.model.fit(X_train, y_train)
        joblib.dump(self.model, self.model_path)
        print("✅ CatBoost model trained and saved.")

    def predict(self, X):
        return self.model.predict_proba(X)[:, 1]

    def evaluate(self, X_test, y_test):
        preds = self.model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        print(f"🐈 CatBoost accuracy: {acc:.3f}")
        return acc

    def load(self):
        self.model = joblib.load(self.model_path)
