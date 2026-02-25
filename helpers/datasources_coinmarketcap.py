#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import json
import time

import requests

def get_coinmarketcap_data(logger, cmc_apikey, start_number, limit, convert):
    """Get the data from CoinMarketCap."""

    cmcdict = {}
    statuscode = -1
    statusmessage = ""

    # Construct query for CoinMarketCap data
    parms = {
        "start": start_number,
        "limit": limit,
        "convert": convert,
        "aux": "cmc_rank",
    }

    headrs = {
        "X-CMC_PRO_API_KEY": cmc_apikey,
    }

    try:
        result = requests.get(
            "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest",
            params=parms,
            headers=headrs,
            timeout=(3.05, 30.0)
        )

        data = result.json()

        if result.ok:
            if "data" in data.keys():
                cmcdict = data["data"]
        else:
            statuscode = data['status']['error_code']
            statusmessage = data['status']['error_message']
    except requests.exceptions.HTTPError as err:
        logger.error(f"Fetching CoinMarketCap data failed with error: {err}")
        return 0, err, {}

    return statuscode, statusmessage, cmcdict
