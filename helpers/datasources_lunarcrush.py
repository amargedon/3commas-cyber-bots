#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import json
import time

import requests

def get_lunarcrush_data(logger, program, config, section, usdtbtcprice):
    """Get the top x GalaxyScore, AltRank coins from LunarCrush."""

    lccoins = {}
    lcapikey = config.get(section, "lc-apikey")
    lcfetchlimit = config.get(section, "lc-fetchlimit")

    # Construct headers
    headers = {"Authorization": f"Bearer {lcapikey}"}

    # Construct query for LunarCrush data
    if "altrank" in program:
        parms = {
            "sort": "alt_rank",
            "limit": lcfetchlimit,
            "desc": 0,
        }
    elif "galaxyscore" in program:
        parms = {
            "sort": "galaxy_score",
            "limit": lcfetchlimit,
        }
    else:
        logger.error("Fetching LunarCrush data failed, could not determine datatype to fetch")
        return {}

    try:
        result = requests.request(
            "GET", "https://lunarcrush.com/api3/coins",
            headers=headers,
            params=parms,
            timeout=(3.05, 30.0)
        )
        result.raise_for_status()
        data = result.json()

        if "data" in data.keys():
            for i, crush in enumerate(data["data"], start=1):
                crush["categories"] = (
                    list(crush["categories"].split(",")) if crush["categories"] else []
                )
                crush["rank"] = i
                crush["volbtc"] = crush["v"] / float(usdtbtcprice)
                logger.debug(
                    f"rank:{crush['rank']:3d}  acr:{crush['acr']:4d}   gs:{crush['gs']:3.1f}   "
                    f"s:{crush['s']:8s} '{crush['n']:25}'   volume in btc:{crush['volbtc']:12.2f}"
                    f"   categories:{crush['categories']}"
                )
            lccoins = data["data"]

    except requests.exceptions.HTTPError as err:
        logger.error(
            "Fetching LunarCrush data failed with code %d: %s" %
            (err.response.status_code, err.response.text)
        )
        return {}

    logger.info("Fetched LunarCrush ranking OK (%s coins)" % (len(lccoins)))

    return lccoins
