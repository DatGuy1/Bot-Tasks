from wikitools import wiki, page, api
import re
import time
from datetime import datetime
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
              "([[Wikipedia:Bots/Requests for approval/DatBot 11|BOT]] - [[User:DatBot/Pending backlog/Run|disable]])"


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
    return page.Page(site, 'User:DatBot/run/task11').getWikiText() == "Run"


def IsEditNecessary(totalPages: int, weeklyReviewed: int) -> bool:
    totalPagesMatch = re.search(r'total_pages\s*=\s*(\d+)', updatePage.getWikiText())
    if totalPagesMatch is not None:
        if int(totalPagesMatch.group(1)) != totalPages:
            return False

    weeklyReviewedMatch = re.search(r'weekly_reviewed\s*=\s*(\d+)', updatePage.getWikiText())
    if weeklyReviewedMatch is not None:
        if int(weeklyReviewedMatch.group(1)) != weeklyReviewed:
            return False

    return True


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
        # Wait until the next 15 interval
        # print("Sleeping {} minutes".format(15 - datetime.now().minute % 15))
        time.sleep((15 - datetime.now().minute % 15) * 60)

        if not IsStartAllowed():
            continue

        totalPages, weeklyReviewed = FetchStats()
        if IsEditNecessary(totalPages, weeklyReviewed):
            UpdateTemplate(totalPages, weeklyReviewed)


if __name__ == "__main__":
    main()
