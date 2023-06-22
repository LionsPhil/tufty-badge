# Battery curve logging.

import time
from typing import Tuple
from machine import ADC, Pin
from pimoroni import Button
from picographics import PicoGraphics, DISPLAY_TUFTY_2040
import micropython

WRITE_LOG = micropython.const(True)
SLEEP_INTERVAL = micropython.const(60)
MAX_VOLTAGE = micropython.const(5.0)

# Pins and analogue-digital converters we need to set up to measure sensors.
lux_vref_pwr = Pin(27, Pin.OUT)
lux = ADC(26)
vbat_adc = ADC(29)
vref_adc = ADC(28)
usb_power = Pin(24, Pin.IN)

display = PicoGraphics(display=DISPLAY_TUFTY_2040)
display.set_backlight(0.375) # (1.0)
display.set_font("bitmap8")
WHITE = display.create_pen(255, 255, 255)
BLACK = display.create_pen(0, 0, 0)
WIDTH, HEIGHT = display.get_bounds()

# Returns a tuple of voltage (fake value if on USB) and "is on USB".
def measure_battery() -> Tuple[float, bool]:
    lux_vref_pwr.value(1)
    # See the battery.py example for how this works.
    vdd = 1.24 * (65535 / vref_adc.read_u16())
    vbat = ((vbat_adc.read_u16() / 65535) * 3 * vdd)
    is_usb = usb_power.value()
    lux_vref_pwr.value(0)

    return (vbat, is_usb)

display.set_pen(BLACK)
display.clear()

x = 0
last_y = 0

while True:
    (voltage, is_usb) = measure_battery()
    log_line = f"{time.time()}\t{voltage}\t{is_usb}"
    print(log_line)

    display.set_pen(BLACK)
    display.rectangle(0, 0, WIDTH, 8)
    display.set_pen(WHITE)
    display.text(f"{voltage:.2f}", 0, 0, WIDTH, 1)

    if WRITE_LOG:
        try:
            with open("batterylog.tsv", mode="a") as log_file:
                log_file.write(f"{log_line}\n")
        except OSError as e:
            print("Log failure:", e)

    y = int(HEIGHT - (((HEIGHT - 8) * voltage) / MAX_VOLTAGE))
    print(y)

    if x != 0:
        display.line(x - 1, last_y, x, y)

    x = x + 1
    if x >= WIDTH:
        x = 0

    last_y = y

    display.update()
    time.sleep(SLEEP_INTERVAL)
