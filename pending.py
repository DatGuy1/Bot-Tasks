from wikitools import wiki, page, api
import re
import time
from datetime import datetime
import userpass

site = wiki.Wiki()
site.login(userpass.username, userpass.password)
updatePage = page.Page(site, 'User:DatBot/pendingbacklog')
templateText = """{{#switch: {{{1}}}
  | level = %d
  | sign = ~~~~~
  | info = %d pages according to [[User:DatBot|DatBot]]
}}"""
summaryText = "[[Wikipedia:Bots/Requests for approval/DatBot 4|Bot]] " \
              "updating pending changes level to level {:d} ({:d} pages)"


def getNumberOfPages():
    params = {'action': 'query',
              'list': 'oldreviewedpages',
              'orlimit': 'max',
              'ordir': 'newer',
              }
    req = api.APIRequest(site, params)
    res = req.query(False)

    return len(res['query']['oldreviewedpages'])


def startAllowed():
    startPage = page.Page(site, 'User:DatBot/Pending backlog/Run')
    return True if startPage.getWikiText() == "Run" else False


def convertPagesToLevel(pageAmount):
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


def editNecessary(pageAmount):
    currentPageAmountMatch = re.search(
        r'info\s*=\s*(\d+)', updatePage.getWikiText())
    if currentPageAmountMatch is not None:
        currentPageAmount = int(currentPageAmountMatch.group(1))
        return currentPageAmount != pageAmount

    return True


def updateTemplate(pageAmount):
    backlogLevel = convertPagesToLevel(pageAmount)
    newText = templateText % (backlogLevel, pageAmount)
    updatePage.edit(
        text=newText,
        summary=summaryText.format(backlogLevel, pageAmount),
        bot=True
    )

    updatePage.purge(forcerecursivelinkupdate=True)


def main():
    while True:
        # Wait until the next 15 interval
        # print("Sleeping {} minutes".format(15 - datetime.now().minute % 15))
        time.sleep((15 - datetime.now().minute % 15) * 60)

        rowAmount = getNumberOfPages()
        if editNecessary(rowAmount):
            updateTemplate(rowAmount)


if __name__ == "__main__":
    main()
