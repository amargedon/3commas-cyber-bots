#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import json
import time

import requests

def get_coingecko_data(logger, cg_apikey, start_number, end_number, convert, change_percentage, page_size, delay_sec):
    """Get the data from CoinGecko."""

    cgdict = []
    statuscode = -1

    # Construct query for CoinGecko data
    parms = {
        "per_page": page_size,
        "page": 1,
        "sparkline": False,
        "vs_currency": convert,
        "order": "market_cap_desc",
        "price_change_percentage": change_percentage
    }

    if cg_apikey:
        parms["x_cg_pro_api_key"] = cg_apikey

    try:
        # Range from first page number to fetch, to page number to stop at
        # The +1 and +1/+2 are required because the page stop should be one
        # higher than the last page to fetch
        rangestart = int(start_number / page_size) + 1
        rangestop = int(end_number / page_size) + (1 if end_number >= page_size else 2)

        logger.debug(
            f"Calculated page range between {rangestart} and {rangestop} "
            f"for page_size = {page_size}, start_number = {start_number}, "
            f"end_number = {end_number}"
        )

        for page in range(rangestart, rangestop, 1):
            # Optimize a bit, request only the remaining coins on the last page
            if page * page_size > end_number:
                if end_number < page_size:
                    # Single page with less than 250 coins requested
                    parms["per_page"] = end_number
                else:
                    # Multiple pages, substract the fetched number of coins from the previous pages
                    parms["per_page"] = end_number - ((page - 1) * page_size)

            parms["page"] = page

            result = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params=parms,
                timeout=(3.05, 30.0)
            )

            if result.ok:
                data = result.json()
                for coin in data:
                    if coin.get("market_cap_rank") is not None:
                        if int(coin["market_cap_rank"]) < start_number:
                            continue

                        if int(coin["market_cap_rank"]) > end_number:
                            break

                        cgdict.append(coin)
                    else:
                        logger.debug(
                            f"Unprocessable coin without readable market_cap_rank: {coin}"
                        )

                # Prevent rate limit error by waiting a bit for the next request
                time.sleep(delay_sec)
            else:
                statuscode = result.status_code
                break
    except requests.exceptions.HTTPError as err:
        logger.error(f"Fetching CoinGecko data failed with error: {err}")
        return 0, {}

    return statuscode, cgdict
