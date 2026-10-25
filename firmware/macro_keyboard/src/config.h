#ifndef __MK_CONFIG_H__
#define __MK_CONFIG_H__

// Firmware version reported by HELLO
#define FW_MAJOR 1
#define FW_MINOR 0

// USB identity (docs/PROTOCOL.md)
#define USB_VID 0x1209
#define USB_PID 0xC55D

// Slots (docs/PROTOCOL.md "슬롯 번호")
#define SLOT_COUNT 9
#define SLOT_KNOB_CW 6
#define SLOT_KNOB_CCW 7
#define SLOT_KNOB_PRESS 8

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
