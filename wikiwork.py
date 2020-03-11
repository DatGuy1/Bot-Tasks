# == PROGRAM DESCRIPTION ==
# This program calculates WikiWork-related junk and
# then outputs it on-wiki in a flexible template.
#
# == COPYRIGHT DETAILS ==
# CC-BY-SA / User:Theopolisme on Wikipedia
# Modified by User:DatGuy

from collections import OrderedDict
import re
from wikitools import *
import userpass

site = wiki.Wiki()
site.login(userpass.username, userpass.password)


def startAllowed():
    startText = page.Page(site, "User:DatBot/run/task7").getWikiText()
    return True if startText == "true" else False


def getProjectList():
    """This function gets a list of all
    of the projects that use WP 1.0 assessments.
    """
    projects = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmnamespace": "14",
        "cmtitle": "Category:Wikipedia 1.0 assessments",
        "cmlimit": "max",
    }
    req = api.APIRequest(site, params)
    res = req.query(False)

    while True:
        categoryList = res["query"]["categorymembers"]
        for categoryMember in categoryList:
            # Get category name, encode it in ascii and convert it from string to bytes
            categoryFullName = str(categoryMember["title"].encode("ascii", "ignore"))
            categoryName = re.search(
                "Category:(?P<name>.*) articles by quality", categoryFullName
            )
            # If we succesfully got the category name, get the actual name
            if categoryName is not None:
                projects.append(categoryName.group("name"))
        if "continue" not in res:  # If we're done, exit
            break
        params["cmcontinue"] = res["continue"]["cmcontinue"]
        req = api.APIRequest(site, params)
        res = req.query(False)
    return projects


def numPagesInCategory(categoryName, secondTry=False):
    """This function gets the number of
    items in a given category (0 -> inf).
    Occasionally it needs to be lowercase, so we try that as well
    """
    params = {
        "action": "query",
        "prop": "categoryinfo",
        # This is honestly dumb and ridiculous. The regex takes the full string and returns it with the project in lowercase
        "titles": re.sub(
            r"^(.+?(?= ) )(.+?(?= articles$)) articles$",
            lambda match: r"{0}{1} articles".format(
                match.group(1), match.group(2).lower()
            ),
            categoryName,
        )
        if secondTry
        else categoryName,
    }

    req = api.APIRequest(site, params)
    res = req.query(False)

    # Only key in res["query"]["pages"] is the page ID, but we don't know it, so we use next(iter()) to get the first key, and then enter than dictionary
    try:
        return res["query"]["pages"][next(iter(res["query"]["pages"]))]["categoryinfo"][
            "pages"
        ]
    except KeyError:  # KeyError occurs whenever the category is missing
        return numPagesInCategory(categoryName, True) if not secondTry else 0


# This function gets individualized project stats.
def getProjectStats(projectName):
    categoryNames = []
    for className in ["FA", "A", "GA", "B", "C", "Start", "Stub"]:
        categoryNames.append(
            "Category:{0}-Class {1} articles".format(className, projectName)
        )  # Build the strings
    # Get number of pages for the category of each class for specified projectName
    results = [numPagesInCategory(categoryName) for categoryName in categoryNames]

    return results  # Take values and convert them into a list


# Builds either the WP score or total articles, both use same format
def printWPScoreOrTA(inputMasterArray):
    finalString = []
    for (
        projectNAS
    ) in (
        inputMasterArray
    ):  # projectNAS contains the project name at the first index and the score for it at the second index, 'project name and score'
        finalString.append(
            """{{#ifeq: {{{1|}}} | """
            + projectNAS[0]
            + """ | {{nts|"""
            + str(projectNAS[1])
            + """}} | }} """
        )
    return " ".join(finalString)


def printOmegaScore(omegaArray):
    finalString = []
    for projectNAS in omegaArray:
        finalString.append(
            """{{#ifeq: {{{1|}}} | """
            + projectNAS[0]
            + """ | """
            + str(projectNAS[1])
            + """ | }} """
        )
    return " ".join(finalString)


def printTable(wikiworkArray, omegaArray):
    headerText = """{| class="wikitable sortable" style=""
|+ WikiWork data
|-
! Project
! WikiWork
! Relative WikiWork
"""
    finalString = []
    finalString.append(headerText)
    for wiProject, omProject in zip(wikiworkArray, omegaArray):
        finalString.append(
            "|-\n! {0}\n| {1} || {2}".format(wiProject[0], wiProject[1], omProject[1])
        )
    finalString.append("\n|}")
    return "\n".join(finalString)


def main():
    if not startAllowed():
        return
    totalArticlesArray = []
    wikiworkArray = []
    omegaArray = []

    projectNames = getProjectList()
    for projectName in projectNames:
        print("Processing {0}".format(projectName))
        projectResults = getProjectStats(projectName)

        # This calculates the scores and totals.
        wpScore = 0
        for i, pagesByClass in enumerate(projectResults):
            wpScore += i * pagesByClass
        totalScore = sum(projectResults)

        try:
            omegaScore = "{:0.2f}".format(round(float(wpScore) / float(totalScore), 2))
        except ZeroDivisionError:
            print("Zero division error, skipping {0}".format(projectName))
            continue
        if totalScore == 0 and omegaScore == 0:
            continue
        print("WW: {0} | TOT: {1} | OM: {2}".format(wpScore, totalScore, omegaScore))

        totalArticlesArray.append([projectName, totalScore])
        wikiworkArray.append([projectName, wpScore])
        omegaArray.append([projectName, omegaScore])
    # This runs these functions and stores their results to a dictionary with the corresponding page name
    newContent = {
        "User:WP 1.0 bot/WikiWork/ar": printWPScoreOrTA(totalArticlesArray),
        "User:WP 1.0 bot/WikiWork/ww": printWPScoreOrTA(wikiworkArray),
        "User:WP 1.0 bot/WikiWork/om": printOmegaScore(omegaArray),
        "User:WP 1.0 bot/WikiWork/all": printTable(wikiWorkArray, omegaArray),
    }

    for pageName, pageContent in newContent.items():
        editPage = page.Page(site, pageName)
        editPage.edit(pageContent, summary="Updating WikiWork data", bot=True)
        print("Pushed {}".format(pageName))


if __name__ == "__main__":
    main()