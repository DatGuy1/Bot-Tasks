#! /usr/bin/python

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
    r"\{\{Non.?free-?\s*Reduce.*?\}\}",
    r"\{\{Reduce.*?\}\}",
    r"\{\{Comic-ovrsize-img.*?\}\}",
    r"\{\{Fair.?Use.?Reduce.*?\}\}",
    r"\{\{Image-toobig.*?\}\}",
    r"\{\{Nfr.*?\}\}",
    r"\{\{Smaller image.*?\}\}",
    r"\{\{Non-free\s*SVG upscale.*?\}\}",
    r"\{\{SVG upscale.*?\}\}",
]

suffixStr = " ([[WP:BOT|BOT]] - [[User:DatBot/NonFreeImageResizer/Run|disable]])"

site = mwclient.Site("en.wikipedia.org")
ErrorPage = site.Pages["User:DatBot/errors/imageresizer"]


def checkFinished(filesDone):
    # Check if bot is finished
    if filesDone % 5 == 0:
        if bot.canRun("User:DatBot/NonFreeImageResizer/Run") is True:
            return True
        else:
            return False
    return True


def fileExists(imagePage):
    """This function makes sure that
    a given image is still tagged with
    {{non-free reduce}}.
    """
    pageText = imagePage.text()

    for regexPhrase in regexList:
        if re.search(regexPhrase, pageText, flags=re.IGNORECASE) is not None:
            return True

    return False


def imageRoutine(imageList, upscaleTask, nonFree):
    filesDone = 0
    for imagePage in imageList:
        print("Working on {0}".format(imagePage.page_title))
        if checkFinished(filesDone):
            if fileExists(imagePage):
                randomName = str(uuid.uuid4())
                fileResult = littleimage.downloadImage(randomName, imagePage)

                if fileResult == "BOMB" and nonFree:
                    print("Decompression bomb warning")
                    errorText = ErrorPage.text()
                    errorText += "\n\n[[:{0}]] is probably a decompression bomb. Skipping. ~~~~~".format(
                        imagePage.name
                    )

                    ErrorPage.save(
                        errorText,
                        summary="Reporting decompression bomb" + suffixStr,
                    )

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "{{Non-free manual reduce}}", text, flags=re.IGNORECASE)
                    imagePage.save(
                        text,
                        summary="Changing template to Non-free manual reduce, "
                                "too many pixels for automatic resizing" + suffixStr,
                    )
                elif fileResult == "PIXEL":
                    print("Removing tag, already close enough to target size.")

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "", text, flags=re.IGNORECASE)
                    imagePage.save(
                        text,
                        summary="Removing {{{{[[Template:{0}|{0}]]}}}} since file is already adequately sized".format(
                            "SVG upscale" if upscaleTask else "Non-free reduce"
                        ) + suffixStr,
                    )
                elif fileResult == "UPSCALE":
                    print("Removing tag, less than 100000 pixels.")

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "", text, flags=re.IGNORECASE)
                    imagePage.save(
                        text,
                        summary="Removing {{{{[[Template:Non-free reduce|Non-free reduce]]}}}} since file is already adequately sized".format(
                        ) + suffixStr,
                    )
                elif fileResult == "MISMATCH":
                    print("Size mismatch")
                    errorText = ErrorPage.text()
                    errorText += "\n\nSize of [[:{0}]] is a mismatch between SVG and PNG. Skipping. ~~~~~".format(
                        imagePage.name
                    )

                    ErrorPage.save(
                        errorText,
                        summary="Reporting size mismatch" + suffixStr,
                    )

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "{{Non-free manual reduce}}", text, flags=re.IGNORECASE)
                    imagePage.save(
                        text,
                        summary="Changing template to Non-free manual reduce, "
                                "size in data doesn't match Wikipedia's size" + suffixStr,
                    )
                elif isinstance(fileResult, tuple) and fileResult[0] == "ERROR":
                    errorText = ErrorPage.text()
                    errorText += "\n\nError loading [[:{0}]]: {1}. Skipping. ~~~~~".format(
                        imagePage.name, fileResult[1]
                    )

                    ErrorPage.save(
                        errorText,
                        summary="Reporting file error" + suffixStr,
                    )

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "{{Non-free manual reduce}}", text, flags=re.IGNORECASE)
                    imagePage.save(
                        text,
                        summary="Changing template to Non-free manual reduce, "
                                "error encountered when resizing file; see [[User:DatBot/errors/imageresizer]]" + suffixStr,
                    )
                elif fileResult == "ERROR":
                    print("Image skipped.")
                    logger.error("Skipped {0}".format(imageName))
                else:
                    try:
                        # What in the world is this autoformatting?
                        # noinspection PyTypeChecker
                        site.upload(
                            open(fileResult, "rb"),
                            imagePage.name,
                            (
                                "Upscale SVG and cleanup SVG code"
                                if upscaleTask
                                else "Reduce size of non-free image"
                            )
                            + suffixStr,
                            ignore=True,
                        )

                        print("Uploaded!")

                        text = imagePage.text()
                        for regexPhrase in regexList:
                            if nonFree:
                                text = re.sub(regexPhrase, "{{Orphaned non-free revisions|date=~~~~~}}", text, flags=re.IGNORECASE)
                            else:
                                text = re.sub(f"{regexPhrase}\\n?", "", text, flags=re.IGNORECASE)

                        imagePage.save(
                            text,
                            summary=("Tagging with {{[[Template:Orphaned non-free revisions|Orphaned non-free "
                                     "revisions]]}}, see [[WP:IMAGERES|instructions]] " if nonFree
                                     else "Removing {{[[Template:SVG upscale|SVG upscale]]}}") + suffixStr,
                        )

                        print("Tagged!")
                    except Exception as e:
                        print("Unknown error. Image skipped.")
                        logger.error(
                            "Unknown error; skipped {0} ({1})".format(imagePage.name, e)
                        )
                
                    bot.deleteFile(fileResult)
            else:
                print("Gah, looks like someone removed the tag.")
                logger.error("Tag removed on image; skipped {0}".format(imagePage.name))
        else:
            print("Ah, darn - looks like the bot was disabled.")
            sys.exit()

        filesDone += 1


def getMembersForCategory(categoryName):
    print(f"Checking {categoryName}...")
    # mwclient automatically converts from Page to Image if in file namespace
    sizeReductionCategory = mwclient.listing.Category(
        site, "Category:{0}".format(categoryName)
    )
    sizeReductionRequests = sizeReductionCategory.members(namespace=6)
    return list(sizeReductionRequests)


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
        "Wikipedia non-free SVG file size reduction requests"
    )
    # downscaleList = getMembersForCategory("Wikipedia non-free svg file size reduction requests")
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
