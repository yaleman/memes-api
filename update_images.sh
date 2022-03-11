#!/bin/bash

SOURCE_IMAGE=memes_api/images/memes-head-512px.png

if [ ! -f "${SOURCE_IMAGE}" ]; then
	echo "Couldn't find ${SOURCE_IMAGE}, bailing"
	exit 1
fi



echo "apple-touch-icon-ipad-76x76.png"
convert "${SOURCE_IMAGE}" -colorspace RGB \
-geometry 76x76 \
	memes_api/images/apple-touch-icon-ipad-76x76.png

echo "apple-touch-icon-base.png 362x363"
convert "${SOURCE_IMAGE}" -colorspace RGB \
	-geometry 362x363 \
	memes_api/images/apple-touch-icon-base.png

echo "apple-touch-icon-ipad-retina-152x152.png"
convert "${SOURCE_IMAGE}" -colorspace RGB \
	-geometry 152x152 \
	memes_api/images/apple-touch-icon-ipad-retina-152x152.png

echo "apple-touch-icon-iphone-retina-120x120.png"
convert "${SOURCE_IMAGE}" -colorspace RGB \
	-geometry 120x120 \
	memes_api/images/apple-touch-icon-iphone-retina-120x120.png

echo "apple-touch-icon-iphone-60x60.png"
convert "${SOURCE_IMAGE}" -colorspace RGB \
	-geometry 60x60 \
	memes_api/images/apple-touch-icon-iphone-60x60.png

echo "favicon.png 256x256"
convert "${SOURCE_IMAGE}" -colorspace RGB \
	-geometry 256x256 \
	memes_api/images/favicon.png

function oxi() {
	oxipng --strip all -a -Z "memes_api/images/$1"
}

oxi apple-touch-icon-ipad-76x76.png
oxi apple-touch-icon-base.png
oxi apple-touch-icon-ipad-retina-152x152.png
oxi apple-touch-icon-iphone-retina-120x120.png
oxi apple-touch-icon-iphone-60x60.png
oxi favicon.png