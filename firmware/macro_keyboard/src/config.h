#ifndef __MK_CONFIG_H__
#define __MK_CONFIG_H__

// Firmware version reported by HELLO and the USB device descriptor
#define FW_MAJOR 1
#define FW_MINOR 1
#define FW_PATCH 0

// Build date reported by HELLO, passed in by tools/build_fw.ps1
// (-DFW_BUILD_YEAR=2026 ...). It stays 0 ("no date") in other builds such
// as the Arduino IDE: __DATE__ would go stale there, because an unchanged
// sketch is not recompiled.
#ifndef FW_BUILD_YEAR
#define FW_BUILD_YEAR 0
#endif
#ifndef FW_BUILD_MONTH
#define FW_BUILD_MONTH 0
#endif
#ifndef FW_BUILD_DAY
#define FW_BUILD_DAY 0
#endif
#ifndef FW_BUILD_HOUR
#define FW_BUILD_HOUR 0
#endif
#ifndef FW_BUILD_MINUTE
#define FW_BUILD_MINUTE 0
#endif

// USB identity (docs/PROTOCOL.md)
#define USB_VID 0x1209
#define USB_PID 0xC55D

// Slots (docs/PROTOCOL.md "슬롯 번호")
#define SLOT_COUNT 9
#define SLOT_KNOB_CW 6
#define SLOT_KNOB_CCW 7
#define SLOT_KNOB_PRESS 8

// Lock pattern (docs/PROTOCOL.md "잠금 패턴"): optional slot 9 of the blob,
// one byte per step holding the slot number of the input (0-8)
#define SLOT_LOCK 9
#define LOCK_MIN_STEPS 4
#define LOCK_MAX_STEPS 8
#define LOCK_MAX_FAILS 5          // then inputs are ignored until replugged
#define LOCK_INPUT_TIMEOUT_MS 3000 // a pause this long starts the pattern over
#define LOCK_WRONG_FLASH_MS 400    // LED goes dark this long after a wrong try

// Config blob lives in the 128-byte DataFlash
#define BLOB_CAPACITY 128
#define BLOB_HEADER_SIZE 8

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

#endif
