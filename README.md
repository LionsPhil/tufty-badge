# Public Tufty 2040 badge scripts.

**See https://www.lionsphil.co.uk/projects/tufty/ !**

Requires pimoroni-pico firmware at least v1.20.3.
See [the project page](https://www.lionsphil.co.uk/projects/tufty/#software) for how to update it.
Make sure you update `main.py` too, or the badge may fail to start due to low memory.

## Badge template

Mostly, read the project page to install, and read the comments to customize.
You will need to use [`convertimg.py`](https://github.com/LionsPhil/tufty-badge/blob/main/convertimg.py) to prepare your artwork, and Thonny to copy it (and the script) over.

Alternatively, you can change the `draw_pri_image` calls to [draw PNGs](https://github.com/pimoroni/pimoroni-pico/blob/main/micropython/modules/picographics/README.md#png-files).
I don't use PNG (yet, anyway) because, aside from this being written before that library was added, the PNG decoder uses more memory and that is quite tight.
I was also having some palette issues, and even if those were solved, [a FR is needed for the color cycling](https://github.com/pimoroni/pimoroni-pico/issues/994).

By default, the badge cycles through the three screens on any of the A/B/C buttons.
Holding the up/down arrows while on the status screen will adjust a brightness cap.

As a debug feature, holding an arrow then holding C (in this order, if you want to avoid cycling screen) will fake a reading; C+up is fake maximum brightness, C+down is fake low battery.

## Convertimg

Converts other images to PRI, for the badge.
Run this on a full computer with a Python environment (like a normal Linux Pi), with a single PNG as an argument, and it will write the matching PRI file.
You don't need any of the command-line flags.
Use Thonny to copy the PRI file onto the Tufty.

(If you've seen my other projects, note that this is an earlier version of PRI than the [PRI2 format](https://github.com/LionsPhil/inkyframe/blob/main/paperthin-server/picorle.py) supported by PaperThin; they're not interchangable.)

## Battery logging

`batterylog.py` saves to the internal flash a trace of the battery voltage, and the two `.tsv` files are those logs for the Tufty 2040 with Galleon (per my build) at 100 and 38 brightness.

[Here's a Google Sheet graph of those discharge curves](https://docs.google.com/spreadsheets/d/e/2PACX-1vTpXWoz99pME7_Eg6EC-DJmQJ_aJ-16jAAGRj1O2WEDJUSpAIutcpOC87QMvEgqXW92cx7S__0H1vUt/pubhtml?gid=483157513&single=true).

**Running this writes to the internal on-die flash.**
I don't think it's particularly limited for write cycles, but it *is* very slowly wearing out an irreplacable part of the board.
I don't expect the micropython "filesystem" to necessarily handle space exhaustion completely gracefully.
I haven't had problems running this a couple of complete discharge cycles, ~20 hours, but use at your own risk etc. etc. and it's not the best idea to leave it running plugged in for ages.
