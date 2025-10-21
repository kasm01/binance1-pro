# trading/strategy_engine.py
class StrategyEngine:
    """
    Strateji motoru:
    - Model tahminleri ve teknik göstergelere göre al-sat sinyali üretir
    """
    def __init__(self, models, indicators):
        self.models = models
        self.indicators = indicators

    def generate_signal(self, X):
        """
        Ensemble model ve teknik göstergelerle sinyal üretir:
        - 1: Al
        - -1: Sat
        - 0: Bekle
        """
        pred = self.models["ensemble"].predict(
            X["lstm"], X["lgb"], X["cat"]
        )
        if pred > 0.6:
            return 1
        elif pred < 0.4:
            return -1
        else:
            return 0
