#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import configparser
import os
import sqlite3
import sys
import time
from pathlib import Path

from helpers.logging import Logger, NotificationHandler
from helpers.misc import (
    wait_time_interval,
)
from helpers.threecommas import (
    get_threecommas_account_marketcode,
    get_threecommas_accounts,
    get_threecommas_blacklist,
    get_threecommas_market,
    init_threecommas_api,
)


def load_config():
    """Create default or load existing config file."""

    cfg = configparser.ConfigParser()
    if cfg.read(f"{datadir}/{program}.ini"):
        return cfg

    cfg["settings"] = {
        "timezone": "Europe/Amsterdam",
        "debug": False,
        "logrotate": 7,
        "3c-apikey": "Your 3Commas API Key",
        "3c-apisecret": "Your 3Commas API Secret",
        "cmc-apikey": "Your CoinMarketCap API Key",
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }
    cfg["blacklist"] = {
        "stable-and-fiat": [
            "AUD",
            "BUSD",
            "DAI",
            "EUR",
            "EURS",
            "FEI",
            "FRAX",
            "GBP",
            "GUSD",
            "HUSD",
            "LUSD",
            "SUSD",
            "TRIBE",
            "TUSD",
            "USD",
            "USDC",
            "USDD",
            "USDN",
            "USDP",
            "USDT",
            "USDX",
            "UST",
            "USTC",
            "XSGD",
            "vBUSD",
            "vUSDC"
        ],
        "add-stable-fiat-pairs": True,
    }
    cfg["binance"] = {
        "add-down-pairs": False,
        "add-up-pairs": False,
    }
    cfg["gdax"] = {
    }
    cfg["ftx"] = {
        "add-bear-pairs": False,
        "add-bull-pairs": False,
        "add-half-pairs": False,
        "add-hedge-pairs": False,
    }
    cfg["ftx_futures"] = {
        "add-perp-pairs": False,
        "add-1230-pairs": False,
        "add-0331-pairs": False,
    }
    cfg["kucoin"] = {
        "add-3L-pairs": False,
        "add-3S-pairs": False,
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


def upgrade_config(thelogger, cfg):
    """Upgrade config file if needed."""

    return cfg


def open_cmc_db():
    """Create or open database to store data."""

    try:
        dbname = f"{program}.sqlite3"
        dbpath = f"file:{datadir}/{dbname}?mode=rw"
        dbconnection = sqlite3.connect(dbpath, uri=True)
        dbconnection.row_factory = sqlite3.Row

        logger.info(f"Database '{datadir}/{dbname}' opened successfully")

    except sqlite3.OperationalError:
        dbconnection = sqlite3.connect(f"{datadir}/{dbname}")
        dbconnection.row_factory = sqlite3.Row
        dbcursor = dbconnection.cursor()
        logger.info(f"Database '{datadir}/{dbname}' created successfully")

        dbcursor.execute(
            "CREATE TABLE IF NOT EXISTS sections ("
            "sectionid STRING Primary Key, "
            "next_processing_timestamp INT"
            ")"
        )

        logger.info("Database tables created successfully")

    return dbconnection


def process_tickerlist(marketcode, tickerlist, blacklist):
    """Process the tickerlist and update the blacklist pairs"""

    for pair in tickerlist:
        exclude = False

        base = pair.split("_")[0]
        coin = pair.split("_")[1]

        exclude, stablefiatpair = is_stable_fiat_pair(base, coin)
        exclude |= process_marketcode(marketcode, base, coin)

        if exclude:
            if pair not in blacklist:
                blacklist.append(pair)
                logger.info(
                    f"Added pair {pair} to blacklist."
                )
            else:
                logger.info(
                    f"Pair {pair} already in blacklist."
                )
        elif pair in blacklist:
            if stablefiatpair:
                blacklist.remove(pair)
                logger.info(
                    f"Removed pair {pair} from blacklist"
                )
            else:
                logger.info(
                    f"Leaving pair {pair} on blacklist"
                )


def is_stable_fiat_pair(base, coin):
    """Check if the given base and coin are a stable or fiat pair"""

    exclude = False
    stablefiatpair = False

    coins = config.get("blacklist", "stable-and-fiat")

    if base in coins and coin in coins:
        exclude = config.getboolean("blacklist", "add-stable-fiat-pairs")
        stablefiatpair = True
        logger.info(
            f"Base {base} and coin {coin} are found as stable or fiat."
        )

    return exclude, stablefiatpair


def process_marketcode(marketcode, base, coin):
    """Process the base and coin based on the marketcode"""

    exclude = False

    if not config.has_section(marketcode):
        logger.warning(
            f"No section for market {marketcode} in configuration. "
        )

    categories = ["down", "up", "bear", "bull", "half", "hedge", "perp", "1230", "0331", "3L", "3S"]
    for category in categories:
        if config.has_option(marketcode, f"add-{category}-pairs") and config.getboolean(marketcode, f"add-{category}-pairs"):
            exclude = category.lower() in coin.lower()

        if exclude:
            logger.info(
                f"Base {base} and coin {coin} excluded based on 'add-{category}-pairs'."
            )
            break

    return exclude


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
parser.add_argument(
    "-b", "--blacklist", help="local blacklist to use instead of 3Commas's", type=str
)

args = parser.parse_args()
if args.datadir:
    datadir = args.datadir
else:
    datadir = os.getcwd()

# pylint: disable-msg=C0103
if args.sharedir:
    sharedir = args.sharedir
else:
    sharedir = None

# pylint: disable-msg=C0103
if args.blacklist:
    blacklistfile = f"{datadir}/{args.blacklist}"
else:
    blacklistfile = None

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
    config = upgrade_config(logger, config)

    logger.info(f"Loaded configuration from '{datadir}/{program}.ini'")

# Initialize 3Commas API
api = init_threecommas_api(config)

# Initialize or open the database
db = open_cmc_db()
cursor = db.cursor()

# Refresh coin pairs based on CoinMarketCap data
while True:

    # Reload config files and refetch data to catch changes
    config = load_config()
    logger.info(f"Reloaded configuration from '{datadir}/{program}.ini'")

    # Configuration settings
    #timeint = int(config.get("settings", "timeinterval"))

    # Get the current blacklist
    blacklist = get_threecommas_blacklist(logger, api)
    logger.info(
        f"Current blacklist: {blacklist}"
    )

    # Current time to determine which sections to process
    #starttime = int(time.time())

    newblacklist = blacklist.copy()    

    # Fetch and process all accounts
    accounts = get_threecommas_accounts(logger, api)
    for account in accounts:
        # Get marketcode (exchange) from account
        marketcode = get_threecommas_account_marketcode(logger, api, account["id"])
        if not marketcode:
            logger.warning(
                f"No marketcode found for account {account['id']}"
            )

        # Load tickerlist for this exchange based on marketcode
        tickerlist = get_threecommas_market(logger, api, marketcode)
        if not tickerlist:
            logger.warning(
                f"No coins found for market {marketcode}"
            )

        # Process the tickerlist
        process_tickerlist(marketcode, tickerlist, newblacklist)

    if blacklist == newblacklist:
        logger.info(
            f"Blacklist already up to date with {len(blacklist)} pair(s)"
        )
    else:
        logger.info(
            f"Blacklist updated from {len(blacklist)} to {len(newblacklist)} pair(s)"
        )

    if not wait_time_interval(logger, notification, 60, False):
        break
