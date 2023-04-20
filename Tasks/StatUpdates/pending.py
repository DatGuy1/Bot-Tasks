import re
import time
from datetime import datetime

import userpass

from wikitools import api, page, wiki

site = wiki.Wiki()
site.login(userpass.username, userpass.password)

RunPage = page.Page(site, "User:DatBot/run/task4")
UpdatePage = page.Page(site, "User:DatBot/pendingbacklog")
TemplateText = """{{{{#switch: {{{{{{1}}}}}}
  | level = {level:d}}
  | sign = ~~~~~
  | info = {num_pages} pages according to [[User:DatBot|DatBot]]
}}"""
SummaryText = (
    "Updating pending changes level to level {:d} with {:d} pages "
    "([[Wikipedia:Bots/Requests for approval/DatBot 4|BOT]] - [[User:DatBot/run/task4|disable]])"
)


def GetNumberOfPages() -> int:
    params = {"action": "query", "list": "oldreviewedpages", "orlimit": "max", "ordir": "newer"}
    req = api.APIRequest(site, params)
    res = req.query(False)

    return len(res["query"]["oldreviewedpages"])


def IsStartAllowed() -> bool:
    return RunPage.getWikiText(force=True) == "Run"


def ConvertPagesToLevel(pageAmount: int) -> int:
    # TODO: Switch to match once Toolforge supports it
    if pageAmount <= 3:
        return 5
    elif pageAmount <= 7:
        return 4
    elif pageAmount <= 12:
        return 3
    elif pageAmount <= 17:
        return 2
    else:
        return 1


def IsEditNecessary(pageAmount: int) -> bool:
    currentPageAmountMatch = re.search(r"info\s*=\s*(\d+)", UpdatePage.getWikiText())
    if currentPageAmountMatch is not None:
        currentPageAmount = int(currentPageAmountMatch.group(1))
        return currentPageAmount != pageAmount

    return True


def UpdateTemplate(pageAmount: int) -> None:
    backlogLevel = ConvertPagesToLevel(pageAmount)
    newText = TemplateText.format(level=backlogLevel, num_pages=pageAmount)
    UpdatePage.edit(text=newText, summary=SummaryText.format(backlogLevel, pageAmount), bot=True)

    UpdatePage.purge(forcerecursivelinkupdate=True)


def main() -> None:
    while True:
        # Wait until the next 15 minute interval
        # print("Sleeping {} minutes".format(15 - datetime.now().minute % 15))
        time.sleep((15 - datetime.now().minute % 15) * 60)

        if not IsStartAllowed():
            continue

        rowAmount = GetNumberOfPages()
        if IsEditNecessary(rowAmount):
            UpdateTemplate(rowAmount)


if __name__ == "__main__":
    main()
