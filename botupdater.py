#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import configparser
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
import tvscreener as tvs
from tvscreener import TimeInterval

from helpers.database import get_next_process_time, set_next_process_time

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
    get_threecommas_currency_rate,
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
        "debug-log-query": False,
        "logrotate": 7,
        "3c-apikey": "Your 3Commas API Key",
        "3c-apisecret": "Your 3Commas API Secret",
        "3c-apikey-path": "Path to your own generated RSA private key, or empty",
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }

    cfgconditionconfig = list()
    cfgconditionconfig.append({
        "pair": "USD_BTC",
        "percent-change-1h": [],
    })

    cfg["bu_default"] = {
        "botids": [12345, 67890],
        "timeinterval": 3600,
        "allowmaxdealchange": True,
        "allowbotstopstart": True,
        "base": "BTC",
        "cmc-rank": [1, 200],
        "altrank": [],
        "galaxyscore": [],
        "percent-change-1h": [],
        "percent-change-4h": [],
        "percent-change-24h": [],
        "percent-change-7d": [],
        "percent-change-14d": [],
        "percent-change-30d": [],
        "percent-change-200d": [],
        "percent-change-1y": [],
        "volatility-24h": [],
        "volume": [],
        "volume-change-24h": [],
        "technical-rating": [],
        "condition": json.dumps(cfgconditionconfig),
        "coin-whitelist": [],
        "coin-blacklist": [],
        "description": "some description",
        "notify-succesful-update": True,
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


def upgrade_config(cfg):
    """Upgrade config file if needed."""

    if not cfg.has_option("settings", "debug-log-query"):
        cfg.set("settings", "debug-log-query", "False")

        with open(f"{datadir}/{program}.ini", "w+") as cfgfile:
            cfg.write(cfgfile)

        logger.info("Upgraded section settings to have debug-log-query option")

    for cfgsection in cfg.sections():
        if not cfgsection.startswith("bu_"):
            continue

        if not cfg.has_option(cfgsection, "percent-change-14d"):
            cfg.set(cfgsection, "percent-change-14d", "[]")
            cfg.set(cfgsection, "percent-change-30d", "[]")
            cfg.set(cfgsection, "percent-change-200d", "[]")
            cfg.set(cfgsection, "percent-change-1y", "[]")

            with open(f"{datadir}/{program}.ini", "w+") as cfgfile:
                cfg.write(cfgfile)

            logger.info("Upgraded section %s to have extended percent-change filters" % cfgsection)

        if not cfg.has_option(cfgsection, "condition"):
            cfgconditionconfig = list()
            cfgconditionconfig.append({
                "pair": "USD_BTC",
                "percent-change-1h": [],
            })

            cfg.set(cfgsection, "condition", json.dumps(cfgconditionconfig))

            with open(f"{datadir}/{program}.ini", "w+") as cfgfile:
                cfg.write(cfgfile)

            logger.info("Upgraded section %s to have condition option" % cfgsection)

        if not cfg.has_option(cfgsection, "coin-whitelist"):
            cfgcoinlist = list()

            cfg.set(cfgsection, "coin-whitelist", json.dumps(cfgcoinlist))
            cfg.set(cfgsection, "coin-blacklist", json.dumps(cfgcoinlist))

            with open(f"{datadir}/{program}.ini", "w+") as cfgfile:
                cfg.write(cfgfile)

            logger.info("Upgraded section %s to have coinlist option" % cfgsection)

        if not cfg.has_option(cfgsection, "notify-succesful-update"):
            cfg.set(cfgsection, "notify-succesful-update", "True")

            with open(f"{datadir}/{program}.ini", "w+") as cfgfile:
                cfg.write(cfgfile)

            logger.info("Upgraded section %s to have notify option" % cfgsection)

        if not cfg.has_option(cfgsection, "percent-change-4h"):
            cfg.set(cfgsection, "percent-change-4h", "[]")
            cfg.set(cfgsection, "volume", "[]")
            cfg.set(cfgsection, "volume-change-24h", "[]")
            cfg.set(cfgsection, "technical-rating", "[]")

            with open(f"{datadir}/{program}.ini", "w+") as cfgfile:
                cfg.write(cfgfile)

            logger.info("Upgraded section %s to have extended TV conditions" % cfgsection)

    if not cfg.has_option("settings", "3c-apikey-path"):
        cfg.set("settings", "3c-apikey-path", "")

        with open(f"{datadir}/{program}.ini", "w+") as cfgfile:
            cfg.write(cfgfile)

        logger.info("Upgraded the configuration file (3c-apikey-path)")

    return cfg


def open_shared_db():
    """Open shared database"""

    try:
        shareddbname = "marketdata.sqlite3"
        shareddbpath = f"file:{sharedir}/{shareddbname}?mode=rw"
        shareddbconnection = sqlite3.connect(shareddbpath, uri=True)
        shareddbconnection.row_factory = sqlite3.Row

        logger.info(f"Shared database '{sharedir}/{shareddbname}' opened successfully")

    except sqlite3.OperationalError:
        logger.info(f"Shared database '{sharedir}/{shareddbname}' couldn't be opened")

    return shareddbconnection


def open_bu_db():
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
            "CREATE TABLE IF NOT EXISTS bots ("
            "botid INT Primary Key, "
            "max_deals INT"
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


def store_bot_maxdeals(bot_id, max_deals):
    """Store the max deals of the given bot in the database"""

    logger.debug(
        f"Store max active deals {max_deals} for bot {bot_id}"
    )

    db.execute(
        f"INSERT OR REPLACE INTO bots ("
        f"botid, "
        f"max_deals "
        f") VALUES ("
        f"{bot_id}, {max_deals}"
        f")"
    )

    db.commit()


def get_bot_maxdeals(bot_id):
    """Get the max deals of the given bot from the database"""

    data = cursor.execute(
        f"SELECT max_deals FROM bots WHERE botid = {bot_id}"
    ).fetchone()

    maxdeals = 0
    if data:
        maxdeals = data[0]

    logger.debug(
        f"Database has {maxdeals} max active deals stored for bot {bot_id}"
    )

    return maxdeals


def process_bu_section(section_id):
    """Process the section from the configuration"""

    botsupdated = False

    # Bot configuration for section
    botids = json.loads(config.get(section_id, "botids"))

    base = config.get(section_id, "base")
    baselist = ("BNB", "BTC", "ETH", "EUR", "USD")
    if base not in baselist:
        logger.error(
            f"Percent change ('{base}') must be one of the following: "
            f"{baselist}"
        )
        return botsupdated

    filteroptions = {}
    filteroptions["cmcrank"] = json.loads(config.get(section_id, "cmc-rank"))
    filteroptions["altrank"] = json.loads(config.get(section_id, "altrank"))
    filteroptions["galaxyscore"] = json.loads(config.get(section_id, "galaxyscore"))

    pricefilter = {}
    pricefilter["change_1h"] = json.loads(config.get(section_id, "percent-change-1h"))
    pricefilter["change_4h"] = json.loads(config.get(section_id, "percent-change-4h"))
    pricefilter["change_24h"] = json.loads(config.get(section_id, "percent-change-24h"))
    pricefilter["change_7d"] = json.loads(config.get(section_id, "percent-change-7d"))
    pricefilter["change_14d"] = json.loads(config.get(section_id, "percent-change-14d"))
    pricefilter["change_30d"] = json.loads(config.get(section_id, "percent-change-30d"))
    pricefilter["change_200d"] = json.loads(config.get(section_id, "percent-change-200d"))
    pricefilter["change_1y"] = json.loads(config.get(section_id, "percent-change-1y"))
    pricefilter["volatility_24h"] = json.loads(config.get(section_id, "volatility-24h"))
    pricefilter["volume"] = json.loads(config.get(section_id, "volume"))
    pricefilter["volume-change_24h"] = json.loads(config.get(section_id, "volume-change-24h"))
    pricefilter["technical_rating"] = json.loads(config.get(section_id, "technical-rating"))
    filteroptions["change"] = pricefilter

    # Ugly way to read the coinlists from the configuration
    # Because JSON is not properly saved by the ConfigParser, we need to parse
    # the data and construct the list
    filteroptions["coin-whitelist"] = [
        coin.replace("'", "").replace("[", "").replace("]","").strip()
        for coin in config.get(section_id, "coin-whitelist").split(",")
    ]
    # TODO: move this to the update section so the total number of blacklisted pairs 
    # can be reported correctly
    filteroptions["coin-blacklist"] = [
        coin.replace("'", "").replace("[", "").replace("]","").strip()
        for coin in config.get(section_id, "coin-blacklist").split(",")
    ]

    # Coindata contains:
    # 0: total number of coins available
    # 1: list of coins after filtering
    # TODO: TV data should move to MarketCollector
    #coindata = get_coins_from_market_data(base, filteroptions)
    coindata = get_coins_from_tradingview_data(base, filteroptions)

    logger.debug(
        f"Fetched {len(coindata[1])} coins from the marketdata database."
    )

    conditionstate = True
    conditionconfig = json.loads(config.get(section_id, "condition"))
    if len(conditionconfig) > 0:
        conditionstate = evaluatecondition(conditionconfig)

    logger.info(
        f"Evaluation of condition(s) for bot(s) in section {section_id} is: {conditionstate}"
    )

    # Walk through all bots configured
    for bot in botids:
        error, data = api.request(
            entity="bots",
            action="show",
            action_id=str(bot),
        )
        if data:
            botsupdated |= update_bot_pairs(section_id, base, data, coindata, conditionstate)
        else:
            botsupdated = False

            if error and "msg" in error:
                logger.error("Error occurred updating bots: %s" % error["msg"])
            else:
                logger.error("Error occurred updating bots")

    return botsupdated


def evaluatecondition(condition_config):
    """Evaluate the state of the condition(s)"""

    conditionstate = True

    logger.debug(
        f"Processing conditions: {condition_config}"
    )

    for entry in condition_config:
        pair = entry["pair"].split("_")

        query = "SELECT prices.coin FROM prices "
        query += f"WHERE prices.base = '{pair[0]}' AND prices.coin = '{pair[1]}' "

        pricefilter = {}

        for period in ("1h", "24h", "7d", "14d", "30d", "200d", "1y"):
            if f"percent-change-{period}" in entry:
                pricefilter[f"change_{period}"] = entry[f"percent-change-{period}"]

        query += create_change_condition(pricefilter)

        if config.getboolean("settings", "debug-log-query"):
            logger.debug(
                f"Execute condition query: {query}"
            )

        dbresult = sharedcursor.execute(query).fetchone()
        if dbresult is None:
            logger.info(
                f"Condition {entry} not met!"
            )
            conditionstate = False
            break

    return conditionstate


def update_bot_pairs(section_id, base, botdata, coindata, condition_state):
    """Find new pairs and update the bot."""

    botupdated = False

    allowbotstopstart = config.getboolean(section_id, "allowbotstopstart")
    if len(coindata[1]) == 0:
        logger.info(
            f"No coins for bot '{botdata['name']}' with id '{botdata['id']}' "
            f"available. Skip update and stop the bot if allowed in the configuration."
        )

        # No data available, stop the bot if allowed to
        handle_bot_stopstart(botdata, 0, condition_state, allowbotstopstart)

        botupdated = True
        return botupdated

    # Gather bot settings
    botbase = botdata["pairs"][0].split("_")[0]
    if botbase in ("BTC", "ETH", "BNB"):
        if botbase != base:
            logger.error(
                f"Bot base currency {botbase} and filter currency {base} do not match. "
                f"Only conversion between fiat or stable coins allowed! "
                f"Bot '{botdata['name']}' with id '{botdata['id']}' not updated."
            )
            return botupdated

    # Start from scratch
    newpairs = list()
    badpairs = list()
    blackpairs = list()
    invalidleveragepairs = list()

    # Get marketcode (exchange) from account
    marketcode = marketcodecache.get(botdata["id"])
    if not marketcode:
        marketcode = get_threecommas_account_marketcode(logger, api, botdata["account_id"])
        marketcodecache[botdata["id"]] = marketcode

        logger.info(
            f"Marketcode for bot {botdata['id']} was not cached. Cache updated "
            f"with marketcode {marketcode}."
        )
    else:
        logger.debug(
            f"Using cached marketcode '{marketcode}' for "
            f"bot {botdata['id']}."
        )

    # Should be there, either from cache or fresh from 3C
    if not marketcode:
        return botupdated

    # Load tickerlist for this exchange. First try from the cache (which is only
    # kept during the current cycle), otherwise fetch the tickerlist and add it
    # to the cache
    tickerlist = tickerlistcache.get(marketcode)
    if not tickerlist:
        tickerlist = get_threecommas_market(logger, api, marketcode)
        tickerlistcache[marketcode] = tickerlist

        logger.info(
            f"Updated cache with tickerlist ({len(tickerlist)} pairs) "
            f"for market '{marketcode}'."
        )
    else:
        logger.debug(
            f"Using cached tickerlist with {len(tickerlist)} pairs "
            f"for market '{marketcode}'."
        )

    # Process list of coins
    # Check availability and blacklist
    for coin in coindata[1]:
        try:
            # Construct pair based on bot settings and marketcode
            # (BTC stays BTC, but USDT can become BUSD)
            pair = format_pair(marketcode, botbase, coin[0])

            # Populate lists
            populate_pair_lists(
                pair, blacklist, blackpairs, badpairs, newpairs, tickerlist
            )

        except KeyError as err:
            logger.error(
                "Something went wrong while parsing coin data. KeyError for field: %s"
                % err
            )
            return botupdated

    # Process list of coins
    # Check available leverage
    if "futures" in marketcode or "perpetual" in marketcode:
        for pair in newpairs:
            validleverage = False

            minleverage = -1.0
            maxleverage = -1.0

            # Try to get the leverage values from the cache
            if pair in pairleveragecache:
                minleverage = pairleveragecache[pair]["min"]
                maxleverage = pairleveragecache[pair]["max"]
            else:
                # Fetch data from 3Commas and store in the cache
                currencydata = get_threecommas_currency_rate(logger, api, marketcode, pair)

                if "minLeverage" in currencydata and "maxLeverage" in currencydata:
                    minleverage = currencydata["minLeverage"]
                    maxleverage = currencydata["maxLeverage"]

                    leveragedata = {
                        "min": minleverage,
                        "max": maxleverage
                    }
                    pairleveragecache[pair] = leveragedata
                else:
                    logger.error(
                        f"minLeverage and/or maxLeverage for pair {pair} are not present "
                        f"in fetched 3C data!"
                    )
            if minleverage != -1 and maxleverage != -1:
                if minleverage <= float(botdata["leverage_custom_value"]) <= maxleverage:
                    logger.debug(
                        f"Required leverage {botdata['leverage_custom_value']} supported for "
                        f"pair {pair} (min: {minleverage}, max: {maxleverage})"
                    )
                    validleverage = True
                else:
                    logger.warning(
                        f"Required leverage {botdata['leverage_custom_value']} not supported for "
                        f"pair {pair} (min: {minleverage}, max: {maxleverage})"
                    )
            else:
                logger.error(
                    f"Invalid leverage data for pair {pair}!"
                )

            if not validleverage:
                invalidleveragepairs.append(pair)

        # And remove the invalid pairs from the list
        for pair in invalidleveragepairs:
            newpairs.remove(pair)

    logger.debug(
        f"Skipped blacklisted pairs: {blackpairs}. "
        f"Skipped pairs not on {marketcode}: {badpairs}. "
        f"Skipped invalid leverage pairs: {invalidleveragepairs}"
    )

    # If sharedir is set, other scripts could provide a file with pairs to exclude
    if sharedir is not None:
        remove_excluded_pairs(logger, sharedir, botdata['id'], marketcode, botbase, newpairs)

    # Lower the number of max deals if not enough new pairs and change allowed and
    # change back to original if possible
    paircount = len(newpairs)
    newmaxdeals = False

    allowmaxdealchange = config.getboolean(section_id, "allowmaxdealchange")
    if allowmaxdealchange:
        newmaxdeals = determine_bot_maxactivedeals(botdata, paircount)

    handle_bot_stopstart(botdata, paircount, condition_state, allowbotstopstart)

    # Update the bot with the new pairs
    if newpairs:
        if botdata["type"] == "Bot::SingleBot" and len(newpairs) > 1:
            # Slice the list as we only can have a single pair
            logger.debug(
                f"Truncated pairlist from {newpairs} to {newpairs[0]} because "
                f"bot '{botdata['name']}' with id '{botdata['id']}' is a single bot"
            )
            newpairs = newpairs[0:1]

        botupdated = set_threecommas_bot_pairs(
            logger, api, botdata, newpairs, newmaxdeals, False, False
            )

        if botupdated and newmaxdeals:
            logger.info(
                f"Bot '{botdata['name']}' with id '{botdata['id']}' changed max "
                f"active deals to {newmaxdeals}.",
                True
            )

        # Send our own notification with more data
        if botupdated and newpairs != botdata["pairs"]:
            excludedcount = abs(coindata[0][0] - len(coindata[1]))
            logger.info(
                f"Bot '{botdata['name']}' with id '{botdata['id']}' updated with {len(newpairs)} "
                f"pairs ({newpairs[0]} ... {newpairs[-1]}). "
                f"Excluded coins: {excludedcount} (filter), {len(blackpairs)} (blacklist), "
                f"{len(badpairs)} (not on exchange), {len(invalidleveragepairs)} (leverage)",
                config.getboolean(section_id, "notify-succesful-update")
            )
    else:
        # No coins in the list are available on the exchange, which can be a normal use-case
        botupdated = True

        logger.debug(
            f"None of the pairs have been found on the {botdata['account_name']} "
            f"({marketcode}) exchange!"
        )

    return botupdated


def determine_bot_maxactivedeals(botdata, paircount):
    """Determine the max active deals for the bot"""

    newmaxdeals = False

    # Get stored value from the database. This could be zero, meaning there is
    # no number of active deals stored yet
    originalmaxdeals = get_bot_maxdeals(botdata["id"])

    if paircount < botdata["max_active_deals"]:
        # Lower number of pairs; limit max active deals
        newmaxdeals = paircount

        # Store current max deals, so we can restore later
        # Only if it's not stored yet (current value is zero) because during updates
        # this number could decrease more
        if originalmaxdeals == 0:
            store_bot_maxdeals(botdata["id"], botdata["max_active_deals"])
    elif originalmaxdeals > 0:
        if (
            paircount > botdata["max_active_deals"]
            and paircount < originalmaxdeals
        ):
            # Higher number of pairs below original; limit max active deals
            newmaxdeals = paircount
        elif (
            paircount > botdata["max_active_deals"]
            and botdata["max_active_deals"] != originalmaxdeals
        ):
            # Increased number of pairs above original; set original max active deals
            newmaxdeals = originalmaxdeals

            # Reset stored value so it can be stored again in the future
            store_bot_maxdeals(botdata["id"], 0)
        elif (
            botdata["max_active_deals"] == originalmaxdeals
        ):
            # Reset stored value so it can be stored again in the future
            store_bot_maxdeals(botdata["id"], 0)

    return newmaxdeals


def handle_bot_stopstart(botdata, paircount, condition_state, allowed_stop_start):
    """Determine and handle bot stop and start"""

    logger.debug(
        f"Bot {botdata['id']}: is_enabled = {botdata['is_enabled']}, "
        f"paircount = {paircount} and condition_state = {condition_state}."
    )

    if (paircount == 0 or not condition_state) and botdata["is_enabled"]:
        # No pairs or condition evaluation is False, and bot is
        # running (zero pairs not allowed), so stop it...
        if allowed_stop_start:
            control_threecommas_bots(logger, api, botdata, "disable")
        else:
            logger.warning(
                f"Bot '{botdata['name']}' with id '{botdata['id']}' must be stopped, "
                f"however not allowed by configuration. Make sure to "
                f"monitor yourself!"
            )
    elif paircount > 0 and condition_state and not botdata["is_enabled"]:
        # Valid pairs, condition evaluation is True and bot is
        # not running, so start it...
        if allowed_stop_start:
            control_threecommas_bots(logger, api, botdata, "enable")
        else:
            logger.warning(
                f"Bot '{botdata['name']}' with id '{botdata['id']}' must be started, "
                f"however not allowed by configuration. Make sure to "
                f"monitor yourself!"
            )


def get_coins_from_market_data(base, filteroptions):
    """Get pairs based on the specified filtering"""

    # Query for the total count of coins
    countquery = f"SELECT COUNT(pairs.coin) FROM pairs WHERE base = '{base}'"

    # Base query and joining of all tables
    query = "SELECT pairs.coin FROM pairs "
    query += "INNER JOIN rankings ON pairs.base = rankings.base AND pairs.coin = rankings.coin "
    query += "INNER JOIN prices ON pairs.base = prices.base AND pairs.coin = prices.coin "

    # Specify the base
    query += f"WHERE pairs.base = '{base}' "

    # Len greater than 2, because empty list has length of 2
    if "coin-whitelist" in filteroptions and len(filteroptions['coin-whitelist']) > 2:
        whitelistquery = "AND pairs.coin IN ("
        whitelistquery += ", ".join(f'"{c}"' for c in filteroptions['coin-whitelist'])
        whitelistquery += ") "

        # Include only the coins of the whitelist in the count
        countquery += whitelistquery
        query += whitelistquery

    # Len greater than 2, because empty list has length of 2
    if "coin-blacklist" in filteroptions and len(filteroptions['coin-blacklist']) > 2:
        blacklistquery = "AND pairs.coin NOT IN ("
        blacklistquery += ", ".join(f'"{c}"' for c in filteroptions['coin-blacklist'])
        blacklistquery += ") "

        # Exclude the coins on the blacklist from the count
        countquery += blacklistquery
        query += blacklistquery

    # Specify cmc-rank
    if "cmcrank" in filteroptions and len(filteroptions['cmcrank']) == 2:
        query += "AND rankings.coinmarketcap "
        query += f"BETWEEN {filteroptions['cmcrank'][0]} AND {filteroptions['cmcrank'][1]} "

    # Specify altrank
    if "altrank" in filteroptions and len(filteroptions['altrank']) == 2:
        query += "AND rankings.altrank "
        query += f"BETWEEN {filteroptions['altrank'][0]} AND {filteroptions['altrank'][1]} "

    # Specify galaxyscore
    if "galaxyscore" in filteroptions and len(filteroptions['galaxyscore']) == 2:
        query += "AND rankings.galaxyscore "
        query += f"BETWEEN {filteroptions['galaxyscore'][0]} AND {filteroptions['galaxyscore'][1]} "

    # Specify percent change
    if "change" in filteroptions:
        query += create_change_condition(filteroptions["change"])

    if config.getboolean("settings", "debug-log-query"):
        logger.debug(
            f"Build query for fetch of coins: {query}"
        )

    return sharedcursor.execute(countquery).fetchone(), sharedcursor.execute(query).fetchall()


def get_coins_from_tradingview_data(base, filteroptions):
    """Get pairs based on the specified filtering"""

    cs = tvs.CryptoScreener()
    cs.set_range(0, 3250)
    cs.search("perpetual")

    df = cs.get(time_interval=TimeInterval.FOUR_HOURS, print_request=False)

    # Hardcoded filter on exchange
    df1 = df.loc[df["Exchange"] == "BYBIT" ]

    # Hardcoded sort for now
    df2 = df1.sort_values(by = ["Volatility", "Technical Rating"], ascending = False)
    df_filtered = df2

    coins = list()
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
        if not filteroptions["change"]["volatility_24h"][0] < volatility < filteroptions["change"]["volatility_24h"][-1]:
            valid = False
            logger.debug(f"{symbol} excluded based on low volatility {volatility:.2f}%")

        if not filteroptions["change"]["change_7d"][0] < change_oneweek < filteroptions["change"]["change_7d"][-1]:
            valid = False
            logger.debug(f"{symbol} excluded based on change 1W {change_oneweek:.2f}%")

        if not filteroptions["change"]["change_4h"][0] < change_fourhour < filteroptions["change"]["change_4h"][-1]:
            valid = False
            logger.debug(f"{symbol} excluded based on change 4h {change_fourhour:.2f}%")

        if not filteroptions["change"]["change_1h"][0] < change_onehour < filteroptions["change"]["change_1h"][-1]:
            valid = False
            logger.debug(f"{symbol} excluded based on change 1h {change_onehour:.2f}%")

        if not filteroptions["change"]["volume-change_24h"][0] < volume_change_oneday < filteroptions["change"]["volume-change_24h"][-1]:
            valid = False
            logger.debug(f"{symbol} excluded based on daily volume change {volume_change_oneday:.2f}%")

        if not filteroptions["change"]["volume"][0] < volume_fourhour < filteroptions["change"]["volume"][-1]:
            valid = False
            logger.debug(f"{symbol} excluded based on low trading volume {volume_fourhour / 1000000}M")

        if not filteroptions["change"]["technical_rating"][0] < technical_rating < filteroptions["change"]["technical_rating"][-1]:
            valid = False
            logger.debug(f"{symbol} excluded based on technical rating {technical_rating}")

        if valid:
            coin = []
            coin.append(symbol.replace("USDT.P", ""))
            coins.append(coin)

    return [len(coins)], coins


def create_change_condition(filteroptions):
    """Build the WHERE query string part for price change"""

    query = ""

    for key, value in filteroptions.items():
        # Only accept entries with lower and upper limit for price change
        if len(value) != 2:
            continue

        firstvalue = float(value[0])
        secondvalue = float(value[-1])

        query += f"AND prices.{key} BETWEEN "

        # Between needs the proper range, so keep that into account
        if secondvalue < firstvalue:
            query += f"{secondvalue} AND {firstvalue} "
        else:
            query += f"{firstvalue} AND {secondvalue} "

    return query


def create_marketcode_cache():
    """Create the cache met MarketCode per bot"""

    allbotids = []

    logger.info("Prefetching marketcodes for all configured bots...")

    for initialsection in config.sections():
        if initialsection.startswith("bu_"):
            allbotids += json.loads(config.get(initialsection, "botids"))

    return prefetch_marketcodes(logger, api, allbotids)


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
    print("This script requires the sharedir to be used (-s option)!")
    sys.exit(0)

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
    config = upgrade_config(config)

    logger.info(f"Loaded configuration from '{datadir}/{program}.ini'")

# Initialize 3Commas API
api = init_threecommas_api(logger, config)
if not api:
    sys.exit(0)

# Initialize or open the database
db = open_bu_db()
cursor = db.cursor()

# Open the shared database
shareddb = open_shared_db()
sharedcursor = shareddb.cursor()

# Prefetch all Marketcodes to reduce API calls and improve speed
# New bot(s) will also be added later, for example when the configuration
# has been changed after starting this script
marketcodecache = create_marketcode_cache()

tickerlistcache = {}

pairleveragecache = {}

# Refresh coin pairs in 3C bots based on the market data
while True:

    # Reload config files and refetch data to catch changes
    config = load_config()
    logger.info(f"Reloaded configuration from '{datadir}/{program}.ini'")

    # Configuration settings
    timeint = int(config.get("settings", "timeinterval"))

    # Update the blacklist
    blacklist = load_blacklist(logger, api, blacklistfile)

    # Cache is used for one cycle, where we can optimize. But, we want to prevent
    # working with old data so therefor clear before each cycle
    tickerlistcache.clear()

    # Current time to determine which sections to process
    starttime = int(time.time())

    # Leverage data can change, make sure to invalidate the cache every 24h
    cleantime = get_next_process_time(db, "sections", "sectionid", "cleanup")
    if starttime >= cleantime or (
            abs(cleantime - starttime) > (3600 * 24)
    ):
        logger.debug(
            "Invalidate cached data..."
        )
        pairleveragecache.clear()
        newtime = starttime + (3600 * 24)
        set_next_process_time(db, "sections", "sectionid", "cleanup", newtime)

    for section in config.sections():
        if section.startswith("bu_"):
            sectiontimeinterval = int(config.get(section, "timeinterval"))
            nextprocesstime = get_next_process_time(db, "sections", "sectionid", section)

            # Only process the section if it's time for the next interval, or
            # time exceeds the check interval (clock has changed somehow)
            if starttime >= nextprocesstime or (
                    abs(nextprocesstime - starttime) > sectiontimeinterval
            ):
                if not process_bu_section(section):
                    # Update failed somewhere, retry in 60s
                    sectiontimeinterval = 60

                    logger.error(
                        f"Update for section {section} failed. Retry possible after 60 seconds."
                    )

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
                f"Section '{section}' not processed (prefix 'bu_' missing)!",
                False
            )

    if not wait_time_interval(logger, notification, timeint, False):
        break
