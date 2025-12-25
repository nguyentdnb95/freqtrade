"""
Enhanced BTC/USDT Monitor with:
- Multi-timeframe RSI monitoring (1h and 4h)
- Extreme RSI alerts (>80 or <25)
- Significant volume detection
- Periodic 4h candle close updates

Usage:
python btc_rsi_monitor.py --config config.json --interval 1800
"""

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

import ccxt
import numpy as np
import requests
import talib


class EnhancedBTCMonitor:
    def __init__(self, config_path, update_interval=1800):
        """
        Initialize Enhanced BTC Monitor

        Args:
            config_path: Path to freqtrade config.json
            update_interval: Update interval in seconds (default: 1800 = 30 minutes)
        """
        self.interval_noti = 1800
        self.last_noti_rsi_hi = datetime.now(timezone.utc)
        self.last_noti_volume_hi = datetime.now(timezone.utc)

        self.update_interval = update_interval
        self.load_config(config_path)
        self.exchange = ccxt.binance()

        # Alert thresholds
        self.rsi_extreme_high = 70
        self.rsi_extreme_low = 35
        self.volume_multiplier = 2.0
        self.last_update_id = 0

        self.data_1h = self.get_data("1h", 100)
        self.data_4h = self.get_data("4h", 100)
        self.data_1d = self.get_data("1d", 100)
        self.indicators_1h = self.calculate_indicators(self.data_1h)
        self.indicators_4h = self.calculate_indicators(self.data_4h)
        self.indicators_1d = self.calculate_indicators(self.data_1d)

        # Track last 4h candle close to send periodic updates
        self.last_4h_close_time = None

    def load_config(self, config_path):
        """Load configuration from freqtrade config"""
        with open(config_path, "r") as f:
            config = json.load(f)

        self.telegram_token = config["telegram"]["token"]
        self.chat_id = config["telegram"]["chat_id"]

    def send_telegram(self, message):
        """Send message to Telegram"""
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}

        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                print(f"✓ Message sent successfully at {datetime.now(timezone.utc)}")
            else:
                print(f"✗ Failed to send message: {response.text}")
        except Exception as e:
            print(f"✗ Error sending message: {e}")

    def get_data(self, timeframe="1h", limit=100):
        """Fetch BTC/USDT data from exchange"""
        try:
            ohlcv = self.exchange.fetch_ohlcv("BTC/USDT", timeframe, limit=limit)

            closes = np.array([x[4] for x in ohlcv])
            highs = np.array([x[2] for x in ohlcv])
            lows = np.array([x[3] for x in ohlcv])
            volumes = np.array([x[5] for x in ohlcv])
            timestamps = [x[0] for x in ohlcv]

            return {
                "close": closes,
                "high": highs,
                "low": lows,
                "volume": volumes,
                "timestamps": timestamps,
                "last_timestamp": timestamps[-1],
            }
        except Exception as e:
            print(f"Error fetching {timeframe} data: {e}")
            return None

    def calculate_indicators(self, data):
        """Calculate RSI and other indicators"""
        close = data["close"]
        high = data["high"]
        low = data["low"]
        volume = data["volume"]

        # Calculate RSI
        rsi = talib.RSI(close, timeperiod=14)

        # Calculate EMAs
        ema_20 = talib.EMA(close, timeperiod=20)
        ema_50 = talib.EMA(close, timeperiod=50)
        ema_200 = talib.EMA(close, timeperiod=200)

        # Calculate MACD
        macd, macd_signal, macd_hist = talib.MACD(close)

        # Calculate Bollinger Bands
        bb_upper, bb_middle, bb_lower = talib.BBANDS(close)

        # Calculate volume average and ratio
        volume_sma = talib.SMA(volume, timeperiod=20)
        volume_ratio = volume[-1] / volume_sma[-1] if volume_sma[-1] > 0 else 0

        # Calculate ATR for volatility
        atr = talib.ATR(high, low, close, timeperiod=14)

        return {
            "current_price": close[-1],
            "volume": volume[-1],
            "rsi": rsi[-1],
            "rsi_prev": rsi[-2] if len(rsi) > 1 else rsi[-1],
            "ema_20": ema_20[-1],
            "ema_50": ema_50[-1],
            "ema_200": ema_200[-1],
            "macd": macd[-1],
            "macd_signal": macd_signal[-1],
            "macd_hist": macd_hist[-1],
            "bb_upper": bb_upper[-1],
            "bb_middle": bb_middle[-1],
            "bb_lower": bb_lower[-1],
            "volume_ratio": volume_ratio,
            "volume_24h": np.sum(volume[-24:]) if len(volume) >= 24 else 0,
            "atr": atr[-1],
            "timestamp": data["last_timestamp"],
        }

    def check_extreme_rsi(self):
        """Check for extreme RSI levels and send alerts"""
        rsi_1h = self.indicators_1h["rsi"]
        rsi_4h = self.indicators_4h["rsi"]
        price = self.indicators_1h["current_price"]
        volume_ratio = self.indicators_1h["volume_ratio"]
        volume_1h = self.indicators_1h["volume"]

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        en_noti = (
            datetime.now(timezone.utc) - self.last_noti_rsi_hi
        ).total_seconds() > self.interval_noti
        # Check for extreme high
        if (rsi_1h > self.rsi_extreme_high or rsi_4h > self.rsi_extreme_high) and en_noti:
            # Volume status
            vol_status = (
                f"🔊 HIGH VOLUME ({volume_ratio:.2f}x)"
                if volume_ratio > self.volume_multiplier
                else f"📊 Volume_1H: {volume_1h} ~{volume_ratio:.2f}x "
            )

            message = f"""
🔴🔥 EXTREME OVERBOUGHT ALERT! 🔥🔴

━━━━━━━━━━━━━━━━━━━━
📊 BTC/USDT
💰 Price: ${price:,.2f}
━━━━━━━━━━━━━━━━━━━━

⚠️ RSI EXTREME HIGH ⚠️
• RSI 1h: {rsi_1h:.2f} {"🔴" if rsi_1h > self.rsi_extreme_high else "⚪"}
• RSI 4h: {rsi_4h:.2f} {"🔴" if rsi_4h > self.rsi_extreme_high else "⚪"}

{vol_status}

⚡ ACTION SUGGESTED:
Consider taking profit or opening short position

⏰ Time: {timestamp}
"""
            self.send_telegram(message)
            self.last_noti_rsi_hi = datetime.now(timezone.utc)
            print(f"🔴 EXTREME OVERBOUGHT ALERT sent!")

        # Check for extreme low
        elif rsi_1h < self.rsi_extreme_low or rsi_4h < self.rsi_extreme_low:
            vol_status = (
                f"🔊 HIGH VOLUME ({volume_ratio:.2f}x)"
                if volume_ratio > self.volume_multiplier
                else f"📊 Volume: {volume_ratio:.2f}x"
            )

            message = f"""
🟢💎 EXTREME OVERSOLD ALERT! 💎🟢

━━━━━━━━━━━━━━━━━━━━
📊 BTC/USDT
💰 Price: ${price:,.2f}
━━━━━━━━━━━━━━━━━━━━

⚠️ RSI EXTREME LOW ⚠️
• RSI 1h: {rsi_1h:.2f} {"🟢" if rsi_1h < self.rsi_extreme_low else "⚪"}
• RSI 4h: {rsi_4h:.2f} {"🟢" if rsi_4h < self.rsi_extreme_low else "⚪"}

{vol_status}

⚡ ACTION SUGGESTED:
Potential strong buying opportunity!

⏰ Time: {timestamp}
"""
            self.send_telegram(message)
            print(f"🟢 EXTREME OVERSOLD ALERT sent!")

    def check_significant_volume(self, indicators):
        """Check for significant volume spike"""
        volume_ratio = indicators["volume_ratio"]
        price = indicators["current_price"]
        rsi = indicators["rsi"]
        volume_1h = indicators["volume"]
        en_noti = (
            datetime.now(timezone.utc) - self.last_noti_volume_hi
        ).total_seconds() > self.interval_noti

        if volume_ratio > self.volume_multiplier and en_noti:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            # Determine if bullish or bearish volume
            if rsi > 50:
                sentiment = "📈 BULLISH"
                emoji = "🟢"
            else:
                sentiment = "📉 BEARISH"
                emoji = "🔴"

            message = f"""
🔊🔥 SIGNIFICANT VOLUME SPIKE! 🔥🔊

━━━━━━━━━━━━━━━━━━━━
📊 BTC/USDT
💰 Price: ${price:,.2f}
📈 RSI: {rsi:.2f}
━━━━━━━━━━━━━━━━━━━━

⚡ Volume1H: {volume_1h} ~{volume_ratio:.2f}x "
{emoji} Sentiment: {sentiment}

⚠️ High volume indicates strong market interest!
Watch for price action confirmation.

⏰ Time: {timestamp}
"""
            self.send_telegram(message)
            self.last_noti_volume_hi = datetime.now(timezone.utc)
            print(f"🔊 SIGNIFICANT VOLUME alert sent! ({volume_ratio:.2f}x)")

    def send_4h_close_update(self):
        """Send update when 4h candle closes"""
        price = self.indicators_1h["current_price"]
        rsi_1h = self.indicators_1h["rsi"]
        rsi_4h = self.indicators_4h["rsi"]

        ema_20_4h = self.indicators_4h["ema_20"]
        ema_50_4h = self.indicators_4h["ema_50"]

        volume_ratio_1h = self.indicators_1h["volume_ratio"]
        volume_ratio_4h = self.indicators_4h["volume_ratio"]
        volume_1h = self.indicators_1h["volume"]
        volume_4h = self.indicators_4h["volume"]

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # RSI zones
        def get_rsi_zone(rsi):
            if rsi > self.rsi_extreme_high:
                return "🔴 OVERBOUGHT"
            elif rsi < self.rsi_extreme_low:
                return "🟢 OVERSOLD"
            else:
                return "⚪ NEUTRAL"

        # Trend determination
        if ema_20_4h > ema_50_4h:
            trend = "📈 BULLISH"
            trend_emoji = "🟢"
        else:
            trend = "📉 BEARISH"
            trend_emoji = "🔴"

        # Price position relative to EMAs
        if price > ema_20_4h:
            price_vs_ema = f"Above EMA20 (+{((price / ema_20_4h - 1) * 100):.2f}%)"
        else:
            price_vs_ema = f"Below EMA20 ({((price / ema_20_4h - 1) * 100):.2f}%)"

        message = f"""
📊 4H CANDLE CLOSE UPDATE 📊

━━━━━━━━━━━━━━━━━━━━
📊 BTC/USDT
💰 Price: ${price:,.2f}
━━━━━━━━━━━━━━━━━━━━

📈 RSI Analysis:
• RSI 1h: {rsi_1h:.2f} - {get_rsi_zone(rsi_1h)}
• RSI 4h: {rsi_4h:.2f} - {get_rsi_zone(rsi_4h)}

📊 4H Indicators:
• EMA 20: ${ema_20_4h:,.2f}
• EMA 50: ${ema_50_4h:,.2f}
{trend_emoji} Trend: {trend}

📍 Position: {price_vs_ema}
🔊 Volume1H: {volume_1h} ~{volume_ratio_1h:.2f}x
🔊 Volume4H: {volume_4h} ~{volume_ratio_4h:.2f}x "

⏰ 4H Candle Closed: {timestamp}
━━━━━━━━━━━━━━━━━━━━
Next 4H close in ~4 hours
"""
        self.send_telegram(message)
        print(f"📊 4H CANDLE CLOSE update sent!")

    def is_4h_candle_close(self, timestamp):
        """Check if 4h candle just closed"""
        dt = datetime.fromtimestamp(timestamp / 1000)

        # Check if this is a new 4h close
        if self.last_4h_close_time is None:
            self.last_4h_close_time = timestamp
            return False

        # 4h candles close at 0, 4, 8, 12, 16, 20 hours
        if dt.hour % 4 == 0 and dt.minute == 0:
            if timestamp != self.last_4h_close_time:
                self.last_4h_close_time = timestamp
                return True

        return False

    def create_regular_update(self):
        """Create regular periodic update message"""
        price = self.indicators_1h["current_price"]
        rsi_1h = self.indicators_1h["rsi"]
        rsi_1h_prev = self.indicators_1h["rsi_prev"]
        rsi_4h = self.indicators_4h["rsi"]
        rsi_1d = self.indicators_1d["rsi"]
        rsi_change = rsi_1h - rsi_1h_prev
        volume_ratio_1h = self.indicators_1h["volume_ratio"]
        volume_1h = self.indicators_1h["volume"]
        volume_ratio_4h = self.indicators_4h["volume_ratio"]
        volume_4h = self.indicators_4h["volume"]

        # Determine zones
        if rsi_1h > self.rsi_extreme_high:
            zone_1h = "🔴 OVERBOUGHT"
        elif rsi_1h < self.rsi_extreme_low:
            zone_1h = "🟢 OVERSOLD"
        else:
            zone_1h = "⚪ NEUTRAL"

        if rsi_4h > self.rsi_extreme_high:
            zone_4h = "🔴 OVERBOUGHT"
        elif rsi_4h < self.rsi_extreme_low:
            zone_4h = "🟢 OVERSOLD"
        else:
            zone_4h = "⚪ NEUTRAL"

        if rsi_1d > self.rsi_extreme_high:
            zone_1d = "🔴 OVERBOUGHT"
        elif rsi_4h < self.rsi_extreme_low:
            zone_1d = "🟢 OVERSOLD"
        else:
            zone_1d = "⚪ NEUTRAL"

        # Trend
        if self.indicators_1h["ema_20"] > self.indicators_1h["ema_50"]:
            trend_1h = "📈 Bullish"
        else:
            trend_1h = "📉 Bearish"

        if self.indicators_4h["ema_20"] > self.indicators_4h["ema_50"]:
            trend_4h = "📈 Bullish"
        else:
            trend_4h = "📉 Bearish"

        # MACD
        if self.indicators_1h["macd"] > self.indicators_1h["macd_signal"]:
            macd_status = "🟢 Bullish"
        else:
            macd_status = "🔴 Bearish"

        # Volume status
        if volume_ratio_1h > self.volume_multiplier:
            vol_emoji = "🔊"
            vol_text = f"""
• Volume1H: {volume_1h} ~ {volume_ratio_1h:.2f}x (HIGH!)
• Volume4H: {volume_4h} ~ {volume_ratio_4h:.2f}x (HIGH!)
"""

        else:
            vol_emoji = "📊"
            vol_text = f"""
• Volume1H: {volume_1h} ~ {volume_ratio_1h:.2f}x
• Volume4H: {volume_4h} ~ {volume_ratio_4h:.2f}x"
"""

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        message = f"""
📊 <b>BTC/USDT Market Update</b>
• Price Live: ${price:,.2f}

• RSI 1H: {rsi_1h:.2f} ({zone_1h})
• RSI 4H: {rsi_4h:.2f} ({zone_4h})
• RSI 1D: {rsi_1d:.2f} ({zone_1d})

• EMA 20 (1H): ${self.indicators_1h["ema_20"]:,.2f}
• EMA 50 (1H): ${self.indicators_1h["ema_50"]:,.2f}
• EMA 20 (4H): ${self.indicators_4h["ema_20"]:,.2f}
• EMA 50 (4H): ${self.indicators_4h["ema_50"]:,.2f}
• EMA 20 (1D): ${self.indicators_1d["ema_20"]:,.2f}
• EMA 50 (1D): ${self.indicators_1d["ema_50"]:,.2f}

• MACD(1H): ${self.indicators_1h["macd"]:,.2f}
• MACD(4H): ${self.indicators_4h["macd"]:,.2f}
• MACD(1D): ${self.indicators_1d["macd"]:,.2f}
{vol_text}
⏰ <b>Time:</b> {timestamp}
"""

        return message

    def tele_update(self, en_verbose):
        # print(f"\n📡 Fetching BTC/USDT data...")

        # Fetch both 1h and 4h data
        self.data_1h = self.get_data("1h", 100)
        self.data_4h = self.get_data("4h", 100)
        self.data_1d = self.get_data("1d", 100)

        if self.data_1h and self.data_4h:
            # Calculate indicators
            self.indicators_1h = self.calculate_indicators(self.data_1h)
            self.indicators_4h = self.calculate_indicators(self.data_4h)
            self.indicators_1n = self.calculate_indicators(self.data_1d)

            # print(f"💰 BTC Price: ${self.indicators_1h['current_price']:,.2f}")
            # print(f"📈 RSI 1h: {self.indicators_1h['rsi']:.2f}")
            # print(f"📊 RSI 4h: {self.indicators_4h['rsi']:.2f}")
            # print(f"🔊 Volume: {self.indicators_1h['volume_ratio']:.2f}x")

            # Check for extreme RSI
            self.check_extreme_rsi()

            # Check for significant volume
            self.check_significant_volume(self.indicators_1h)

            # Check if 4h candle closed
            if self.is_4h_candle_close(self.indicators_4h["timestamp"]) or en_verbose:
                self.send_4h_close_update()

            # Send regular update
            if self.is_4h_candle_close(self.indicators_4h["timestamp"]) or en_verbose:
                message = self.create_regular_update()
                self.send_telegram(message)

    # ============================================
    def telegram_bot_loop(self):
        """Separate thread for handling Telegram commands"""
        try:
            updates = self.get_telegram_updates()

            for update in updates:
                self.last_update_id = update["update_id"]

                if "message" in update and "text" in update["message"]:
                    chat_id = update["message"]["chat"]["id"]
                    text = update["message"]["text"]

                    # Only process commands from authorized chat_id
                    if str(chat_id) == str(self.chat_id):
                        if text.startswith("/"):
                            self.process_command(text, chat_id)
                    else:
                        print(f"⚠️ Unauthorized access attempt from chat_id: {chat_id}")

        except Exception as e:
            print(f"Error in bot loop: {e}")

    def get_telegram_updates(self):
        """Poll for new Telegram messages/commands"""
        url = f"https://api.telegram.org/bot{self.telegram_token}/getUpdates"
        params = {"offset": self.last_update_id + 1, "timeout": 1}

        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data["ok"] and data["result"]:
                    return data["result"]
        except Exception as e:
            print(f"Error getting updates: {e}")

        return []

    def process_command(self, command, chat_id):
        """Process Telegram bot commands"""
        command = command.lower().strip()

        print(f"📨 Received command: {command}")

        if command == "/technical":
            message = self.create_regular_update()
            self.send_telegram(message)

        else:
            message = f"❓ Unknown command: {command}\n\nUse /help to see available commands."
            self.send_telegram(message, chat_id)

    def run(self):
        """Main monitoring loop"""
        print(f"🚀 Enhanced BTC/USDT Monitor Started")
        print(f"⏰ Update interval: {self.update_interval // 60} minutes")
        print(f"📊 Monitoring: 1h and 4h timeframes")
        print(f"🎯 RSI Alerts: >{self.rsi_extreme_high} or <{self.rsi_extreme_low}")
        print(f"🔊 Volume Alert: >{self.volume_multiplier}x average")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Send startup message
        startup_msg = f"""
🤖 <b>Enhanced BTC Monitor Started</b>

Monitoring BTC/USDT on multiple timeframes
• 1h and 4h RSI tracking
• Extreme RSI alerts (>{self.rsi_extreme_high} or <{self.rsi_extreme_low})
• Significant volume detection (>{self.volume_multiplier}x)
• 4h candle close updates

━━━━━━━━━━━━━━━━━━━━
⏰ Updates every {self.update_interval // 60} minutes
Waiting for first update...
"""
        self.send_telegram(startup_msg)
        self.tele_update(en_verbose=True)

        while True:
            try:
                self.tele_update(en_verbose=False)
                self.telegram_bot_loop()
                time.sleep(0.5)

            except KeyboardInterrupt:
                print("\n\n👋 Monitor stopped by user")
                break
            except Exception as e:
                print(f"\n❌ Error in monitoring loop: {e}")
                print(f"Retrying in 60 seconds...")
                time.sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enhanced BTC/USDT Monitor")
    parser.add_argument("--config", type=str, required=True, help="Path to freqtrade config.json")
    parser.add_argument(
        "--interval",
        type=int,
        default=1800,
        help="Update interval in seconds (default: 1800 = 30 min)",
    )

    args = parser.parse_args()

    monitor = EnhancedBTCMonitor(args.config, args.interval)
    monitor.run()
