# data/batch_learning.py
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score

class BatchTrainer:
    def __init__(self, model_path: str = "models/batch_model.pkl"):
        self.model_path = model_path

    def train(self, X, y):
        """Batch (toplu) model eğitimi."""
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
        model = GradientBoostingClassifier(n_estimators=200, learning_rate=0.05)
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        joblib.dump(model, self.model_path)
        print(f"✅ Batch training complete — accuracy: {acc:.3f}")
        return acc

    def load_model(self):
        return joblib.load(self.model_path)
