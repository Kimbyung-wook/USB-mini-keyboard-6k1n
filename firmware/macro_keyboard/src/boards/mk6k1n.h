#ifndef __MK_BOARD_MK6K1N_H__
#define __MK_BOARD_MK6K1N_H__

// MK6K1N: the 6-key + 1-knob CH552G mini keyboard with one LED
// (docs/PINMAP.md 2). The name must match gui/boards.py.

#define BOARD_NAME "MK6K1N" // up to 8 ASCII characters
// One WS2812 is fitted, at a chain position not known: every color is sent
// to 8 positions (as test_pinmap did)
#define BOARD_LED_COUNT 8
#define BOARD_KEY_LEDS 0 // 1: LED i sits under key i

#include "ch552_6k1n.h"

#endif
