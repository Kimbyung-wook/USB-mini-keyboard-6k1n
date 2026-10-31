/*
  test_mk6k1nl: hardware test for the MK6K1NL keyboard (6 keys + 1 knob,
  CH552G, a WS2812 under every key; src/boards/mk6k1nl.h of macro_keyboard).
  test_pinmap is the test for MK6K1N.

  Every CH552G pin is already taken by the keys, the knob and P3.4, so the
  key LEDs are one chain on P3.4. This sketch shows how many LEDs there are
  and in which order, and types the pin of every key.

  - Knob press    -> next mode, typed as "MODE: ...":
                     WALK -> AUTO -> COLOR -> OFF -> RAW -> RAW+LED -> WALK ...
      WALK : one LED lit (white), the knob turns it to the next/previous
             position and types "LED n"
      AUTO : the lit position moves on by itself every second, typing
             "LED n"; each position gets the next color of red/green/blue
      COLOR: every position red -> green -> blue -> white, 0.5 s each
             (checks the color order of each LED)
      OFF  : all dark
      RAW  : all dark; types every change of the encoder lines as
             "AB xy" (x = A on P3.0, y = B on P3.1, 1 = high) and every key
             press and release ("P1.6", "P1.6 up"), to see whether a key
             disturbs the encoder
      RAW+LED: as RAW, and the pressed key's LED is green while held (does
             the LED current disturb the encoder?)
  - Key press     -> types the GPIO name of the key, e.g. "P1.5", as
                     test_pinmap does (checks that the key pins match)
  - Holding the knob while plugging in enters the bootloader

  Board options: CH552 Board, 24 MHz (internal) 5V,
                 USB Settings: USER CODE w/ 148B USB ram,
                 Bootloader pin: P1.5 pull-down
  cli board options: usb_settings=user148,bootloader_pin=p15

  USB files in src/userUsbHidKeyboard are copied from the CH55xduino
  HidKeyboard example (LGPL-2.1).
*/

#ifndef USER_USB_RAM
#error "This sketch needs to be compiled with a USER USB setting"
#endif

#include <WS2812.h>
#include "src/userUsbHidKeyboard/USBHIDKeyboard.h"

// CH55xduino pin numbers: port * 10 + bit (e.g. 15 = P1.5)
#define ENC_A_PIN 30
#define ENC_B_PIN 31
#define KNOB_SW_PIN 33

// Key pins of the first board, plus the knob switch (last)
#define NUM_INPUTS 7
__code uint8_t inputPins[NUM_INPUTS] = {11, 14, 15, 16, 17, 32, KNOB_SW_PIN};

#define DEBOUNCE_MS 20

__xdata uint8_t inputStable[NUM_INPUTS];
__xdata uint8_t inputLast[NUM_INPUTS];
__xdata uint16_t inputChangedAt[NUM_INPUTS];

// Quadrature decoder: index = (prev << 2) | curr, value = step direction.
// On the first board a clockwise turn counts negative.
__code int8_t encTable[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
uint8_t encPrev;
int8_t encCount = 0;

// More positions than any 6-key board should have: the last lit position
// that shows on the board is the length of the chain
#define MAX_LEDS 24
#define NUM_BYTES (MAX_LEDS * 3)
#define LEVEL 40 // kept dim: 24 x white stays well under USB current

__xdata uint8_t ledData[NUM_BYTES];

#define MODE_WALK 0
#define MODE_AUTO 1
#define MODE_COLOR 2
#define MODE_OFF 3
#define MODE_RAW 4
#define MODE_RAWLED 5
#define NUM_MODES 6
__code const char *modeNames[NUM_MODES] = {"WALK", "AUTO", "COLOR", "OFF", "RAW", "RAW+LED"};

#define AUTO_STEP_MS 1000
#define COLOR_STEP_MS 500

uint8_t mode = MODE_WALK;
uint8_t ledIndex = 0; // lit position in WALK / AUTO
uint8_t colorStep = 0;
uint16_t stepAt = 0;

void clearLeds() {
  for (uint8_t i = 0; i < NUM_BYTES; i++) {
    ledData[i] = 0;
  }
}

void showLeds() { neopixel_show_P3_4(ledData, NUM_BYTES); }

// Red, green, blue, white for step 0..3
void colorOf(uint8_t step, uint8_t *r, uint8_t *g, uint8_t *b) {
  *r = (step == 0 || step == 3) ? LEVEL : 0;
  *g = (step == 1 || step == 3) ? LEVEL : 0;
  *b = (step == 2 || step == 3) ? LEVEL : 0;
}

uint8_t readEncoder() {
  return (digitalRead(ENC_A_PIN) << 1) | digitalRead(ENC_B_PIN);
}

// "AB xy": the encoder lines, 1 = high (both high at rest)
void typeLines(uint8_t lines) {
  Keyboard_print("AB ");
  Keyboard_write('0' + (lines >> 1));
  Keyboard_write('0' + (lines & 1));
  Keyboard_write('\n');
}

void typeNumber(uint8_t n) {
  if (n >= 10) {
    Keyboard_write('0' + n / 10);
  }
  Keyboard_write('0' + n % 10);
}

void typePinName(uint8_t pin) {
  Keyboard_write('P');
  Keyboard_write('0' + pin / 10);
  Keyboard_write('.');
  Keyboard_write('0' + pin % 10);
  Keyboard_write('\n');
}

// One position lit: white in WALK, red/green/blue by position in AUTO
void showIndex() {
  uint8_t r, g, b;
  colorOf(mode == MODE_AUTO ? ledIndex % 3 : 3, &r, &g, &b);
  clearLeds();
  set_pixel_for_GRB_LED(ledData, ledIndex, r, g, b);
  showLeds();
  Keyboard_print("LED ");
  typeNumber(ledIndex);
  Keyboard_write('\n');
}

void showColor() {
  uint8_t r, g, b;
  colorOf(colorStep, &r, &g, &b);
  for (uint8_t i = 0; i < MAX_LEDS; i++) {
    set_pixel_for_GRB_LED(ledData, i, r, g, b);
  }
  showLeds();
}

void setMode(uint8_t m) {
  mode = m;
  ledIndex = 0;
  colorStep = 0;
  stepAt = (uint16_t)millis();
  Keyboard_print("MODE: ");
  Keyboard_print(modeNames[m]);
  Keyboard_write('\n');
  if (m == MODE_WALK || m == MODE_AUTO) {
    showIndex();
  } else if (m == MODE_COLOR) {
    showColor();
  } else {
    clearLeds();
    showLeds();
  }
  if (m >= MODE_RAW) {
    typeLines(readEncoder());
  }
}

void updateLeds() {
  uint16_t now = (uint16_t)millis();

  if (mode == MODE_AUTO && (uint16_t)(now - stepAt) >= AUTO_STEP_MS) {
    stepAt += AUTO_STEP_MS;
    ledIndex = ledIndex + 1 == MAX_LEDS ? 0 : ledIndex + 1;
    showIndex();
  } else if (mode == MODE_COLOR && (uint16_t)(now - stepAt) >= COLOR_STEP_MS) {
    stepAt += COLOR_STEP_MS;
    colorStep = (colorStep + 1) & 3;
    showColor();
  }
}

void scanEncoder() {
  uint8_t curr = readEncoder();

  if (curr == encPrev) {
    return;
  }
  if (mode >= MODE_RAW) {
    typeLines(curr);
  }
  encCount += encTable[(encPrev << 2) | curr];
  encPrev = curr;

  // One step per detent, when both lines are back at rest (high)
  if (curr == 3 && encCount != 0) {
    if (mode == MODE_WALK) {
      if (encCount < 0) { // clockwise: next position
        ledIndex = ledIndex + 1 == MAX_LEDS ? 0 : ledIndex + 1;
      } else {
        ledIndex = ledIndex == 0 ? MAX_LEDS - 1 : ledIndex - 1;
      }
      showIndex();
    }
    encCount = 0;
  }
}

void scanInputs() {
  uint16_t now = (uint16_t)millis();

  for (uint8_t i = 0; i < NUM_INPUTS; i++) {
    uint8_t pin = inputPins[i];
    uint8_t pressed = !digitalRead(pin);

    if (pressed != inputLast[i]) {
      inputLast[i] = pressed;
      inputChangedAt[i] = now;
    } else if (pressed != inputStable[i] &&
               (uint16_t)(now - inputChangedAt[i]) >= DEBOUNCE_MS) {
      inputStable[i] = pressed;
      if (mode >= MODE_RAW && pin != KNOB_SW_PIN) {
        if (mode == MODE_RAWLED) {
          clearLeds();
          if (pressed) {
            set_pixel_for_GRB_LED(ledData, i, 0, LEVEL, 0); // LED i = key i
          }
          showLeds();
        }
        Keyboard_write('P');
        Keyboard_write('0' + pin / 10);
        Keyboard_write('.');
        Keyboard_write('0' + pin % 10);
        Keyboard_print(pressed ? "\n" : " up\n");
        continue;
      }
      if (!pressed) {
        continue;
      }
      if (pin == KNOB_SW_PIN) {
        setMode(mode + 1 == NUM_MODES ? 0 : mode + 1);
      } else {
        typePinName(pin);
      }
    }
  }
}

void jumpToBootloader() {
  USB_CTRL = 0;
  EA = 0; // Disabling all interrupts is required.
  TMOD = 0;
  delayMicroseconds(50000);
  delayMicroseconds(50000);

  __asm__("lcall #0x3800"); // Jump to bootloader code

  while (1)
    ;
}

void setup() {
  for (uint8_t i = 0; i < NUM_INPUTS; i++) {
    pinMode(inputPins[i], INPUT_PULLUP);
  }
  pinMode(ENC_A_PIN, INPUT_PULLUP);
  pinMode(ENC_B_PIN, INPUT_PULLUP);
  pinMode(34, OUTPUT); // P3.4: LED data
  digitalWrite(34, LOW);

  // Holding the knob while plugging in enters the bootloader
  delay(20);
  if (!digitalRead(KNOB_SW_PIN)) {
    jumpToBootloader();
  }

  encPrev = readEncoder();
  clearLeds();
  showLeds();
  USBInit();

  // Give the host time to set up the keyboard before typing the first mode
  delay(1500);
  setMode(MODE_WALK);
}

void loop() {
  scanEncoder();
  scanInputs();
  updateLeds();
}
