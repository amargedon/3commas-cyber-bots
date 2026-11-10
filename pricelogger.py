#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import configparser
import csv
from datetime import datetime, timezone
from math import fabs
import os
import requests
import json
import sys
import time

from babel.numbers import format_decimal
from pathlib import Path
from helpers.datasources_coinmarketcap import get_coinmarketcap_price
from helpers.logging import Logger, NotificationHandler
from helpers.misc import (
    wait_time_interval
)

def format_price(value: float) -> str:
    """Format price using Dutch locale (comma decimal separator)."""
    return format_decimal(value, format='#,##0.000000000000', locale='nl_NL')

def parse_price(value: str) -> float:
    """Convert '1.234,56' → 1234.56"""
    return float(value.replace('.', '').replace(',', '.'))

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
        "cmc-apikey": "Your CoinMarketCap API Key",
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }
    cfg["logger_bitvavo"] = {
        "symbols": ["BTC", "ETH"],
        "currency": "EUR",
        "timeframe-latest-candle": "1d"
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


def upgrade_config(cfg):
    """Upgrade config file if needed."""

    return cfg


def get_bitvavo_markets(logger):
    """Fetch the available markets from Bitvavo and return a list of market symbols."""

    markets = []
    try:
        response = requests.get("https://api.bitvavo.com/v2/markets")
        response.raise_for_status()
        data = response.json()
        for market in data:
            markets.append(market["market"])

        logger.debug(f"Fetched markets from Bitvavo: {markets}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching markets from Bitvavo: {e}")
    
    return markets


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


def get_monthly_candle_close_price(coin: str, currency: str = "EUR", month: str = "January", year: int = 2024) -> float:
    """
    Fetch the monthly candle close price for a specified coin from Bitvavo.
    
    Args:
        coin: Coin symbol (e.g., "BTC", "ETH")
        currency: Target currency (default: "EUR")
        month: Month name (e.g., "January")
        year: Year (e.g., 2024)

    Returns:
        Close price as float
    """ 

    # Convert month name to month number
    month_number = time.strptime(month, "%B").tm_mon

    # Get timestamp for the first day of the specified month and year
    #start = datetime(year=year, month=month_number, day=1, hour=0, minute=0, tzinfo=timezone.utc)


    market = f"{coin}-{currency}"
    url = f"https://api.bitvavo.com/v2/{market}/candles"
    
    # Params could be used to fetch only the required candle, however API is broken and doesn't 
    # return any data when using start and limit parameters together for monthly candles.
    # So we fetch all monthly candles and loop through them to find the required one
    params = {
        "interval": "1M"
        #"start": int(start.timestamp() * 1000),  # Convert to milliseconds
        #"limit": 1
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    candles = response.json()
    logger.debug(f"Fetched monthly candles for {market} starting from {year}-{month}: {candles}")

    # Loop through candles to find the one that matches the specified month and year
    for candle in candles:
        candle_time = datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc)  # Convert timestamp to datetime
        if candle_time.year == year and candle_time.month == month_number:
             return float(candle[4])  # Close price is at index 4
    
    raise ValueError(f"No monthly candle data available for {market} starting from {year}-{month}")


def process_latest_prices(symbols: list, currency: str, timeframe: str):
    """Fetch and log latest prices for configured symbols."""

    # Create local data structure to store fetched data for all symbols in this section
    section_data = []

    for symbol in symbols:
        try:
            # Fetch current price via Bitvavo if in markets, otherwise fallback to CoinMarketCap 
            # to fetch the price for this symbol and log a warning
            currentprice = 0.0
            source = "none"
            if f"{symbol}-{currency}" in markets:
                currentprice = get_current_price(symbol, currency)
                source = "Bitvavo"
            else:
                logger.warning(f"Symbol '{symbol}' not found in Bitvavo markets, fetching current price from CoinMarketCap as fallback.", False)
                currentprice = get_coinmarketcap_price(logger, config.get("settings", "cmc-apikey"), symbol, currency)
                source = "CoinMarketCap"

            # Make sure the prices are not in scientific notation. If they are, convert them to a decimal 
            # format with 8 decimal places for better readability.
            if "e" in str(currentprice):
                currentprice = f"{currentprice:.12f}"
            logger.info(f"Current price for {symbol}: {currentprice} (Price source: {source})")

            # Fetch latest candle close price via Bitvavo if in markets, otherwise skip and log a warning
            closeprice = 0.0
            if f"{symbol}-{currency}" in markets:
                closeprice = get_latest_candle_close_price(symbol, currency, timeframe)

                # Make sure the prices are not in scientific notation. If they are, convert them to a decimal 
                # format with 8 decimal places for better readability.
                if "e" in str(closeprice):
                    closeprice = f"{closeprice:.12f}"
                logger.info(f"Latest candle close price for {symbol}: {closeprice}")
            else:
                logger.warning(f"Symbol '{symbol}' not found in Bitvavo markets, skipping candle close price fetch for this symbol.")

            section_data.append({
                "symbol": symbol,
                "current_price": currentprice,
                "close_price": closeprice,
                "average_bought_percentage_change": 0.0
            })
        except Exception as e:
            logger.error(f"Error fetching current price for {symbol}: {e}")
            section_data.append({
                "symbol": symbol,
                "current_price": 0.0,
                "close_price": 0.0,
                "average_bought_percentage_change": 0.0
            })
    
    # Return if no data was fetched to avoid writing empty files and calculating price changes without data
    if not section_data:
        logger.warning(f"No price data fetched for any symbols in this section, skipping writing to file and price change calculation.")
        return

    # Sort section data by symbol
    section_data.sort(key=lambda x: x["symbol"])

    # Compare current price with price of last run, calculate the percentage change and log it
    filename = f"latest_prices_{currency}_{timeframe}.csv"

    if os.path.exists(f"{datadir}/{filename}"):
        last_prices = {}
        last_average_bought_percentages = {}

        # Open file from previous run
        with open(f"{datadir}/{filename}", newline="") as f:
            reader = csv.reader(f, delimiter=';')

            for row in reader:
                # Skip Excel hint or header
                if not row or row[0] in ("sep=", "symbol"):
                    continue

                symbol = row[0]
                current_price = parse_price(row[1])

                last_prices[symbol] = current_price

                if len(row) > 3:
                    last_average_bought_percentages[symbol] = float(row[3])
                else:
                    last_average_bought_percentages[symbol] = 0.0

        average_bought_prices = {}
        with open(f"{datadir}/average_bought_prices.csv", newline="") as f:
            reader = csv.reader(f, delimiter=';')

            for row in reader:
                # Skip Excel hint or header
                if not row or row[0] in ("sep=", "symbol"):
                    continue

                symbol = row[0]
                average_price = parse_price(row[1])

                average_bought_prices[symbol] = average_price

        # Compare prices. Collect the changes in a list and sort by highest percentage change to 
        # lowest to log the most significant changes first
        price_changes = []
        for item in section_data:
            symbol = item["symbol"]
            current_price = float(item["current_price"])

            # Calculate price change percentage compared to last run if we have a last price, 
            # otherwise skip the change calculation for this symbol
            if symbol in last_prices and last_prices[symbol] > 0:
                last_price = last_prices[symbol]

                price_change = ((current_price - last_price) / last_price) * 100
                price_changes.append((symbol, price_change, last_price, current_price))
            
            # Calculate win or loss percentage compared to average bought price if we have 
            # an average bought price,
            if symbol in average_bought_prices and average_bought_prices[symbol] > 0:
                average_price = average_bought_prices[symbol]
                if average_price <= 0.0:
                    logger.warning(f"Average bought price for {symbol} is zero or negative, skipping win/loss calculation for this symbol.", False)
                    continue

                item["average_bought_percentage_change"] = ((current_price - average_price) / average_price) * 100
                change_percentage = item["average_bought_percentage_change"] - last_average_bought_percentages.get(symbol, 0.0)
                if symbol in last_average_bought_percentages and fabs(change_percentage) >= 0.50:
                    if change_percentage >= 0:
                        logger.info(f"Win/loss of {symbol}: +{change_percentage:.2f}% ({last_average_bought_percentages[symbol]:.2f} -> {item['average_bought_percentage_change']:.2f})", True)
                    else:
                        logger.info(f"Win/loss of {symbol}: {change_percentage:.2f}% ({last_average_bought_percentages[symbol]:.2f} -> {item['average_bought_percentage_change']:.2f})", True)

        # Sort by highest percentage change to lowest
        logger.info(f"{timeframe} price changes above 1% since last run: ", True)
        price_changes.sort(key=lambda x: x[1], reverse=True)
        for symbol, price_change, last_price, current_price in price_changes:
            if abs(price_change) >= 1.0:
                logger.info(
                    f"Price change for {symbol}: "
                    f"{price_change:.2f}% "
                    f"({last_price:.6f} -> {current_price:.6f})",
                    True
                )

    # Write section data to csv file including a header row
    with open(f"{datadir}/{filename}", "w", newline="") as f:
        writer = csv.writer(f, delimiter=';')

        # Excel hint
        f.write("sep=;\n")

        writer.writerow(["symbol", "current_price", "close_price", "average_bought_percentage_change"])

        for item in section_data:
            writer.writerow([
                item["symbol"],
                format_price(item["current_price"]),
                format_price(item["close_price"]),
                item["average_bought_percentage_change"]
            ])


def process_monthly_prices(symbols: list, currency: str, month: str, year: int):
    """Fetch and log monthly prices for configured symbols."""

    # Return if file for month and year already exists to avoid duplicate data
    filename = f"monthly_prices_{currency}_{month}_{year}.csv"
    if os.path.exists(f"{datadir}/{filename}"):
        logger.info(f"File '{datadir}/{filename}' already exists, skipping monthly price fetch for {month} {year}")
        return
    else:
        logger.info(f"File '{datadir}/{filename}' does not exist, fetching monthly prices for {month} {year}")

    # Create local data structure to store fetched data for all symbols in this section
    section_data = []

    for symbol in symbols:
        try:
            #Check if symbols is in Bitvavo markets, otherwise skip fetching price and log a warning
            if f"{symbol}-{currency}" not in markets:
                logger.warning(f"Symbol '{symbol}' not found in Bitvavo markets, skipping monthly price fetch for this symbol.", False)
                section_data.append({
                    "symbol": symbol,
                    "close_price": 0.0
                })
                continue

            # Fetch monthly candle close price
            closeprice = get_monthly_candle_close_price(symbol, currency, month, year)

            # Make sure the prices are not in scientific notation. If they are, convert them to a decimal 
            # format with 8 decimal places for better readability.
            if "e" in str(closeprice):
                closeprice = f"{closeprice:.12f}"

            logger.info(f"Monthly candle close price for {symbol} in {month} {year}: {closeprice}")

            section_data.append({
                "symbol": symbol,
                "close_price": closeprice
            })
        except Exception as e:
            logger.error(f"Error fetching monthly candle close price for {symbol} in {month} {year}: {e}")
            section_data.append({
                "symbol": symbol,
                "close_price": 0.0
            })

    # Sort section data by symbol
    section_data.sort(key=lambda x: x["symbol"])

    # Write section data to csv file including a header row
    with open(f"{datadir}/{filename}", "w", newline="") as f:
        writer = csv.writer(f, delimiter=';')

        f.write("sep=;\n")
        writer.writerow(["symbol", "close_price"])

        for item in section_data:
            writer.writerow([
                item["symbol"],
                format_price(item["close_price"])
            ])


def is_candle_closed(timeframe: str) -> bool:
    """Check if the last candle for the specified timeframe is closed based on the current time."""

    now = datetime.now()
    if timeframe.endswith("h"):
        hours = int(timeframe[:-1])
        logger.debug(f"Checking if current candle for timeframe '{timeframe}' is closed based on hour {now.hour} (hours {hours}) and minute {now.minute}")
        return now.hour % hours == 0 and now.minute <= 55
    elif timeframe.endswith("d"):
        logger.debug(f"Checking if current candle for timeframe '{timeframe}' is closed based on hour {now.hour} and minute {now.minute}")
        return now.hour == 0 and now.minute <= 55
    elif timeframe.endswith("W"):
        logger.debug(f"Checking if current candle for timeframe '{timeframe}' is closed based on weekday {now.weekday()}, hour {now.hour} and minute {now.minute}")
        return now.weekday() == 0 and now.hour == 0 and now.minute <= 55
    elif timeframe.endswith("M"):
        logger.debug(f"Checking if current candle for timeframe '{timeframe}' is closed based on day {now.day}, hour {now.hour} and minute {now.minute}")
        return now.day == 1 and now.hour == 0 and now.minute <= 55
    
    raise ValueError(f"Invalid timeframe '{timeframe}' for candle close check.")


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

    markets = get_bitvavo_markets(logger)

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

            # Fetch montly prices for the previous month if the current day is the first of the month to capture the monthly candle close price
            previous_month = time.localtime().tm_mon - 1 or 12
            previous_year = time.localtime().tm_year if previous_month != 12 else time.localtime().tm_year - 1
            month_name = time.strftime("%B", time.strptime(str(previous_month), "%m"))
            process_monthly_prices(symbols, currency, month_name, previous_year)

            timeframe = config.get(section, "timeframe-latest-candle")
            if not is_candle_closed(timeframe):
                logger.debug(f"Current candle for timeframe '{timeframe}' is not closed yet, skipping price fetch for this section.")
                continue

            process_latest_prices(symbols, currency, timeframe)
        elif section != "settings":
            logger.warning(
                f"Section '{section}' not processed (prefix 'cmc_' missing)!",
                False
            )

    # Create time object for 5 minutes past next hour
    next_hour = time.localtime().tm_hour
    next_run = time.mktime((time.localtime().tm_year, time.localtime().tm_mon, time.localtime().tm_mday, next_hour, 5, 0, 0, 0, 0))

    # Calculate sleep time from now till next run time
    wait_time = int(next_run - time.time())

    if not wait_time_interval(logger, notification, wait_time, False):
        break
