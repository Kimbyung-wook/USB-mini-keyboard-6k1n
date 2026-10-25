/*
  test_pinmap: hardware test for the 6-key + 1-knob CH552G mini keyboard

  - Key press     -> types the GPIO name of the pressed key, e.g. "P1.5"
  - Knob rotation -> types "CW" / "CCW" (encoder assumed on P3.0 / P3.1)
  - Knob press    -> types "P3.3" and cycles the LED test mode on P3.4:
                     OFF -> WS2812 -> GPIO blink -> OFF ...

  Board options: CH552 Board, 24 MHz (internal) 5V,
                 USB Settings: USER CODE w/ 148B USB ram
  cli board options: usb_settings=user148

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
#define LED_PIN 34

// Every free GPIO is watched, not only the expected key pins, so a wrong
// guess in the continuity map still shows up. P3.4 is watched only while
// the LED test is OFF (it is an output in the other modes).
#define NUM_INPUTS 8
__code uint8_t inputPins[NUM_INPUTS] = {11, 14, 15, 16, 17, 32, 33, 34};

#define DEBOUNCE_MS 20

__xdata uint8_t inputStable[NUM_INPUTS];
__xdata uint8_t inputLast[NUM_INPUTS];
__xdata uint16_t inputChangedAt[NUM_INPUTS];

// Quadrature decoder: index = (prev << 2) | curr, value = step direction
__code int8_t encTable[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
uint8_t encPrev;
int8_t encCount = 0;

#define LED_MODE_OFF 0
#define LED_MODE_WS2812 1
#define LED_MODE_GPIO 2
#define LED_STEP_MS 500

#define NUM_LEDS 8
#define NUM_BYTES (NUM_LEDS * 3)
__xdata uint8_t ledData[NUM_BYTES];
uint8_t ledMode = LED_MODE_OFF;
uint8_t ledStep = 0;
uint16_t ledStepAt = 0;

uint8_t readEncoder() {
  return (digitalRead(ENC_A_PIN) << 1) | digitalRead(ENC_B_PIN);
}

void typePinName(uint8_t pin) {
  Keyboard_write('P');
  Keyboard_write('0' + pin / 10);
  Keyboard_write('.');
  Keyboard_write('0' + pin % 10);
  Keyboard_write('\n');
}

void fillLeds(uint8_t r, uint8_t g, uint8_t b) {
  for (uint8_t i = 0; i < NUM_LEDS; i++) {
    set_pixel_for_GRB_LED(ledData, i, r, g, b);
  }
  neopixel_show_P3_4(ledData, NUM_BYTES);
}

void setLedMode(uint8_t mode) {
  // Leave WS2812 LEDs dark before releasing the data line
  if (ledMode == LED_MODE_WS2812) {
    fillLeds(0, 0, 0);
  }
  ledMode = mode;
  ledStep = 0;
  ledStepAt = (uint16_t)millis();

  if (mode == LED_MODE_OFF) {
    pinMode(LED_PIN, INPUT_PULLUP);
    Keyboard_print("LED: OFF\n");
  } else if (mode == LED_MODE_WS2812) {
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);
    Keyboard_print("LED: WS2812\n");
  } else {
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);
    Keyboard_print("LED: GPIO\n");
  }
}

void updateLeds() {
  uint8_t level;

  if (ledMode == LED_MODE_OFF) {
    return;
  }
  if ((uint16_t)((uint16_t)millis() - ledStepAt) < LED_STEP_MS) {
    return;
  }
  ledStepAt += LED_STEP_MS;

  if (ledMode == LED_MODE_WS2812) {
    // red -> green -> blue -> white, kept dim
    level = 40;
    if (ledStep == 0) {
      fillLeds(level, 0, 0);
    } else if (ledStep == 1) {
      fillLeds(0, level, 0);
    } else if (ledStep == 2) {
      fillLeds(0, 0, level);
    } else {
      fillLeds(level, level, level);
    }
    ledStep = (ledStep + 1) & 3;
  } else {
    ledStep ^= 1;
    digitalWrite(LED_PIN, ledStep);
  }
}

void scanInputs() {
  uint16_t now = (uint16_t)millis();

  for (uint8_t i = 0; i < NUM_INPUTS; i++) {
    uint8_t pin = inputPins[i];
    uint8_t pressed;

    if (pin == LED_PIN && ledMode != LED_MODE_OFF) {
      continue;
    }
    pressed = !digitalRead(pin);

    if (pressed != inputLast[i]) {
      inputLast[i] = pressed;
      inputChangedAt[i] = now;
    } else if (pressed != inputStable[i] &&
               (uint16_t)(now - inputChangedAt[i]) >= DEBOUNCE_MS) {
      inputStable[i] = pressed;
      if (pressed) {
        typePinName(pin);
        if (pin == KNOB_SW_PIN) {
          setLedMode(ledMode == LED_MODE_GPIO ? LED_MODE_OFF : ledMode + 1);
        }
      }
    }
  }
}

void scanEncoder() {
  uint8_t curr = readEncoder();

  if (curr == encPrev) {
    return;
  }
  encCount += encTable[(encPrev << 2) | curr];
  encPrev = curr;

  // Report once per detent, when both lines are back at rest (high)
  if (curr == 3 && encCount != 0) {
    if (encCount > 0) {
      Keyboard_print("CW\n");
    } else {
      Keyboard_print("CCW\n");
    }
    encCount = 0;
  }
}

void setup() {
  USBInit();

  for (uint8_t i = 0; i < NUM_INPUTS; i++) {
    pinMode(inputPins[i], INPUT_PULLUP);
    inputStable[i] = 0;
    inputLast[i] = 0;
    inputChangedAt[i] = 0;
  }
  pinMode(ENC_A_PIN, INPUT_PULLUP);
  pinMode(ENC_B_PIN, INPUT_PULLUP);
  encPrev = readEncoder();
}

void loop() {
  scanEncoder();
  scanInputs();
  updateLeds();
}
