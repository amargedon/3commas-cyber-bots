#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import configparser
from math import fabs
import os
import sqlite3
import sys
import time
from pathlib import Path
from helpers.database import get_next_process_time, set_next_process_time

from helpers.datasources import (
    get_coinmarketcap_data
)
from helpers.logging import Logger, NotificationHandler
from helpers.misc import (
    unix_timestamp_to_string,
    wait_time_interval,
)


def load_config():
    """Create default or load existing config file."""

    cfg = configparser.ConfigParser()
    if cfg.read(f"{datadir}/{program}.ini"):
        return cfg

    cfg["settings"] = {
        "timezone": "Europe/Amsterdam",
        "timeinterval": 900,
        "cleanup-treshold": 86400,
        "debug": False,
        "logrotate": 7,
        "cmc-apikey": "Your CoinMarketCap API Key",
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }
    cfg["cmc_btc"] = {
        "start-number": 1,
        "end-number": 200,
        "timeinterval": 3600,
        "percent-change-compared-to": "BTC",
    }
    cfg["cmc_usd"] = {
        "start-number": 1,
        "end-number": 200,
        "timeinterval": 3600,
        "percent-change-compared-to": "USD",
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


def upgrade_config(cfg):
    """Upgrade config file if needed."""

    logger.info(
        "No configuration file upgrade required at this moment."
    )

    return cfg


def open_mc_db():
    """Create or open database to store data."""

    try:
        dbname = "marketdata.sqlite3"
        dbpath = f"file:{sharedir}/{dbname}?mode=rw"
        dbconnection = sqlite3.connect(dbpath, uri=True)
        dbconnection.row_factory = sqlite3.Row

        logger.info(f"Database '{sharedir}/{dbname}' opened successfully")

    except sqlite3.OperationalError:
        dbconnection = sqlite3.connect(f"{sharedir}/{dbname}")
        dbconnection.row_factory = sqlite3.Row
        dbcursor = dbconnection.cursor()
        logger.info(f"Database '{sharedir}/{dbname}' created successfully")

        dbcursor.execute(
            "CREATE TABLE IF NOT EXISTS pairs ("
            "base STRING, "
            "coin STRING, "
            "last_updated INT, "
            "PRIMARY KEY(base, coin)"
            ")"
        )

        dbcursor.execute(
            "CREATE TABLE IF NOT EXISTS rankings ("
            "base STRING, "
            "coin STRING, "
            "coinmarketcap INT DEFAULT 0, "
            "altrank INT DEFAULT 0, "
            "galaxyscore FLOAT DEFAULT 0.0, "
            "PRIMARY KEY(base, coin)"
            ")"
        )

        dbcursor.execute(
            "CREATE TABLE IF NOT EXISTS prices ("
            "base STRING, "
            "coin STRING, "
            "change_1h FLOAT DEFAULT 0.0, "
            "change_24h FLOAT DEFAULT 0.0, "
            "change_7d FLOAT DEFAULT 0.0, "
            "volatility_24h FLOAT DEFAULT 0.0, "
            "PRIMARY KEY(base, coin)"
            ")"
        )

        dbcursor.execute(
            "CREATE TABLE IF NOT EXISTS sections ("
            "sectionid STRING Primary Key, "
            "next_processing_timestamp INT"
            ")"
        )

        logger.info("Database tables created successfully")

    return dbconnection


def has_pair(base, coin):
    """Check if pair already exists in database."""

    return cursor.execute(
            f"SELECT * FROM pairs WHERE base = '{base}' AND coin = '{coin}'"
        ).fetchone()


def add_pair(base, coin):
    """Add a new base_coin to the tables in the database"""

    logger.debug(
        f"Add pair {base}_{coin} to database."
    )

    db.execute(
        f"INSERT INTO pairs ("
        f"base, "
        f"coin, "
        f"last_updated "
        f") VALUES ("
        f"'{base}', '{coin}', {int(time.time())}"
        f")"
    )
    db.execute(
        f"INSERT INTO rankings ("
        f"base, "
        f"coin "
        f") VALUES ("
        f"'{base}', '{coin}'"
        f")"
    )
    db.execute(
        f"INSERT INTO prices ("
        f"base, "
        f"coin "
        f") VALUES ("
        f"'{base}', '{coin}'"
        f")"
    )
    # db.commit() left out on purpose


def remove_pair(base, coin):
    """Remove a base_coin from the tables in the database"""

    logger.debug(
        f"Remove pair {base}_{coin} from database."
    )

    db.execute(
        f"DELETE FROM pairs "
        f"WHERE base = '{base}' AND coin = '{coin}'"
    )
    db.execute(
        f"DELETE FROM rankings "
        f"WHERE base = '{base}' AND coin = '{coin}'"
    )
    db.execute(
        f"DELETE FROM prices "
        f"WHERE base = '{base}' AND coin = '{coin}'"
    )
    # db.commit() left out on purpose


def update_pair_last_updated(base, coin):
    """Update the pair's last updated value in database."""

    db.execute(
        f"UPDATE pairs SET last_updated = {int(time.time())} "
        f"WHERE base = '{base}' AND coin = '{coin}'"
    )
    # db.commit() left out on purpose


def update_values(table, base, coin, data):
    """Update one or more specific field(s) in a single table in the database"""

    query = f"UPDATE {table} SET "

    keyvalues = ""
    for key, value in data.items():
        if keyvalues:
            keyvalues += ", "

        keyvalues += f"{key} = {value}"

    query += keyvalues
    query += f" WHERE base = '{base}' AND coin = '{coin}'"

    logger.debug(
        f"Execute query '{query}' for pair {base}_{coin}."
    )

    db.execute(
        query
    )
    # db.commit() left out on purpose


def process_cmc_section(section_id):
    """Process the cmc section from the configuration"""

    # Download CoinMarketCap data
    startnumber = int(config.get(section_id, "start-number"))
    endnumber = 1 + (int(config.get(section_id, "end-number")) - startnumber)
    base = config.get(section_id, "percent-change-compared-to")

    baselist = ("BNB", "BTC", "ETH", "EUR", "USD")
    if base not in baselist:
        logger.error(
            f"Percent change ('{base}') must be one of the following: "
            f"{baselist}"
        )
        return False

    data = get_coinmarketcap_data(
        logger, config.get("settings", "cmc-apikey"), startnumber, endnumber, base
    )

    # Check if CMC replied with an error
    # 0: errorcode
    # 1: errormessage
    # 2: cmc data
    if data[0] != -1:
        logger.error(
            f"Received error {data[0]}: {data[1]}. "
            f"Stop processing and retry in 24h again."
        )

        # And exit loop so we can wait 24h before trying again
        return False

    for entry in data[2]:
        try:
            coin = entry["symbol"]

            # The base could be as coin inside the list, and then skip it
            if base == coin:
                continue

            rank = entry["cmc_rank"]
            coinpercent1h = fabs(float(entry["quote"][base]["percent_change_1h"]))
            coinpercent24h = fabs(float(entry["quote"][base]["percent_change_24h"]))
            coinpercent7d = fabs(float(entry["quote"][base]["percent_change_7d"]))

            if not has_pair(base, coin):
                # Pair does not yet exist
                add_pair(base, coin)

            # Update rankings data
            rankdata = {}
            rankdata["coinmarketcap"] = rank
            update_values("rankings", base, coin, rankdata)

            # Update pricings data
            pricesdata = {}
            pricesdata["change_1h"] = coinpercent1h
            pricesdata["change_24h"] = coinpercent24h
            pricesdata["change_7d"] = coinpercent7d
            update_values("prices", base, coin, pricesdata)

            # Make sure to update the last_updated field to avoid deletion
            update_pair_last_updated(base, coin)

            # Commit everyting for this coin to the database
            db.commit()
        except KeyError as err:
            logger.error(
                "Something went wrong while parsing CoinMarketCap data. KeyError for field: %s"
                % err
            )
            return False

    logger.info(
        f"{base}: updated {len(data[2])} coins.",
        True
    )

    # No exceptions or other cases happened, everything went Ok
    return True


def cleanup_database():
    """Cleanup the database and remove old / not updated data"""

    cleanuptime = int(time.time()) - int(config.get("settings", "cleanup-treshold"))

    logger.debug(
        f"Remove data older than "
        f"{unix_timestamp_to_string(cleanuptime, '%Y-%m-%d %H:%M:%S')}."
    )

    pairdata = cursor.execute(
            f"SELECT base, coin FROM pairs WHERE last_updated < {cleanuptime}"
        ).fetchall()

    if pairdata:
        logger.info(f"Found {len(pairdata)} pairs to cleanup...")

        for entry in pairdata:
            remove_pair(entry[0], entry[1])

        # Commit everyting to the database
        db.commit()
    else:
        logger.debug(
            "No pair data to cleanup."
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

# pylint: disable-msg=C0103
if args.sharedir:
    sharedir = args.sharedir
else:
    print("This script requires the sharedir to be used (-s option)!")
    sys.exit(0)

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


# Initialize or open the database
db = open_mc_db()
cursor = db.cursor()

# Refresh market data based on several data sources
while True:

    # Reload config files and refetch data to catch changes
    config = load_config()
    logger.info(f"Reloaded configuration from '{datadir}/{program}.ini'")

    # Configuration settings
    timeint = int(config.get("settings", "timeinterval"))

    # Current time to determine which sections to process
    starttime = int(time.time())

    # House keeping
    cleanup_database()

    for section in config.sections():
        if section.startswith("cmc_"):
            sectiontimeinterval = int(config.get(section, "timeinterval"))
            nextprocesstime = get_next_process_time(db, "sections", "sectionid", section)

            # Only process the section if it's time for the next interval, or
            # time exceeds the check interval (clock has changed somehow)
            if starttime >= nextprocesstime or (
                    abs(nextprocesstime - starttime) > sectiontimeinterval
            ):
                process_cmc_section(section)

                # Determine new time to process this section
                newtime = starttime + sectiontimeinterval
                set_next_process_time(db, "sections", "sectionid", section, newtime)
            else:
                logger.debug(
                    f"Section {section} will be processed after "
                    f"{unix_timestamp_to_string(nextprocesstime, '%Y-%m-%d %H:%M:%S')}."
                )
        elif section != "settings":
            logger.warning(
                f"Section '{section}' not processed (prefix 'cmc_' missing)!",
                False
            )

    if not wait_time_interval(logger, notification, timeint, False):
        break