# models/lightgbm_model.py
import lightgbm as lgb
import joblib
from sklearn.metrics import accuracy_score

class LightGBMModel:
    def __init__(self, model_path="models/lightgbm.pkl"):
        self.model_path = model_path
        self.model = lgb.LGBMClassifier(
            num_leaves=40,
            learning_rate=0.01,
            n_estimators=300,
            objective="binary"
        )

    def train(self, X_train, y_train):
        self.model.fit(X_train, y_train)
        joblib.dump(self.model, self.model_path)
        print("✅ LightGBM model trained and saved.")

    def predict(self, X):
        return self.model.predict_proba(X)[:, 1]

    def evaluate(self, X_test, y_test):
        preds = self.model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        print(f"🎯 LightGBM accuracy: {acc:.3f}")
        return acc

    def load(self):
        self.model = joblib.load(self.model_path)
