#ifndef __MK_LED_H__
#define __MK_LED_H__

#include <stdint.h>
#include "config.h"

// What the LEDs show (docs/MANUAL.md "LED 색 요약"): locked = dark with a
// short red blink every 3 s, pattern entry = solid red, blocked = red
// blinking, open = blue, green for a moment on every key press (and while
// typing), white flash after saving, purple before the bootloader. With an
// LED under every key (BOARD_KEY_LEDS) only the pressed key's LED turns
// green, and in a pattern entry the pressed key's LED goes dark for a
// moment; a knob action shows on all of them.

// Colors: index into hal_palette
#define COLOR_OFF 0
#define COLOR_IDLE 1
#define COLOR_TYPING 2
#define COLOR_SAVED 3
#define COLOR_BOOT 4
#define COLOR_RED 5

void led_task(void);           // from loop(), after the other tasks
void led_saved(void);          // a config was saved: white flash
void led_boot(void);           // purple, right before the bootloader
void led_typed(uint8_t slot);  // an action typed on an open keyboard
#if BOARD_KEY_LEDS
void led_entered(uint8_t slot); // an action in a pattern entry
#else
#define led_entered(slot) // the single LED stays red
#endif

#endif
