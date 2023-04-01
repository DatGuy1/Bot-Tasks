# -*- coding: utf-8 -*-
import re
import json
import sys
from wikitools import *
import userpass
import mwparserfromhell

site = wiki.Wiki()
site.login(userpass.username, userpass.password)
eTitles = ["Template:Infobox journal", "Template:Infobox magazine"]
journalTitlesStart = "Infobox journal"
journalStart = "WikiProject Academic Journals"
magazineStart = "WikiProject Magazines"
bannershellStart = "WikiProject banner shell"

def fetchList(templateTitle):
    returnList = [templateTitle]
    params = {"action":"query",
              "list":"backlinks",
              "bltitle":"Template:{}".format(templateTitle),
              "bllimit":"max",
              "blfilterredir":"redirects",
              "blnamespace":"10"
              }

    for pageElement in api.APIRequest(site, params).query(False)["query"]["backlinks"]:
        returnList.append("{{"+pageElement["title"][9:].lower())

    return returnList

def updateLists():
    journalTitles = fetchList(journalTitlesStart)
    journalProjects = fetchList(journalStart)
    magazineProjects = fetchList(magazineStart)
    bannershellWP = fetchList(bannershellStart)

    return [journalTitles, journalProjects, magazineProjects, bannershellWP]

def startAllowed():
    if page.Page(site, "User:DatBot/run/task9").getWikiText() != "true":
        return False
    else:
        return True

def getEmbeds():
    ePages1 = []
    ePages2 = []
    for pageTitle in eTitles:
        params = {"action":"query",
                  "list":"embeddedin",
                  "eititle": pageTitle,
                  "eilimit":"5000",
                  "eifilterredir":"nonredirects",
                  "einamespace":"0"
                  }
        req = api.APIRequest(site, params)
        res = req.query(False)
        length = len(res["query"]["embeddedin"])

        while length >= 5000:
            for pageName in res["query"]["embeddedin"]:
                if pageTitle == "Template:Infobox journal":
                    ePages1.append(pageName["title"])
                else:
                    ePages2.append(pageName["title"])

            length = len(res["query"]["embeddedin"])

            try:
                params["eicontinue"] = res["continue"]["eicontinue"]
            except KeyError:
                pass

            req = api.APIRequest(site, params)
            res = req.query(False)

        return [ePages1, ePages2]

def changePage(pageTitle, isJournal, originalPage, bannershellWP):
    if not startAllowed():
        print("no start")
        return

    if page.Page(site, pageTitle).exists:
        fileText = page.Page(site, pageTitle).getWikiText()
    else:
        fileText = ""

    if not allowBots(fileText):
        return

    if isJournal:
        stringAdd = "{{WikiProject Academic Journals|class=File}}"
        transcludePage = eTitles[0]
    else:
        stringAdd = "{{WikiProject Magazines|class=File}}"
        transcludePage = eTitles[1]

    bannershellCheck = [s for s in bannershellWP if s in fileText]

    if len(bannershellCheck) > 0:
        fileText = re.sub(r"({}.*\|1=)".format(bannershellCheck[0]), "\g<1>\n{}".format(stringAdd), fileText, re.IGNORECASE)
    else:
        fileText = "{}\n".format(stringAdd + fileText)

    editReason = "Adding {} because [[{}]] transcludes {} ([[Wikipedia:Bots/Requests for approval/DatBot 9|BOT]])".format(stringAdd, originalPage, transcludePage)
    print(editReason)

    try:
        page.Page(site, pageTitle).edit(text = fileText,
                                        bot = True,
                                        summary = editReason)
    except Exception as e:
        page.Page(site, "User:DatBot/pageerror").edit(
            appendtext="\n\n[[{}]]: {}".format(originalPage, e),
            bot = True,
            summary = "Reporting error")

def main():
    pagesChecked = ""

    if not startAllowed():
        print("no start")
        return

    [journalTitles, journalProjects, magazineProjects, bannershellWP] = updateLists()
    [ePages1, ePages2] = getEmbeds()

    with open("/data/project/datbot/Tasks/wikiproject/pageschecked.txt", "r") as f:
        pagesChecked = f.read()

    appendFile = open("/data/project/datbot/Tasks/wikiproject/pageschecked.txt", "a")
    for ePage in ePages1 + list(set(ePages2) - set(ePages1)):
        if ePage in pagesChecked:
            continue
        else:
            try:
                # https://regex101.com/r/BXBwby/1
                fileName = re.findall(r"^\s*\|\s*(?:image|cover|image_file|logo)\s*=\s*(?:\[\[)?(?:(?:File|Image)\s*:\s*)?(\w[^\|<\]}{\n]*)",
                          page.Page(site, ePage).getWikiText(), re.IGNORECASE | re.M)[0]

                fileTalk = "File talk:{}".format(fileName)
                fileText = ""
                talkObject = page.Page(site, fileTalk)

                try:
                    if talkObject.exists:
                        fileText = talkObject.getWikiText()
                except Exception as e:
                    page.Page(site, "User:DatBot/pageerror").edit(
                    appendtext="\n\n[[{}]]: {}".format(ePage, e),
                    bot = True,
                    summary = "Reporting error")
                    continue

                if ePage in ePages1:
                    if any(pageElement in fileText.lower() for pageElement in journalProjects):
                        raise IndexError

                    changePage(fileTalk, True, ePage, bannershellWP)

                if ePage in ePages2:
                    if any(pageElement in fileText.lower() for pageElement in magazineProjects):
                        raise IndexError

                    changePage(fileTalk, False, ePage, bannershellWP)

            except IndexError:
                pass
            appendFile.write("{}\n".format(ePage)) # all refreshed monthly
    appendFile.close()

def allowBots(text):
    user = "datbot"
    text = mwparserfromhell.parse(text)
    for tl in text.filter_templates():
        if tl.name.matches(["bots", "nobots"]):
            break
    else:
        return True
    for param in tl.params:
        bots = [x.lower().strip() for x in param.value.split(",")]
        if param.name == "allow":
            if "".join(bots) == "none": return False
            for bot in bots:
                if bot in (user, "all"):
                    return True
        elif param.name == "deny":
            if "".join(bots) == "none": return True
            for bot in bots:
                if bot in (user, "all"):
                    return False
    if (tl.name.matches("nobots") and len(tl.params) == 0):
        return False
    return True

if __name__ == "__main__":
    main()
