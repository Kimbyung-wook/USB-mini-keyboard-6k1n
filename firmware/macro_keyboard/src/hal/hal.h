#ifndef __MK_HAL_H__
#define __MK_HAL_H__

// Hardware abstraction layer (docs/BOARD_INFO.md 8). The keyboard's
// functions (src/*.c: storage, macro, lock, protocol, input, led) use only
// the names below; each chip family implements them in src/hal/<chip>/,
// picked by the board file. On CH55x most of them are macros, so the layer
// costs no code. host_test builds the same functions against
// firmware/host_test/stub/hal_host.h.
//
// Time
//   uint16_t hal_ms()                  milliseconds since start, wraps at 65536
// Inputs (from the board file's pins)
//   uint8_t hal_switches()             bit i = switch i pressed: the keys in
//                                      slot order, then the knob switch
//   uint8_t hal_encoder()              knob lines: A << 1 | B, 1 = high
// LEDs
//   hal_leds(color, mask, maskColor)   every LED in hal_palette[color], the
//                                      LEDs in mask (bit i = LED i) in
//                                      hal_palette[maskColor]; mask is used
//                                      only with BOARD_KEY_LEDS
//   hal_palette[][3]                   R, G, B per color, defined by led.c
// Config storage (BLOB_CAPACITY bytes that survive a power cycle)
//   uint8_t hal_store_read(addr), hal_store_write(addr, value)
// HID keyboard (interface 0)
//   uint8_t kb_ready()                 configured by a host
//   uint8_t kb_busy()                  last report not yet collected
//   uint8_t kb_send(mods, key)         queue one report
//   kb_cancel()                        withdraw a report that is not collected
//   uint8_t kb_caps_lock()             the host's Caps Lock is on
// Config channel (vendor HID, interface 1, docs/PROTOCOL.md)
//   uint8_t vendor_has_request()       HAL_REQ holds a request
//   uint8_t vendor_in_busy()           last response not yet collected
//   vendor_send()                      send HAL_RES, accept the next request
//   HAL_REQ[64], HAL_RES[64]           request and response buffers
// System
//   hal_init()                         pins; LEDs off
//   uint8_t hal_boot_held()            the knob is held at power-up
//   hal_usb_start()                    start USB (after hal_init)
//   hal_enter_bootloader()             leave for the ROM bootloader
//   uint8_t hal_chip_uid(i)            byte i (0-3) of the chip's unique ID

#include "../config.h"

#if defined(HAL_HOST)
#include "hal_host.h" // firmware/host_test/stub
#elif BOARD_HAL_CH55X
#include "ch552/hal_ch552.h"
#else
#error no HAL for this board (src/hal)
#endif

#endif
