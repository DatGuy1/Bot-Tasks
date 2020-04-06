#! /usr/bin/env python
from PIL import Image, UnidentifiedImageError
import pyexiv2
import uuid
import sys
import math
import os

sys.path.append("/data/project/datbot/Tasks/NonFreeImageResizer")

# CC-BY-SA Theopolisme, DatGuy
# Task 3 on DatBot


def updateMetadata(sourcePath, destPath, image):
    """This function moves the metadata
    from the old image to the new, reduced
    image using pyexiv2.
    """
    sourceImage = pyexiv2.metadata.ImageMetadata(sourcePath)
    sourceImage.read()
    destImage = pyexiv2.metadata.ImageMetadata(destPath)
    destImage.read()
    sourceImage.copy(destImage)
    destImage["Exif.Photo.PixelXDimension"] = image.size[0]
    destImage["Exif.Photo.PixelYDimension"] = image.size[1]
    destImage.write()


def downloadImage(randomName, origName, site):
    """This function creates the new image, runs
    metadata(), and passes along the new image's
    random name.
    """
    extension = os.path.splitext(origName)[1]
    extensionLower = extension[1:].lower()

    if extensionLower == "jpg":
        extensionLower = "jpeg"
    elif extensionLower == "gif":
        return "SKIP"

    mwImage = site.Images[origName]

    tempFile = str(uuid.uuid4()) + extension
    with open(tempFile, "wb") as f:
        mwImage.download(f)

    try:
        fullName = randomName + extension
        img = Image.open(tempFile)
        imgWidth = img.size[0]
        imgHeight = img.size[1]
        if (imgWidth * imgHeight) > 80000000:
            img.close()
            return "BOMB"

        baseWidth = int(math.sqrt((100000.0 * float(imgWidth)) / (imgHeight)))
        widthPercent = baseWidth / float(imgWidth)
        heightSize = int((float(imgHeight) * float(widthPercent)))

        originalPixels = imgWidth * imgHeight
        modifiedPixels = baseWidth * heightSize
        percentChange = 100.0 * (originalPixels - modifiedPixels) / float(originalPixels)
        if percentChange > 5:
            originalMode = img.mode
            if originalMode in ["1", "L", "P"]:
                img = img.convert("RGBA")

            img = img.resize((int(baseWidth), int(heightSize)), Image.ANTIALIAS)
            if originalMode in ["1", "L", "P"]:
                img = img.convert(originalMode, palette=Image.ADAPTIVE)

            img.save(fullName, **img.info, quality=95)
        else:
            img.close()
            print("Looks like we'd have a less than 5% change in pixel counts. Skipping.")
            return "PIXEL"
    except UnidentifiedImageError as e:
        print("Unable to open image {0} - aborting ({1})".format(origName, e))
        return "ERROR"
    except IOError as e:
        img.close()
        print("Unable to open image {0} - aborting ({1})".format(origName, e))
        return "ERROR"

    print("Image saved to disk at {0}{1}".format(randomName, extension))

    try:
        updateMetadata(tempFile, fullName, img)  # pyexiv2, see top
        print("Image EXIF data copied!")
    except (IOError, ValueError) as e:
        print("EXIF copy failed. Oh well - no pain, no gain. {0}".format(e))

    filelist = [f for f in os.listdir(".") if f.startswith(tempFile)]
    for fa in filelist:
        os.remove(fa)

    return fullName
