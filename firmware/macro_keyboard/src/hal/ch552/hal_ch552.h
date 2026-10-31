#ifndef __MK_HAL_CH552_H__
#define __MK_HAL_CH552_H__

// CH55x implementation of src/hal/hal.h on the CH55xDuino core. Include
// hal.h, not this file.

// clang-format off
#include <Arduino.h>
#include "usb/hid.h"
#include "usb/USBconstant.h"
// clang-format on

#define hal_ms() ((uint16_t)millis())

uint8_t hal_switches(void);
uint8_t hal_encoder(void);

extern __code uint8_t hal_palette[][3];
#if BOARD_KEY_LEDS
void hal_leds(uint8_t color, uint8_t mask, uint8_t maskColor);
#else
// One color for the whole chain: the mask is never used
void hal_leds_all(uint8_t color);
#define hal_leds(color, mask, maskColor) hal_leds_all(color)
#endif

// The core's DataFlash access
#define hal_store_read(addr) eeprom_read_byte(addr)
#define hal_store_write(addr, value) eeprom_write_byte(addr, value)

extern __xdata uint8_t keyboardLedStatus; // usb/hid.c, bit 1: Caps Lock
#define kb_caps_lock() (keyboardLedStatus & 0x02)

// Fixed buffers: indexing them is much shorter than going through a pointer
// clang-format off
extern __xdata __at (EP2_ADDR) uint8_t Ep2Buffer[];
extern __xdata __at (EP2_ADDR + 64) uint8_t Ep2InBuffer[];
// clang-format on
#define HAL_REQ Ep2Buffer
#define HAL_RES Ep2InBuffer

void hal_init(void);
uint8_t hal_boot_held(void);
#define hal_usb_start() USBInit()
void hal_enter_bootloader(void);
// The unique ID in ROM, the same bytes the bootloader shows
#define hal_chip_uid(i) (*(__code uint8_t *)(ROM_CHIP_ID_LO + (i)))

#endif
