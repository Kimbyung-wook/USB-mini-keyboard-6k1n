#ifndef __MK_BOARD_H__
#define __MK_BOARD_H__

// MK6K1N: the 6-key + 1-knob CH552G mini keyboard (docs/BOARD_INFO.md).
// The name must match gui/boards.py.

#define BOARD_NAME "MK6K1N" // up to 8 ASCII characters
#define BOARD_CHIP "CH552"
#define BOARD_CHIP_ID 0x52 // as the bootloader's Detect reports it
#define BOARD_KEYS 6
#define BOARD_KNOBS 1
#define BOARD_ROWS 2
#define BOARD_FEATURES (BOARD_FEATURE_RGB_LED | BOARD_FEATURE_LOCK)

// CH55xduino pin numbers: port * 10 + bit (confirmed with test_pinmap)
#define PIN_KEY_A 11 // P1.1
#define PIN_KEY_B 17 // P1.7
#define PIN_KEY_C 16 // P1.6
#define PIN_KEY_D 15 // P1.5, also the ROM bootloader pin
#define PIN_KEY_E 14 // P1.4
#define PIN_KEY_F 32 // P3.2
#define PIN_KNOB_SW 33 // P3.3
#define PIN_ENC_A 30 // P3.0
#define PIN_ENC_B 31 // P3.1
#define PIN_LED 34   // P3.4, one WS2812 (GRB)

// Switch bits in slot order (keys A-F, then the knob switch). The first
// BOARD_P1_SWITCHES are on P1, the rest on P3.
#define BOARD_P1_SWITCHES 5
#define BOARD_SWITCH_BITS                                                      \
  PIN_BIT(PIN_KEY_A), PIN_BIT(PIN_KEY_B), PIN_BIT(PIN_KEY_C),                  \
      PIN_BIT(PIN_KEY_D), PIN_BIT(PIN_KEY_E), PIN_BIT(PIN_KEY_F),              \
      PIN_BIT(PIN_KNOB_SW)

// The sketch reads and writes the ports directly instead of digitalRead and
// friends (saves the core's pin tables). It relies on this layout:
#if PIN_PORT(PIN_KEY_A) != 1 || PIN_PORT(PIN_KEY_B) != 1 ||                   \
    PIN_PORT(PIN_KEY_C) != 1 || PIN_PORT(PIN_KEY_D) != 1 ||                   \
    PIN_PORT(PIN_KEY_E) != 1
#error keys A-E must be on P1
#endif
#if PIN_PORT(PIN_KEY_F) != 3 || PIN_PORT(PIN_KNOB_SW) != 3 ||                 \
    PIN_ENC_A != 30 || PIN_ENC_B != 31 || PIN_LED != 34
#error key F and the knob must be on P3, encoder A/B on P3.0/P3.1, LED on P3.4
#endif
#define P1_INPUTS                                                              \
  (PIN_BIT(PIN_KEY_A) | PIN_BIT(PIN_KEY_B) | PIN_BIT(PIN_KEY_C) |              \
   PIN_BIT(PIN_KEY_D) | PIN_BIT(PIN_KEY_E))
#define P3_INPUTS                                                              \
  (PIN_BIT(PIN_KEY_F) | PIN_BIT(PIN_KNOB_SW) | PIN_BIT(PIN_ENC_A) |            \
   PIN_BIT(PIN_ENC_B))

#endif
