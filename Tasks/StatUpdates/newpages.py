from typing import Any, Dict

import re

import userpass

from wikitools import api, page, wiki

site = wiki.Wiki()
site.login(userpass.username, userpass.password)

RunPage = page.Page(site, "User:DatBot/run/task11")
UpdatePage = page.Page(site, "User:DatBot/newpagesbacklog")
TemplateText = """{{{{#switch: {{{{{{1}}}}}}
  | unreviewed_articles = {unreviewed_articles:d}
  | unreviewed_redirects = {unreviewed_redirects:d}
  | unreviewed_drafts = {unreviewed_drafts:d}
  | oldest_article = {oldest_article}
  | oldest_redirect = {oldest_redirect}
  | oldest_draft = {oldest_draft}
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
        "oldest_article": pageStats["unreviewedarticle"]["oldest"],
        "oldest_redirect": pageStats["unreviewedredirect"]["oldest"],
        "oldest_draft": pageStats["unrevieweddraft"]["oldest"],
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
    if not IsStartAllowed():
        return

    newValues = FetchStats()
    if IsEditNecessary(newValues):
        UpdateTemplate(newValues)


if __name__ == "__main__":
    main()
