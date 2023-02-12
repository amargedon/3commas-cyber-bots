"""Cyberjunky's 3Commas bot helpers."""
from math import nan
from py3cw.request import Py3CW

from helpers.misc import get_round_digits

from .threecommas_websocket import ThreeCommasWebsocketHandler


def load_blacklist(logger, api, blacklistfile):
    """Return blacklist data to be used."""

    # Return file based blacklist
    if blacklistfile:
        newblacklist = []
        try:
            with open(blacklistfile, "r") as file:
                newblacklist = file.read().splitlines()
            if newblacklist:
                logger.info(
                    "Reading local blacklist file '%s' OK (%s pairs)"
                    % (blacklistfile, len(newblacklist))
                )
        except FileNotFoundError:
            logger.error(
                "Reading local blacklist file '%s' failed with error: File not found"
                % blacklistfile
            )

        return newblacklist

    # Return defined blacklist from 3Commaas
    return get_threecommas_blacklist(logger, api)


def init_threecommas_api(cfg):
    """Init the 3commas API."""

    return Py3CW(
        key = cfg.get("settings", "3c-apikey"),
        secret = cfg.get("settings", "3c-apisecret"),
        request_options={
            "request_timeout": 10,
            "nr_of_retries": 3,
            "retry_status_codes": [502, 429],
            "retry_backoff_factor": 1,
        },
    )


def init_threecommas_websocket(cfg, event_handler):
    """Init the 3commas WebSocket connection."""

    return ThreeCommasWebsocketHandler(
        api_key = cfg.get("settings", "3c-apikey"),
        api_secret = cfg.get("settings", "3c-apisecret"),
        channel = "DealsChannel",
        external_event_handler = event_handler
    )


def get_threecommas_blacklist(logger, api):
    """Get the pair blacklist from 3Commas."""

    newblacklist = list()
    error, data = api.request(
        entity="bots",
        action="pairs_black_list",
    )
    if data:
        logger.info(
            "Fetched 3Commas pairs blacklist OK (%s pairs)" % len(data["pairs"])
        )
        newblacklist = data["pairs"]
    else:
        if "msg" in error:
            logger.error(
                "Fetching 3Commas pairs blacklist failed with error: %s" % error["msg"]
            )
        else:
            logger.error("Fetching 3Commas pairs blacklist failed")

    return newblacklist


def get_threecommas_btcusd(logger, api):
    """Get current USDT_BTC value to calculate BTC volume24h in USDT."""

    price = 20000.0
    price = get_threecommas_currency_rate(logger, api, "binance", "USDT_BTC")

    return price


def get_threecommas_currency_rate(logger, api, market_code, pair):
    """Get current price of pair on selected market."""

    price = nan
    error, data = api.request(
        entity="accounts",
        action="currency_rates",
        payload={"market_code": market_code, "pair": pair},
    )
    if data:
        price = data["last"]
        logger.info(f"Fetched 3Commas price OK ({pair} {price})")
    else:
        if error and "msg" in error:
            logger.error(
                f"Fetching 3Commas price for {pair} failed with error: {error['msg']}"
            )
        else:
            logger.error(f"Fetching 3Commas price for {pair} failed")

    return price


def get_threecommas_accounts(logger, api):
    """Get all data for an account."""

    # Fetch all account data, in real mode
    error, data = api.request(
        entity="accounts",
        action="",
        additional_headers={"Forced-Mode": "real"},
    )
    if data:
        return data

    if error and "msg" in error:
        logger.error("Fetching 3Commas accounts data failed error: %s" % error["msg"])
    else:
        logger.error("Fetching 3Commas accounts data failed")

    return None


def get_threecommas_account(logger, api, accountid):
    """Get account details."""

    # Find account data for accountid, in real mode
    error, data = api.request(
        entity="accounts",
        action="account_info",
        action_id=str(accountid),
        additional_headers={"Forced-Mode": "real"},
    )
    if data:
        return data

    if error and "msg" in error:
        logger.error(
            "Fetching 3Commas account data failed for id %s error: %s"
            % (accountid, error["msg"])
        )
    else:
        logger.error("Fetching 3Commas account data failed for id %s", accountid)

    return None


def get_threecommas_account_marketcode(logger, api, accountid):
    """Get market_code for account."""

    # get account data for accountid, in real mode
    error, data = api.request(
        entity="accounts",
        action="account_info",
        action_id=str(accountid),
        additional_headers={"Forced-Mode": "real"},
    )
    if data:
        return data["market_code"]
    if error and "status_code" in error:
        if error["status_code"] == 404:
            logger.error(
                "Error occurred fetching 3Commas account market code: accountid '%s' was not found" % accountid
            )
    elif error and "msg" in error:
        logger.error(
            "Fetching 3Commas account market code failed for id '%s' error: %s"
            % (accountid, error["msg"])
        )
    else:
        logger.error("Fetching 3Commas account market code failed for id %s", accountid)

    return None


def get_threecommas_account_balance(logger, api, accountid):
    """Get account balances."""

    # Fetch account balance data for accountid, in real mode
    error, data = api.request(
        entity="accounts",
        action="load_balances",
        action_id=str(accountid),
        additional_headers={"Forced-Mode": "real"},
    )
    if data:
        return data

    if error and "msg" in error:
        logger.error(
            "Fetching 3Commas account balances data failed for id %s error: %s"
            % (accountid, error["msg"])
        )
    else:
        logger.error(
            "Fetching 3Commas account balances data failed for id %s", accountid
        )

    return None



def get_threecommas_account_table_balance(logger, api, accountid):
    """Get complete account balances."""

    # Fetch account balance data for accountid, in real mode
    error, data = api.request(
        entity="accounts",
        action="account_table_data",
        action_id=str(accountid),
        additional_headers={"Forced-Mode": "real"},
    )
    if data:
        return data

    if error and "msg" in error:
        logger.error(
            "Fetching 3Commas account table balances data failed for id %s error: %s"
            % (accountid, error["msg"])
        )
    else:
        logger.error(
            "Fetching 3Commas account table balances data failed for id %s", accountid
        )

    return None


def get_threecommas_account_balance_chart_data(
    logger, api, accountid, begindate, enddate
):
    """Get account balance chart data."""

    # Fetch account balance chart data for accountid, in real mode
    error, data = api.request(
        entity="accounts",
        action="balance_chart_data",
        action_id=str(accountid),
        additional_headers={"Forced-Mode": "real"},
        payload={"date_from": begindate, "date_to": enddate},
    )
    if data:
        return data

    if error and "msg" in error:
        logger.error(
            "Fetching 3Commas account balance chart data failed for id %s error: %s"
            % (accountid, error["msg"])
        )
    else:
        logger.error("Fetching 3Commas account balance chart data for id %s", accountid)

    return None


def get_threecommas_market(logger, api, market_code):
    """Get all the valid pairs for market_code from 3Commas account."""

    tickerlist = []
    error, data = api.request(
        entity="accounts",
        action="market_pairs",
        payload={"market_code": market_code},
    )
    if data:
        tickerlist = data
        logger.info(
            "Fetched 3Commas market data for '%s' OK (%s pairs)"
            % (market_code, len(tickerlist))
        )
    else:
        if error and "msg" in error:
            logger.error(
                "Fetching 3Commas market data failed for market code %s with error: %s"
                % (market_code, error["msg"])
            )
        else:
            logger.error(
                "Fetching 3Commas market data failed for market code %s", market_code
            )

    return tickerlist


def set_threecommas_bot_pairs(logger, api, thebot, newpairs, newmaxdeals, notify=True, notify_uptodate=True):
    """Update bot with new pairs."""

    botupdated = False

    # Do we already use these pairs?
    if newpairs == thebot["pairs"]:
        logger.info(
            "Bot '%s' with id '%s' is already using the new pair(s)"
            % (thebot["name"], thebot["id"]),
            notify_uptodate,
        )
        botupdated = True
        return botupdated

    if not newmaxdeals:
        maxactivedeals = thebot["max_active_deals"]
    else:
        maxactivedeals = newmaxdeals

    # Sort the list for logging and notification purpose
    sortednewpairs = sorted(newpairs)
    logger.debug("Current pair(s): %s\nNew pair(s): %s" % (thebot["pairs"], sortednewpairs))

    error, data = api.request(
        entity="bots",
        action="update",
        action_id=str(thebot["id"]),
        payload={
            "name": str(thebot["name"]),
            "pairs": sortednewpairs,
            "base_order_volume": float(thebot["base_order_volume"]),
            "take_profit": float(thebot["take_profit"]),
            "safety_order_volume": float(thebot["safety_order_volume"]),
            "martingale_volume_coefficient": float(
                thebot["martingale_volume_coefficient"]
            ),
            "martingale_step_coefficient": float(thebot["martingale_step_coefficient"]),
            "max_safety_orders": int(thebot["max_safety_orders"]),
            "max_active_deals": int(maxactivedeals),
            "active_safety_orders_count": int(thebot["active_safety_orders_count"]),
            "safety_order_step_percentage": float(
                thebot["safety_order_step_percentage"]
            ),
            "take_profit_type": thebot["take_profit_type"],
            "strategy_list": thebot["strategy_list"],
            "leverage_type": thebot["leverage_type"],
            "leverage_custom_value": thebot["leverage_custom_value"],
            "bot_id": int(thebot["id"]),
        },
    )
    if data:
        botupdated = True

        logger.debug("Bot pair(s) updated: %s" % data)
        if len(sortednewpairs) == 1:
            logger.info(
                "Bot '%s' with id '%s' updated with pair '%s'"
                % (thebot["name"], thebot["id"], sortednewpairs[0]),
                notify,
            )
        else:
            if len(sortednewpairs) < 10:
                logger.info(
                "Bot '%s' with id '%s' updated with %d pairs (%s)"
                % (
                    thebot["name"],
                    thebot["id"],
                    len(sortednewpairs),
                    sortednewpairs,
                ),
                notify,
            )
            else:
                logger.info(
                    "Bot '%s' with id '%s' updated with %d pairs (%s ... %s)"
                    % (
                        thebot["name"],
                        thebot["id"],
                        len(sortednewpairs),
                        sortednewpairs[0],
                        sortednewpairs[-1],
                    ),
                    notify,
                )
        if newmaxdeals:
            logger.info(
                "Max active deals changed to %s" % newmaxdeals,
                notify,
            )
    else:
        if error and "msg" in error:
            logger.error(
                "Error occurred while updating bot '%s' error: %s"
                % (thebot["name"], error["msg"]),
                True,
            )
        else:
            logger.error(
                "Error occurred while updating bot '%s'" % thebot["name"],
                True,
            )

    return botupdated


def trigger_threecommas_bot_deal(logger, api, thebot, pair, skip_checks=False):
    """Trigger bot to start deal asap."""

    error, data = api.request(
        entity="bots",
        action="start_new_deal",
        action_id=str(thebot["id"]),
        payload={"pair": pair, "skip_signal_checks": skip_checks, "bot_id": thebot["id"]},
    )
    if data:
        logger.debug("Bot deal triggered: %s" % data)
        logger.info(
            "Bot '%s' with id '%s' triggered start_new_deal for: %s"
            % (thebot["name"], thebot["id"], pair),
            True,
        )
    else:
        if error and "msg" in error:
            logger.error(
                "Error occurred while triggering start_new_deal bot '%s' error: %s"
                % (thebot["name"], error["msg"]),
            )
        else:
            logger.error(
                "Error occurred while triggering start_new_deal bot '%s'"
                % thebot["name"],
            )


def control_threecommas_bots(logger, api, thebot, cmd):
    """Enable or disable a bot."""

    error, data = api.request(
        entity="bots",
        action=cmd,
        action_id=str(thebot["id"]),
    )
    if data:
        logger.info(
            "Bot '%s' is %sd" % (thebot["name"], cmd),
            True,
        )
    else:
        if error and "msg" in error:
            logger.error(
                "Error occurred while '%s' bot was %sd error: %s"
                % (thebot["name"], cmd, error["msg"]),
            )
        else:
            logger.error(
                "Error occurred while '%s' bot was %sd" % (thebot["name"], cmd),
            )


def get_threecommas_deals(logger, api, botid, actiontype="finished"):
    """Get all deals from 3Commas linked to a bot."""

    data = None
    if actiontype == "finished":
        payload = {
            "scope": "finished",
            "bot_id": str(botid),
            "limit": 100,
            "order": "closed_at",
        }
    else:
        payload = {
            "scope": "active",
            "bot_id": str(botid),
            "limit": 100,
        }

    error, data = api.request(
        entity="deals",
        action="",
        payload=payload,
    )
    if error:
        if "msg" in error:
            logger.error(
                "Error occurred while fetching deals error: %s" % error["msg"],
            )
        else:
            logger.error("Error occurred while fetching deals")
    else:
        logger.debug("Fetched the deals for bot %s OK (%s deals)" % (botid, len(data)))

    return data


def close_threecommas_deal(logger, api, dealid, pair):
    """Close deal with certain id."""

    data = None
    error, data = api.request(
        entity="deals",
        action="panic_sell",
        action_id=str(dealid),
    )
    if error:
        if "msg" in error:
            logger.error(
                "Error occurred while closing deal error: %s" % error["msg"],
            )
        else:
            logger.error("Error occurred while closing deal")
    else:
        logger.info(
            "Closed deal (panic_sell) for deal with id '%s' and pair '%s'"
            % (dealid, pair),
            True,
        )

    return data


def get_threecommas_bots(logger, api, accountid):
    """Get account details."""

    # Find bots data for accountid
    error, data = api.request(
        entity="bots",
        action="",
        payload= {
            "account_id": accountid
        }
    )

    if data:
        return data

    if error and "msg" in error:
        logger.error(
            "Fetching 3Commas bots data failed for id %s error: %s"
            % (accountid, error["msg"])
        )
    # No else, there are just no bots for the account

    return None


def threecommas_deal_add_funds(logger, api, deal_pair, deal_id, quantity, limit_price):
    """Add funds to existing deal."""

    orderplaced = False

    error, data = api.request(
        entity="deals",
        action="add_funds",
        action_id=str(deal_id),
        payload={
            "quantity": quantity,
            "is_market": False,
            "rate": limit_price,
            "deal_id": deal_id,
        },
    )
    if data:
        if data["status"] == "success":
            rounddigits = get_round_digits(deal_pair)

            logger.debug(
                f"{deal_pair}/{deal_id}: add {quantity} {deal_pair.split('_')[1]} "
                f"at limit price {limit_price:0.{rounddigits}f}."
            )

            orderplaced = True
        else:
            logger.debug(
                f"{deal_id}: add funds not succesfull: {data}."
            )
    else:
        if error and "msg" in error:
            logger.error(
                "Error occurred adding funds to deal: %s" % error["msg"]
            )
        else:
            logger.error("Error occurred adding funds to deal")

    return orderplaced


def get_threecommas_deal_order_status(logger, api, deal_pair, deal_id, order_id):
    """Get the status of the specified order."""

    orderstatus = ""

    error, data = api.request(
        entity="deals",
        action="market_orders",
        action_id=str(deal_id)
    )

    if data:
        for order in data:
            orderid = order["order_id"]
            orderstatus = order["status_string"]

            if str(orderid) == str(order_id):
                break

        if not orderstatus:
            logger.debug(
                f"{deal_pair}/{deal_id}: order {order_id} not found! "
                f"Received data from 3C: {data}."
            )
    else:
        if error and "msg" in error:
            logger.error(
                "Error occurred while fetching active market orders for deal: %s" % error["msg"]
            )
        else:
            logger.error("Error occurred while fetching active market orders for deal")

    return orderstatus


def get_threecommas_deal_order_id(logger, api, deal_pair, deal_id, order_type, order_status):
    """Get the order id for the specified deal, type and status."""

    orderid = ""

    error, data = api.request(
        entity="deals",
        action="market_orders",
        action_id=str(deal_id)
    )

    if data:
        for order in data:
            orderid = order["order_id"]
            ordertype = order["deal_order_type"]
            orderstatus = order["status_string"]

            if (ordertype.lower() == order_type.lower() and
              orderstatus.lower() == order_status.lower()):
                break

        if not orderid:
            logger.debug(
                f"{deal_pair}/{deal_id}: order with type {order_type} "
                f"and status {order_status} not found! "
                f"Received data from 3C: {data}."
            )
    else:
        if error and "msg" in error:
            logger.error(
                "Error occurred while fetching active market orders for deal: %s" % error["msg"]
            )
        else:
            logger.error("Error occurred while fetching active market orders for deal")

    return orderid


def threecommas_deal_cancel_order(logger, api, deal_id, order_id):
    """Cancel an earlier placed order."""

    ordercancelled = False

    error, data = api.request(
        entity="deals",
        action="cancel_order",
        action_id=str(deal_id),
        payload={
            "order_id": order_id,
            "deal_id": deal_id,
        },
    )

    if data:
        for order in data:
            orderid = order["order_id"]
            orderstatus = order["status_string"]

            if str(orderid) == str(order_id) and orderstatus.lower() == "cancelled":
                logger.debug(
                    f"{deal_id}: order '{orderid}' is Cancelled!"
                )
                ordercancelled = True
                break

        if not ordercancelled:
            logger.debug(
                f"{deal_id}: cancel of order {order_id} failed! "
                f"Received data from 3C: {data}."
            )
    else:
        if error and "msg" in error:
            logger.error(
                "Error occurred cancelling order for deal: %s" % error["msg"]
            )
        else:
            logger.error("Error occurred cancelling order for deal")

    return ordercancelled


def threecommas_get_data_for_adding_funds(logger, api, deal):
    """Get data about tick size."""

    fundsdata = {}

    error, data = api.request(
        entity="deals",
        action="data_for_adding_funds",
        action_id=str(deal["id"])
    )

    if data:
        logger.info(
            f"Data for adding funds to deal {deal['pair']}/{deal['id']}: "
            f"Received response data: {data}"
        )

        fundsdata = data
    else:
        if error and "msg" in error:
            logger.error(
                "Error occurred retrieving data for adding funds to deal: %s" % error["msg"]
            )
        else:
            logger.error("Error occurred retrieving data for adding funds to deal")

    return fundsdata


def prefetch_marketcodes(logger, api, botids):
    """Gather and return marketcodes for all bots."""

    marketcodearray = {}

    logger.debug(
        f"Prefetch marketcodes for the following bots: {botids}"
    )

    for botid in botids:
        if botid and botid not in marketcodearray:
            boterror, botdata = api.request(
                entity="bots",
                action="show",
                action_id=str(botid),
            )

            if botdata:
                accountid = botdata["account_id"]
                # Get marketcode (exchange) from account if not already fetched
                marketcode = get_threecommas_account_marketcode(logger, api, accountid)
                marketcodearray[botdata["id"]] = marketcode

                logger.info(
                    f"Fetched marketcode '{marketcode}' for "
                    f"bot {botdata['id']} with account id {accountid}."
                )
            else:
                if boterror and "msg" in boterror:
                    logger.error(
                        "Error occurred fetching marketcode data: %s" % boterror["msg"]
                    )
                else:
                    logger.error("Error occurred fetching marketcode data")

    return marketcodearray
