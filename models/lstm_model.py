# models/lstm_model.py
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam
import joblib

class LSTMModel:
    def __init__(self, input_shape=(60, 8), model_path="models/lstm_model.h5"):
        self.input_shape = input_shape
        self.model_path = model_path
        self.model = self._build_model()

    def _build_model(self):
        model = Sequential([
            LSTM(64, input_shape=self.input_shape, return_sequences=True),
            Dropout(0.2),
            LSTM(32),
            Dropout(0.2),
            Dense(1, activation="sigmoid")
        ])
        model.compile(loss="binary_crossentropy", optimizer=Adam(0.001), metrics=["accuracy"])
        return model

    def train(self, X_train, y_train, epochs=15, batch_size=32, validation_split=0.2):
        history = self.model.fit(X_train, y_train, epochs=epochs, batch_size=batch_size, validation_split=validation_split, verbose=1)
        self.model.save(self.model_path)
        print("✅ LSTM model trained and saved.")
        return history

    def predict(self, X):
        preds = self.model.predict(X)
        return preds.flatten()

    def load(self):
        self.model = tf.keras.models.load_model(self.model_path)
