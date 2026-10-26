// clang-format off
#include <Arduino.h>
#include "config.h"
#include "lock.h"
#include "storage.h"
// clang-format on

static __xdata uint8_t state = LOCK_OPEN;
static __xdata uint8_t entered[LOCK_MAX_STEPS];
static __xdata uint8_t enteredLen = 0;
static __xdata uint8_t fails = 0;
static __xdata uint16_t lastInputAt;
static __xdata uint8_t wrongFlash = 0;
static __xdata uint16_t wrongAt;

void lock_init(void) {
  state = storage_lock_len() ? LOCK_LOCKED : LOCK_OPEN;
  enteredLen = 0;
  fails = 0;
  wrongFlash = 0;
}

void lock_config_changed(void) {
  // Saving while open keeps it open (the owner is at the GUI); the new
  // pattern applies from the next plug-in. A config written while locked
  // replaced everything, so its own pattern decides.
  if (state != LOCK_OPEN) {
    lock_init();
  }
}

uint8_t lock_state(void) { return state; }

uint8_t lock_flags(void) {
  __data uint8_t flags = 0;
  if (storage_lock_len()) {
    flags |= LOCK_FLAG_SET;
  }
  if (state != LOCK_OPEN) {
    flags |= LOCK_FLAG_LOCKED;
  }
  if (state == LOCK_BLOCKED) {
    flags |= LOCK_FLAG_BLOCKED;
  }
  return flags;
}

void lock_input(__data uint8_t slot) {
  __data uint16_t now = (uint16_t)millis();
  __data uint8_t len = storage_lock_len();
  __xdata uint8_t *steps = storage_lock_steps();
  __data uint8_t match = 1;

  if (state != LOCK_LOCKED) {
    return;
  }
  if (enteredLen && (uint16_t)(now - lastInputAt) >= LOCK_INPUT_TIMEOUT_MS) {
    enteredLen = 0;
  }
  lastInputAt = now;
  entered[enteredLen++] = slot;
  if (enteredLen < len) {
    return;
  }

  // A full-length try: compare it all, then start over
  enteredLen = 0;
  for (__data uint8_t i = 0; i < len; i++) {
    if (entered[i] != steps[i]) {
      match = 0;
    }
  }
  if (match) {
    state = LOCK_OPEN;
    fails = 0;
    return;
  }
  wrongFlash = 1;
  wrongAt = now;
  if (++fails >= LOCK_MAX_FAILS) {
    state = LOCK_BLOCKED;
  }
}

uint8_t lock_wrong_flash(void) {
  if (wrongFlash &&
      (uint16_t)((uint16_t)millis() - wrongAt) >= LOCK_WRONG_FLASH_MS) {
    wrongFlash = 0;
  }
  return wrongFlash;
}
