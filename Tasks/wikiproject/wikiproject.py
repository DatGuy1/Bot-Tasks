# -*- coding: utf-8 -*-
import pathlib
import re

import userpass

import mwparserfromhell
from wikitools import *

site = wiki.Wiki()
site.login(userpass.username, userpass.password)

RunPage = page.Page(site, "User:DatBot/run/task9")

infoboxTemplates = {"journal": "Template:Infobox journal", "magazine": "Template:Infobox magazine"}
journalStart = "WikiProject Academic Journals"
magazineStart = "WikiProject Magazines"
bannershellStart = "WikiProject banner shell"


def FetchWikiProjectTemplateNames(templateTitle: str) -> set[str]:
    returnList = {templateTitle}
    params = {
        "action": "query",
        "list": "backlinks",
        "bltitle": f"Template:{templateTitle}",
        "bllimit": "max",
        "blfilterredir": "redirects",
        "blnamespace": "10",
    }

    for pageElement in api.APIRequest(site, params).query(False)["query"]["backlinks"]:
        returnList.add("{{" + pageElement["title"][9:].lower())

    return returnList


def UpdateLists() -> tuple[set[str], set[str], set[str]]:
    journalProjects = FetchWikiProjectTemplateNames(journalStart)
    magazineProjects = FetchWikiProjectTemplateNames(magazineStart)
    bannershellWP = FetchWikiProjectTemplateNames(bannershellStart)

    return journalProjects, magazineProjects, bannershellWP


def IsStartAllowed() -> bool:
    return RunPage.getWikiText(force=True) == "true"


def GetEmbeds() -> tuple[set[str], set[str]]:
    journalPages: set[str] = set()
    magazinePages: set[str] = set()
    for infoboxTemplate in infoboxTemplates.values():
        params = {
            "action": "query",
            "list": "embeddedin",
            "eititle": infoboxTemplate,
            "eilimit": "5000",
            "eifilterredir": "nonredirects",
            "einamespace": "0",
        }
        req = api.APIRequest(site, params)
        res = req.query(False)
        numPages = len(res["query"]["embeddedin"])

        while numPages >= 5000:
            for pageName in res["query"]["embeddedin"]:
                if infoboxTemplate == "Template:Infobox journal":
                    journalPages.add(pageName["title"])
                elif infoboxTemplate == "Template:Infobox magazine":
                    magazinePages.add(pageName["title"])

            numPages = len(res["query"]["embeddedin"])
            try:
                params["eicontinue"] = res["continue"]["eicontinue"]
            except KeyError:
                pass

            req = api.APIRequest(site, params)
            res = req.query(False)

        return journalPages, magazinePages


def EditPage(pageTitle: str, isJournal: bool, originalPage: str, bannershellWP: set[str]) -> None:
    if not IsStartAllowed():
        print("no start")
        return

    if page.Page(site, pageTitle).exists:
        fileText = page.Page(site, pageTitle).getWikiText()
    else:
        fileText = ""

    if not BotAllowed(fileText, "DatBot"):
        return

    if isJournal:
        wpToAdd = "{{WikiProject Academic Journals|class=File}}"
        transcludePage = infoboxTemplates[0]
    else:
        wpToAdd = "{{WikiProject Magazines|class=File}}"
        transcludePage = infoboxTemplates[1]

    bannershellCheck = [s for s in bannershellWP if s in fileText]

    if len(bannershellCheck) > 0:
        fileText = re.sub(
            r"({}.*\|1=)".format(bannershellCheck[0]), r"\g<1>\n{}".format(wpToAdd), fileText, re.IGNORECASE
        )
    else:
        fileText = "{}\n".format(wpToAdd + fileText)

    editReason = (
        f"Adding {wpToAdd} because [[{originalPage}]] transcludes {transcludePage} "
        f"([[Wikipedia:Bots/Requests for approval/DatBot 9|BOT]])"
    )
    print(editReason)

    try:
        page.Page(site, pageTitle).edit(text=fileText, bot=True, summary=editReason)
    except Exception as e:
        page.Page(site, "User:DatBot/errors/wikiproject").edit(
            appendtext="\n\n[[{}]]: {}".format(originalPage, e), bot=True, summary="Reporting error"
        )


def main() -> None:
    if not IsStartAllowed():
        print("no start")
        return

    journalProjects, magazineProjects, bannershellWP = UpdateLists()
    journalPages, magazinePages = GetEmbeds()

    pagesCheckedPath = pathlib.Path(__file__).parent / "pageschecked.txt"
    with pagesCheckedPath.open("r") as f:
        pagesChecked = f.read()

    appendFile = pagesCheckedPath.open("a")
    for pageWithInfobox in journalPages.union(magazinePages):
        if pageWithInfobox in pagesChecked:
            continue
        else:
            try:
                # https://regex101.com/r/BXBwby/1
                fileName = re.findall(
                    r"^\s*\|\s*(?:image|cover|image_file|logo)\s*=\s*(?:\[\[)?(?:(?:File|Image)\s*:\s*)?(\w[^\|<\]}{\n]*)",  # noqa: E501
                    page.Page(site, pageWithInfobox).getWikiText(),
                    re.IGNORECASE | re.M,
                )[0]

                fileTalk = f"File talk:{fileName}"
                fileText = ""
                talkObject = page.Page(site, fileTalk)

                try:
                    if talkObject.exists:
                        fileText = talkObject.getWikiText()
                except Exception as e:
                    page.Page(site, "User:DatBot/pageerror").edit(
                        appendtext=f"\n\n[[{pageWithInfobox}]]: {e}. ~~~~~", bot=True, summary="Reporting error"
                    )
                    continue

                if pageWithInfobox in journalPages:
                    if any(pageElement in fileText.lower() for pageElement in journalProjects):
                        # If any journal WikiProject templates are already there. Maybe switch this to category check?
                        raise IndexError

                    EditPage(fileTalk, True, pageWithInfobox, bannershellWP)

                if pageWithInfobox in magazinePages:
                    if any(pageElement in fileText.lower() for pageElement in magazineProjects):
                        # If any magazine WikiProject templates are already there. Maybe switch this to category check?
                        raise IndexError

                    EditPage(fileTalk, False, pageWithInfobox, bannershellWP)

            except IndexError:
                pass

            appendFile.write("{}\n".format(pageWithInfobox))  # all refreshed monthly
    appendFile.close()


@property
def BotAllowed(text: str, botName: str) -> bool:
    botName = botName.lower()

    text = mwparserfromhell.parse(text)
    for tl in text.filter_templates():
        if tl.name.matches(["bots", "nobots"]):
            break
    else:
        return True
    for param in tl.params:
        bots = [x.lower().strip() for x in param.value.split(",")]
        if param.name == "allow":
            if "".join(bots) == "none":
                return False
            for bot in bots:
                if bot in (botName, "all"):
                    return True
        elif param.name == "deny":
            if "".join(bots) == "none":
                return True
            for bot in bots:
                if bot in (botName, "all"):
                    return False
    if tl.name.matches("nobots") and len(tl.params) == 0:
        return False
    return True


if __name__ == "__main__":
    main()
