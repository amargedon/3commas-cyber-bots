#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import configparser
#import json
import os
import sys
import time
from pathlib import Path

import tvscreener as tvs
from tvscreener import CryptoField, StockField, TimeInterval
from tvscreener.filter import FilterOperator
#from tvscreener import ExtraFilter
#from tvscreener.field import Exchange, SubMarket, SymbolType

from helpers.logging import Logger, NotificationHandler
from helpers.misc import (
    format_pair,
    populate_pair_lists,
    remove_excluded_pairs,
    unix_timestamp_to_string,
    wait_time_interval,
)
from helpers.threecommas import (
    control_threecommas_bots,
    get_threecommas_market,
    get_threecommas_account_marketcode,
    init_threecommas_api,
    load_blacklist,
    set_threecommas_bot_pairs,
    prefetch_marketcodes
)


def load_config():
    """Create default or load existing config file."""

    cfg = configparser.ConfigParser()
    if cfg.read(f"{datadir}/{program}.ini"):
        return cfg

    cfg["settings"] = {
        "timezone": "Europe/Amsterdam",
        "timeinterval": 3600,
        "debug": False,
        "logrotate": 7,
        "3c-apikey": "Your 3Commas API Key",
        "3c-apisecret": "Your 3Commas API Secret",
        "3c-apikey-path": "Path to your own generated RSA private key, or empty",
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }

    cfg["tv_default"] = {
        "botids": [12345, 67890]
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


def upgrade_config(cfg):
    """Upgrade config file if needed."""

    return cfg


def process_tv_section(section_id):
    """Process the section from the configuration"""

    botsupdated = False

    # Bot configuration for section
    #botids = json.loads(config.get(section_id, "botids"))

    cs = tvs.CryptoScreener()
    cs.set_range(0, 500)
    #cs.add_filter(CryptoField.EXCHANGE, FilterOperator.MATCH, 'BYBIT')
    #cs.add_filter(CryptoField.TECHNICAL_RATING, FilterOperator.IN_RANGE, [0.1, 1.0])
    cs.search("usdt.p")
    #cs.sort_by(CryptoField.VOLATILITY, ascending=False)

    df = cs.get(time_interval=TimeInterval.FOUR_HOURS, print_request=False)
    
    #for column_headers in df.columns: 
    #    print(column_headers)

    choices = []
    counter = 0
    # loop through the rows using iterrows()
    for index, row in df.iterrows():
        counter += 1

        symbol = row["Name"]
        exchange = row["Exchange"]
        volatility = row["Volatility"]
        change_onehour = row["Change 1h, %"]
        change_fourhour = row["Change %"]
        change_oneweek = row["Change 1W, %"]
        volume_change_oneday = row["Volume 24h Change %"]
        volume_fourhour = row["Volume"]
        technical_rating = row["Technical Rating"]

        if exchange != "BYBIT":
            continue

        if technical_rating <= 0.1:
            continue;

        logger.debug(
            f"{symbol} / {exchange}: volatility: {volatility} - "
            f"Change % 1h {change_onehour}, 4h: {change_fourhour}, 1W: {change_oneweek} - "
            f"Volume 4h: {volume_fourhour}, change % 1D: {volume_change_oneday} - "
            f"Technical Rating: {technical_rating}."
        )

        valid = True
        if volatility < 15.0:
            valid = False
            logger.debug(f"{symbol} excluded based on low volatility %")

        if change_onehour <= 0.0 and (change_fourhour <= 0.0 or change_oneweek <= 0.0):
            valid = False
            logger.debug(f"{symbol} excluded based on negative change %")

        if volume_change_oneday > 1000.0:
            valid = False
            logger.debug(f"{symbol} excluded based on daily volume change")

        if volume_fourhour <= 10000000.0:
            valid = False
            logger.debug(f"{symbol} excluded based on low trading volume")

        if valid:
            choices.append(symbol)

    logger.info(f"Remy!!!! is going to choose from {choices}...", True)

    return botsupdated


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

# Initialize 3Commas API
#api = init_threecommas_api(logger, config)
#if not api:
#    sys.exit(0)

# Refresh coin pairs in 3C bots based on the market data
while True:

    # Reload config files and refetch data to catch changes
    config = load_config()
    logger.info(f"Reloaded configuration from '{datadir}/{program}.ini'")

    # Configuration settings
    timeint = int(config.get("settings", "timeinterval"))

    for section in config.sections():
        if section.startswith("tv_"):
            process_tv_section(section)
        elif section != "settings":
            logger.warning(
                f"Section '{section}' not processed (prefix 'tv_' missing)!",
                False
            )

    if not wait_time_interval(logger, notification, timeint, False):
        break
