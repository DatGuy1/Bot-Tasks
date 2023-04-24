from typing import Any, Dict

import re
import time
from datetime import datetime, timedelta

import userpass

from wikitools import api, page, wiki

site = wiki.Wiki()
site.login(userpass.username, userpass.password)

RunPage = page.Page(site, "User:DatBot/run/task11")
UpdatePage = page.Page(site, "User:DatBot/newpagesbacklog")
TemplateText = """
{{{{#switch: {{{{{{1}}}}}}
  | unreviewed_articles = {unreviewed_articles:d}
  | unreviewed_redirects = {unreviewed_redirects:d}
  | unreviewed_drafts = {unreviewed_drafts:d}
  | weekly_reviewed_articles = {weekly_reviewed_articles:d}
  | weekly_reviewed_redirects = {weekly_reviewed_redirects:d}
  | timestamp = ~~~~~
  | attribution = according to [[User:DatBot|DatBot]]
}}}}"""
SummaryText = (
    "Updating page triage stats: {unreviewed_articles:d} articles unreviewed "
    "([[Wikipedia:Bots/Requests for approval/DatBot 11|BOT]] - [[User:DatBot/run/task11|disable]])"
)


# TODO: Use typing.TypeAlias when toolforge supports it
def FetchStats() -> Dict[str, int]:
    params = {"action": "pagetriagestats", "namespace": "0"}
    req = api.APIRequest(site, params)
    pageStats = req.query(False)["pagetriagestats"]["stats"]

    triageStats = {
        "unreviewed_articles": pageStats["unreviewedarticle"]["count"],
        "unreviewed_redirects": pageStats["unreviewedredirect"]["count"],
        "unreviewed_drafts": pageStats["unrevieweddraft"]["count"],
        "weekly_reviewed_articles": pageStats["reviewedarticle"]["reviewed_count"],
        "weekly_reviewed_redirects": pageStats["reviewedredirect"]["reviewed_count"],
    }

    return triageStats


def IsStartAllowed() -> bool:
    return RunPage.getWikiText(force=True) == "Run"


def IsEditNecessary(newValues: Dict[str, int]) -> bool:
    pageText = UpdatePage.getWikiText()

    def IsValueModified(searchKey: Any, newValue: int) -> bool:
        keyMatch = re.search(rf"{searchKey}\s*=\s*(\d+)", pageText)
        if keyMatch is None:
            # Something is corrupted, reset it
            return True
        else:
            return int(keyMatch.group(1)) != newValue

    if any(IsValueModified(statName, statValue) for statName, statValue in newValues.items()):
        return True

    return False


def UpdateTemplate(newValues: Dict[str, int]) -> None:
    newText = TemplateText.format(**newValues)
    UpdatePage.edit(text=newText, summary=SummaryText.format(**newValues), bot=True)

    UpdatePage.purge(forcerecursivelinkupdate=True)


def main() -> None:
    while True:
        # Wait until the next even-hour interval
        timeNow = datetime.utcnow()
        if timeNow.hour % 2 == 0:
            nextEditTime = timeNow + timedelta(hours=2)
        else:
            nextEditTime = timeNow + timedelta(hours=1)

        nextEditTime = nextEditTime.replace(minute=0, second=0, microsecond=0)
        waitTime = (nextEditTime - timeNow).total_seconds()

        # print("Sleeping {:.0f} minutes".format(waitTime / 60))
        time.sleep(waitTime)

        if not IsStartAllowed():
            continue

        newValues = FetchStats()
        if IsEditNecessary(newValues):
            UpdateTemplate(newValues)

        # I'm not really sure why there was a return call here. Hopefully it still works.
        time.sleep(120)


if __name__ == "__main__":
    main()
