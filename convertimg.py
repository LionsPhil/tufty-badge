#!/usr/bin/env python3
# Convert image to RLE binary blob, since the only decoder library on the
# Tufty 2040 is...JPEG. :|
#
# Using RLE makes rendering it slightly more efficient through PicoGraphics.
# Format:
#  256 x 3 RGB bytes for the palette
#  240 rows of spans summing to 320 columns
#    span starting with zero: next byte is number of bytes in "non-RLE" span,
#      each is a pixel value (indexed)
#    span starting with nonzero: next byte is pixel repeated that many times
# There is *no* size header, but images of other sizes are possible if the
# decoder is told the same size.
#
# Copyright 2023 Philip Boulain.
# Licensed under the EUPL-1.2-or-later.

import argparse
import sys
import os
from PIL import Image

arg_parser = argparse.ArgumentParser(description='Pico RLE Image encoder.')
arg_parser.add_argument('filename')
arg_parser.add_argument('--allow-other-dimensions', action='store_true',
    help="Don't validate the input image dimensions.")
arg_parser.add_argument('--no-generate-unspans', action='store_true',
    help="Don't generate unspans for efficient noisy regions.")
arg_parser.add_argument('--round-trip', action='store_true',
    help="Decode the image back to (file)-roundtrip.png to test.")
args = arg_parser.parse_args()

infile = args.filename
if infile == '':
    raise ValueError('bad argv; need exactly one file')

# Pico RLE Image
outfile = os.path.splitext(os.path.basename(infile))[0] + '.pri'
# Round-trip file, to debug the encoding
rtfile = os.path.splitext(os.path.basename(infile))[0] + '-roundtrip.png'

sys.stderr.write(f"Generating {outfile} from {infile}...\n")

# Propagating exceptions to kill the program is fine.
im = Image.open(infile)

if im.mode == 'P':
    sys.stderr.write("Image is already palettized\n")
    if not args.allow_other_dimensions:
        if im.width != 320 or im.height != 240:
            # Trying to resize this means something is wrong (and would be ugly).
            raise ValueError("Palettized image is wrong size; aborting\n")
else:
    if not args.allow_other_dimensions:
        # Resize as needed; any wrong aspect ratio just gets smushed.
        im = im.resize([320, 240], Image.LANCZOS)

    # Drop to 256 colors.
    # https://github.com/Chadys/QuantizeImageMethods
    im = im.quantize(colors=256, method=Image.MEDIANCUT,
        dither=Image.FLOYDSTEINBERG)

pal = im.getpalette()
assert len(pal) == 256 * 3
if not args.allow_other_dimensions:
    assert im.height == 240
    assert im.width == 320

GENERATE_UNSPANS = not args.no_generate_unspans

with open(outfile, "wb") as outf:
    for i, _ in enumerate(pal):
        outf.write(pal[i].to_bytes(length=1, byteorder='big'))
    for y in range(0, im.height):
        span_pixel = -1
        span_count = 0
        unspan = []
        def write_unspan():
            if len(unspan) == 0:
                return
            elif len(unspan) == 1:
                # Simpler to just write this as a size-one span.
                outf.write(b'\x01')
                outf.write(unspan[0].to_bytes(length=1, byteorder='big'))
            else:
                # Write a zero, a size, and then the non-RLE'd pixels.
                outf.write(b'\x00')
                outf.write(len(unspan).to_bytes(length=1, byteorder='big'))
                for p in unspan:
                    outf.write(p.to_bytes(length=1, byteorder='big'))
            # Python rant: if this is "= []", I could understand that trampling
            # the binding, but it *actually* confuses the binding so that it
            # doesn't even make it in the first place, and complains about
            # unassigned access; if you then use "nonlocal unspan" things get
            # *worse* and pylance(?) knows it's a list now but nonlocal can't
            # find the binding (even though it should! and is in theory
            # even necessary with these nested functions!)
            unspan.clear()

        def write_span():
            if span_count == 0:
                write_unspan()  # Flush any unspan as well.
            elif GENERATE_UNSPANS and span_count == 1:
                # Buffer this up as an unspan of non-contiguous pixels.
                unspan.append(span_pixel)
                if len(unspan) == 255:
                    write_unspan()  # Don't overflow unspan size.
            else:
                # A genuine RLE span!
                write_unspan()  # If we'd built one up.
                outf.write(span_count.to_bytes(length=1, byteorder='big'))
                outf.write(span_pixel.to_bytes(length=1, byteorder='big'))

        for x in range(0, im.width):
            pixel = im.getpixel((x,y))
            if pixel == span_pixel:
                # Extend the existing span.
                span_count += 1
                # Commit and start a new one if we reached max length.
                if span_count == 255:
                    write_span()
                    span_pixel = -1
                    span_count = 0
            else:
                # Commit the previous span, and start a new one of this.
                write_span()
                span_pixel = pixel
                span_count = 1
        # Write any leftover span (zero-length automatically ignored).
        write_span()
        # Flush any unspan as well; write_span() can refill this if the very
        # last column was a unique pixel.
        write_unspan()

# Old, non-RLE ".raw" format:
#  256 x 3 RGB bytes for the palette
#  240 rows of 320 columns of raw single-byte pixels (pallettized)
if False:
    with open(outfile, "wb") as outf:
        for i, _ in enumerate(pal):
            outf.write(pal[i].to_bytes(length=1, byteorder='big'))
        for y in range(0, im.height):
            for x in range(0, im.width):
                outf.write(im.getpixel((x,y)).to_bytes(length=1, byteorder='big'))

# Roundtrip

if args.round_trip:
    sys.stderr.write(f"Generating {rtfile} from {outfile}...\n")

    with open(outfile, "rb") as handle:
        im = Image.new('P', (im.width, im.height))
        paldata = bytearray(256 * 3)
        handle.readinto(paldata)
        im.putpalette(paldata)

        span_data = bytearray(2)
        for y in range(0, im.height):
            x = 0
            while x < im.width:
                handle.readinto(span_data)
                count = int(span_data[0])
                value = int(span_data[1])
                if count == 0:
                    # This is actually an unspan; value is our read size.
                    unspan_data = handle.read(value)
                    #print("Unspan", unspan_data)
                    for pixel in unspan_data:
                        im.putpixel((x, y), pixel)
                        x += 1
                else:
                    # Normal RLE span.
                    #print("Span", x, y, count, value)
                    while count > 0:
                        im.putpixel((x, y), value)
                        x += 1
                        count -= 1

        im.save(rtfile, format='PNG')

sys.stderr.write("Done\n")
