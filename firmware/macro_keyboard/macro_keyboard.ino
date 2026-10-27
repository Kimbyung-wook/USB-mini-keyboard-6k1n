/*
  macro_keyboard: firmware for the 6-key + 1-knob CH552G mini keyboard
  (board MK6K1N, src/boards/mk6k1n.h)

  - Interface 0: HID keyboard. Each key/knob action types the text of its
    slot (macro syntax in docs/PROTOCOL.md).
  - Interface 1: vendor HID for the config GUI (gui/), protocol v2.
  - Config is stored in the 128-byte DataFlash.
  - Lock (README.md "잠금 상태도"): with a lock pattern stored, it starts
    locked and ignores every input. Holding the knob for 2 s starts a
    pattern entry: the pattern unlocks it. On an open keyboard the same hold
    and pattern lock it again (five wrong re-lock tries lock it as well).
  - LED (WS2812 on P3.4): locked = dark with a short red blink every 3 s,
    pattern entry = solid red, blocked (five wrong unlock tries) = red
    blinking, open = blue, green for a moment on every key press (and while
    typing), white flash after saving, purple before jumping to the
    bootloader.
  - Bootloader: hold key D (ROM bootloader, P1.5) or hold the knob while
    plugging in, or send BOOT from the GUI.

  Board options: CH552 Board, 24 MHz (internal) 5V,
                 USB Settings: USER CODE w/ 266B USB ram,
                 Bootloader pin: P1.5 pull-down
  cli board options: usb_settings=user266,bootloader_pin=p15

  USB code in src/usb is adapted from the CH55xduino qmkCompatibleKeyboard
  example (LGPL-2.1).
*/

#ifndef USER_USB_RAM
#error "This sketch needs to be compiled with a USER USB setting"
#endif

#include <WS2812.h>
#include "src/config.h"
#include "src/protocol.h"
#include "src/storage.h"
#include "src/lock.h"
#include "src/macro.h"
#include "src/usb/hid.h"

// Switches: the keys (switch i types slot i), then the knob switch. Port and
// bit of each come from the board file.
#define NUM_KEYS (BOARD_KEYS + 1)
#define KNOB_KEY BOARD_KEYS // index of the knob switch
__code uint8_t keyBits[NUM_KEYS] = {BOARD_SWITCH_BITS};

#define DEBOUNCE_MS 20

__xdata uint8_t keyStable[NUM_KEYS];
__xdata uint8_t keyLast[NUM_KEYS];
__xdata uint16_t keyChangedAt[NUM_KEYS];

// Quadrature decoder: index = (prev << 2) | curr, value = step direction.
// On this board a clockwise turn counts negative (checked with test_pinmap).
__code int8_t encTable[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
// Small state in this file sits in indirect internal RAM (__idata): shorter
// code than xdata, and __data is already used by macro.c and lock.c
__idata uint8_t encPrev;
__idata int8_t encCount;

#define COLOR_OFF 0
#define COLOR_IDLE 1
#define COLOR_TYPING 2
#define COLOR_SAVED 3
#define COLOR_BOOT 4
#define COLOR_RED 5
#define SAVED_FLASH_MS 300
#define PRESS_FLASH_MS 200      // green at least this long after a key press
#define LOCKED_BLINK_PERIOD 3000 // locked: one short red blink per period
#define LOCKED_BLINK_MS 100
#define BLOCKED_BLINK_SHIFT 9   // blocked: blink period 2 x 512 ms
#define LED_REFRESH_MS 200

// Only one LED is visible, but which position in the chain it has is not
// known, so every color is sent to 8 positions (as test_pinmap did).
#define NUM_LEDS 8

__xdata uint8_t ledData[NUM_LEDS * 3];
__idata uint8_t ledColor; // COLOR_OFF
__idata uint16_t ledSentAt;
__idata uint8_t savedFlash;
__idata uint16_t savedAt;
__idata uint8_t pressFlash;
__idata uint16_t pressAt;
__idata uint16_t blinkAt; // start of the current locked blink period

// millis() read once per loop(): one 32-bit read instead of one per use
__data uint16_t now16;

// R, G, B per COLOR_* value
__code uint8_t colorRGB[][3] = {
    {0, 0, 0},    // COLOR_OFF
    {0, 0, 40},   // COLOR_IDLE
    {0, 40, 0},   // COLOR_TYPING
    {40, 40, 40}, // COLOR_SAVED
    {40, 0, 40},  // COLOR_BOOT
    {40, 0, 0},   // COLOR_RED
};

void fillLeds(uint8_t r, uint8_t g, uint8_t b) {
  // GRB order, walked with a pointer (set_pixel_for_GRB_LED multiplies i * 3)
  __xdata uint8_t *p = ledData;
  for (uint8_t i = 0; i < NUM_LEDS; i++) {
    *p++ = g;
    *p++ = r;
    *p++ = b;
  }
}

void showColor(uint8_t color) {
  // Resend periodically even without a change, so a frame lost at power-up
  // does not leave the LED dark
  if (color == ledColor && (uint16_t)(now16 - ledSentAt) < LED_REFRESH_MS) {
    return;
  }
  ledColor = color;
  fillLeds(colorRGB[color][0], colorRGB[color][1], colorRGB[color][2]);
  neopixel_show_P3_4(ledData, NUM_LEDS * 3);
  ledSentAt = now16;
}

void updateLed() {
  if (savedFlash) {
    if ((uint16_t)(now16 - savedAt) < SAVED_FLASH_MS) {
      showColor(COLOR_SAVED);
      return;
    }
    savedFlash = 0;
  }
  if (pressFlash && (uint16_t)(now16 - pressAt) >= PRESS_FLASH_MS) {
    pressFlash = 0;
  }
  if (lock_state() == LOCK_BLOCKED) {
    showColor((now16 >> BLOCKED_BLINK_SHIFT) & 1 ? COLOR_OFF : COLOR_RED);
  } else if (lock_entering()) {
    showColor(COLOR_RED);
  } else if (lock_state() == LOCK_LOCKED) {
    // 16-bit period counter instead of millis() % period (32-bit modulo)
    uint16_t sinceBlink = now16 - blinkAt;
    if (sinceBlink >= LOCKED_BLINK_PERIOD) {
      blinkAt += sinceBlink; // restart the period now, also after a long gap
      sinceBlink = 0;
    }
    showColor(sinceBlink < LOCKED_BLINK_MS ? COLOR_RED : COLOR_OFF);
  } else {
    showColor(macro_busy() || pressFlash ? COLOR_TYPING : COLOR_IDLE);
  }
}

void jumpToBootloader() {
  showColor(COLOR_BOOT);
  USB_CTRL = 0;
  EA = 0; // Disabling all interrupts is required.
  TMOD = 0;
  delayMicroseconds(50000);
  delayMicroseconds(50000);

  __asm__("lcall #0x3800"); // Jump to bootloader code

  while (1)
    ;
}

// A key or knob action: a pattern step during a pattern entry, typed when
// open, ignored when locked
void onInput(uint8_t slot) {
  lock_activity();
  if (lock_entering()) {
    lock_input(slot);
  } else if (lock_state() == LOCK_OPEN) {
    macro_enqueue(slot);
    pressFlash = 1; // green even for an empty slot
    pressAt = now16;
  }
}

// Knob switch. With a lock pattern stored, a press is typed on release so
// that holding it for LOCK_HOLD_MS can start a pattern entry instead.
__idata uint8_t knobHeld; // a press still waiting for release or the hold time
__idata uint16_t knobDownAt;

void knobDown() {
  if (lock_entering() || !storage_lock_len()) {
    onInput(SLOT_KNOB_PRESS);
    return;
  }
  knobHeld = 1;
  knobDownAt = now16;
}

void knobUp() {
  if (knobHeld) {
    knobHeld = 0;
    onInput(SLOT_KNOB_PRESS); // a short press: typed when open
  }
}

void checkKnobHold() {
  if (knobHeld && (uint16_t)(now16 - knobDownAt) >= LOCK_HOLD_MS) {
    knobHeld = 0;
    lock_start_entry();
  }
}

uint8_t readEncoder() {
  uint8_t p = P3; // A = P3.0, B = P3.1
  return ((p & 1) << 1) | ((p >> 1) & 1);
}

void scanKeys() {
  for (uint8_t i = 0; i < NUM_KEYS; i++) {
    uint8_t pressed = !((i < BOARD_P1_SWITCHES ? P1 : P3) & keyBits[i]);

    if (pressed != keyLast[i]) {
      keyLast[i] = pressed;
      keyChangedAt[i] = now16;
    } else if (pressed != keyStable[i] &&
               (uint16_t)(now16 - keyChangedAt[i]) >= DEBOUNCE_MS) {
      keyStable[i] = pressed;
      if (i == KNOB_KEY) {
        if (pressed) {
          knobDown();
        } else {
          knobUp();
        }
      } else if (pressed) {
        onInput(i);
      }
    }
  }
  checkKnobHold();
}

void scanEncoder() {
  uint8_t curr = readEncoder();

  if (curr == encPrev) {
    return;
  }
  encCount += encTable[(encPrev << 2) | curr];
  encPrev = curr;

  // One action per detent, when both lines are back at rest (high)
  if (curr == 3 && encCount != 0) {
    onInput(encCount < 0 ? SLOT_KNOB_CW : SLOT_KNOB_CCW);
    encCount = 0;
  }
}

void setup() {
  // Same registers as pinMode: inputs with pull-up are open drain + pull-up,
  // the LED pin push-pull output, driven low
  P1_MOD_OC |= P1_INPUTS;
  P1_DIR_PU |= P1_INPUTS;
  P3_MOD_OC = (P3_MOD_OC | P3_INPUTS) & ~PIN_BIT(PIN_LED);
  P3_DIR_PU |= P3_INPUTS | PIN_BIT(PIN_LED);
  P3 &= ~PIN_BIT(PIN_LED);

  // Holding the knob while plugging in enters the bootloader
  delay(20);
  if (!(P3 & PIN_BIT(PIN_KNOB_SW))) {
    jumpToBootloader();
  }

  storage_init();
  lock_init();
  encPrev = readEncoder();
  USBInit();
  now16 = (uint16_t)millis();
  updateLed();
}

void loop() {
  uint8_t event;

  now16 = (uint16_t)millis();
  event = protocol_poll();

  if (event == PROTO_EVT_BOOT) {
    // Give the host a moment to collect the OK response
    uint16_t start = (uint16_t)millis();
    while (vendor_in_busy() && (uint16_t)((uint16_t)millis() - start) < 100)
      ;
    jumpToBootloader();
  } else if (event == PROTO_EVT_SAVED) {
    savedFlash = 1;
    savedAt = now16;
  }

  scanEncoder();
  scanKeys();
  lock_task();
  macro_task();
  updateLed();
}
