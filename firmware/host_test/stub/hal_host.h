// Host (gcc) implementation of src/hal/hal.h for host_test: host_test.c
// provides the functions (a fake clock, switches, knob lines, LEDs,
// storage and keyboard).
#ifndef __HOST_HAL_H__
#define __HOST_HAL_H__

#include <stdint.h>

// SDCC memory spaces mean nothing on the host
#define __xdata
#define __data
#define __idata
#define __code
#define __at(x)

uint16_t hal_ms(void);

uint8_t hal_switches(void);
uint8_t hal_encoder(void);

extern uint8_t hal_palette[][3];
void hal_leds(uint8_t color, uint8_t mask, uint8_t maskColor);

uint8_t hal_store_read(uint8_t addr);
void hal_store_write(uint8_t addr, uint8_t value);

uint8_t kb_ready(void);
uint8_t kb_busy(void);
uint8_t kb_send(uint8_t modifiers, uint8_t keycode);
void kb_cancel(void);
uint8_t kb_caps_lock(void);

#endif
