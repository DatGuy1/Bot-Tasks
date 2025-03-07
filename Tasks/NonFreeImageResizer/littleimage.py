from typing import TYPE_CHECKING, Any, Optional, Union

import math
import os
import pathlib
import re
import subprocess
import uuid
from contextlib import suppress

import defusedxml.minidom
import mwclient.image
import pyexiv2
from PIL import Image, ImageFile, ImageOps, ImageSequence
from PIL.Image import Palette, Resampling

if TYPE_CHECKING:
    import xml.dom.minidom

ImageFile.LOAD_TRUNCATED_IMAGES = True
SavePath = pathlib.Path(__file__).parent.resolve() / "files"

# svgMatch = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(px|in|cm|mm|pt|pc|%)?")

# CC-BY-SA Theopolisme, DatGuy
# Task 3 on DatBot


def generateThumbnails(frames: ImageSequence.Iterator, size: tuple[int, int]):
    for frame in frames:
        thumbnail = frame.copy()
        thumbnail.thumbnail(size, Resampling.LANCZOS, 3.0)
        yield thumbnail


def calculateNewSize(origWidth: int, origHeight: int):
    newWidth = math.sqrt((100000.0 * origWidth) / origHeight)
    widthPercent = newWidth / origWidth
    newHeight = origHeight * widthPercent

    originalPixels = origWidth * origHeight
    modifiedPixels = newWidth * newHeight
    percentChange = 100.0 * (abs(modifiedPixels - originalPixels) / float(modifiedPixels))
    return newWidth, newHeight, percentChange


def GetSizeFromAttribute(attribute: Any) -> Optional[float]:
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


def updateMetadata(sourcePath: pathlib.Path, destPath: pathlib.Path) -> None:
    """
    This function moves the metadata
    from the old image to the new, reduced
    image using Pillow (previously pyexiv2).
    """
    sourceImage, destImage = None, None
    try:
        sourceImage = pyexiv2.Image(str(sourcePath))
        destImage = pyexiv2.Image(str(destPath))
    except RuntimeError:
        if sourceImage is not None:
            sourceImage.close()
        return

    with suppress(RuntimeError, UnicodeDecodeError):
        imageExif = sourceImage.read_exif()
        # Remove 'Orientation' since we exif_transpose-d it earlier
        imageExif.pop("Exif.Image.Orientation", None)
        destImage.modify_exif(imageExif)
        destImage.modify_xmp(sourceImage.read_xmp())
        destImage.modify_iptc(sourceImage.read_iptc())

    sourceImage.close()
    destImage.close()


# TODO: Cleanup the return value
def downloadImage(randomName: str, imagePage: mwclient.image.Image) -> Union[pathlib.Path, str, tuple[str, str]]:
    """
    This function creates the new image, runs
    metadata(), and passes along the new image's
    random name.
    """
    extension: str = os.path.splitext(imagePage.page_title)[1]
    extensionLower = extension[1:].lower()
    fullName = (SavePath / randomName).with_suffix(extension)
    img: Optional[Image] = None

    tempFile = SavePath / (str(uuid.uuid4()) + extension)
    with tempFile.open("wb") as f:
        imagePage.download(f)

    oldWidth: int
    oldHeight: int
    oldWidth, oldHeight = imagePage.imageinfo["width"], imagePage.imageinfo["height"]
    try:
        # Maybe move this all to seperate functions?
        if extensionLower == "svg":
            # Get size
            useViewBox = False
            docElement: xml.dom.minidom.Element = defusedxml.minidom.parse(str(tempFile)).documentElement

            newWidth, newHeight, percentChange = calculateNewSize(oldWidth, oldHeight)
            if percentChange < 5:
                print(f"Looks like we'd have less than 5% change in pixel counts ({percentChange}). Skipping.")
                tempFile.unlink()
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
                docElement.setAttribute("viewBox", f"{viewboxOffsetX} {viewboxOffsetY} {svgWidth} {svgHeight}")
            elif len(viewboxArray) == 0 or (len(viewboxArray) == 1 and viewboxArray[0] == ""):
                docElement.setAttribute("viewBox", f"0 0 {svgWidth} {svgHeight}")

            with fullName.open("wb") as f:
                f.write(docElement.toxml(encoding="utf-8"))

            """# Condense file size
            subprocess.run(
                ["/data/project/datbot/svgcleaner/svgcleaner", str(fullName), str(fullName)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )"""
        else:
            try:
                img: Image = ImageOps.exif_transpose(Image.open(tempFile))
            except ValueError:
                tempFile.unlink()
                return "BOMB"

            if (oldWidth * oldHeight) > 80000000:
                img.close()
                tempFile.unlink()
                return "BOMB"
            elif (oldWidth * oldHeight) < 100000:
                img.close()
                tempFile.unlink()
                return "UPSCALE"

            newWidth, newHeight, percentChange = calculateNewSize(oldWidth, oldHeight)
            if percentChange < 5:
                img.close()
                print("Looks like we'd have a less than 5% change in pixel counts. Skipping.")
                tempFile.unlink()
                return "PIXEL"

            if extensionLower == "gif":
                gifFrames = ImageSequence.Iterator(img)
                gifFrames = generateThumbnails(gifFrames, (int(newWidth), int(newHeight)))

                newGif: Image = next(gifFrames)  # First frame
                newGif.info = img.info
                newGif.save(fullName, save_all=True, append_images=list(gifFrames))
            else:
                # https://pillow.readthedocs.io/en/stable/handbook/concepts.html#concept-modes
                originalMode: str = img.mode
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
    # except (UnidentifiedImageError, IOError) as e:
    #     print("Unable to open image {0} - aborting ({1})".format(imagePage.page_title, e))
    #     os.remove(tempFile)
    #     return "ERROR"
    except Exception as e:
        errorText = "{}.{}: {}".format(type(e).__module__, type(e).__qualname__, e)
        print("Unable to resize image {0} - aborting ({1})".format(imagePage.page_title, errorText))
        tempFile.unlink()
        return "ERROR", errorText

    print(f"Image saved to disk at {randomName}{extension}")
    if img is not None:
        img.close()
        updateMetadata(tempFile, fullName)  # pyexiv2, see top
        print("Image EXIF data copied!")

    tempFile.unlink()
    return fullName
