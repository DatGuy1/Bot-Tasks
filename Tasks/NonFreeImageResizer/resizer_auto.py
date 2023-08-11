import typing

import logging
import os
import pathlib
import re
import sys
import uuid

import userpass

import littleimage
import mwclient

if typing.TYPE_CHECKING:
    import mwclient.image
    import mwclient.listing
    import mwclient.page

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
ErrorPage = site.pages["User:DatBot/errors/imageresizer"]
RunPage = site.pages["User:DatBot/NonFreeImageResizer/Run"]


def deleteFile(fileName: typing.Union[str, pathlib.Path]) -> None:
    # fileList = [f for f in os.listdir(".") if f.startswith(fileName)]
    # for fileObject in fileList:
    if isinstance(fileName, pathlib.Path):
        fileName.unlink(True)
    elif os.path.isfile(fileName):
        os.remove(fileName)


def checkFinished(filesDone: int) -> bool:
    # Check if bot is finished
    if filesDone % 5 == 0:
        return RunPage.text(cache=False) != "Run"

    return False


def fileExists(imagePage: mwclient.page.Page) -> bool:
    """This function makes sure that
    a given image is still tagged with
    {{non-free reduce}}.
    """
    pageText = imagePage.text()
    for regexPhrase in regexList:
        if re.search(regexPhrase, pageText, flags=re.IGNORECASE) is not None:
            return True

    return False


def imageRoutine(imageList: list[mwclient.image.Image], upscaleTask: bool, nonFree: bool) -> None:
    filesDone = 0
    for imagePage in imageList:
        print(f"Working on {imagePage.page_title}")
        if checkFinished(filesDone):
            print("Ah, darn - looks like the bot was disabled.")
            sys.exit()
        else:
            if not fileExists(imagePage):
                print("Gah, looks like someone removed the tag.")
                logger.error(f"Tag removed on image; skipped {imagePage.name}")
            else:
                randomName = str(uuid.uuid4())
                fileResult = littleimage.downloadImage(randomName, imagePage)

                # TODO: Switch to match statement when Python 3.10 is available
                if fileResult == "BOMB" and nonFree:
                    print("Decompression bomb warning")
                    errorText = ErrorPage.text()
                    errorText += f"\n\n[[:{imagePage.name}]] is probably a decompression bomb. Skipping. ~~~~~"

                    ErrorPage.edit(errorText, summary="Reporting decompression bomb" + suffixStr)

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "{{Non-free manual reduce}}", text, flags=re.IGNORECASE)

                    imagePage.edit(
                        text,
                        summary="Changing template to Non-free manual reduce, too many pixels for automatic resizing"
                        + suffixStr,
                    )
                elif fileResult == "PIXEL":
                    print("Removing tag, already close enough to target size.")

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "", text, flags=re.IGNORECASE)
                    imagePage.edit(
                        text,
                        summary="Removing {{{{[[Template:{0}|{0}]]}}}} since file is already adequately sized".format(
                            "SVG upscale" if upscaleTask else "Non-free reduce"
                        )
                        + suffixStr,
                    )
                elif fileResult == "UPSCALE":
                    print("Removing tag, less than 100000 pixels.")

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "", text, flags=re.IGNORECASE)
                    imagePage.edit(
                        text,
                        summary="Removing {{{{[[Template:Non-free reduce|Non-free reduce]]}}}} since file is already "
                        "adequately sized" + suffixStr,
                    )
                elif fileResult == "MISMATCH":
                    # This isn't currently used. Not sure why.
                    print("Size mismatch")
                    errorText = ErrorPage.text()
                    errorText += f"\n\nSize of [[:{imagePage.name}]] is a mismatch between SVG and PNG. Skipping. ~~~~~"

                    ErrorPage.edit(errorText, summary="Reporting size mismatch" + suffixStr)

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "{{Non-free manual reduce}}", text, flags=re.IGNORECASE)
                    imagePage.edit(
                        text,
                        summary="Changing template to Non-free manual reduce, size in data doesn't match Wikipedia's"
                        " size" + suffixStr,
                    )
                elif isinstance(fileResult, tuple) and fileResult[0] == "ERROR":
                    logger.error(f"Skipped {imagePage.page_title}: {fileResult[1]}")
                    print("Image skipped.")
                    errorText = ErrorPage.text()
                    errorText += f"\n\nError loading [[:{imagePage.name}]]: {fileResult[1]}. Skipping. ~~~~~"

                    ErrorPage.edit(errorText, summary="Reporting file error" + suffixStr)

                    text = imagePage.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, "{{Non-free manual reduce}}", text, flags=re.IGNORECASE)
                    imagePage.edit(
                        text,
                        summary="Changing template to Non-free manual reduce, error encountered when resizing file; "
                        "see [[User:DatBot/errors/imageresizer]]" + suffixStr,
                    )
                else:
                    try:
                        uploadComment = (
                            "Upscale SVG and cleanup SVG code" if upscaleTask else "Reduce size of non-free image"
                        )
                        with fileResult.open("rb") as fileHandle:
                            # noinspection PyTypeChecker
                            site.upload(fileHandle, imagePage.name, uploadComment + suffixStr, ignore=True)

                        print("Uploaded!")
                        text = imagePage.text()
                        for regexPhrase in regexList:
                            if nonFree:
                                text = re.sub(
                                    regexPhrase, "{{Orphaned non-free revisions|date=~~~~~}}", text, flags=re.IGNORECASE
                                )
                            else:
                                text = re.sub(f"{regexPhrase}\\n?", "", text, flags=re.IGNORECASE)

                        imagePage.edit(
                            text,
                            summary=(
                                "Tagging with {{[[Template:Orphaned non-free revisions|Orphaned non-free revisions]]}},"
                                " see [[WP:IMAGERES|instructions]] "
                                if nonFree
                                else "Removing {{[[Template:SVG upscale|SVG upscale]]}}"
                            )
                            + suffixStr,
                        )
                        print("Tagged!")
                    except Exception as e:
                        print("Unknown error. Image skipped.")
                        logger.error("Unknown error; skipped {0} ({1})".format(imagePage.name, e))

                    deleteFile(fileResult)

        filesDone += 1


def getMembersForCategory(categoryName: str) -> list[mwclient.image.Image]:
    print(f"Checking {categoryName}...")
    # mwclient automatically converts from Page to Image if in file namespace
    sizeReductionCategory = mwclient.listing.Category(site, f"Category:{categoryName}")
    sizeReductionRequests = sizeReductionCategory.members(namespace=6)
    return list(sizeReductionRequests)


def main() -> None:
    """
    This defines and fills a global
    variable for the site, and then gets
    selection of images to work with from
    Category:Wikipedia non-free file size reduction requests.
    Then it runs image_routine() on this selection.
    """
    site.login(userpass.username, userpass.password)

    downscaleList = getMembersForCategory("Wikipedia non-free file size reduction requests")
    downscaleList += getMembersForCategory("Wikipedia non-free SVG file size reduction requests")
    imageRoutine(downscaleList, False, True)

    upscaleListNonFree = getMembersForCategory("Wikipedia non-free SVG upscale requests")
    imageRoutine(upscaleListNonFree, True, True)

    upscaleListFree = getMembersForCategory("Wikipedia free SVG upscale requests")
    imageRoutine(upscaleListFree, True, False)

    print("We're DONE!")


if __name__ == "__main__":
    main()
