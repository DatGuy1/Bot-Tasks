#! /usr/bin/python
# TODO: Major cleanup required

import logging
import re
import sys
import time
import uuid

import bot
import littleimage
import mwclient
import userpass

sys.path.append("/data/project/datbot/Tasks/NonFreeImageResizer")

# CC-BY-SA Theopolisme, DatGuy
# Task 3 DatBot

logger = logging.getLogger("resizer_auto")
hdlr = logging.FileHandler("resizer_auto.log")
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.WARNING)

regexList = [
    r"\{\{[Nn]on.?free-?\s*[Rr]educe.*?\}\}",
    r"\{\{[Rr]educe.*?\}\}",
    r"\{\{[Cc]omic-ovrsize-img.*?\}\}",
    r"\{\{[Ff]air.?[Uu]se.?[Rr]educe.*?\}\}",
    r"\{\{[Ii]mage-toobig.*?\}\}",
    r"\{\{[Nn]fr.*?\}\}",
    r"\{\{[Ss]maller image.*?\}\}",
    r"\{\{([Nn]on-free\s*)?[sS][vV][gG] upscale.*?\}\}",
]

suffixStr = " ([[WP:BOT|BOT]] - [[User:DatBot/NonFreeImageResizer/Run|disable]])"

site = mwclient.Site("en.wikipedia.org")


def checkFinished(filesDone):
    # Check if bot is finished
    if filesDone % 5 == 0:
        if bot.canRun("User:DatBot/NonFreeImageResizer/Run") is True:
            return True
        else:
            return False
    return True


def fileExists(imageTitle):
    """This function makes sure that
    a given image is still tagged with
    {{non-free reduce}}.
    """
    fullImage = "File:{0}".format(imageTitle)

    page = site.Pages[fullImage]
    pageText = page.text()

    for regexPhrase in regexList:
        if re.search(regexPhrase, pageText) is not None:
            return True

    return False


def imageRoutine(imageList, upscaleTask, nonFree):
    filesDone = 0
    for imageName in imageList:
        print("Working on {0}".format(imageName))
        if checkFinished(filesDone):
            if fileExists(imageName):
                fullImageName = "File:{0}".format(imageName)
                imagePage = site.Images[imageName]

                randomName = str(uuid.uuid4())
                fileResult = littleimage.downloadImage(randomName, imagePage, site)

                if fileResult == "BOMB" and nonFree:
                    print("Decompression bomb warning")
                    errorPage = site.Pages["User:DatBot/pageerror"]
                    errorText = errorPage.text()
                    errorText += "\n\n[[:{0}]] is probably a decompression bomb. Skipping.".format(
                        fullImageName
                    )

                    errorPage.save(
                        errorText,
                        summary="Reporting decompression bomb" + suffixStr,
                    )

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "{{Non-free manual reduce}}", text)
                    imagePage.save(
                        text,
                        summary="Changing template to Non-free manual reduce, "
                                "too many pixels for automatic resizing" + suffixStr,
                    )
                elif fileResult == "PIXEL":
                    print("Removing tag, already close enough to target size.")

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "", text)
                    imagePage.save(
                        text,
                        summary="Removing {{{{[[Template:{0}|{0}]]}}}} since file is already adequately sized".format(
                            "SVG upscale" if upscaleTask else "Non-free reduce"
                        ) + suffixStr,
                    )
                elif fileResult == "MISMATCH":
                    print("Size mismatch")
                    errorPage = site.Pages["User:DatBot/pageerror"]
                    errorText = errorPage.text()
                    errorText += "\n\nSize of [[:File:{0}]] is a mismatch between SVG and PNG. Skipping.".format(
                        imageName
                    )

                    errorPage.save(
                        errorText,
                        summary="Reporting size mismatch" + suffixStr,
                    )

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "{{Non-free manual reduce}}", text)
                    imagePage.save(
                        text,
                        summary="Changing template to Non-free manual reduce, "
                                "size in data doesn't match Wikipedia's size" + suffixStr,
                    )
                elif fileResult == "ERROR":
                    print("Image skipped.")
                    logger.error("Skipped {0}" + imageName)
                    bot.deleteFile(randomName)
                else:
                    try:
                        # noinspection PyTypeChecker
                        site.upload(
                            open(fileResult, "rb"),
                            imageName,
                            (
                                "Upscale SVG and cleanup SVG code"
                                if upscaleTask
                                else "Reduce size of non-free image"
                            )
                            + suffixStr,
                            ignore=True,
                        )

                        print("Uploaded!")

                        bot.deleteFile(randomName)

                        text = imagePage.text()
                        for regexPhrase in regexList:
                            text = re.sub(
                                regexPhrase,
                                "{{Orphaned non-free revisions|date=~~~~~}}"
                                if nonFree
                                else "",
                                text,
                            )
                        imagePage.save(
                            text,
                            summary=("Tagging with {{[[Template:Orphaned non-free revisions|Orphaned non-free "
                                     "revisions]]}}, see [[WP:IMAGERES|instructions]] " if nonFree
                                     else "Removing {{[["
                                          "Template:SVG "
                                          "upscale|SVG "
                                          "upscale]]}}") + suffixStr,
                        )

                        print("Tagged!")
                    except Exception as e:
                        print("Unknown error. Image skipped.")
                        logger.error(
                            "Unknown error; skipped {0} ({1})".format(imageName, e)
                        )
                        bot.deleteFile(imageName)
            else:
                print("Gah, looks like someone removed the tag.")
                logger.error("Tag removed on image; skipped {0}".format(imageName))
        else:
            print("Ah, darn - looks like the bot was disabled.")
            sys.exit()

        filesDone += 1


def getMembersForCategory(categoryName):
    cleanImageList = []
    print(categoryName)
    sizeReductionCategory = mwclient.listing.Category(
        site, "Category:{0}".format(categoryName)
    )
    sizeReductionRequests = sizeReductionCategory.members()

    for image in sizeReductionRequests:
        pageTitle = image.page_title
        print(pageTitle)
        cleanImageList.append(pageTitle)

    return cleanImageList


def main():
    """
    This defines and fills a global
    variable for the site, and then gets
    selection of images to work with from
    Category:Wikipedia non-free file size reduction requests.
    Then it runs image_routine() on this selection.
    """
    site.login(userpass.username, userpass.password)

    downscaleList = getMembersForCategory("Wikipedia non-free file size reduction requests") + getMembersForCategory(
        "Wikipedia non-free svg file size reduction requests"
    )
    imageRoutine(downscaleList, False, True)

    upscaleListNonFree = getMembersForCategory(
        "Wikipedia non-free SVG upscale requests"
    )
    imageRoutine(upscaleListNonFree, True, True)

    upscaleListFree = getMembersForCategory("Wikipedia free SVG upscale requests")
    imageRoutine(upscaleListFree, True, False)

    print("We're DONE!")


if __name__ == "__main__":
    main()
