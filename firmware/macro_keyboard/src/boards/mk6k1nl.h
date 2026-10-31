#ifndef __MK_BOARD_MK6K1NL_H__
#define __MK_BOARD_MK6K1NL_H__

// MK6K1NL: 6-key + 1-knob CH552G keyboard with a WS2812 under every key
// (docs/PINMAP.md 3). Keys, knob and LED pin are the same as on MK6K1N
// (confirmed with firmware/test_mk6k1nl). The name must match gui/boards.py.

#define BOARD_NAME "MK6K1NL" // up to 8 ASCII characters
#define BOARD_LED_COUNT 6    // chain position i = key i (A-F), GRB
#define BOARD_KEY_LEDS 1

#include "ch552_6k1n.h"

#endif
