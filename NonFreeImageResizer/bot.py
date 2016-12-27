#Will work on
#Apache License 2.0 - DatGuy
import re
import mwparserfromhell
import sys
from wikitools import *
import string
import datetime
import userpass
import time


#Login
site = wiki.Wiki()
site.login(userpass.username, userpass.password)

#Check if enabled or not for task
def startAllowed():
    print "Checking if allowed"
    start = page.page(site, 'User:DatBot/task3')
    startext = start.getWikiText()
    if startext == "Run":
        return True
    else:
        return False
    
def transclusions(template):
    templatename = 'Template:' + template
    #Not needed right now, but maybe for a future bot task?
    results = pagelist.listFromQuery(site, result['query']['embeddedin'], eititle=templatename)
    return results

def nobots(editpage, user='DatBot', task=None):
    #Thanks to Theo for inspiration
    editpage = page.Page(site, editpage)
    textpage = editpage.getWikiText()
    if task == None:
        task = user
    else:
        task = user + '-' + task
    textpage = mwparserfromhell.parse(textpage)
    for tl in textpage.filter_templates():
        if tl.name in ('bots', 'nobots'):
            break
    else:
            return True
    for param in tl.params:
        bots = [x.lower().strip() for x in param.value.split(",")]
        if param.name == 'allow':
            if ''.join(bots) == 'none':
                return False
            for bot in bots:
                if bot in (user, task, 'all'):
                    return True
        elif param.name == 'deny':
            if ''.join(bots) == 'none':
                return True
            for bot in bots:
                if bot in (user, task, 'all'):
                    return False
    return False
