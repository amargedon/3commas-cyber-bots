#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import aiocron
import argparse
import configparser
import json
from math import nan
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

from telethon import TelegramClient, events

from helpers.logging import Logger, NotificationHandler
from helpers.misc import unix_timestamp_to_string
from helpers.smarttrade import (
    construct_smarttrade_position,
    construct_smarttrade_stoploss,
    construct_smarttrade_takeprofit,
    get_smarttrade_direction,
    is_valid_smarttrade
)
from helpers.threecommas import (
    get_threecommas_currency_rate,
    init_threecommas_api,
    load_blacklist,
    prefetch_marketcodes
)
from helpers.threecommas_smarttrade import (
    cancel_threecommas_smarttrade,
    close_threecommas_smarttrade,
    get_threecommas_smarttrades,
    open_threecommas_smarttrade
)
from helpers.watchlist import (
    process_botlist
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
        "tgram-phone-number": "Your Telegram Phone number",
        "tgram-api-id": "Your Telegram API ID",
        "tgram-api-hash": "Your Telegram API Hash",
        "generate-pair-json": False,
        "generate-pair-lifetime": 86400,
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }

    cfg["custom"] = {
        "channel-name": "Telegram Channel to watch",
        "usdt-botids": [12345, 67890],
        "btc-botids": [12345, 67890],
    }

    cfg["hodloo_5"] = {
        "exchange": "Bittrex / Binance / Kucoin",
        "bnb-botids": [12345, 67890],
        "btc-botids": [12345, 67890],
        "busd-botids": [12345, 67890],
        "eth-botids": [12345, 67890],
        "eur-botids": [12345, 67890],
        "usdt-botids": [12345, 67890],
    }

    cfg["hodloo_10"] = {
        "exchange": "Bittrex / Binance / Kucoin",
        "bnb-botids": [12345, 67890],
        "btc-botids": [12345, 67890],
        "busd-botids": [12345, 67890],
        "eth-botids": [12345, 67890],
        "eur-botids": [12345, 67890],
        "usdt-botids": [12345, 67890],
    }

    cfg["smarttrade"] = {
        "channel-names": json.dumps(["channel 1", "channel 2"]),
    }

    cfg["smarttrade_settings_channel 1"] = {
        "account-id": 123456789,
        "amount-usdt": 100.0,
        "amount-btc": 0.001,
        "entry-strategy": "market/limit",
        "entry-limit-option": "low/high/average",
        "entry-limit-deviation": 0.0,
        "target-price-deviation": 0.0,
        "botids": [12345, 67890],
    }

    cfg["smarttrade_settings_channel 2"] = {
        "account-id": 123456789,
        "amount-usdt": 100.0,
        "amount-btc": 0.001,
        "entry-strategy": "market/limit",
        "entry-limit-option": "low/high/average",
        "entry-limit-deviation": 0.0,
        "target-price-deviation": 0.0,
        "botids": [12345, 67890],
    }

    with open(f"{datadir}/{program}.ini", "w", encoding = "utf-8") as cfgfile:
        cfg.write(cfgfile)

    return None


def upgrade_config(thelogger, cfg):
    """Upgrade config file if needed."""

    if not cfg.has_option("settings", "generate-pair-json"):
        cfg.set("settings", "generate-pair-json", "False")
        cfg.set("settings", "generate-pair-lifetime", "86400")

        with open(f"{datadir}/{program}.ini", "w+", encoding = "utf-8") as cfgfile:
            cfg.write(cfgfile)

        thelogger.info("Upgraded the configuration file")

    return cfg


def open_watchlist_db():
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
            "CREATE TABLE IF NOT EXISTS coins ("
            "coin STRING Primary Key, "
            "timestamp INT"
            ")"
        )

        logger.info("Database tables created successfully")

    return dbconnection


async def handle_custom_event(event):
    """Handle the received Telegram event"""

    logger.info(
        "Received custom message '%s'"
        % (event.message.text.replace("\n", " - "))
    )

    # Parse the event and do some error checking
    trigger = event.raw_text.splitlines()

    try:
        exchange = trigger[0].replace("\n", "")
        pair = trigger[1].replace("#", "").replace("\n", "")
        base = pair.split("_")[0].replace("#", "").replace("\n", "")
        coin = pair.split("_")[1].replace("\n", "")

        # Fix for future pair format
        if coin.endswith(base) and len(coin) > len(base):
            coin = coin.replace(base, "")

        trade = trigger[2].replace("\n", "")
        if trade == "LONG" and len(trigger) == 4 and trigger[3] == "CLOSE":
            trade = "CLOSE"
    except IndexError:
        logger.error("Invalid trigger message format!")
        return

    if exchange.lower() not in ("binance", "ftx", "kucoin"):
        logger.warning(
            f"Exchange '{exchange}' is not yet supported."
        )
        return

    if trade not in ('LONG', 'CLOSE'):
        logger.warning(f"Trade type '{trade}' is not supported yet!")
        return

    if base == "USDT":
        botids = json.loads(config.get("custom", "usdt-botids"))
        if len(botids) == 0:
            logger.warning(
                f"No valid usdt-botids configured for '{base}', cannot start "
                f"a deal for '{coin}'"
            )
            return
    elif base == "BTC":
        botids = json.loads(config.get("custom", "btc-botids"))
        if len(botids) == 0:
            logger.warning(
                f"No valid btc-botids configured for '{base}', cannot start "
                f"a deal for '{coin}'"
            )
            return
    else:
        logger.error(
            f"The base of pair '{pair}' being '{base}' is not supported yet!"
        )
        return

    if len(botids) == 0:
        logger.warning(
            f"{base}_{coin}: no valid botids configured for base '{base}'."
        )
        return

    await client.loop.run_in_executor(
        None, process_botlist, logger, api, blacklistfile, blacklist, marketcodecache,
                                botids, coin, trade
    )


async def handle_telegram_smarttrade_event(source, event):
    """Handle the received Telegram event"""

    # Parse the event and do some error checking
    data = event.raw_text.splitlines()

    try:
        # Check if some prashes are in the message, otherwise it's not
        # required to start parsing the message at all
        searchphrases = [
            "Targets",
            "Target 1",
            "TP1",
            "SL",
            "Buy Between",
            "Incase Of Breakout Expecting"
        ]

        if any(phrase in event.message.text for phrase in searchphrases):
            logger.info(f"Received {source} message: {data}", True)

            parse_event(source, data)
        else:
            logger.info(
                f"Received {source} message which didn't pass the required word filter"
            )
    except Exception as exception:
        logger.error(f"Exception occured: {exception}")


def parse_event(source, event_data):
    """Parse the data of an event and extract trade data"""

    coin = None
    pair = None
    entries = list()
    targets = list()
    stoploss = nan

    logger.info(f"Parsing received event from '{source}': {event_data}")

    searchlistpair = ["/USDT", "/BTC", "#"]
    searchlistentry = ["Buy Between"]
    searchlisttarget = ["Target", "Tp 1", "Tp 2", "Tp 3", "Tp 4"]
    searchliststoploss = ["Stoploss", "SL:", "Stop loss"]

    for event_line in event_data:
        if any(word in event_line for word in searchlistpair):
            coin, pair = parse_smarttrade_pair(event_line)
        elif any(word in event_line for word in searchlistentry):
            parse_smarttrade_entry(event_line, entries)
        elif any(word in event_line for word in searchlisttarget):
            parse_smarttrade_target(event_line, targets)
        elif any(word in event_line for word in searchliststoploss):
            stoploss = parse_smarttrade_stoploss(event_line)

    if coin is None or pair is None:
        logger.warning(
            "No pair found in event. Cannot create any deal."
        )
        return -1

    # Try to open a SmartTrade
    dealid = process_for_smarttrade(source, pair, entries, targets, stoploss)

    # Try to start a DCA deal
    process_for_dca(source, pair, "long")

    # Store the pair for external usage
    if sharedir and config.getboolean("settings", "generate-pair-json"):
        process_for_storage(coin)

    # Return the SmartTrade deal id
    return dealid


def process_for_smarttrade(source, pair, entry_list, target_list, stoploss):
    """Process the event further for smarttrade"""

    if entry_list is None or len(entry_list) == 0:
        logger.warning(
            "No entries found in event. Cannot create a SmartTrade."
        )
        return -1

    if target_list is None or len(target_list) == 0:
        logger.warning(
            "No targets found in event. Cannot create a SmartTrade."
        )
        return -1

    # Check if there is already a deal active for this pair
    accountid = config.get(f"smarttrade_settings_{source}", "account-id")
    smarttradedata = get_threecommas_smarttrades(
        logger, api, accountid, "active", pair, "smart_trade"
    )
    if smarttradedata:
        logger.warning(
            f"Smart_trade {smarttradedata[0]['id']} already active for "
            f"pair {pair} on this account. Not starting a new one!"
        )
        return -1

    direction = get_smarttrade_direction(target_list)

    # Calculate the units and price to buy them for. Unitpricedata contains:
    # 0 - Order type (market, limit)
    # 1 - Units
    # 2 - Price
    unitpricedata = calculate_position_units_price(source, pair, entry_list)

    # Calculate the volume for each target, and update the price according
    # to the configuration
    calculate_target_price_volume(source, target_list)

    dealid = 0
    if is_valid_smarttrade(logger, unitpricedata, target_list, stoploss, direction):
        message = (
            f"New smarttrade received ({direction}) "
            f"for {pair} with entry '{entry_list}', "
            f"targets '{target_list}' "
            f"and stoploss '{stoploss}'. "
        )

        positiontype = "buy" if direction == "long" else "sell"
        positiondata = construct_smarttrade_position(
            positiontype, unitpricedata[0], unitpricedata[1], unitpricedata[2]
        )
        logger.info(
            f"Position {positiondata} created."
        )

        takeprofitdata = construct_smarttrade_takeprofit("limit", target_list)
        logger.info(
            f"Takeprofit {takeprofitdata} created."
        )

        stoplossdata = construct_smarttrade_stoploss("limit", stoploss)
        logger.info(
            f"Stoploss {stoplossdata} created."
        )

        data = open_threecommas_smarttrade(
            logger, api, accountid, pair, f"Deal started based on signal from {source}",
            positiondata, takeprofitdata, stoplossdata
        )
        dealid = handle_open_smarttrade_data(data)

        message += (
            f"\nStarted trade {dealid} with entry {entry_list}, "
            f"targets {target_list} and stoploss {stoplossdata}."
        )

        logger.info(message, True)
    else:
        logger.error("Cannot start smarttrade because of invalid data.")

    return dealid


def process_for_dca(source, pair, direction):
    """Process the event further for DCA deal"""

    botids = json.loads(config.get(f"smarttrade_settings_{source}", "botids"))
    if len(botids) > 0:
        process_botlist(logger, api, blacklistfile, blacklist, marketcodecache,
                            botids, pair.split("_")[1], direction
        )


def process_for_storage(coin):
    """Process the coin and store it"""

    # Store coin, and remove in two days
    removetime = int(time.time()) + config.getint("settings", "generate-pair-lifetime")

    db.execute(
        f"INSERT OR REPLACE INTO coins ("
        f"coin, "
        f"timestamp "
        f") VALUES ("
        f"'{coin}', {removetime}"
        f")"
    )
    db.commit()

    logger.info(
        f"Stored coin {coin} until {unix_timestamp_to_string(removetime, '%Y-%m-%d %H:%M:%S')}"
    )

    write_pair_file()


def write_pair_file():
    """Write the json pair file to disk"""

    coinlist = [c[0] for c in db.execute(
        f"SELECT coin FROM coins"
    ).fetchall()]

    pairdata = {
        "pairs": []
    }

    baselist = ["BNB", "BTC", "ETH", "BUSD", "USDT", "TUSD"]
    for coin in coinlist:
        for base in baselist:
            pair = f"{coin}/{base}"
            pairdata["pairs"].append(pair)

    filename = f"{sharedir}/tradepairs.json"

    # Serializing json
    json_object = json.dumps(pairdata, indent = 2)
    
    # Writing to sample.json
    with open(filename, "w") as outfile:
        outfile.write(json_object)

    logger.debug(
        f"Wrote {len(coinlist)} coins to {filename}."
    )

@aiocron.crontab('*/10 * * * *')
async def cleanup_stored_coins():
    """Remove coins from database"""

    currenttime = int(time.time())

    db.execute(
        f"DELETE FROM coins WHERE timestamp <= {currenttime}"
    )
    db.commit()

    write_pair_file()

def handle_open_smarttrade_data(data):
    """Handle the return data of 3C"""

    dealid = -1

    if data is not None:
        dealid = data["id"]

    return dealid


def parse_smarttrade_pair(data):
    """Parse data and extract pair data"""

    pair = None
    coin = None

    # Use casefold to search case insensitive
    if "/USDT".casefold() in data.casefold() or "/BTC".casefold() in data.casefold():
        pairdata = data.split(" ")[0].split("/")
        base = pairdata[1].replace("#", "")
        coin = pairdata[0].replace("#", "")
    elif "#" in data:
        base = "USDT"
        pairdata = data.split(" ")
        logger.info(f"Parsing pairdata {pairdata}")

        for line in pairdata:
            if "#" in line:
                coinorpair = line.replace("#", "")

                if "/" in coinorpair:
                    coin = coinorpair.split('/')[0].upper()
                elif "BTC" in coinorpair.upper():
                    base = "BTC"
                    coin = coinorpair.upper().replace("BTC", "")
                else:
                    coin = coinorpair.upper()

                break

    pair = f"{base}_{coin}"

    logger.info(f"Pair '{pair}' found in {data} (base: {base}, coin: {coin}).")

    return coin, pair


def parse_smarttrade_entry(data, entry_list):
    """Parse data and extract entrie(s) data"""

    convertsatoshi = False
    if "satoshi" in data:
        convertsatoshi = True

    entrydata = re.findall(r"[0-9]{1,5}[.,]\d{1,8}k?|[0-9]{2,}k?", data)
    for price in entrydata:
        if convertsatoshi:
            price = float(price) * 0.00000001
        if isinstance(price, str) and "k" in price:
            price = float(price.replace("k", ""))
            price *= 1000.0
        else:
            price = float(price)

        entry_list.append(price)

    logger.info(f"Entries '{entry_list}' found in {data} (regex returned {entrydata}).")


def parse_smarttrade_target(data, target_list):
    """Parse data and extract target(s) data"""

    convertsatoshi = False
    if "satoshi" in data:
        convertsatoshi = True

    tpdata = re.findall(r"[0-9]{1,5}[.,]\d{1,8}k?|[0-9]{2,}k?", data.split("(")[0])
    for takeprofit in tpdata:
        step = {}

        price = takeprofit
        if convertsatoshi:
            price = float(price) * 0.00000001
        if isinstance(price, str) and "k" in price:
            price = float(price.replace("k", ""))
            price *= 1000.0
        else:
            price = float(price)

        step["price"] = price
        step["volume"] = 0

        target_list.append(step)

        logger.info(f"Take Profit of '{takeprofit}' found in {data} (regex returned {tpdata}).")


def calculate_position_units_price(source, pair, entry_list):
    """Calculate the price to open the position on"""

    price = float(get_threecommas_currency_rate(logger, api, "binance", pair))

    ordertype = config.get(f"smarttrade_settings_{source}", "entry-strategy")
    if ordertype == "limit":
        if config.get(f"smarttrade_settings_{source}", "entry-limit-option") == "low":
            price = min(entry_list)
        elif config.get(f"smarttrade_settings_{source}", "entry-limit-option") == "high":
            price = max(entry_list)
        elif config.get(f"smarttrade_settings_{source}", "entry-limit-option") == "average":
            price = sum(entry_list) / len(entry_list)

    deviation = config.getfloat(f"smarttrade_settings_{source}", "entry-limit-deviation")
    if deviation != 0.0:
        price = price * ((100.0 + deviation) / 100.0)

    amount = config.getfloat(f"smarttrade_settings_{source}", "amount-usdt")
    if "BTC" in pair:
        amount = config.getfloat(f"smarttrade_settings_{source}", "amount-btc")

    units = amount
    if not ("USDT" in pair and "BTC" in pair):
        units /= price

    logger.info(
        f"Calculated units {units} based on amount {amount} and price {price}"
    )

    return ordertype, units, price


def calculate_target_price_volume(source, target_list):
    """Calculate the price and volume of each target"""

    quotient, remainder = divmod(100, len(target_list))
    logger.info(
        f"Calculated quotient of {quotient} and remainder {remainder} "
        f"based on len {len(target_list)}"
    )

    deviation = config.getfloat(f"smarttrade_settings_{source}", "target-price-deviation")

    for step in target_list:
        # Adjust the price if specified in the configuration
        if deviation != 0.0:
            step["price"] *= (100.0 + deviation) / 100.0

        # Volume is calculated based on number of targets. This could be a float result
        # and result in a volume of less than 100% due to rounding. So, the quotient is
        # calculated for every target and the remaining volume is added to the first target
        step["volume"] = quotient

    target_list[0]["volume"] += remainder


def parse_smarttrade_stoploss(data):
    """Parse data and extract stoploss data"""

    stoploss = nan

    sldata = re.search(r"[0-9]{1,5}[.,]\d{1,8}k?|[0-9]{2,}k?", data)
    if sldata is not None:
        stoploss = sldata.group()
        if "k" in stoploss:
            stoploss = float(stoploss.replace("k", ""))
            stoploss *= 1000.0
        else:
            stoploss = float(stoploss)

    logger.info(f"Stoploss of '{stoploss}' found in {data} (regex returned {sldata}).")

    return stoploss


async def handle_hodloo_event(category, event):
    """Handle the received Telegram event"""

    logger.info(
        "Received message on Hodloo %s: '%s'"
        % (category, event.message.text.replace("\n", " - "))
    )

    # Parse the event and do some error checking
    trigger = event.raw_text.splitlines()

    pair = trigger[0].replace("\n", "").replace("**", "")
    base = pair.split("/")[1]
    coin = pair.split("/")[0]

    logger.info(
        f"Received message on {category}% for {base}_{coin}"
    )

    if base.lower() not in ("bnb", "btc", "busd", "eth", "eur", "usdt"):
        logger.warning(
            f"{base}_{coin}: base '{base}' is not yet supported."
        )
        return

    botids = get_hodloo_botids(category, base)

    if len(botids) == 0:
        logger.warning(
            f"{base}_{coin}: no valid botids configured for base '{base}'."
        )
        return

    await client.loop.run_in_executor(
        None, process_botlist, logger, api, blacklistfile, blacklist, marketcodecache,
                                botids, coin, "LONG"
    )


def get_hodloo_botids(category, base):
    """Get list of botids from configuration based on category and base"""

    return json.loads(config.get(f"hodloo_{category}", f"{base.lower()}-botids"))


def get_smarttrade_botids(smarttrade_channels):
    """Get list of botids from configuration used for smarttrades"""

    botids = []

    for channel in smarttrade_channels:
        if config.has_option(f"smarttrade_settings_{channel}", "botids"):
            botids += json.loads(config.get(f"smarttrade_settings_{channel}", "botids"))

    return botids


def is_config_ok(hl5_exchange, hl10_exchange, smarttrade_channels):
    """Check if the configuration is complete"""

    configok = True

    if hl5_exchange not in ("none", "Bittrex", "Binance", "Kucoin"):
        logger.error(
            f"Exchange {hl5_exchange} not supported. Must be 'Bittrex', 'Binance' or 'Kucoin'!"
        )
        configok = False

    if hl10_exchange not in ("none", "Bittrex", "Binance", "Kucoin"):
        logger.error(
            f"Exchange {hl10_exchange} not supported. Must be 'Bittrex', 'Binance' or 'Kucoin'!"
        )
        configok = False

    for channel in smarttrade_channels:
        if not config.has_section(f"smarttrade_settings_{channel}"):
            logger.error(
                f"Channel {channel} should be read, but required "
                f"smarttrade_settings_{channel} section is missing!"
            )
            configok = False

        if config.get(f"smarttrade_settings_{channel}", "entry-strategy") not in ("market", "limit"):
            logger.error(
                f"Channel {channel} is having an invalid entry-strategy. "
                f"Allowed options: 'market' or 'limit'."
            )
            configok = False

        if config.get(f"smarttrade_settings_{channel}", "entry-limit-option") not in ("low", "high", "average"):
            logger.error(
                f"Channel {channel} is having an invalid entry-limit-option. "
                f"Allowed options: 'low', 'high' or 'average'."
            )
            configok = False

        if not config.has_option(f"smarttrade_settings_{channel}", "entry-limit-deviation"):
            logger.error(
                f"Channel {channel} is missing the entry-limit-deviation. "
            )
            configok = False

        if not config.has_option(f"smarttrade_settings_{channel}", "target-price-deviation"):
            logger.error(
                f"Channel {channel} is missing the target-price-deviation. "
            )
            configok = False

    return configok


def run_tests():
    """Some tests which can be run to test data processing"""

    logger.info("Running some test cases. Should not happen when running for you!!!")

    data = list()

    if False:
        # Format for Forex Trading
        data.clear()
        data.append(r'LTO/BTC')
        data.append(r'LTO Network has established itself as Europeâ€™s leading blockchain with strong real-world usage.')
        data.append(r'Technically lying above strong support. RSI is in the oversold region. MACD is showing bullish momentum. It will pump hard from here. so now is the right time to build your position in it before breakout for massive profitsðŸ˜Š')
        data.append(r'')
        data.append(r'Targets: 493-575-685-795 satoshi')
        tradeid = parse_event("***** Manually testing the script *****", data)
        time.sleep(10) #Pause for some time, allowing 3C to open the deal before we can close it
        if not close_threecommas_smarttrade(logger, api, tradeid):
            cancel_threecommas_smarttrade(logger, api, tradeid)

    if False:
        # Format for Forex Trading
        data.clear()
        data.append(r'LTO/USDT lying above strong support. Stochastic is giving a buying signal. It will bounce hard from here. so now is the right time to build your position in it before breakout for massive profitsðŸ˜Š')
        data.append(r'')
        data.append(r'Targets: $0.1175-0.1575-0.2015-0.2565')
        data.append(r'SL: $0.0952')
        tradeid = parse_event("***** Manually testing the script *****", data)
        time.sleep(10) #Pause for some time, allowing 3C to open the deal before we can close it
        if not close_threecommas_smarttrade(logger, api, tradeid):
            cancel_threecommas_smarttrade(logger, api, tradeid)

    if False:
        data.clear()
        data.append(r'Longing #SAND')
        data.append(r'Lev - 5x')
        data.append(r'Single Entry around CMP1.354')
        data.append(r'Stoploss - H4 close below 1.3$')
        data.append(r'Targets - 1.385 - 1.42 - 1.48 - 1.72 (25% Each)')
        data.append(r'@Forex_Tradings')
        tradeid = parse_event("***** Manually testing the script *****", data)
        time.sleep(10) #Pause for some time, allowing 3C to open the deal before we can close it
        if not close_threecommas_smarttrade(logger, api, tradeid):
            cancel_threecommas_smarttrade(logger, api, tradeid)

    if False:
        data.clear()
        data.append(r'#BTC/USDT (Swing Short)')
        data.append(r'Lev - 5x')
        data.append(r'Entry 1 - 24350 (50%)')
        data.append(r'Entry 2 - 25.5k (50%)')
        data.append(r'Stoploss - Daily Close above 26k')
        data.append(r'Targets - 23.5k - 22.6k - 21.5k - 20k - 17k')
        tradeid = parse_event("***** Manually testing the script *****", data) # Need to test
        time.sleep(10) #Pause for some time, allowing 3C to open the deal before we can close it
        if not close_threecommas_smarttrade(logger, api, tradeid):
            cancel_threecommas_smarttrade(logger, api, tradeid)

    if False:
        data.clear()
        data.append(r'#AAVE ')
        data.append(r'Breakout Targets - 92 - 105 - 127 - 153 - 178 - 250 ')
        tradeid = parse_event("***** Manually testing the script *****", data)
        time.sleep(10) #Pause for some time, allowing 3C to open the deal before we can close it
        if not close_threecommas_smarttrade(logger, api, tradeid):
            cancel_threecommas_smarttrade(logger, api, tradeid)

    if False:
        # Format for World Of Charts (Crypto)
        data.clear()
        data.append(r'#Perl')
        data.append(r'Buy Between 0.02 - 0.023')
        data.append(r'')
        data.append(r'Stop loss 0.033')
        data.append(r'')
        data.append(r'Tp 1 0.04')
        data.append(r'')
        data.append(r'Tp 2 0.046')
        data.append(r'')
        data.append(r'Tp 3 0.052')
        data.append(r'')
        data.append(r'Tp 4 0.058')
        tradeid = parse_event("My Test Channel", data)
        time.sleep(10) #Pause for some time, allowing 3C to open the deal before we can close it
        if not close_threecommas_smarttrade(logger, api, tradeid):
            cancel_threecommas_smarttrade(logger, api, tradeid)

    if False:
        # Format for World Of Charts (Crypto)
        data.clear()
        data.append(r'#Snx')
        data.append(r'Buy Between 2.40 - 2.65')
        data.append(r'')
        data.append(r'Stop loss 1.80')
        data.append(r'')
        data.append(r'Tp 1 3')
        data.append(r'')
        data.append(r'Tp 2 3.40')
        data.append(r'')
        data.append(r'Tp 3 3.80')
        data.append(r'')
        data.append(r'Tp 4 4.20')
        tradeid = parse_event("My Test Channel", data)
        time.sleep(10) #Pause for some time, allowing 3C to open the deal before we can close it
        if not close_threecommas_smarttrade(logger, api, tradeid):
            cancel_threecommas_smarttrade(logger, api, tradeid)

    if False:
        #TODO: still have to test this one
        # Format for World Of Charts (Crypto)
        data.clear()
        data.append(r'#Pivxbtc')
        data.append(r'Buy Between 0.00001700 - 0.00001800')
        data.append(r'')
        data.append(r'Stop loss 0.0.00001500')
        data.append(r'')
        data.append(r'Tp 1 0.00002050')
        data.append(r'')
        data.append(r'Tp 2 0.00002300')
        data.append(r'')
        data.append(r'Tp 3 0.00002550')
        tradeid = parse_event("My Test Channel", data)
        time.sleep(10) #Pause for some time, allowing 3C to open the deal before we can close it
        if not close_threecommas_smarttrade(logger, api, tradeid):
            cancel_threecommas_smarttrade(logger, api, tradeid)


# Start application
program = Path(__file__).stem

# Parse and interpret options.
parser = argparse.ArgumentParser(description="Cyberjunky's 3Commas bot helper.")
parser.add_argument(
    "-d", "--datadir", help="data directory to use", type=str
)
parser.add_argument(
    "-b", "--blacklist", help="blacklist to use", type=str
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
if args.blacklist:
    blacklistfile = f"{datadir}/{args.blacklist}"
else:
    blacklistfile = ""

# pylint: disable-msg=C0103
if args.sharedir:
    sharedir = args.sharedir
else:
    sharedir = None

# Create or load configuration file
config = load_config()
if not config:
    logger = Logger(datadir, program, None, 7, False, False)
    logger.info(
        f"Created example config file '{program}.ini', edit it and restart the program"
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

# Validation of data before starting
hl5exchange = config.get("hodloo_5", "exchange") if config.has_section("hodloo_5") else "none"
hl10exchange = config.get("hodloo_10", "exchange") if config.has_section("hodloo_10") else "none"
customchannelname = config.get("custom", "channel-name") if config.has_section("custom") else "none"
smarttradechannels = json.loads(config.get("smarttrade", "channel-names"))

if not is_config_ok(hl5exchange, hl10exchange, smarttradechannels):
    logger.error(
        "Configuration contains errors, script will exit!"
    )
    sys.exit(0)

# Initialize 3Commas API
api = init_threecommas_api(config)

# Initialize or open the database
db = open_watchlist_db()
cursor = db.cursor()

# Code to enable testing instead of waiting for events.
#run_tests()
#sys.exit(0)

# Prefetch marketcodes for all bots
# - Custom bots
allbotids = json.loads(config.get("custom", "usdt-botids")) + json.loads(config.get("custom", "btc-botids"))

# - Hodloo bots
hlcategories = []
if hl5exchange != "none":
    hlcategories.append("5")
if hl10exchange != "none":
    hlcategories.append("10")

for hlcategory in hlcategories:
    for hlbase in ("bnb", "btc", "busd", "eth", "eur", "usdt"):
        allbotids += get_hodloo_botids(hlcategory, hlbase)

# - DCA bots used for SmartTrades
allbotids += get_smarttrade_botids(smarttradechannels)

marketcodecache = prefetch_marketcodes(logger, api, allbotids)

# Prefetch blacklists
blacklist = load_blacklist(logger, api, blacklistfile)

# Telethon client for Telegram
client = TelegramClient(
    f"{datadir}/{program}",
    config.get("settings", "tgram-api-id"),
    config.get("settings", "tgram-api-hash"),
).start(config.get("settings", "tgram-phone-number"))

logger.info("Listing all subscribed TG Channels and on which to listen:")
for dialog in client.iter_dialogs():
    if dialog.is_channel:
        logger.info(
            f"{dialog.id}:{dialog.title}"
        )

        if customchannelname != "none" and dialog.title == customchannelname:
            logger.info(
                f"Listening to updates from '{dialog.title}' (id={dialog.id}) ...",
                True
            )
            @client.on(events.NewMessage(chats=dialog.id))
            async def callback_custom(event):
                """Receive Telegram message."""

                await handle_custom_event(event)
                notification.send_notification()

        elif hl5exchange != "none" and dialog.title == f"Hodloo {hl5exchange} 5%":
            logger.info(
                f"Listening to updates from '{dialog.title}' (id={dialog.id}) ...",
                True
            )
            @client.on(events.NewMessage(chats=dialog.id))
            async def callback_5(event):
                """Receive Telegram message."""

                await handle_hodloo_event("5", event)
                notification.send_notification()

        elif hl10exchange != "none" and dialog.title == f"Hodloo {hl10exchange} 10%":
            logger.info(
                f"Listening to updates from '{dialog.title}' (id={dialog.id}) ...",
                True
            )
            @client.on(events.NewMessage(chats=dialog.id))
            async def callback_10(event):
                """Receive Telegram message."""

                await handle_hodloo_event("10", event)
                notification.send_notification()

        elif dialog.title in smarttradechannels:
            logger.info(
                f"Listening to updates from '{dialog.title}' (id={dialog.id}) ...",
                True
            )
            @client.on(events.NewMessage(chats=dialog.id))
            async def callback_smarttrade(event):
                """Receive Telegram message."""

                chat_from = event.chat if event.chat else (await event.get_chat())
                await handle_telegram_smarttrade_event(chat_from.title, event)
                notification.send_notification()

# Start telegram client
client.start()
logger.info(
    "Client started listening to updates on mentioned channels...",
    True
)
notification.send_notification()

client.run_until_disconnected()
