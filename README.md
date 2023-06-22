# Public Tufty 2040 badge scripts.

See https://www.lionsphil.co.uk/projects/tufty/ !

**Requires pimoroni-pico firmware at least v1.20.3.**

## Battery logging

`batterylog.py` saves to the internal flash a trace of the battery voltage, and the two `.tsv` files are those logs for the Tufty 2040 with Galleon (per my build) at 100 and 38 brightness.

[Here's a Google Sheet graph of those discharge curves](https://docs.google.com/spreadsheets/d/e/2PACX-1vTpXWoz99pME7_Eg6EC-DJmQJ_aJ-16jAAGRj1O2WEDJUSpAIutcpOC87QMvEgqXW92cx7S__0H1vUt/pubhtml?gid=483157513&single=true).

**Running this writes to the internal on-die flash.**
I don't think it's particularly limited for write cycles, but it *is* very slowly wearing out an irreplacable part of the board.
I don't expect the micropython "filesystem" to necessarily handle space exhaustion completely gracefully.
I haven't had problems running this a couple of complete discharge cycles, ~20 hours, but use at your own risk etc. etc. and it's not the best idea to leave it running plugged in for ages.
