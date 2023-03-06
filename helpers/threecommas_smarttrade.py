"""Cyberjunky's 3Commas bot helpers."""

def open_threecommas_smarttrade(logger, api, accountid, pair, note, position, take_profit, stop_loss):
    """Open smarttrade with the given position, profit and stoploss."""

    payload = {
        "account_id": accountid,
        "pair": pair,
        "note": note,
        "leverage": {
            "enabled": "false",
        },
        "position": position,
        "take_profit": take_profit,
        "stop_loss": stop_loss
    }

    logger.debug(
        f"Sending new on smart_trades_v2 for pair {pair}: {payload}"
    )

    data = None
    error, data = api.request(
        entity="smart_trades_v2",
        action="new",
        payload=payload,
        additional_headers={"Forced-Mode": "paper"},
    )

    if error:
        if "msg" in error:
            logger.error(
                f"Error occurred while opening smarttrade: {error['msg']}",
            )
        else:
            logger.error("Error occurred while opening smarttrade")

    return data


def close_threecommas_smarttrade(logger, api, smarttradeid):
    """Close smarttrade (on current market price) with the given id."""

    data = None
    error, data = api.request(
        entity="smart_trades_v2",
        action="close_by_market",
        action_id=str(smarttradeid),
        additional_headers={"Forced-Mode": "paper"}
    )

    if error:
        if "msg" in error:
            logger.error(
                f"Error occurred while closing smarttrade: {error['msg']}",
            )
        else:
            logger.error("Error occurred while closing smarttrade")
    else:
        logger.info(
            f"Closed smarttrade {smarttradeid}.",
            True
        )

    return data


def cancel_threecommas_smarttrade(logger, api, smarttradeid):
    """Cancel smarttrade (was not opened yet) with the given id."""

    data = None
    error, data = api.request(
        entity="smart_trades_v2",
        action="cancel",
        action_id=str(smarttradeid),
        additional_headers={"Forced-Mode": "paper"}
    )

    if error:
        if "msg" in error:
            logger.error(
                f"Error occurred while cancelling smarttrade: {error['msg']}",
            )
        else:
            logger.error("Error occurred while cancelling smarttrade")
    else:
        logger.info(
            f"Cancelled smarttrade {smarttradeid}.",
            True
        )

    return data


def get_threecommas_smarttrades(logger, api, account_id, pair, trade_type, status):
    """Get smarttrade(s) with the given id."""

    payload= {
        "account_id": account_id
    }

    if pair:
        payload["pair"] = pair

    if trade_type:
        payload["type"] = trade_type

    if status:
        payload["status"] = status

    data = None
    error, data = api.request(
        entity="smart_trades_v2",
        action="",
        payload=payload,
        additional_headers={"Forced-Mode": "paper"}
    )

    if error:
        if "msg" in error:
            logger.error(
                f"Error occurred while cancelling smarttrade: {error['msg']}",
            )
        else:
            logger.error("Error occurred while cancelling smarttrade")

    return data
