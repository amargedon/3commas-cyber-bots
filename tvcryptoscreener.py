#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import configparser
from datetime import datetime
import json
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
    cs.set_range(0, 3250)
    #cs.add_filter(CryptoField.EXCHANGE, FilterOperator.MATCH, 'BYBIT')
    #cs.add_filter(CryptoField.TECHNICAL_RATING, FilterOperator.IN_RANGE, [0.1, 1.0])
    #cs.search("usdt.p")
    cs.search("perpetual")
    #cs.sort_by(CryptoField.VOLATILITY, ascending=False)

    df = cs.get(time_interval=TimeInterval.FOUR_HOURS, print_request=False)

    #for column_headers in df.columns:
    #    print(column_headers)

    currentDateTime = datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
    df.to_csv(f"{datadir}/logs/dataframe-full-{currentDateTime}.csv", sep=';', index=True, encoding='utf-8')

    df1 = df.loc[df["Exchange"] == "BYBIT" ]
    df2 = df1.loc[df1["Technical Rating"] > 0.1 ]
    df3 = df2.sort_values(by = ["Volatility", "Technical Rating"], ascending = False)
    df_filtered = df3

    df_filtered.to_csv(f"{datadir}/logs/dataframe-filtered-{currentDateTime}.csv", sep=';', index=True, encoding='utf-8')

    buychoices = []
    strongbuychoices = []
    # loop through the rows using iterrows()
    for _, row in df_filtered.iterrows():
        symbol = row["Name"]
        exchange = row["Exchange"]
        volatility = row["Volatility"]
        change_onehour = row["Change 1h, %"]
        change_fourhour = row["Change %"]
        change_oneweek = row["Change 1W, %"]
        volume_change_oneday = row["Volume 24h Change %"]
        volume_fourhour = row["Volume"]
        technical_rating = row["Technical Rating"]

        logger.debug(
            f"{symbol} / {exchange}: volatility: {volatility} - "
            f"Change % 1h {change_onehour}, 4h: {change_fourhour}, 1W: {change_oneweek} - "
            f"Volume 4h: {volume_fourhour}, change % 1D: {volume_change_oneday} - "
            f"Technical Rating: {technical_rating}."
        )

        valid = True
        if volatility < 12.5:
            valid = False
            logger.debug(f"{symbol} excluded based on low volatility {volatility:.2f}%")

        if not 2.0 < change_oneweek < 35.0:
            valid = False
            logger.debug(f"{symbol} excluded based on change 1W {change_oneweek:.2f}%")

        if not -2.0 < change_fourhour < 12.5:
            valid = False
            logger.debug(f"{symbol} excluded based on change 4h {change_fourhour:.2f}%")

        if not -4.0 < change_onehour < 5.0:
            valid = False
            logger.debug(f"{symbol} excluded based on change 1h {change_onehour:.2f}%")

        if not -20 < volume_change_oneday < 1500.0:
            valid = False
            logger.debug(f"{symbol} excluded based on daily volume change {volume_change_oneday:.2f}%")

        if volume_fourhour < 5000000.0:
            valid = False
            logger.debug(f"{symbol} excluded based on low trading volume {volume_fourhour / 1000000}M")

        if valid:
            if technical_rating >= 0.5:
                strongbuychoices.append(symbol.replace("USDT.P", ""))
            else:
                buychoices.append(symbol.replace("USDT.P", ""))

    logger.info(f"Remy!!!! is going to choose from {strongbuychoices}, {buychoices}...", True)

    process_for_storage(strongbuychoices, buychoices)

    return botsupdated


def process_for_storage(strong_buy_coins, buy_coins):
    """Process the coin and store it"""

    pairdata = {
        "pairs": []
    }

    baselist = ["USDT"]
    for coin in strong_buy_coins:
        for base in baselist:
            pair = f"{coin}/{base}:USDT"
            pairdata["pairs"].append(pair)

    for coin in buy_coins:
        for base in baselist:
            pair = f"{coin}/{base}:USDT"
            pairdata["pairs"].append(pair)

    filename = f"{sharedir}/tradepairs_volatile.json"

    # Serializing json
    json_object = json.dumps(pairdata, indent = 2)

    # Writing to sample.json
    with open(filename, "w") as outfile:
        outfile.write(json_object)

    logger.debug(
        f"Wrote {len(pairdata['pairs'])} coins to {filename}."
    )



# Start application
program = Path(__file__).stem

# Parse and interpret options.
parser = argparse.ArgumentParser(description="Cyberjunky's 3Commas bot helper.")
parser.add_argument(
    "-d", "--datadir", help="directory to use for config and logs files", type=str
)

parser.add_argument(
    "-s", "--sharedir", help="directory to use for shared files", type=str
)

args = parser.parse_args()
if args.datadir:
    datadir = args.datadir
else:
    datadir = os.getcwd()

if args.sharedir:
    sharedir = args.sharedir
else:
    sharedir = None

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
