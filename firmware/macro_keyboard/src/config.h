#ifndef __MK_CONFIG_H__
#define __MK_CONFIG_H__

// Firmware version reported by HELLO and the USB device descriptor
#define FW_MAJOR 1
#define FW_MINOR 5
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

// Board file: chip, key/knob count, pins (docs/BOARD_INFO.md 6). Pick one
// with -DBOARD_xxx (tools/build_fw.ps1 -Board); a build without one, such as
// the Arduino IDE, gets the 6-key keyboard.
#define BOARD_INFO_VERSION 1 // HELLO byte 17
#define BOARD_FEATURE_RGB_LED 0x01
#define BOARD_FEATURE_LOCK 0x02
#define BOARD_FEATURE_AUTO_LOCK 0x08 // settings slot: auto-lock minutes (1.4.0)
// CH55xduino pin numbers are port * 10 + bit
#define PIN_PORT(p) ((p) / 10)
#define PIN_BIT(p) (1 << ((p) % 10))
#if defined(BOARD_MK6K1N)
#include "boards/mk6k1n.h"
#elif defined(BOARD_MK6K1NL)
#include "boards/mk6k1nl.h"
#else
#include "boards/mk6k1n.h"
#endif

// Slots (docs/BOARD_INFO.md 1): keys, then CW, CCW, PRESS of the knob
#if BOARD_KNOBS != 1
#error the sketch reads exactly one knob
#endif
#define SLOT_COUNT (BOARD_KEYS + 3 * BOARD_KNOBS)
#define SLOT_KNOB_CW BOARD_KEYS
#define SLOT_KNOB_CCW (BOARD_KEYS + 1)
#define SLOT_KNOB_PRESS (BOARD_KEYS + 2)
#if SLOT_COUNT > 63
#error too many slots (docs/BOARD_INFO.md 1)
#endif

// Lock pattern (docs/PROTOCOL.md "패턴 암호"): optional last slot of the
// blob, one byte per step holding the slot number of the input
#define SLOT_LOCK SLOT_COUNT
#define LOCK_MIN_STEPS 4
#define LOCK_MAX_STEPS 8
#define LOCK_MAX_FAILS 5          // then inputs are ignored until replugged
#define LOCK_HOLD_MS 2000          // knob hold that starts a pattern entry (3000 before 1.3.1)
// A pause this long cancels a pattern entry (unlock / re-lock)
#define LOCK_UNLOCK_TIMEOUT_MS 10000
#define LOCK_RELOCK_TIMEOUT_MS 10000

// Settings (docs/PROTOCOL.md "설정 슬롯"): optional slot after the lock slot.
// Byte 0 = auto-lock minutes: an open keyboard with a lock pattern locks
// after that long without input (0 or no settings slot = never).
#define SLOT_SETTINGS (SLOT_LOCK + 1)

// Config blob lives in the 128-byte DataFlash
#define BLOB_CAPACITY 128
#define BLOB_HEADER_SIZE 8

#endif
