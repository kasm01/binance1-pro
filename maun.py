import asyncio
import logging
import signal
from datetime import datetime

from config.settings import Config
from data.feeds import BinanceDataClient
from data.websocket_client import WebSocketClient
from database.manager import DatabaseManager
from risk.manager import RiskManager
from monitoring.performance import PerformanceMonitor
from retrain.hybrid_model import HybridModel
from strategies.trading_strategy import TradingStrategy
from trading.top_coin_tracker import TopCoinTracker
from execution.multi_position_executor import MultiPositionExecutor
from cache.redis_cache import RedisCache
from notifications.cloud_telegram_notifier import CloudTelegramNotifier

class Binance1Bot:
    def __init__(self):
        self.config = Config()
        self.config.validate()

        # Componentler
        self.database = DatabaseManager(self.config)
        self.websocket = WebSocketClient(self.config)
        self.risk_manager = RiskManager(self.config)
        self.performance_monitor = PerformanceMonitor()
        self.data_client = BinanceDataClient(self.config)
        self.hybrid_model = HybridModel(self.config, self.data_client, self.risk_manager)
        self.trading_strategy = TradingStrategy(self.config, self.hybrid_model)
        self.top_coin_tracker = TopCoinTracker()
        self.multi_executor = MultiPositionExecutor(max_positions=3)
        self.redis_cache = RedisCache(self.config.redis_url)
        self.telegram = CloudTelegramNotifier(self.config.telegram_token, self.config.telegram_chat_id)

        self.is_running = False
        self.portfolio_value = 10000.0

    async def initialize(self):
        logging.info("Initializing Binance1 Bot")
        await self.database.connect()
        await self.redis_cache.connect()
        self.websocket.add_message_handler(self._handle_ws_message)
        self.websocket.start()
        await self.hybrid_model.initialize()
        self.telegram.send_message("Binance1 Bot started!")

    async def run(self):
        self.is_running = True
        logging.info("Starting main loop")
        try:
            while self.is_running:
                market_data = await self.data_client.get_market_data(self.config.trading.SYMBOLS)
                top_coins = self.top_coin_tracker.update_top_coins(market_data)
                tasks = []
                for symbol in top_coins:
                    tasks.append(self._process_symbol(symbol))
                await asyncio.gather(*tasks)
                await asyncio.sleep(60)
        except Exception as e:
            logging.error(f"Main loop error: {e}")
            self.telegram.send_message(f"Main loop error: {e}")
        finally:
            await self.shutdown()

    async def _process_symbol(self, symbol):
        try:
            current_price = self.websocket.get_current_price(symbol)
            order_book = self.websocket.get_order_book(symbol)
            price_data = await self.data_client.get_historical_klines(symbol, '5m', 100)
            if price_data.empty:
                return

            signal_result = await self.trading_strategy.generate_signal(
                symbol=symbol,
                price_data=price_data,
                current_price=current_price,
                order_book=order_book,
                volume=price_data['volume'].iloc[-1]
            )

            hybrid_pred = self.hybrid_model.predict(price_data)
            signal_result['confidence'] = hybrid_pred

            await self.database.save_signal(signal_result)

            if signal_result['should_trade'] and hybrid_pred > self.config.ml.MIN_CONFIDENCE:
                await self.multi_executor.execute_trade(
                    symbol=symbol,
                    side=signal_result['final_signal'],
                    quantity=self.risk_manager.calculate_position_size(self.portfolio_value, current_price),
                    price=current_price,
                    stop_loss=self.risk_manager.calculate_stop_loss_take_profit(current_price, signal_result['final_signal'])['stop_loss'],
                    take_profit=self.risk_manager.calculate_stop_loss_take_profit(current_price, signal_result['final_signal'])['take_profit'],
                    trade_callback=self._execute_trade_callback
                )

        except Exception as e:
            logging.error(f"Error processing symbol {symbol}: {e}")
            self.telegram.send_message(f"Error processing symbol {symbol}: {e}")

    async def _execute_trade_callback(self, symbol, side, quantity, price, stop_loss, take_profit):
        """Gerçek trade API entegrasyonu burada yapılacak"""
        logging.info(f"Trade callback: {symbol} {side} {quantity}@{price}")
        self.telegram.send_trade_alert(symbol, side, quantity, price)

    def _handle_ws_message(self, message):
        self.performance_monitor.record_websocket_message()
        # Redis cache update
        asyncio.create_task(self.redis_cache.set("last_ws_message", str(message), expire=60))

    async def shutdown(self):
        logging.info("Shutting down Binance1 Bot")
        self.is_running = False
        self.websocket.stop()
        await self.redis_cache.close()
        self.telegram.send_message("Binance1 Bot stopped.")

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    bot = Binance1Bot()

    signal.signal(signal.SIGINT, lambda s,f: asyncio.create_task(bot.shutdown()))
    signal.signal(signal.SIGTERM, lambda s,f: asyncio.create_task(bot.shutdown()))

    await bot.initialize()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
