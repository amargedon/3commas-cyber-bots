#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import json

import cloudscraper
import requests
from bs4 import BeautifulSoup

def get_botassist_data(logger, botassistlist, start_number, limit):
    """Get the top pairs from 3c-tools bot-assist explorer."""

    url = "https://www.3c-tools.com/markets/bot-assist-explorer"
    parms = {"list": botassistlist}

    pairs = list()
    try:
        result = requests.get(url, params=parms)
        result.raise_for_status()
        soup = BeautifulSoup(result.text, features="html.parser")
        data = soup.find("table", class_="table table-striped table-sm")

        if data is not None:
            columncount = 0
            columndict = {}

            # Build list of columns we are interested in
            tablecolumns = data.find_all("th")

            for column in tablecolumns:
                if column.text not in ("#"):
                    columndict[columncount] = column.text

                columncount += 1

            tablerows = data.find_all("tr")
            for row in tablerows:
                rowcolums = row.find_all("td")
                if len(rowcolums) > 0:
                    rank = int(rowcolums[0].text)
                    if start_number and rank < start_number:
                        continue

                    pairdata = {}

                    # Iterate over the available columns and collect the data
                    for key, value in columndict.items():
                        if value == "24h volume":
                            pairdata[value] = float(
                                    rowcolums[key].text.replace(" BTC", "").replace(",", "")
                                )
                        elif value == "volatility":
                            pairdata[value] = float(
                                    rowcolums[key].text.replace("%", "").replace(",", "")
                                )
                        else:
                            pairdata[value] = rowcolums[key].text.replace("\n", "")

                    # For some the symbol is unknown, so extract it from the pair
                    if pairdata["symbol"].replace(" ", "") == "-":
                        pairdata["symbol"] = pairdata["pair"].split("_")[1]

                    pairs.append(pairdata)

                    if limit and rank == limit:
                        break
        else:
            logger.warning(
                f"Table on {botassistlist} does not have any content (rows/columns). Cannot fetch "
                f"any pairs. This could be ok when no pairs are listed."
            )

    except requests.exceptions.HTTPError as err:
        logger.error("Fetching 3c-tools bot-assist data failed with error: %s" % err)
        if result.status_code == 500:
            logger.error(f"Check if the list setting '{botassistlist}' is correct")

        return pairs

    logger.info(
        f"Fetched 3c-tools {botassistlist} data OK ({len(pairs)} pairs)"
    )

    return pairs


def get_shared_bot_data(logger, bot_id, bot_secret):
    """Get the shared bot data from the 3C website"""

    url = "https://app.3commas.io/wapi/bots/%s/get_bot_data?secret=%s" % (bot_id, bot_secret)

    data = {}
    try:
        statuscode = 0
        scrapecount = 0
        while (scrapecount < 3) and (statuscode != 200):
            scraper = cloudscraper.create_scraper(
                interpreter = "nodejs", delay = scrapecount * 6, debug = False
            )

            page = scraper.get(url)
            statuscode = page.status_code

            logger.debug(
                f"Status {statuscode} for bot {bot_id}"
            )

            if statuscode == 200:
                data = json.loads(page.text)
                logger.info("Fetched %s 3C shared bot data OK" % (bot_id))

            scrapecount += 1

        if statuscode != 200:
            data = None
            logger.error("Failed to fetch %s 3C shared bot data" % (bot_id))

    except json.decoder.JSONDecodeError:
        logger.error(f"Shared bot data ({bot_id}) is not valid json")

    return data
