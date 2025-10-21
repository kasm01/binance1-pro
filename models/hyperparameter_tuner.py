# models/hyperparameter_tuner.py
import optuna
import lightgbm as lgb
from sklearn.model_selection import cross_val_score
import joblib

class HyperparameterTuner:
    def __init__(self, model_path="models/tuned_lgbm.pkl"):
        self.model_path = model_path

    def objective(self, trial, X, y):
        params = {
            "num_leaves": trial.suggest_int("num_leaves", 20, 80),
            "learning_rate": trial.suggest_float("learning_rate", 0.001, 0.05, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 600),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        }
        model = lgb.LGBMClassifier(**params)
        score = cross_val_score(model, X, y, cv=3, scoring="accuracy").mean()
        return score

    def tune(self, X, y, n_trials=30):
        study = optuna.create_study(direction="maximize")
        study.optimize(lambda trial: self.objective(trial, X, y), n_trials=n_trials)
        best_params = study.best_params
        print("🏆 Best params found:", best_params)
        model = lgb.LGBMClassifier(**best_params)
        model.fit(X, y)
        joblib.dump(model, self.model_path)
        print("✅ Tuned model saved.")
        return model, best_params
