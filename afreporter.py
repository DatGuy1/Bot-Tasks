# Filter reporter, DatBot task 3. Python 3.5, but lots of leftover Python2 code (e.g. string formatting)

# -*- coding: utf-8 -*-
# Copyright 2013 Alex Zaddach (mrzmanwiki@gmail.com). Derative work/modified by 'John Smith' (DatGuy)

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import configparser
import datetime
import json
import threading
import time
from functools import lru_cache
from urllib.parse import quote

import pymysql as MySQLdb
import userpass
from cachetools import TTLCache
from irc.bot import ServerSpec, SingleServerIRCBot
from wikitools import *

IRCActive = False
LogActive = False

site = wiki.Wiki()
site.setMaxlag(-1)
site.login(userpass.username, userpass.password)

AIVPage = None
UAAPage = None

GlobalFilterHitQuota = 10
GlobalFilterTime = 5

configParser = configparser.ConfigParser()
configParser.read("/data/project/datbot/replica.my.cnf")
sqlUser = configParser.get("client", "user").strip().strip("'")
sqlPassword = configParser.get("client", "password").strip().strip("'")

labsDB = MySQLdb.connect(
    db="enwiki_p", host="enwiki.labsdb", user=sqlUser, password=sqlPassword
)
labsDB.autocommit(True)
labsDB.ping(True)
labsCursor = labsDB.cursor()


class Filter:
    filter_id = None
    filter_name = ""
    note = None
    hits_required = None
    time_expiry = None

    def __init__(self, filter_id, note="", hits_required=None, time_expiry=None):
        self.filter_id = filter_id
        self.filter_name = GetFilterName(filter_id)
        self.note = note if bool(note) else None
        self.hits_required = hits_required
        self.time_expiry = time_expiry

    def __repr__(self):
        return "{klass}({attrs})".format(
            klass=self.__class__.__name__,
            attrs=" ".join("{}={!r}".format(k, v) for k, v in self.__dict__.items() if bool(v)),
        )


class TimedTracker(dict):
    def __init__(self):
        super().__init__()
        self.timeSet = set([(item, int(time.time())) for item in self.keys()])

    def purgeExpired(self):
        currentTime = int(time.time())
        removedSet = set([item for item in self.timeSet if item[1] < currentTime - item[0][1].time_expiry])
        self.timeSet.difference_update(removedSet)
        for item in removedSet:
            super().__delitem__(item[0])

    def __getitem__(self, key):
        self.purgeExpired()
        if key not in self:
            return 0

        return super().__getitem__(key)

    def __setitem__(self, key, value):
        self.purgeExpired()
        if key not in self:
            self.timeSet.add((key, int(time.time())))

        return super().__setitem__(key, value)

    def __delitem__(self, key):
        self.timeSet = set([item for item in self.timeSet if item[0] != key])
        self.purgeExpired()
        return super().__delitem__(key)

    def __contains__(self, key):
        self.purgeExpired()
        return super().__contains__(key)


class CommandBot(SingleServerIRCBot):
    def __init__(self, channel: str, nickname: str, serverSpec: ServerSpec):
        SingleServerIRCBot.__init__(self, server_list=[serverSpec], nickname=nickname, realname=nickname)
        self.channel = channel
        self.abuseChannel = None

    def on_welcome(self, connection, _):
        connection.privmsg("NickServ", "identify {0}".format(userpass.ircPassword))
        time.sleep(1)
        connection.join(self.channel)
        self.abuseChannel = connection
        return

    def send_message(self, message: str):
        if self.abuseChannel is None:
            return

        self.abuseChannel.privmsg("#wikipedia-en-abuse-log", message)


class BotRunnerThread(threading.Thread):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    def run(self):
        self.bot.start()


def checkLag(ircBot):
    lagWaitedOut = False
    useAPI = False

    while True:
        # Check replication lag
        labsCursor.execute(
            "SELECT UNIX_TIMESTAMP() - UNIX_TIMESTAMP(rc_timestamp) FROM recentchanges ORDER BY rc_timestamp DESC "
            "LIMIT 1"
        )
        repLag = labsCursor.fetchone()[0]
        # Fallback to API if replag is too high
        if repLag > 300 and not useAPI:
            useAPI = True
            ircBot.send_message("Labs replag too high, falling back to API")
        if repLag < 120 and useAPI:
            useAPI = False
            ircBot.send_message("Using Labs database")

        # Check maxlag if we're using the API
        if useAPI:
            params = {"action": "query", "meta": "siteinfo", "siprop": "dbrepllag"}
            req = api.APIRequest(site, params)
            res = req.query(False)
            maxLag = res["query"]["dbrepllag"][0]["lag"]
            # If maxlag is too high, just stop
            if maxLag > 600 and not lagWaitedOut:
                lagWaitedOut = True
                ircBot.send_message("Server lag too high, stopping reports")
            if lagWaitedOut and maxLag > 120:
                time.sleep(120)
                continue
        break

    if lagWaitedOut:
        ircBot.send_message("Restarting reports")

    return useAPI


def getStart(useAPI):
    if useAPI:
        params = {
            "action": "query",
            "list": "abuselog",
            "aflprop": "ids|timestamp",
            "afllimit": "1",
        }
        req = api.APIRequest(site, params)
        res = req.query(False)
        row = res["query"]["abuselog"][0]
        lastEditTime = row["timestamp"]
        lastEditId = row["id"]
    else:
        labsCursor.execute(
            "SELECT afl_timestamp, afl_id FROM abuse_filter_log ORDER BY afl_id DESC LIMIT 1"
        )
        (lastEditTime, lastEditId) = labsCursor.fetchone()

    return lastEditTime, lastEditId


def normaliseTimestamp(timestamp):  # normalize a timestamp to the API format
    timestamp = str(timestamp)
    if "Z" in timestamp:
        return timestamp

    timestamp = datetime.datetime.strptime(timestamp, "%Y%m%d%H%M%S")
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def logFromAPI(lastEditTime):
    lastEditTime = normaliseTimestamp(lastEditTime)
    params = {
        "action": "query",
        "list": "abuselog",
        "aflstart": lastEditTime,
        "aflprop": "ids|user|action|title|timestamp",
        "afllimit": "50",
        "afldir": "newer",
    }
    req = api.APIRequest(site, params)
    res = req.query(False)
    rows = res["query"]["abuselog"]
    if len(rows) > 0:
        del rows[0]  # The API uses >=, so the first row will be the same as the last row of the last set

    returnList = []
    for row in rows:
        entry = {
            "l": row["id"],
            "a": row["action"],
            "ns": row["ns"],
            "t": page.Page(site, row["title"], check=False, namespace=row["ns"]).unprefixedTitle,
            "u": row["user"],
            "ts": row["timestamp"],
            "f": str(row["filter_id"])
        }
        returnList.append(entry)

    return returnList


def logFromDB(lastid):
    labsCursor.execute(
        """SELECT SQL_NO_CACHE afl_id, afl_action, afl_namespace, afl_title, 
    afl_user_text, afl_timestamp, afl_filter_id FROM abuse_filter_log
    WHERE afl_id > %s ORDER BY afl_id """
        % lastid
    )

    returnList = []
    queryResponse = labsCursor.fetchall()
    for row in queryResponse:
        entry = {
            "l": row[0],
            "a": row[1].decode(encoding="utf-8"),
            "ns": row[2],
            "t": page.Page(site, row[3].decode(encoding="utf-8"), check=False, namespace=row[2]).unprefixedTitle,
            "u": row[4].decode(encoding="utf-8"),
            "ts": row[5].decode(encoding="utf-8"),
            "f": str(row[6])
        }
        returnList.append(entry)

    return returnList


def main():
    logChannel = "#wikipedia-en-abuse-log"
    logServer = "irc.libera.chat"
    botNickname = "DatBot"
    ircBot = CommandBot(logChannel, botNickname, ServerSpec(logServer))
    commandThread = BotRunnerThread(ircBot)
    commandThread.daemon = True
    commandThread.start()

    while len(ircBot.channels) < 1:
        print("Channels not initialised, waiting")
        time.sleep(4)

    vandalismDict, usernameDict = GetLists(ircBot)
    lastListCheck = time.time()

    useAPI = checkLag(ircBot)
    lastLagCheck = time.time()

    # values expire after ttl seconds
    userTripTracker = TTLCache(maxsize=1000, ttl=300)
    IRCreportTracker = TTLCache(maxsize=1000, ttl=60)
    titlesTracker = TTLCache(maxsize=1000, ttl=300)

    AIVreportTracker = TTLCache(maxsize=1000, ttl=600)
    AIVuserTracker = TimedTracker()

    (lastEditTime, lastEditId) = getStart(useAPI)
    while True:
        # Refetch lists every five minutes
        if time.time() > lastListCheck + 300:
            vandalismDict, usernameDict = GetLists(ircBot)
            lastListCheck = time.time()
        if time.time() > lastLagCheck + 600:
            useAPI = checkLag(ircBot)
            lastLagCheck = time.time()

        if useAPI:
            rows = logFromAPI(lastEditTime)
        else:
            rows = logFromDB(lastEditId)

        filterHits = []
        for row in rows:
            logId = row["l"]
            if logId <= lastEditId:
                continue
            action = row["a"]
            pageNamespace = row["ns"]
            title = row["t"]
            trippedFilter = row["f"]
            timestamp = row["ts"]
            wikiUser = user.User(site, row["u"])

            if not wikiUser.exists and not wikiUser.isIP:
                continue

            targetUsername = wikiUser.name
            if not checkStartAllowed():
                time.sleep(60)
                break

            if trippedFilter in usernameDict:
                ircBot.send_message(
                    "Reporting https://en.wikipedia.org/wiki/Special:Contributions/"
                    + targetUsername.replace(" ", "_")
                    + " to UAA for tripping https://en.wikipedia.org/wiki/Special:AbuseFilter/"
                    + trippedFilter
                )
                reportUserUAA(wikiUser, usernameDict[trippedFilter])

            # Is this necessary?
            if title == "Special:UserLogin" or title == "UserLogin" or action == "createaccount":
                continue

            # Prevent multiple hits from the same edit attempt
            if (targetUsername, timestamp) in filterHits:
                pass # continue

            filterHits.append((targetUsername, timestamp))

            # Hits on pagemoves
            if action == "move":
                ircBot.send_message(
                    "User:%s has tripped a filter doing a pagemove"
                    ": https://en.wikipedia.org/wiki/Special:AbuseLog/%s"
                    % (targetUsername, str(logId))
                )

            # Five hits on one article in five minutes or less
            titlesTracker[(pageNamespace, title)] = titlesTracker.get((pageNamespace, title), 0) + 1
            if titlesTracker[(pageNamespace, title)] == 5 and (pageNamespace, title) not in IRCreportTracker:
                p = page.Page(site, title, check=False, followRedirects=False, namespace=pageNamespace)
                ircBot.send_message(
                    "Five filters in the last five minutes have been tripped on %s: "
                    "https://en.wikipedia.org/wiki/Special:AbuseLog?wpSearchTitle=%s"
                    % (p.title, p.urlTitle)
                )
                del titlesTracker[(pageNamespace, title)]
                IRCreportTracker[(pageNamespace, title)] = True

            # Check if the filter is in vandalism list
            if trippedFilter not in vandalismDict:
                continue

            # Generic trip reporting checks
            userTripTracker[targetUsername] = userTripTracker.get(targetUsername, 0) + 1
            # GlobalFilterHitQuota hits in GlobalFilterTime minutes
            if (
                    userTripTracker[targetUsername] >= GlobalFilterHitQuota
                    and trippedFilter in vandalismDict
                    and targetUsername not in AIVreportTracker
            ):
                ircBot.send_message(
                    "User:%s has tripped %d filters within the last %d minutes: "
                    "https://en.wikipedia.org/wiki/Special:AbuseLog?wpSearchUser=%s"
                    % (targetUsername, userTripTracker[targetUsername], 5, quote(targetUsername))
                )
                del userTripTracker[targetUsername]
                reportUser(wikiUser)
                AIVreportTracker[targetUsername] = True

            trippedFilterObject = vandalismDict[trippedFilter]
            numTrips = AIVuserTracker.get((targetUsername, trippedFilterObject), 0) + 1

            AIVuserTracker[(targetUsername, trippedFilterObject)] = numTrips
            if numTrips >= trippedFilterObject.hits_required and targetUsername not in AIVreportTracker:
                ircBot.send_message(
                    "Reporting https://en.wikipedia.org/wiki/Special:Contributions/{} to AIV for tripping "
                    "https://en.wikipedia.org/wiki/Special:AbuseFilter/{} {} times within the last {} minutes".format(
                        targetUsername.replace(" ", "_"), trippedFilterObject.filter_id, numTrips,
                        trippedFilterObject.time_expiry / 60
                    )
                )

                del AIVuserTracker[(targetUsername, trippedFilterObject)]
                reportUser(wikiUser, trippedFilterObject)
                AIVreportTracker[targetUsername] = True

        if rows:
            rows.reverse()
            lastEdit = rows[0]
            lastEditId = lastEdit["l"]
            lastEditTime = lastEdit["ts"]

        time.sleep(1.5)


def checkStartAllowed() -> bool:
    runPage = page.Page(site, "User:DatBot/Filter reporter/Run")
    if runPage.getWikiText() == "Run":
        return True
    else:
        return False


def reportUserUAA(targetUser: user.User, trippedFilter=None):
    if targetUser.isBlocked(True):
        return

    targetUsername = targetUser.name
    reportLine = "\n*{{user-uaa|1=%s}} - " % targetUsername
    editSummary = "Reporting [[Special:Contributions/%s]]" % targetUsername
    if trippedFilter is not None:
        reportLine += "Tripped [[Special:AbuseFilter/%(f)s|filter %(f)s]] (%(n)s)." % {
            "f": trippedFilter.filter_id,
            "n": trippedFilter.filter_name,
        }
        if trippedFilter.note is not None:
            reportLine += " Note: {}.".format(trippedFilter.note)

        editSummary += " for tripping [[Special:AbuseFilter/%(f)s|filter %(f)s]] (%(n)s)" % {
            "f": trippedFilter.filter_id,
            "n": trippedFilter.filter_name,
        }

    reportLine += " ~~~~"
    editSummary += " ([[WP:BOT|BOT]] - [[User:DatBot/Filter reporter/Run|disable]])"

    UAAPage.edit(appendtext=reportLine, summary=editSummary)


def reportUser(targetUser: user.User, trippedFilter=None):
    if targetUser.isBlocked(True):
        return

    targetUsername = targetUser.name

    if targetUser.isIP:
        reportLine = "\n* {{IPvandal|%s}} - " % targetUsername
    else:
        reportLine = "\n* {{Vandal|1=%s}} - " % targetUsername

    editSummary = "Reporting [[Special:Contributions/%s]]" % targetUsername
    if trippedFilter is None:
        reportLine += (
                "Tripped %d abuse filters in the last %d minutes: "
                "([{{fullurl:Special:AbuseLog|wpSearchUser=%s}} details])."
                % (GlobalFilterHitQuota, GlobalFilterTime, quote(targetUsername))
        )
    else:
        reportLine += (
                "Tripped [[Special:AbuseFilter/%(f)s|filter %(f)s]] (%(n)s, "
                "[{{fullurl:Special:AbuseLog|wpSearchUser=%(h)s}} details])."
                % {"f": trippedFilter.filter_id, "n": trippedFilter.filter_name, "h": quote(targetUsername)}
        )
        if trippedFilter.note is not None:
            reportLine += " Note: {}.".format(trippedFilter.note)

        editSummary += " for triggering [[Special:AbuseFilter/{filter_id}|filter {filter_id}]]".format(
            filter_id=trippedFilter.filter_id
        )

    reportLine += " ~~~~"
    editSummary += " ([[WP:BOT|BOT]] - [[User:DatBot/Filter reporter/Run|disable]])"

    AIVPage.edit(appendtext=reportLine, summary=editSummary)


@lru_cache(maxsize=64)
def GetFilterName(filterId):
    filterId = str(filterId)

    params = {
        "action": "query",
        "list": "abusefilters",
        "abfprop": "description",
        "abfstartid": filterId,
        "abflimit": 1,
    }
    req = api.APIRequest(site, params, False)
    res = req.query(False)
    filterName = res["query"]["abusefilters"][0]["description"]
    return filterName


def GetLists(ircBot):
    # Globals not the best but eh why not
    global AIVPage, UAAPage, GlobalFilterHitQuota, GlobalFilterTime

    vandalismFilters = {}
    usernameFilters = {}
    filtersPage = page.Page(site, "Template:DatBot filters")

    try:
        pageJson = json.loads(filtersPage.getWikiText(force=True))
    except json.decoder.JSONDecodeError:
        ircBot.send_message("Syntax error detected in filter list page - [[Template:DatBot filters]]")
        return vandalismFilters, usernameFilters

    for filterId in pageJson["vandalism"]:
        currentItem = pageJson["vandalism"][filterId]
        vandalismFilters[filterId] = Filter(filter_id=filterId, note=currentItem.get("note"),
            hits_required=currentItem.get("hits", 5), time_expiry=currentItem.get("time", 5) * 60
        )

    for filterId in pageJson["username"]:
        usernameFilters[filterId] = Filter(filter_id=filterId, note=pageJson["username"][filterId].get("note"))

    AIVPage = page.Page(site, pageJson.get("aiv", "Wikipedia:Administrator intervention against vandalism/TB2"))
    UAAPage = page.Page(site, pageJson.get("uaa", "Wikipedia:Usernames for administrator attention/Bot"))

    GlobalFilterHitQuota = pageJson["global"].get("hits", 10)
    GlobalFilterTime = pageJson["global"].get("time", 5)

    return vandalismFilters, usernameFilters


if __name__ == "__main__":
    main()
