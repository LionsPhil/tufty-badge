# LionsPhil's badge template for Tufty2040
# Copyright 2023 Philip Boulain,
# with parts derived from MIT-licensed Pimoroni example code.
# Licensed under the EUPL-1.2-or-later.

# Derived from examples from:
# https://github.com/pimoroni/pimoroni-pico/tree/main/micropython/examples/tufty2040
# Docs about the lux sensor and act LED are at:
# https://learn.pimoroni.com/article/getting-started-with-tufty-2040
# And details of PicoGraphics capabilities, like paletted mode:
# https://github.com/pimoroni/pimoroni-pico/blob/main/micropython/modules/picographics/README.md

# There's a lot here, because this is a slightly cleaned and genericized version
# of my own LP-202 badge. But if you work from the top down and read the
# comments, you should be able to figure out which parts you want to change.

# If you're just after the automatic brightness, I upstreamed that as the
# "autobright" example, and it's a little cleaner to take from there since here
# it's tangled with some status-tracking stuff.

from picographics import PicoGraphics, DISPLAY_TUFTY_2040, PEN_P8
from pimoroni import Button
from machine import ADC, Pin
import micropython
import random
import time
import qrcode


# Text (most likely a website) to encode as a QR code.
QR_TEXT = micropython.const("lionsphil.co.uk")

# Constants for automatic brightness adjustment.
# Below about 3/8ths, the backlight is entirely off. The top of the range is OK.
BACKLIGHT_LOW = micropython.const(0.375)
BACKLIGHT_HIGH = micropython.const(1.0)
# The luminance sensor seems to cover the whole 16-bit range pretty well from
# buried in shadow to bright phone torch in its face, but setting a lower high
# point will make it generally bias brighter in calm room lighting, and a higher
# low will use the darkest backlight without needing to completely hard-mask the
# sensor in complete darkness.
LUMINANCE_LOW = micropython.const(256)
LUMINANCE_HIGH = micropython.const(2048)  # 65535 to use the full range.

# Fursona reaction hysteresis thresholds are set much higher.
REACT_BRIGHT_SET   = micropython.const(32768)
REACT_BRIGHT_RESET = micropython.const(16384)

# If on battery, and the supply voltage drops below this, force minimum
# backlight brightness. Set to zero to not even measure voltage.
# The bottom of the Tufty2040 input range is 3.0v, so values below that likely
# will not trigger before it cuts out.
# Implements hysteresis thresholding using the RECOVERED voltage.
LOW_BATTERY_VOLTAGE = micropython.const(3.1)
RECOVERED_BATTERY_VOLTAGE = micropython.const(3.3)

# Reference voltages for a full/empty battery, in volts.
# Values for a Galleon 400mAh LiPo (I'm getting 3.8, not 3.7):
VBAT_HIGH = micropython.const(3.8)
VBAT_LOW = micropython.const(2.5)

display = PicoGraphics(display=DISPLAY_TUFTY_2040, pen_type=PEN_P8)
display.set_backlight(0.0)  # Until we've had a chance to repaint
WIDTH, HEIGHT = display.get_bounds()
button_a = Button(7, invert=False)
button_b = Button(8, invert=False)
button_c = Button(9, invert=False)
button_up = Button(22, invert=False)
button_down = Button(6, invert=False)
button_boot = Button(23, invert=True)
lux_vref_pwr = Pin(27, Pin.OUT)
lux = ADC(26)
vbat_adc = ADC(29)
vref_adc = ADC(28)
usb_power = Pin(24, Pin.IN)
led = Pin(25, Pin.OUT)

stats = {
    "vbat": 0.0,
    "vbat_low": 100.0,
    "vbat_high": 0.0,
    "low_battery": False,
    "usb": False,
    "lum": 0,
    "lum_low": 65535,
    "lum_high": 0,
    "backlight": 0.0,  # Also used to smooth changes (so will fade in)
}


# This is an optimization annotation for making the PRI image loader fast.
# https://docs.micropython.org/en/latest/reference/speed_python.html#the-viper-code-emitter
# See also @micropython.native ; viper is not fully compliant (but seems OK!)
# Neither native nor viper can handle "with", so this is factored out.
@micropython.viper
def blit_from_io_spans(handle):
    span_data = bytearray(2)
    for y in range(0, 240):
        # Comment this out if you don't like the activity light blinking.
        led.value((y % 8) < 4)
        x = 0
        while x < 320:
            handle.readinto(span_data)
            count = int(span_data[0])
            value = int(span_data[1])
            if count == 0:
                # This is actually an unspan; value is our read size.
                unspan_data = handle.read(value)
                for pixel in unspan_data:
                    display.set_pen(pixel)
                    display.pixel(x, y)
                    x += 1
            else:
                # Normal RLE span.
                display.set_pen(value)
                display.pixel_span(x, y, count)
                x += count


# Pico RLE Image; see convertimg.py for format (and generating these).
def draw_pri_image(filename):
    palette = [None] * 256
    # Uncomment these and the below lines for poor-man's profiling.
    #t_start = time.ticks_ms()
    #t_donepal = None
    #t_done = None

    with open(filename, "rb") as raw:
        # Reading the whole palette upfront actually seems slower; guess it
        # might be the larger allocation.
        palbuf = bytearray(3)
        for palette_index in range(0, 256):
            raw.readinto(palbuf)
            palette[palette_index] = (palbuf[0], palbuf[1], palbuf[2])
        display.set_palette(palette)
        #t_donepal = time.ticks_ms()
        blit_from_io_spans(raw)

    #t_done = time.ticks_ms()
    #td_pal = time.ticks_diff(t_donepal, t_start)
    #td_blit = time.ticks_diff(t_done, t_donepal)
    #print(f"draw_pri_image({filename}): pal {td_pal}ms, blit {td_blit}ms")
    return palette


# Draw chunky 3D rectangles.
def draw_3d_rect(x, y, w, h, highlight, fill, shadow):
    display.set_pen(shadow)
    display.rectangle(x, y, w, h)
    display.set_pen(highlight)
    display.rectangle(x, y, w-2, h-2)
    display.set_pen(fill)
    display.rectangle(x+2, y+2, w-4, h-4)


def draw_text_centered(text, x, y, wordwrap, scale=2.0, spacing=1):
    w = display.measure_text(text, scale, spacing)
    display.text(text, int(x + ((wordwrap - w) / 2)), y, wordwrap,
                 scale=scale, spacing=spacing)


def draw_text_right(text, x, y, wordwrap, scale=2.0, spacing=1):
    w = display.measure_text(text, scale, spacing)
    display.text(text, x + (wordwrap - w), y, wordwrap,
                 scale=scale, spacing=spacing)


# This is useful for badge modes that don't want to do anything on tick.
def do_nothing():
    pass


### Badge mode: Look At My Fursona
#
# (If you want something more conventional, you can splice some of retro_badge
# from the examples in here, printing some text and a JPEG instead.)
#
# This expects four images to exist on the Tufty!
#   fursona-regular.pri - Main variation
#   fursona-turn.pri    - Randomly switched to and back every so often
#   fursona-bright.pri  - When exposed to bright light
#   fursona-lowbat.pri  - When the battery is low
#
# Read the comments! This cycles the last 128 palette entries by default.

bmode_fursona_current_face = None
bmode_fursona_ticks_until_turn = 10*25
bmode_fursona_is_bright = False
bmode_fursona_palette = None


def bmode_fursona_init():
    global bmode_fursona_current_face
    bmode_fursona_current_face = None
    bmode_fursona_tick()


def bmode_fursona_tick():
    global bmode_fursona_current_face
    global bmode_fursona_ticks_until_turn
    global bmode_fursona_is_bright
    global bmode_fursona_palette
    face = "regular"

    # Stay turned if we're turned.
    if bmode_fursona_current_face == "turn":
        face = "turn"

    # Threshold brightness changes.
    if stats["lum"] > REACT_BRIGHT_SET:
        bmode_fursona_is_bright = True
    if stats["lum"] < REACT_BRIGHT_RESET:
        bmode_fursona_is_bright = False

    # Override with bright or low battery faces.
    # LUX is not measured during low battery, so this priority isn't used.
    if bmode_fursona_is_bright:
        face = "bright"
    elif stats["low_battery"]:
        face = "lowbat"

    # If there's no face override...
    if face == "regular" or face == "turn":
        # ...count down a flip between regular and turn.
        # We don't tick consistently...the sleep is for 50Hz, but without
        # any compensation for work, we hit more like half to 2/3rds that.
        bmode_fursona_ticks_until_turn -= 1
        if bmode_fursona_ticks_until_turn <= 0:
            if bmode_fursona_current_face == "regular":
                face = "turn"
                bmode_fursona_ticks_until_turn = random.randint(1*25, 3*25)
            elif bmode_fursona_current_face == "turn":
                face = "regular"
                bmode_fursona_ticks_until_turn = random.randint(10*25, 60*25)

    if bmode_fursona_current_face != face:
        bmode_fursona_current_face = face
        bmode_fursona_palette = draw_pri_image(f"fursona-{face}.pri")
        #display.update()  # Redundant with palette cycling, which needs one.

    # Cycle the palette.
    # You can comment all this out if you don't want it, and enable the update
    # just above instead. You can also adjust the range.
    PALCYCLE_FIRST = micropython.const(128)
    PALCYCLE_LAST = micropython.const(255)
    wrap = bmode_fursona_palette[PALCYCLE_LAST]
    bmode_fursona_palette[PALCYCLE_FIRST+1:PALCYCLE_LAST+1] = (
        bmode_fursona_palette[PALCYCLE_FIRST:PALCYCLE_LAST])
    bmode_fursona_palette[PALCYCLE_FIRST] = wrap
    display.set_palette(bmode_fursona_palette)
    display.update()


### Badge mode: QR code
#
# This is largely the same as the retro_badge example.

def measure_qr_code(size, code):
    w, h = code.get_size()
    module_size = int(size / w)
    return module_size * w, module_size


def draw_qr_code(ox, oy, size, code):
    size, module_size = measure_qr_code(size, code)
    display.set_pen(1)
    display.rectangle(ox, oy, size, size)
    display.set_pen(2)
    for x in range(size):
        led.value((x % 4) < 2)
        for y in range(size):
            if code.get_module(x, y):
                display.rectangle(ox + x * module_size, oy + y * module_size, module_size, module_size)


def bmode_qr_init():
    # Don't use pure white to work around an issue with large expanses of it:
    # https://github.com/pimoroni/pimoroni-pico/issues/567
    # Using a light border helps a lot with phones scanning it; stops the
    # exposure blooming so badly, and helps them pick out the corners.
    # This is my usual #FFAA00 but at luminance of 240 and 192. It reads really
    # well in testing.
    display.set_palette([(255, 245, 225), (255, 212, 129), (0, 0, 0)])
    display.set_pen(0)
    display.clear()

    led.value(True)  # Set LED for progress while generating QRcode, as images.
    code = qrcode.QRCode()
    code.set_text(QR_TEXT)

    size, module_size = measure_qr_code(HEIGHT, code)
    left = int((WIDTH // 2) - (size // 2))
    top = int((HEIGHT // 2) - (size // 2))
    draw_qr_code(left, top, HEIGHT, code)
    led.value(False)  # Blink it off now we're moving on to text rendering.

    display.set_pen(2)
    # You can put some set_font() and text() calls here to write in the borders.

    # Note how because the QR code has no animation, we update the display in
    # init instead of tick, and then don't have to do anything in tick.
    display.update()


### Badge mode: Status readout
#
# Draw bars for battery voltage, light level, and backlight level.
#
# This expects status.pri to exist on the Tufty, and have a palette that matches
# all the constants in bmode_status_tick() (it's the Windows pallette). You can
# of course change that!
#
# A suitable blank template exists as status.png in the repository, which you
# can customize, convert (convertimg.py), and upload (via Thonny).

def bmode_status_init():
    draw_pri_image("status.pri")
    display.set_font("bitmap8")
    bmode_status_tick()


def bmode_status_tick():
    WPAL_BLACK    = micropython.const(0)
    WPAL_DRED     = micropython.const(1)
    WPAL_DGREEN   = micropython.const(2)
    WPAL_DYELLOW  = micropython.const(3)
    WPAL_DBLUE    = micropython.const(4)
    WPAL_DMAGENTA = micropython.const(5)
    WPAL_DCYAN    = micropython.const(6)
    WPAL_GREY     = micropython.const(7)
    WPAL_DGREY    = micropython.const(248)
    WPAL_RED      = micropython.const(249)
    WPAL_GREEN    = micropython.const(250)
    WPAL_YELLOW   = micropython.const(251)
    WPAL_BLUE     = micropython.const(252)
    WPAL_MAGENTA  = micropython.const(253)
    WPAL_CYAN     = micropython.const(254)
    WPAL_WHITE    = micropython.const(255)
    GAUGE_X           = micropython.const(56)
    GAUGE_VBAT_Y      = micropython.const(24)
    GAUGE_LUX_Y       = micropython.const(96)
    GAUGE_BACKLIGHT_Y = micropython.const(168)
    GAUGE_W           = micropython.const(256)
    GAUGE_H           = micropython.const(64)
    SCALE = micropython.const(2)

    display.set_pen(WPAL_BLACK)
    display.rectangle(GAUGE_X, GAUGE_VBAT_Y, GAUGE_W, GAUGE_H)
    display.rectangle(GAUGE_X, GAUGE_LUX_Y, GAUGE_W, GAUGE_H)
    display.rectangle(GAUGE_X, GAUGE_BACKLIGHT_Y, GAUGE_W, GAUGE_H)

    # Battery gauge debugging for while attached to Thonny.
    if False:
        stats["usb"] = False
        stats['vbat_low'] = 3.0
        stats['vbat'] -= 0.01
        stats['vbat_high'] = 3.8
        if stats['vbat'] < VBAT_LOW:
            stats['vbat'] = VBAT_HIGH

    if stats["usb"]:
        display.set_pen(WPAL_WHITE)
        draw_text_centered("On USB power", GAUGE_X,
                           int(GAUGE_VBAT_Y + ((GAUGE_H - (8*SCALE)) / 2)),
                           256, SCALE)
    else:
        BAT_THRESH = (LOW_BATTERY_VOLTAGE - VBAT_LOW) / (VBAT_HIGH - VBAT_LOW)
        bat_frac = (stats['vbat'] - VBAT_LOW) / (VBAT_HIGH - VBAT_LOW)
        bat_frac = min(1.0, max(0.0, bat_frac))
        # Overdraw hides the right border of the red segment
        w = int(bat_frac * 256)  # int(min(BAT_THRESH, bat_frac) * 256)
        draw_3d_rect(GAUGE_X, GAUGE_VBAT_Y, w, GAUGE_H,
                     WPAL_YELLOW, WPAL_RED, WPAL_DRED)
        if bat_frac > BAT_THRESH:
            w = int(bat_frac * 256) - int(BAT_THRESH * 256)
            draw_3d_rect(GAUGE_X + int(BAT_THRESH * 256), GAUGE_VBAT_Y, w, GAUGE_H,
                         WPAL_GREEN, WPAL_DGREEN, WPAL_DGREY)
            # Patch the left edge of the green segment
            display.set_pen(WPAL_DGREEN)
            display.rectangle(GAUGE_X + int(BAT_THRESH * 256), GAUGE_VBAT_Y + 2,
                              min(2, w), GAUGE_H - 4)
        display.set_pen(WPAL_WHITE)
        draw_text_centered(f"{bat_frac * 100.0:.2f}%",
                           GAUGE_X,
                           int(GAUGE_VBAT_Y + ((GAUGE_H - (8*SCALE)) / 2)),
                           256, SCALE)
        y = GAUGE_VBAT_Y + GAUGE_H - (2 + 8*2)
        display.text(f"{stats['vbat_low']:.2f}v",
                     GAUGE_X + 2, y, 252, SCALE)
        draw_text_centered(f"{stats['vbat']:.2f}v",
                           GAUGE_X + 2, y, 252, SCALE)
        draw_text_right(f"{stats['vbat_high']:.2f}v",
                        GAUGE_X + 2, y, 252, SCALE)

    w = int(stats['lum'] / (8192 / 256))  # Reduced range from 65536
    w = min(w, 256)
    draw_3d_rect(GAUGE_X, GAUGE_LUX_Y, w, GAUGE_H,
                 WPAL_WHITE, WPAL_YELLOW, WPAL_DYELLOW)
    display.set_pen(WPAL_MAGENTA)
    draw_text_centered(f"{stats['lum'] / 655.36:.2f}%",
                       GAUGE_X,
                       int(GAUGE_LUX_Y + ((GAUGE_H - (8*SCALE)) / 2)),
                       256, SCALE)
    y = GAUGE_LUX_Y + GAUGE_H - (2 + 8*2)
    display.text(f"{stats['lum_low'] / 655.36:.2f}%",
                 GAUGE_X + 2, y, 252, SCALE)
    draw_text_right(f"{stats['lum_high'] / 655.36:.2f}%",
                    GAUGE_X + 2, y, 252, SCALE)

    w = int(stats['backlight'] * 256)
    draw_3d_rect(GAUGE_X, GAUGE_BACKLIGHT_Y, w, GAUGE_H,
                 WPAL_CYAN, WPAL_DCYAN, WPAL_DBLUE)
    display.set_pen(WPAL_YELLOW)
    draw_text_centered(f"{int(stats['backlight'] * 100)}%", GAUGE_X,
                       int(GAUGE_BACKLIGHT_Y + ((GAUGE_H - (8*SCALE)) / 2)),
                       256, SCALE)

    display.update()


def auto_brightness():
    luminance = lux.read_u16()
    if button_up.is_pressed:
        # Debug key
        luminance = 65535
    luminance_frac = max(0.0, float(luminance - LUMINANCE_LOW))
    luminance_frac = min(1.0, luminance_frac / (LUMINANCE_HIGH - LUMINANCE_LOW))
    backlight = BACKLIGHT_LOW + (luminance_frac * (BACKLIGHT_HIGH - BACKLIGHT_LOW))
    # Use the stats to gently smear the backlight to reduce flickering.
    backlight_diff = backlight - stats["backlight"]
    backlight = stats["backlight"] + (backlight_diff * (1.0 / 32.0))
    display.set_backlight(backlight)

    stats["lum"] = luminance
    stats["lum_low"] = min(stats["lum_low"], luminance)
    stats["lum_high"] = max(stats["lum_high"], luminance)
    stats["backlight"] = backlight


def measure_battery():
    if button_down.is_pressed:
        # Debug key
        stats["vbat"] = 3.0
        stats["usb"] = False
        stats["low_battery"] = True
        return

    if LOW_BATTERY_VOLTAGE == 0.0:
        return False  # Don't even measure; assume the battery is good.
    if usb_power.value():
        stats["usb"] = True
        stats["low_battery"] = False
        return False  # We have LIMITLESS POWER from USB!
    # See the battery.py example for how this works.
    vdd = 1.24 * (65535 / vref_adc.read_u16())
    vbat = ((vbat_adc.read_u16() / 65535) * 3 * vdd)

    stats["vbat"] = vbat
    stats["vbat_low"] = min(stats["vbat_low"], vbat)
    stats["vbat_high"] = max(stats["vbat_high"], vbat)
    stats["usb"] = False

    if vbat < LOW_BATTERY_VOLTAGE:
        stats["low_battery"] = True
    elif vbat > RECOVERED_BATTERY_VOLTAGE:
        stats["low_battery"] = False


# Blink the activity LED a bit, and block while at it, which avoids a button
# press getting double-counted. See the "led_pwm" example for a different way
# to drive this, although you'll have to change the image loading and QR
# routines as well to match.
def blocking_led_pulse():
    for i in range(0, 2):
        for on in range(1, -1, -1):
            led.value(on)
            time.sleep(0.05)


# This is a list of modes the badge will cycle through when you press one of the
# A/B/C buttons. Each mode has an "init" function, which is called once when the
# mode is switched to, and a "tick" function that is then called repeatedly.
# You will need to update the display yourself in whichever is appropriate.
# (See the QR code and status display as an example.)
badge_modes = [
    {
        "init": bmode_fursona_init,
        "tick": bmode_fursona_tick,
    },
    {
        "init": bmode_qr_init,
        "tick": do_nothing,
    },
    {
        "init": bmode_status_init,
        "tick": bmode_status_tick,
    },
]
current_mode = 0

# Draw the badge for the first time.
badge_modes[current_mode]["init"]()
random.seed()  # Tufty firmware apparently defines a default RNG source.

while True:
    # Turn on VREF and LUX only while we measure things.
    lux_vref_pwr.value(1)
    measure_battery()
    if stats["low_battery"]:
        display.set_backlight(BACKLIGHT_LOW)
        stats["backlight"] = BACKLIGHT_LOW
    else:
        auto_brightness()
    lux_vref_pwr.value(0)

    if button_a.is_pressed or button_b.is_pressed or button_c.is_pressed:
        current_mode += 1
        if current_mode >= len(badge_modes):
            current_mode = 0
        badge_modes[current_mode]["init"]()
        blocking_led_pulse()

    badge_modes[current_mode]["tick"]()
    # This controls how fast we go. It's *up to* 50Hz; there's no rate control
    # to allow for how long everything else in this loop takes.
    time.sleep(1.0 / 50.0)
