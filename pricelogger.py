#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import configparser
import os
import requests
import json
import sys
import time

from pathlib import Path
from helpers.logging import Logger, NotificationHandler
from helpers.misc import (
    unix_timestamp_to_string,
    wait_time_interval
)

def load_config():
    """Create default or load existing config file."""

    cfg = configparser.ConfigParser()
    if cfg.read(f"{datadir}/{program}.ini"):
        return cfg

    cfg["settings"] = {
        "timezone": "Europe/Amsterdam",
        "timeinterval": 86400,
        "debug": False,
        "logrotate": 7,
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }
    cfg["logger_bitvavo"] = {
        "symbols": ["BTC", "ETH"],
        "currency": "EUR"
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


def upgrade_config(cfg):
    """Upgrade config file if needed."""

    return cfg


def get_current_price(coin: str, currency: str = "EUR") -> float:
    """
    Fetch the current price for a specified coin from Bitvavo.
    
    Args:
        coin: Coin symbol (e.g., "BTC", "ETH")
        currency: Target currency (default: "EUR")
    
    Returns:
        Current price as float
    """
    market = f"{coin}-{currency}"
    url = f"https://api.bitvavo.com/v2/ticker/price"
    
    params = {
        "market": market
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    
    data = response.json()
    return float(data["price"])


def get_latest_candle_close_price(coin: str, currency: str = "EUR", interval: str = "1h") -> float:
    """
    Fetch the latest candle close price for a specified coin from Bitvavo.
    
    Args:
        coin: Coin symbol (e.g., "BTC", "ETH")
        currency: Target currency (default: "EUR")
        interval: Candle interval (default: "1h")
    
    Returns:
        Close price as float
    """

    # Check if interval is valid
    valid_intervals = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "1W", "1M"]
    if interval not in valid_intervals:
        raise ValueError(f"Invalid interval '{interval}'. Valid intervals are: {', '.join(valid_intervals)}")

    market = f"{coin}-{currency}"
    url = f"https://api.bitvavo.com/v2/{market}/candles"
    
    params = {
        "market": market,
        "interval": interval,
        "limit": 1
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    candles = response.json()
    logger.debug(f"Fetched candles for {market} with interval {interval}: {candles}")
    if candles:
        return float(candles[0][4])  # Close price is at index 4
    
    raise ValueError(f"No candle data available for {market}")


# Start application
program = Path(__file__).stem

# Parse and interpret options.
parser = argparse.ArgumentParser(description="Cyberjunky's 3Commas bot helper.")
parser.add_argument(
    "-d", "--datadir", help="directory to use for config and logs files", type=str
)

args = parser.parse_args()
if args.datadir:
    datadir = args.datadir
else:
    datadir = os.getcwd()

# Create or load configuration file
config = load_config()
if not config:
    # Initialise temp logging
    logger = Logger(datadir, program, None, 7, False, False)
    logger.info(
        f"Created example config file '{datadir}/{program}.ini', edit it and restart the program"
    )
    sys.exit(0)
else:
    # Handle timezone
    if hasattr(time, "tzset"):
        os.environ["TZ"] = config.get(
            "settings", "timezone", fallback="Europe/Amsterdam"
        )
        time.tzset()

    # Init notification handler
    notification = NotificationHandler(
        program,
        config.getboolean("settings", "notifications"),
        config.get("settings", "notify-urls"),
    )

    # Initialise logging
    logger = Logger(
        datadir,
        program,
        notification,
        int(config.get("settings", "logrotate", fallback=7)),
        config.getboolean("settings", "debug"),
        config.getboolean("settings", "notifications"),
    )

    # Upgrade config file if needed
    config = upgrade_config(config)

    logger.info(f"Loaded configuration from '{datadir}/{program}.ini'")

# Refresh coin pairs based on CoinMarketCap data
while True:

    # Reload config files and refetch data to catch changes
    config = load_config()
    logger.info(f"Reloaded configuration from '{datadir}/{program}.ini'")

    # Configuration settings
    timeint = int(config.get("settings", "timeinterval"))

    # Current time
    starttime = int(time.time())

    for section in config.sections():
        if section.startswith("logger_"):
            exchange = section.removeprefix("logger_")
            if exchange != "bitvavo":
                logger.warning(
                    f"Section '{section}' not processed (unsupported exchange '{exchange}')!",
                    False
                )
                continue

            symbols = json.loads(config.get(section, "symbols"))
            currency = config.get(section, "currency")

            # Create local data structure to store fetched data for all symbols in this section
            section_data = []

            for symbol in symbols:
                try:
                    # Fetch current price
                    currentprice = get_current_price(symbol, currency)
                    logger.info(f"Current price for {symbol}: {currentprice}")

                    # Fetch latest candle close price
                    closeprice = get_latest_candle_close_price(symbol, currency, "1d")
                    logger.info(f"Latest candle close price for {symbol}: {closeprice}")

                    section_data.append({
                        "symbol": symbol,
                        "current_price": currentprice,
                        "close_price": closeprice
                    })
                except Exception as e:
                    logger.error(f"Error fetching current price for {symbol}: {e}")
            
            # Sort section data by symbol
            section_data.sort(key=lambda x: x["symbol"])

            # Write section data to csv file including a header row
            filename = unix_timestamp_to_string(starttime, '%Y-%m-%d %H:%M:%S')
            with open(f"{datadir}/{filename}.csv", "w") as f:
                f.write("symbol_currency, current_price, close_price\n")
            with open(f"{datadir}/{filename}.csv", "a") as f:
                for item in section_data:
                    f.write(f"{item['symbol']}_{currency}, {item['current_price']}, {item['close_price']}\n")
        elif section != "settings":
            logger.warning(
                f"Section '{section}' not processed (prefix 'cmc_' missing)!",
                False
            )

    if not wait_time_interval(logger, notification, timeint, False):
        break
