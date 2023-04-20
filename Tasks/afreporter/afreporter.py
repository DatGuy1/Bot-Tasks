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
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Optional

import configparser
import datetime
import json
import threading
import time
from dataclasses import dataclass
from functools import cache
from urllib.parse import quote

import userpass

import pymysql as MySQLdb
from cachetools import TTLCache
from irc.bot import ServerSpec, SingleServerIRCBot
from num2words import num2words
from wikitools import *

if TYPE_CHECKING:
    from irc.client import ServerConnection

IRCActive = False
LogActive = False

site = wiki.Wiki()
site.setMaxlag(-1)
site.login(userpass.username, userpass.password)

SummarySuffix = " ([[WP:BOT|BOT]] - [[User:DatBot/Filter reporter/Run|disable]])"

AIVPage: Optional[page.Page] = None
UAAPage: Optional[page.Page] = None
ErrorPage = page.Page(site, "User:DatBot/errors/afreporter")
RunPage = page.Page(site, "User:DatBot/Filter reporter/Run")

GlobalFilterHitQuota = 10
GlobalFilterTime = 5

DefaultFilterTime = 5

configParser = configparser.ConfigParser()
configParser.read("/data/project/datbot/replica.my.cnf")
sqlUser = configParser.get("client", "user").strip().strip("'")
sqlPassword = configParser.get("client", "password").strip().strip("'")

labsDB = MySQLdb.connect(db="enwiki_p", host="enwiki.labsdb", user=sqlUser, password=sqlPassword)
labsDB.autocommit(True)
labsDB.ping(True)
labsCursor = labsDB.cursor()


@dataclass
class FilterHit:
    hit_id: int
    action: Literal["edit", "delete", "createaccount", "move", "upload", "autocreateaccount", "stashupload"]
    page: page.Page
    user: user.User
    timestamp: str
    filter_id: int

    @classmethod
    def fromAPIResponse(cls, apiResponse: dict[Any, Any]) -> FilterHit:
        return cls(
            hit_id=apiResponse["id"],
            action=apiResponse["action"],
            page=page.Page(site, apiResponse["title"], namespace=apiResponse["ns"], check=False, followRedirects=False),
            user=user.User(site, apiResponse["user"], check=False),
            timestamp=apiResponse["timestamp"],
            filter_id=apiResponse["filter_id"],
        )

    @classmethod
    def fromDBResponse(cls, dbResponse: tuple[Any, ...]) -> FilterHit:
        return cls(
            hit_id=dbResponse[0],
            action=dbResponse[1].decode(),
            page=page.Page(site, dbResponse[3].decode(), namespace=dbResponse[2], check=False, followRedirects=False),
            user=user.User(site, dbResponse[4].decode(), check=False),
            timestamp=dbResponse[5].decode(),
            filter_id=dbResponse[6],
        )


class Filter:
    def __init__(
        self,
        filter_id: int,
        note: Optional[str] = "",
        hits_required: Optional[int] = None,
        time_expiry: Optional[int] = None,
    ) -> None:
        self.filter_id = filter_id
        self.filter_name = GetFilterName(filter_id)
        self.note = note if bool(note) else None
        self.hits_required = hits_required
        self.time_expiry = time_expiry

    def __repr__(self) -> str:
        return "{klass}({attrs})".format(
            klass=self.__class__.__name__,
            attrs=" ".join("{}={!r}".format(k, v) for k, v in self.__dict__.items() if bool(v)),
        )


class TimedTracker(dict):
    def __init__(self) -> None:
        super().__init__()
        self.timeSet = set([(item, int(time.time())) for item in self.keys()])

    def purgeExpired(self) -> None:
        currentTime = int(time.time())
        removedSet = set([item for item in self.timeSet if item[1] < currentTime - item[0][1].time_expiry])
        self.timeSet.difference_update(removedSet)
        for item in removedSet:
            super().__delitem__(item[0])

    def __getitem__(self, key: Any) -> Any:
        self.purgeExpired()
        if key not in self:
            return 0

        return super().__getitem__(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        self.purgeExpired()
        if key not in self:
            self.timeSet.add((key, int(time.time())))

        return super().__setitem__(key, value)

    def __delitem__(self, key: Any) -> None:
        self.timeSet = set([item for item in self.timeSet if item[0] != key])
        self.purgeExpired()
        return super().__delitem__(key)

    def __contains__(self, key: Any) -> bool:
        self.purgeExpired()
        return super().__contains__(key)


class CommandBot(SingleServerIRCBot):
    def __init__(self, channel: str, nickname: str, serverSpec: ServerSpec) -> None:
        SingleServerIRCBot.__init__(self, server_list=[serverSpec], nickname=nickname, realname=nickname)
        self.channel = channel
        self.abuseChannel = None

    def on_welcome(self, connection: ServerConnection, _) -> None:
        connection.privmsg("NickServ", "identify {0}".format(userpass.ircPassword))
        time.sleep(1)
        connection.join(self.channel)
        self.abuseChannel = connection

    def send_message(self, message: str) -> None:
        if self.abuseChannel is None:
            return

        self.abuseChannel.privmsg("#wikipedia-en-abuse-log", message)


class BotRunnerThread(threading.Thread):
    def __init__(self, bot: CommandBot) -> None:
        super().__init__()
        self.bot = bot

    def run(self) -> None:
        self.bot.start()


def checkLag(ircBot: CommandBot) -> bool:
    """Returns whether to use the API"""
    lagWaitedOut = False
    useAPI = False

    while True:
        # Check replication lag
        labsCursor.execute(
            "SELECT UNIX_TIMESTAMP() - UNIX_TIMESTAMP(rc_timestamp) FROM recentchanges "
            "ORDER BY rc_timestamp DESC LIMIT 1"
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


def FormatOccurrences(occurrences: int) -> str:
    # TODO: Switch to `match` once Python 3.10 is supported
    if occurrences == 1:
        return ""
    elif occurrences == 2:
        return "twice "
    else:
        wordRepresentation = num2words(occurrences, lang="en-GB")
        return f"{wordRepresentation} times "


def getStart(useAPI: bool) -> tuple[int, int]:
    if useAPI:
        params = {"action": "query", "list": "abuselog", "aflprop": "ids|timestamp", "afllimit": "1"}
        req = api.APIRequest(site, params)
        res = req.query(False)
        row = res["query"]["abuselog"][0]
        lastHitTime = row["timestamp"]
        lastHitId = row["id"]
    else:
        labsCursor.execute("SELECT afl_timestamp, afl_id FROM abuse_filter_log ORDER BY afl_id DESC LIMIT 1")
        (lastHitTime, lastHitId) = labsCursor.fetchone()

    return lastHitTime, lastHitId


def normaliseTimestamp(timestamp: Any) -> str:  # normalize a timestamp to the API format
    timestamp = str(timestamp)
    if "Z" in timestamp:
        return timestamp

    timestamp = datetime.datetime.strptime(timestamp, "%Y%m%d%H%M%S")
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def logFromAPI(lastEditTime: int) -> list[FilterHit]:
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
        # The API uses >=, so the first row will be the same as the last row of the last set
        del rows[0]

    return [FilterHit.fromAPIResponse(row) for row in rows]


def logFromDB(lastHitId: int) -> list[FilterHit]:
    labsCursor.execute(
        "SELECT SQL_NO_CACHE afl_id, afl_action, afl_namespace, afl_title, "
        "afl_user_text, afl_timestamp, afl_filter_id FROM abuse_filter_log "
        f"WHERE afl_id > {lastHitId} ORDER BY afl_id"
    )
    return [FilterHit.fromDBResponse(row) for row in labsCursor.fetchall()]


def main() -> None:
    logChannel = "#wikipedia-en-abuse-log"
    logServer = "irc.libera.chat"
    botNickname = "DatBot"
    ircBot = CommandBot(logChannel, botNickname, ServerSpec(logServer))
    commandThread = BotRunnerThread(ircBot)
    commandThread.daemon = True
    commandThread.start()

    vandalismFilters, usernameFilters = GetLists(ircBot)
    lastListCheck = time.time()

    useAPI = checkLag(ircBot)
    lastLagCheck = time.time()

    # values expire after ttl seconds
    userTripTracker = TTLCache(maxsize=1000, ttl=GlobalFilterTime * 60)
    IRCreportTracker = TTLCache(maxsize=1000, ttl=60)
    titlesTracker = TTLCache(maxsize=1000, ttl=300)

    AIVreportTracker = TTLCache(maxsize=1000, ttl=1800)
    AIVuserTracker = TimedTracker()

    (lastHitTime, lastHitId) = getStart(useAPI)
    while True:
        # Refetch lists every five minutes
        timeNow = time.time()
        if timeNow > lastListCheck + 300:
            vandalismFilters, usernameFilters = GetLists(ircBot)
            lastListCheck = timeNow
        if timeNow > lastLagCheck + 600:
            useAPI = checkLag(ircBot)
            lastLagCheck = timeNow

        registeredHits: list[tuple[user.User, str]] = []
        filterHits = logFromAPI(lastHitTime) if useAPI else logFromDB(lastHitId)
        for filterHit in filterHits:
            if filterHit.hit_id <= lastHitId:
                continue

            if not StartAllowed:
                print("Start disabled, exiting...")
                time.sleep(60)
                break

            trippedFilter = filterHit.filter_id
            if trippedFilter not in usernameFilters and trippedFilter not in vandalismFilters:
                continue

            hitUser = filterHit.user
            hitUser.setUserInfo()
            if not hitUser.exists and not hitUser.isIP:
                continue

            targetUsername = hitUser.name
            if trippedFilter in usernameFilters:
                trippedFilterObject = usernameFilters[trippedFilter]
                ircBot.send_message(
                    f"Reporting https://en.wikipedia.org/wiki/Special:Contributions/{quote(targetUsername)} to UAA for "
                    f"tripping https://en.wikipedia.org/wiki/Special:AbuseFilter/{trippedFilterObject.filter_id}"
                )
                reportUserUAA(hitUser, trippedFilterObject)

            # Is this necessary?
            # if title == "Special:UserLogin" or title == "UserLogin" or action == "createaccount":
            #     continue

            # Hits on pagemoves
            if filterHit.action == "move":
                ircBot.send_message(
                    f"User:{targetUsername} has tripped a filter doing a pagemove: "
                    f"https://en.wikipedia.org/wiki/Special:AbuseLog/{filterHit.hit_id}"
                )

            # Ten hits on one article in five minutes or less
            hitPage = filterHit.page
            titlesTracker[hitPage] = titlesTracker.get(hitPage, 0) + 1
            if titlesTracker[hitPage] == 10 and hitPage not in IRCreportTracker:
                ircBot.send_message(
                    f"Ten filters have been tripped in the last five minutes on {hitPage.title}: "
                    f"https://en.wikipedia.org/wiki/Special:AbuseLog?wpSearchTitle={hitPage.urlTitle}"
                )
                del titlesTracker[hitPage]
                IRCreportTracker[hitPage] = True

            # Check if the filter is in vandalism list
            if trippedFilter not in vandalismFilters:
                continue

            # Check for filter hits_required
            trippedFilterObject = vandalismFilters[trippedFilter]
            numTrips = AIVuserTracker.get((hitUser, trippedFilterObject), 0) + 1

            AIVuserTracker[(hitUser, trippedFilterObject)] = numTrips
            if numTrips >= trippedFilterObject.hits_required and hitUser not in AIVreportTracker:
                messageToSend = (
                    "Reporting https://en.wikipedia.org/wiki/Special:Contributions/{} to AIV for "
                    "tripping https://en.wikipedia.org/wiki/Special:AbuseFilter/{}".format(
                        targetUsername.replace(" ", "_"), trippedFilterObject.filter_id
                    )
                )
                if numTrips > 0:
                    formattedOccurences = FormatOccurrences(numTrips)
                    messageToSend += (
                        f"{formattedOccurences}within the last {trippedFilterObject.time_expiry / 60} minutes"
                    )
                ircBot.send_message(messageToSend)

                del AIVuserTracker[(hitUser, trippedFilterObject)]
                reportUser(hitUser, trippedFilterObject)
                AIVreportTracker[hitUser] = True

            # Prevent multiple hits from the same edit attempt
            if (hitUser, filterHit.timestamp) in registeredHits:
                continue

            registeredHits.append((hitUser, filterHit.timestamp))

            # Generic trip reporting checks
            userTripTracker[hitUser] = userTripTracker.get(hitUser, 0) + 1
            # GlobalFilterHitQuota hits in GlobalFilterTime minutes
            if (
                userTripTracker[hitUser] >= GlobalFilterHitQuota
                and trippedFilter in vandalismFilters
                and hitUser not in AIVreportTracker
            ):
                ircBot.send_message(
                    "Reporting User:{} to AIV for tripping disruption-catching filters {}within "
                    "the last {} minutes: https://en.wikipedia.org/wiki/Special:AbuseLog?wpSearchUser={}".format(
                        targetUsername,
                        FormatOccurrences(userTripTracker[hitUser]),
                        GlobalFilterTime,
                        quote(targetUsername),
                    )
                )
                del userTripTracker[hitUser]
                reportUser(hitUser)
                AIVreportTracker[hitUser] = True

        if len(filterHits) > 0:
            lastHitId = filterHits[-1].hit_id
            lastHitTime = filterHits[-1].filter_id

        time.sleep(1.5)


@property
def StartAllowed() -> bool:
    return RunPage.getWikiText() == "Run"


def reportUserUAA(targetUser: user.User, trippedFilter: Optional[Filter] = None) -> None:
    if targetUser.isBlocked(force=True):
        return

    targetUsername = targetUser.name
    reportLine = "\n*{{user-uaa|1=%s}} - " % targetUsername
    editSummary = "Reporting [[Special:Contributions/{0}|{0}]]".format(targetUsername)
    if trippedFilter is not None:
        reportLine += "Tripped [[Special:AbuseFilter/{filter_id}|filter {filter_id}]] ({filter_name}).".format(
            filter_id=trippedFilter.filter_id, filter_name=trippedFilter.filter_name
        )
        if trippedFilter.note is not None:
            reportLine += f" Note: {trippedFilter.note}."

        editSummary += " for tripping [[Special:AbuseFilter/{filter_id}|filter {filter_id}]] ({filter_name})".format(
            filter_id=trippedFilter.filter_id, filter_name=trippedFilter.filter_name
        )

    reportLine += " ~~~~"
    editSummary += SummarySuffix

    UAAPage.edit(appendtext=reportLine, summary=editSummary)


def reportUser(targetUser: user.User, trippedFilter: Optional[Filter] = None) -> None:
    if targetUser.isBlocked(force=True):
        return

    targetUsername = targetUser.name
    if targetUser.isIP:
        reportLine = "\n* {{IPvandal|%s}} - " % targetUsername
    else:
        reportLine = "\n* {{Vandal|1=%s}} - " % targetUsername

    editSummary = f"Reporting [[Special:Contributions/{targetUsername}]]"
    if trippedFilter is None:
        reportLine += (
            "Tripped disruption-catching filters %d times in the last %d minutes "
            "([{{fullurl:Special:AbuseLog|wpSearchUser=%s}} details])."
            % (GlobalFilterHitQuota, GlobalFilterTime, quote(targetUsername))
        )
        editSummary += (
            f" for triggering disruption-catching filters {GlobalFilterHitQuota} times in the last "
            f"{GlobalFilterTime} minutes"
        )
    else:
        filterOccurrences = FormatOccurrences(trippedFilter.hits_required)
        timeframeText = (
            f"in the last {trippedFilter.time_expiry / 60} minutes "
            if trippedFilter.time_expiry != DefaultFilterTime
            else ""
        )
        reportLine += (
            "Tripped [[Special:AbuseFilter/{filter_id}|filter {filter_id}]] {occurrences}{timeframe}({filter_name}), "
            "[{{{{fullurl:Special:AbuseLog|wpSearchUser={escaped_username}}}}} details]).".format(
                filter_id=trippedFilter.filter_id,
                filter_name=trippedFilter.filter_name,
                occurrences=filterOccurrences,
                timeframe=timeframeText,
                escaped_username=quote(targetUsername),
            )
        )
        if trippedFilter.note is not None:
            reportLine += f" Note: {trippedFilter.note}."

        editSummary += " for triggering [[Special:AbuseFilter/{filter_id}|filter {filter_id}]] {occurrences}".format(
            filter_id=trippedFilter.filter_id, occurrences=filterOccurrences.strip()
        )

    reportLine += " ~~~~"
    editSummary += SummarySuffix

    try:
        AIVPage.edit(appendtext=reportLine, summary=editSummary)
    except Exception as e:
        errorText = f"\n#{type(e).__module__}.{type(e).__qualname__}: {e} ~~~~~"
        ErrorPage.edit(appendtext=errorText, summary="Reporting error " + SummarySuffix)


@cache
def GetFilterName(filterId: str) -> str:
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


def GetLists(ircBot: CommandBot) -> tuple[dict[int, Filter], dict[int, Filter]]:
    global AIVPage, UAAPage, DefaultFilterTime, GlobalFilterHitQuota, GlobalFilterTime

    vandalismFilters = {}
    usernameFilters = {}
    filtersPage = page.Page(site, "Template:DatBot filters")

    try:
        pageJson = json.loads(filtersPage.getWikiText(force=True))
    except json.decoder.JSONDecodeError:
        ircBot.send_message("Syntax error detected in filter list page - [[Template:DatBot filters]]")
        return vandalismFilters, usernameFilters

    DefaultFilterTime = pageJson["defaults"].get("time", 5)
    defaultHits = pageJson["defaults"].get("hits", 5)

    for filterId, filterItem in pageJson["vandalism"].items():
        vandalismFilters[int(filterId)] = Filter(
            filter_id=int(filterId),
            note=filterItem.get("note"),
            hits_required=filterItem.get("hits", defaultHits),
            time_expiry=filterItem.get("time", DefaultFilterTime) * 60,
        )

    for filterId, filterItem in pageJson["username"]:
        usernameFilters[int(filterId)] = Filter(filter_id=int(filterId), note=filterItem.get("note"))

    AIVPage = page.Page(site, pageJson.get("aiv", "Wikipedia:Administrator intervention against vandalism/TB2"))
    UAAPage = page.Page(site, pageJson.get("uaa", "Wikipedia:Usernames for administrator attention/Bot"))

    GlobalFilterHitQuota = pageJson["global"].get("hits", 10)
    GlobalFilterTime = pageJson["global"].get("time", 5)

    return vandalismFilters, usernameFilters


if __name__ == "__main__":
    main()
