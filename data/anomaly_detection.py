# data/anomaly_detection.py
import numpy as np
import pandas as pd

class AnomalyDetector:
    def __init__(self, z_threshold: float = 3.0):
        self.z_threshold = z_threshold

    def detect_anomalies(self, df: pd.DataFrame, column: str = "close") -> pd.DataFrame:
        """Z-score yöntemiyle anomali tespiti yapar."""
        mean = df[column].mean()
        std = df[column].std()
        df["z_score"] = (df[column] - mean) / std
        df["anomaly"] = df["z_score"].abs() > self.z_threshold
        return df

    def remove_anomalies(self, df: pd.DataFrame) -> pd.DataFrame:
        """Anomalik verileri temizler."""
        clean_df = df[df["anomaly"] == False].drop(columns=["z_score", "anomaly"], errors="ignore")
        return clean_df
