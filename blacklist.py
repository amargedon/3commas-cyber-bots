#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import asyncio
import configparser
import os
import sqlite3
import sys
import time
from pathlib import Path

from helpers.datasources import (
    get_binance_announcement_data
)

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
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }
    cfg["blacklist"] = {
        "stable-and-fiat": [
            "1GOLD",
            "AGEUR",
            "ALUSD",
            "ARTH",
            "AUSD",
            "AUD",
            "BAC",
            "BEAN",
            "BGBP",
            "BIDR",
            "BITCNY",
            "BITEUR",
            "BITGOLD",
            "BITUSD",
            "BKRW",
            "BRCP",
            "BRZ",
            "BSD",
            "BUSD",
            "BVND",
            "CADC",
            "CEUR",
            "COFFIN",
            "CONST",
            "COUSD",
            "CUSD",
            "CUSDT",
            "DAI",
            "DGD",
            "DGX",
            "DJED",
            "DOLA",
            "DPT",
            "DSD",
            "DUSD",
            "EBASE",
            "EOSDT",
            "ESD",
            "EUR",
            "EUROC",
            "EUROS",
            "EURS",
            "EURT",
            "FEI",
            "FLOAT",
            "FLUSD",
            "FRAX",
            "FUSD",
            "GBP",
            "GBPT",
            "GUSD",
            "GYEN",
            "H2O",
            "HGT",
            "HUSD",
            "IDRT",
            "IRON",
            "IST",
            "ITL",
            "IUSDS",
            "JPYC",
            "KBC",
            "KRT",
            "LUSD",
            "MDS",
            "MDO",
            "MIM",
            "MIMATIC",
            "MONEY",
            "MTR",
            "MUSD",
            "MXNT",
            "NUSD",
            "ONC",
            "ONEICHI",
            "OUSD",
            "PAR",
            "QC",
            "RSV",
            "SAC",
            "SBD",
            "SEUR",
            "STATIK",
            "SUSD",
            "TRIBE",
            "TRYB",
            "TOR",
            "TUSD",
            "UETH",
            "USD",
            "USDAP",
            "USDB",
            "USDC",
            "USDD",
            "USDEX"
            "USDFL",
            "USDI",
            "USDH",
            "USDJ",
            "USDK",
            "USDL",
            "USDN",
            "USDP",
            "USDQ",
            "USDR",
            "USDS",
            "USDT",
            "USDX",
            "USDZ",
            "USN",
            "USNBT",
            "UST",
            "USTC",
            "USX",
            "VAI",
            "WANUSDT",
            "XCHF",
            "XEUR",
            "XIDR",
            "XSGD",
            "XSTUSD",
            "XUSD",
            "YUSD",
            "ZUSD",
            "fUSDT",
            "mCEUR",
            "mCUSD",
            "vBUSD",
            "vDAI",
            "vUSDC",
            "vUSDT",
            "xDAI"
        ],
        "add-stable-fiat-pairs": True,
    }
    cfg["binance"] = {
        "add-down-pairs": False,
        "add-up-pairs": False,
    }
    cfg["binance_delist"] = {
        "enable": False,
        "close-smarttrades": "none / pair / coin",
        "close-dca-deals": "none / pair / coin",
    }
    cfg["gdax"] = {
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


def open_blacklist_db():
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

        #dbcursor.execute(
        #    "CREATE TABLE IF NOT EXISTS sections ("
        #    "sectionid STRING Primary Key, "
        #    "next_processing_timestamp INT"
        #    ")"
        #)

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

    coins = [x.lower() for x in config.get("blacklist", "stable-and-fiat")]

    if base.lower() in coins and coin.lower() in coins:
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

    categories = ["down", "up", "3L", "3S"]
    for category in categories:
        if config.has_option(marketcode, f"add-{category}-pairs") and config.getboolean(marketcode, f"add-{category}-pairs"):
            exclude = category.lower() in coin.lower()

        if exclude:
            logger.info(
                f"Base {base} and coin {coin} excluded based on 'add-{category}-pairs'."
            )
            break

    return exclude


def handle_delisting():
    """Handle delisting of pairs and coins"""

    if not config.getboolean("binance_delist", "enable"):
        return

    loop = asyncio.get_event_loop()
    coroutine = get_binance_announcement_data(logger)
    data = loop.run_until_complete(coroutine)

    logger.info(
        f"Received data: {data}"
    )

    coinlist = []
    pairlist = []
    for entry in data:
        pairs = entry["pairs"]

        tmplist = pairs.split(",")
        for tmppair in tmplist:
            coin, base = tmppair.split("/")

            coin = coin.strip()
            base = base.strip()

            pair = f"{base}_{coin}"
            if pair not in pairlist:
                pairlist.append(pair)
            
            if coin not in coinlist:
                coinlist.append(coin)

    logger.info(
        f"Coins: {coinlist}. \nPairs: {pairlist}"
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
#api = init_threecommas_api(config)

# Initialize or open the database
db = open_blacklist_db()
cursor = db.cursor()

# Refresh coin pairs based on CoinMarketCap data
while True:

    # Reload config files and refetch data to catch changes
    config = load_config()
    logger.info(f"Reloaded configuration from '{datadir}/{program}.ini'")

    handle_delisting()
    exit(0)

    # Get the current blacklist
    blacklist = get_threecommas_blacklist(logger, api)
    logger.info(
        f"Current blacklist: {blacklist}"
    )

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
