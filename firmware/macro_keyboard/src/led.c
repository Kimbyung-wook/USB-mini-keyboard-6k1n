// clang-format off
#include "hal/hal.h"
#include "input.h"
#include "led.h"
#include "lock.h"
#include "macro.h"
// clang-format on

#define SAVED_FLASH_MS 300
#define PRESS_FLASH_MS 200       // green at least this long after a key press
#define LOCKED_BLINK_PERIOD 3000 // locked: one short red blink per period
#define LOCKED_BLINK_MS 100
#define BLOCKED_BLINK_SHIFT 9    // blocked: blink period 2 x 512 ms
#define LED_REFRESH_MS 200
#define ENTRY_DARK_MS 150        // key LEDs: dark after a pattern step

// R, G, B per COLOR_* value (hal.h)
__code uint8_t hal_palette[][3] = {
    {0, 0, 0},    // COLOR_OFF
    {0, 0, 40},   // COLOR_IDLE
    {0, 40, 0},   // COLOR_TYPING
    {40, 40, 40}, // COLOR_SAVED
    {40, 0, 40},  // COLOR_BOOT
    {40, 0, 0},   // COLOR_RED
};

static __idata uint8_t ledColor; // COLOR_OFF
static __idata uint16_t ledSentAt;
static __idata uint8_t savedFlash;
static __idata uint16_t savedAt;
static __idata uint8_t pressFlash;
static __idata uint16_t pressAt;
static __idata uint16_t blinkAt; // start of the current locked blink period

#if BOARD_KEY_LEDS
#if BOARD_KEYS > 8 || BOARD_LED_COUNT != BOARD_KEYS
#error key LEDs: one LED per key, at most 8
#endif
#define ALL_KEYS ((1 << BOARD_KEYS) - 1)
static __idata uint8_t greenKeys; // pressed during the current typing
static __idata uint8_t darkKeys;  // pressed in a pattern entry, dark for a moment
static __idata uint16_t darkAt;
static __idata uint8_t ledMask;   // LEDs shown in ledMaskColor instead of ledColor
static __idata uint8_t ledMaskColor;

// The key LED of an action; a knob action stands for all of them
#define KEY_LEDS_OF(slot) ((slot) < BOARD_KEYS ? 1 << (slot) : ALL_KEYS)

static void showLeds(uint8_t color, uint8_t mask, uint8_t maskColor) {
  // Resend periodically even without a change, so a frame lost at power-up
  // does not leave the LED dark
  if (color == ledColor && mask == ledMask && maskColor == ledMaskColor &&
      (uint16_t)(now16 - ledSentAt) < LED_REFRESH_MS) {
    return;
  }
  ledColor = color;
  ledMask = mask;
  ledMaskColor = maskColor;
  hal_leds(color, mask, maskColor);
  ledSentAt = now16;
}

static void showColor(uint8_t color) { showLeds(color, 0, COLOR_OFF); }

void led_entered(uint8_t slot) {
  darkKeys = KEY_LEDS_OF(slot);
  darkAt = now16;
}
#else
static void showColor(uint8_t color) {
  // Resend periodically even without a change, so a frame lost at power-up
  // does not leave the LED dark
  if (color == ledColor && (uint16_t)(now16 - ledSentAt) < LED_REFRESH_MS) {
    return;
  }
  ledColor = color;
  hal_leds(color, 0, COLOR_OFF);
  ledSentAt = now16;
}
#endif

void led_typed(uint8_t slot) {
  pressFlash = 1;
  pressAt = now16;
#if BOARD_KEY_LEDS
  greenKeys |= KEY_LEDS_OF(slot);
#else
  (void)slot;
#endif
}

void led_saved(void) {
  savedFlash = 1;
  savedAt = now16;
}

void led_boot(void) { hal_leds(COLOR_BOOT, 0, COLOR_OFF); }

void led_task(void) {
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
#if BOARD_KEY_LEDS
    // The key just entered goes dark for a moment (a knob step: all)
    if ((uint16_t)(now16 - darkAt) >= ENTRY_DARK_MS) {
      darkKeys = 0;
    }
    showLeds(COLOR_RED, darkKeys, COLOR_OFF);
#else
    showColor(COLOR_RED);
#endif
  } else if (lock_state() == LOCK_LOCKED) {
    // 16-bit period counter instead of now % period (32-bit modulo)
    uint16_t sinceBlink = now16 - blinkAt;
    if (sinceBlink >= LOCKED_BLINK_PERIOD) {
      blinkAt += sinceBlink; // restart the period now, also after a long gap
      sinceBlink = 0;
    }
    showColor(sinceBlink < LOCKED_BLINK_MS ? COLOR_RED : COLOR_OFF);
  } else if (macro_busy() || pressFlash) {
#if BOARD_KEY_LEDS
    showLeds(COLOR_IDLE, greenKeys, COLOR_TYPING);
#else
    showColor(COLOR_TYPING);
#endif
  } else {
#if BOARD_KEY_LEDS
    greenKeys = 0;
#endif
    showColor(COLOR_IDLE);
  }
}
