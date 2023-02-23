#! /usr/bin/env python
import math
import os
import pathlib
import re
import subprocess
import sys
import uuid

import defusedxml.minidom
import pyexiv2
from PIL import Image, ImageSequence, ImageOps, UnidentifiedImageError
from PIL.Image import Resampling, Palette

savePath = pathlib.Path(__file__).parent.resolve() / "files"

# svgMatch = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(px|in|cm|mm|pt|pc|%)?")

# CC-BY-SA Theopolisme, DatGuy
# Task 3 on DatBot

def generateThumbnails(frames, size):
    for frame in frames:
        thumbnail = frame.copy()
        thumbnail.thumbnail(size, Resampling.LANCZOS, 3.0)
        yield thumbnail

def calculateNewSize(origWidth, origHeight):
    newWidth = math.sqrt((100000.0 * origWidth) / origHeight)
    widthPercent = newWidth / origWidth
    newHeight = origHeight * widthPercent

    originalPixels = origWidth * origHeight
    modifiedPixels = newWidth * newHeight
    percentChange = 100.0 * (abs(modifiedPixels - originalPixels) / float(modifiedPixels))
    return newWidth, newHeight, percentChange


def GetSizeFromAttribute(attribute):
    # If we can instantly convert, go ahead
    try:
        cutNumber = float(attribute)
        return cutNumber
    except ValueError:
        pass

    # Change '135mm' to '135'
    newNumber = ""
    characterList = list(attribute)
    if len(characterList) < 1:
        return None

    for character in characterList:
        if character.isdigit() or character == ".":
            newNumber += character
    try:
        cutNumber = float(newNumber)
    except ValueError:
        return None

    return cutNumber


def updateMetadata(sourcePath, destPath, image):
    """
    This function moves the metadata
    from the old image to the new, reduced
    image using Pillow (previously pyexiv2).
    """
    try:
        sourceImage = pyexiv2.metadata.ImageMetadata(sourcePath)
        sourceImage.read()
        destImage = pyexiv2.metadata.ImageMetadata(destPath)
        destImage.read()
        sourceImage.copy(destImage)
        destImage["Exif.Photo.PixelXDimension"] = image.size[0]
        destImage["Exif.Photo.PixelYDimension"] = image.size[1]
        destImage.write()
    except TypeError:
        pass


def downloadImage(randomName, imagePage) -> str:
    """
    This function creates the new image, runs
    metadata(), and passes along the new image's
    random name.
    """

    extension = os.path.splitext(imagePage.page_title)[1]
    extensionLower = extension[1:].lower()
    fullName = str(savePath / (randomName + extension))
    img = None

    tempFile = str(savePath / (str(uuid.uuid4()) + extension))
    with open(tempFile, "wb") as f:
        imagePage.download(f)

    oldWidth, oldHeight = imagePage.imageinfo["width"], imagePage.imageinfo["height"]
    try:
        # Maybe move this all to seperate functions?
        if extensionLower == "svg":
            # Get size
            useViewBox = False
            docElement = defusedxml.minidom.parse(tempFile).documentElement

            newWidth, newHeight, percentChange = calculateNewSize(oldWidth, oldHeight)
            if percentChange < 5:
                print(
                    "Looks like we'd have a less than 5% change "
                    "in pixel counts. Skipping."
                )
                os.remove(tempFile)
                return "PIXEL"

            svgWidth, svgHeight = GetSizeFromAttribute(docElement.getAttribute("width")), GetSizeFromAttribute(
                docElement.getAttribute("height")
            )

            viewboxArray = re.split("[ ,\t]+", docElement.getAttribute("viewBox"))

            viewboxOffsetX, viewboxOffsetY = 0, 0

            if svgWidth is None or svgHeight is None:
                useViewBox = True
                viewboxOffsetX = float(viewboxArray[0] if len(viewboxArray) > 0 else 0)
                viewboxOffsetY = float(viewboxArray[1] if len(viewboxArray) > 1 else 0)
                svgWidth = float(viewboxArray[2] if len(viewboxArray) > 2 else 0)
                svgHeight = float(viewboxArray[3] if len(viewboxArray) > 3 else 0)

            # If in different units
            # newWidth *= (svgWidth / oldWidth)
            # newHeight *= (svgHeight / oldHeight)

            # Resize
            docElement.setAttribute("width", str(newWidth))
            docElement.setAttribute("height", str(newHeight))

            if useViewBox:
                docElement.setAttribute(
                    "viewBox",
                    "{} {} {} {}".format(
                        viewboxOffsetX, viewboxOffsetY, svgWidth, svgHeight
                    ),
                )
            elif len(viewboxArray) == 0 or (len(viewboxArray) == 1 and viewboxArray[0] == ""):
                docElement.setAttribute(
                    "viewBox",
                    "0 0 {} {}".format(
                        svgWidth, svgHeight
                    ),
                )

            with open(fullName, "wb") as f:
                f.write(docElement.toxml(encoding="utf-8"))

            # Condense file size
            subprocess.run(["/data/project/datbot/svgcleaner/svgcleaner", fullName, fullName],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            try:
                img = ImageOps.exif_transpose(Image.open(tempFile))
            except ValueError:
                os.remove(tempFile)
                return "BOMB"

            if (oldWidth * oldHeight) > 80000000:
                img.close()
                os.remove(tempFile)
                return "BOMB"
            elif (oldWidth * oldHeight) < 100000:
                img.close()
                os.remove(tempFile)
                return "UPSCALE"

            newWidth, newHeight, percentChange = calculateNewSize(oldWidth, oldHeight)

            if percentChange < 5:
                img.close()
                print(
                    "Looks like we'd have a less than 5% change in pixel counts. Skipping."
                )
                os.remove(tempFile)
                return "PIXEL"

            if extensionLower == "gif":
                gifFrames = ImageSequence.Iterator(img)
                gifFrames = generateThumbnails(gifFrames, (int(newWidth), int(newHeight)))

                newGif = next(gifFrames) # First frame
                newGif.info = img.info
                newGif.save(fullName, save_all=True, append_images=list(gifFrames))
            else:
                originalMode = img.mode
                if originalMode in ["1", "L", "P"]:
                    img = img.convert("RGBA")

                img = img.resize((int(newWidth), int(newHeight)), Resampling.LANCZOS)
                if originalMode in ["1", "L", "P"]:
                    img = img.convert(originalMode, palette=Palette.ADAPTIVE)

                # 100 disables portions of the JPEG compression algorithm
                try:
                    img.save(fullName, **img.info, quality=100)
                except ValueError:
                    img.save(fullName, **img.info)
    except (UnidentifiedImageError, IOError) as e:
        print("Unable to open image {0} - aborting ({1})".format(imagePage.page_title, e))
        os.remove(tempFile)
        return "ERROR"
    except Exception as e:
        errorText = "{}.{}: {}".format(type(e).__module__, type(e).__qualname__, e)
        print("Unable to resize SVG {0} - aborting ({1})".format(imagePage.page_title, errorText))
        os.remove(tempFile)
        return "ERROR", errorText


    print("Image saved to disk at {0}{1}".format(randomName, extension))

    """
    if img is not None and extensionLower != "gif":
        try:
            updateMetadata(tempFile, fullName, img)  # pyexiv2, see top
            print("Image EXIF data copied!")
        except (IOError, ValueError) as e:
            print("EXIF copy failed. Oh well - no pain, no gain. {0}".format(e))
    """

    os.remove(tempFile)
    return fullName
