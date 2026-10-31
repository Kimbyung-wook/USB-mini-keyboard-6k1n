// Small replacement for the CH55xDuino core's main.c (0.0.26), which also
// carries UART0/UART1/INT0/INT1/touch-key interrupt handlers and with them
// HardwareSerial*ISR, WInterrupts and serial buffers this firmware never uses.
// The linker takes main() from here, so the core's main.c is left out.
//
// SDCC builds the interrupt vector table in the file that has main(), so every
// interrupt in use must be declared here: only USB and timer 0 (millis).
// If CH55xDuino is updated, compare with its cores/ch55xduino/main.c.

// clang-format off
#include <Arduino.h>
// clang-format on

void USBInterrupt(void); // usb/USBhandler.c

void DeviceUSBInterrupt(void) __interrupt(INT_NO_USB) { USBInterrupt(); }

// clang-format off
// millis() counter; wiring.c's timer 0 interrupt updates it as R0~R4 of
// register bank 1, so it must stay at these addresses (as in the core)
__idata __at (0x08) volatile uint32_t timer0_overflow_count = 0;
__idata __at (0x0C) volatile uint8_t timer0_overflow_count_5th_byte = 0;
// clang-format on

// In wiring.c, using register bank 1
void Timer0Interrupt(void) __interrupt(INT_NO_TMR0) __using(1);

void main(void) {
  init();
  setup();
  for (;;) {
    loop();
  }
}

unsigned char __sdcc_external_startup(void) __nonbanked { return 0; }
