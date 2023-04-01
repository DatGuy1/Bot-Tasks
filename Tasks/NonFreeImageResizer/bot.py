#! /usr/bin/env python
import mwclient
import re
import mwparserfromhell
import sys
import string
import datetime
import os
import userpass
import time

# CC-BY-SA Theopolisme, DatGuy
# A series of functions useful to DatBot's NonFreeImageResizer.

# This logs in to enwiki as DatBot
global site
site = mwclient.Site("en.wikipedia.org")
site.login(userpass.username, userpass.password)


def deleteFile(fileName):
    # fileList = [f for f in os.listdir(".") if f.startswith(fileName)]
    # for fileObject in fileList:
    if os.path.isfile(fileName):
        os.remove(fileName)


def canRun(page):
    """ Returns True if the given check page is still set to "Run";
	otherwise, returns false. Accepts one required argument, "page."
	"""
    print("Checking checkpage.")
    page = site.Pages[page]
    text = page.text()

    if text == "Run":
        print("We're good!")
        return True

    return False


def finishCheck(checkPage, pagesDone=0, checkEvery=5, shutdown=0):
    """This function wraps the above
	subfunction, canRun().
	"""

    if shutdown != 0:
        if pagesDone >= shutdown:
            print("I've done {0}; all done!".format(pagesDone))
            return False
    if pagesDone % donenow_div == 0:
        if checkpage(checkpagey) == True:
            return True
        else:
            print("I've been disabled.")
            return False
    return True


def nobotCheck(page, user="DatBot", task=None):
    """Checks a page to make sure
	bot is not denied. Returns true
	if bot is allowed. Two parameters accepted,
	"page" and "bot."
	"""
    page = site.Pages[page]
    text = page.edit()

    if task == None:
        task = user
    else:
        task = user + "-" + task
    text = mwparserfromhell.parse(text)
    for tl in text.filter_templates():
        if tl.name in ("bots", "nobots"):
            break
    else:
        return True
    for param in tl.params:
        bots = [x.lower().strip() for x in param.value.split(",")]
        if param.name == "allow":
            if "".join(bots) == "none":
                return False
            for bot in bots:
                if bot in (user, task, "all"):
                    return True
        elif param.name == "deny":
            if "".join(bots) == "none":
                return True
            for bot in bots:
                if bot in (user, task, "all"):
                    return False
    return False
