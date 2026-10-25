// Host (gcc) stand-in for the CH55xduino Arduino.h, used by host_test only
#ifndef __HOST_ARDUINO_H__
#define __HOST_ARDUINO_H__

#include <stdint.h>

#define __xdata
#define __data
#define __code
#define __at(x)

uint32_t millis(void);
uint8_t eeprom_read_byte(uint8_t addr);
void eeprom_write_byte(uint8_t addr, uint8_t val);

#endif
