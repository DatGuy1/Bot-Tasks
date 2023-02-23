from wikitools import wiki, page, api
import re
import time
from datetime import datetime, timedelta
import userpass

site = wiki.Wiki()
site.login(userpass.username, userpass.password)

updatePage = page.Page(site, 'User:DatBot/newpagesbacklog')
templateText = """{{{{#switch: {{{{{{1}}}}}}
  | total_pages = {:d}
  | weekly_reviewed = {:d}
  | timestamp = ~~~~~
  | attribution = according to [[User:DatBot|DatBot]]
}}}}"""
summaryText = "Updating page triage stats: {:d} pages unreviewed " \
              "([[Wikipedia:Bots/Requests for approval/DatBot 11|BOT]] - [[User:DatBot/run/task11|disable]])"


def FetchStats():
    params = {
        'action': 'pagetriagestats',
        'namespace': '0'
    }
    req = api.APIRequest(site, params)
    pageStats = req.query(False)['pagetriagestats']['stats']

    # total_pages, weekly_reviewed
    return pageStats['unreviewedarticle']['count'], pageStats['reviewedarticle']['reviewed_count']


def IsStartAllowed() -> bool:
    return page.Page(site, 'User:DatBot/run/task11').getWikiText() == 'Run'


def IsEditNecessary(totalPages: int, weeklyReviewed: int) -> bool:
    pageText = updatePage.getWikiText()

    totalPagesMatch = re.search(r'total_pages\s*=\s*(\d+)', pageText)
    if totalPagesMatch is not None:
        if int(totalPagesMatch.group(1)) != totalPages:
            return True

    weeklyReviewedMatch = re.search(r'weekly_reviewed\s*=\s*(\d+)', pageText)
    if weeklyReviewedMatch is not None:
        if int(weeklyReviewedMatch.group(1)) != weeklyReviewed:
            return True

    return False


def UpdateTemplate(totalPages: int, weeklyReviewed: int) -> None:
    newText = templateText.format(totalPages, weeklyReviewed)
    updatePage.edit(
        text=newText,
        summary=summaryText.format(totalPages),
        bot=True
    )

    updatePage.purge(forcerecursivelinkupdate=True)


def main():
    while True:
        # Wait until the next even-hour interval
        nextEditTime = timeNow = datetime.utcnow()
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

        totalPages, weeklyReviewed = FetchStats()
        if IsEditNecessary(totalPages, weeklyReviewed):
            UpdateTemplate(totalPages, weeklyReviewed)

        return

if __name__ == "__main__":
    main()
