#! /usr/bin/python
import mwclient
import uuid
import sys
import re
import logging
import littleimage
import userpass
import bot
sys.path.append("/data/project/datbot/Tasks/NonFreeImageResizer")

# CC-BY-SA Theopolisme, DatGuy
# Task 3 DatBot

logger = logging.getLogger('resizer_auto')
hdlr = logging.FileHandler('resizer_auto.log')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.WARNING)

regexList = [r'\{\{[Nn]on.?free-?\s*[Rr]educe.*?\}\}', r'\{\{[Rr]educe.*?\}\}',
             r'\{\{[Cc]omic-ovrsize-img.*?\}\}',
             r'\{\{[Ff]air.?[Uu]se.?[Rr]educe.*?\}\}',
             r'\{\{[Ii]mage-toobig.*?\}\}', r'\{\{[Nn]fr.*?\}\}',
             r'\{\{[Ss]maller image.*?\}\}']


def checkFinished(filesDone):
    # Check if bot is finished
    if filesDone % 5 == 0:
        if bot.canRun("User:DatBot/NonFreeImageResizer/Run") is True:
            return True
        else:
            return False

    return True


def fileExists(imageTitle):
    """ This function makes sure that
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


def imageRoutine(imageList):
    """ This function does most of the work:
    * First, checks the checkpage using checkFinished()
    * Then makes sure the image file still exists using are_you_still_there()
    * Next it actually resizes the image.
    * As long as the resize works, we reupload the file.
    * Then we update the page with {{Orphaned non-free revisions}}.
    * And repeat!
    """
    filesDone = 0
    for imageName in imageList:
        print("Working on {0}".format(imageName))
        if checkFinished(filesDone):
            if fileExists(imageName):
                fullImageName = "File:{0}".format(imageName)
                randomName = str(uuid.uuid4())
                fileResult = littleimage.downloadImage(randomName, imageName, site)

                if fileResult == "BOMB":
                    print("Decompression bomb warning")
                    errorPage = site.Pages["User:DatBot/pageerror"]
                    errorText = errorPage.text()
                    errorText += "\n\n[[:File:{0}]] is probably a decompression bomb. Skipping.".format(imageName)
                    errorPage.save(errorText, summary="Reporting decompresion bomb ([[WP:BOT|BOT]] - [[User:DatBot/NonFreeImageResizer/Run|disable]])")

                    page = site.Pages["File:{0}".format(imageName)]
                    text = page.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, '{{Non-free manual reduce}}', text)

                    page.save(text, summary="Changing template to Non-free manual reduce, too many pixels for automatic resizing ([[WP:BOT|BOT]] - [[User:DatBot/NonFreeImageResizer/Run|disable]])")

                elif fileResult == "SKIP":
                    print("Skipping GIF.")
                    logger.error("Skipped gif: {0}".format(imageName))

                elif fileResult == "PIXEL":
                    print("Removing tag...already reduced...")

                    page = site.Pages[fullImageName]
                    text = page.text()
                    for regexPhrase in regexList:
                        text = re.sub(regexPhrase, '', text)

                    page.save(text, summary="Removing {{[[Template:Non-free reduce|Non-free reduce]]}} since file "
                                            "is already adequately reduced ([[WP:BOT|BOT]] - "
                                            "[[User:DatBot/NonFreeImageResizer/Run|disable]])")

                elif fileResult == "ERROR":
                    print("Image skipped.")
                    logger.error("Skipped {0}" + imageName)
                    bot.deleteFile(randomName)
                else:
                    try:
                        site.upload(open(fileResult, 'rb'), imageName, "Reduce size of non-free image ([[WP:BOT|BOT]] - [[User:DatBot/NonFreeImageResizer/Run|disable]])", ignore=True)

                        print("Uploaded!")
                        bot.deleteFile(randomName)

                        page = site.Pages[fullImageName]
                        text = page.text()
                        for regexPhrase in regexList:
                            text = re.sub(regexPhrase, '{{Orphaned non-free revisions|date=~~~~~}}', text)

                        page.save(text, summary="Tagging with {{[[Template:Orphaned non-free revisions|Orphaned non-free revisions]]}}"
                                                " ([[WP:BOT|BOT]] - [[User:DatBot/NonFreeImageResizer/Run|disable]])")

                        print("Tagged!")
                    except Exception as e:
                        print("Unknown error. Image skipped.")
                        logger.error("Unknown error; skipped {0} ({1})".format(imageName, e))
                        bot.deleteFile(imageName)
            else:
                print("Gah, looks like someone removed the tag.")
                logger.error("Tag removed on image; skipped {0}".format(imageName))
        else:
            print("Ah, darn - looks like the bot was disabled.")
            sys.exit()

        filesDone += 1


def main():
    """This defines and fills a global
    variable for the site, and then gets
    selection of images to work with from
    Category:Wikipedia non-free file size reduction requests.
    Then it runs image_routine() on this selection.
    """
    global site
    site = mwclient.Site('en.wikipedia.org')
    site.login(userpass.username, userpass.password)

    sizeReductionCategory = mwclient.listing.Category(site, "Category:Wikipedia non-free file size reduction requests")
    sizeReductionRequests = sizeReductionCategory.members()
    cleanImageList = []
    for image in sizeReductionRequests:
        pageTitle = image.page_title
        print(pageTitle)
        cleanImageList.append(pageTitle)

    imageRoutine(cleanImageList)
    print("We're DONE!")


if __name__ == '__main__':
    main()
