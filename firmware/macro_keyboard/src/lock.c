// clang-format off
#include "hal/hal.h"
#include "lock.h"
#include "storage.h"
// clang-format on

// States and transitions: README.md "잠금 상태도"
// Internal RAM (__data): much shorter code than xdata under --model-large
static __data uint8_t state; // LOCK_OPEN
static __data uint8_t entered[LOCK_MAX_STEPS];
static __data uint8_t enteredLen;
static __data uint8_t unlockFails; // wrong unlock tries; LOCK_MAX_FAILS blocks
static __data uint8_t relockFails; // wrong re-lock tries; LOCK_MAX_FAILS locks
static __data uint16_t lastInputAt;
// Auto-lock: time open without input, in whole minutes and seconds counted
// from idleTickAt (8-bit counters, no multiply: 255 min at most)
static __data uint16_t idleTickAt;
static __data uint8_t idleSeconds;
static __data uint8_t idleMinutes;

void lock_activity(void) {
  idleSeconds = 0;
  idleMinutes = 0;
  idleTickAt = hal_ms();
}

void lock_init(void) {
  state = storage_lock_len() ? LOCK_LOCKED : LOCK_OPEN;
  enteredLen = 0;
  unlockFails = 0;
  relockFails = 0;
  lock_activity();
}

void lock_config_changed(void) {
  // Saving while open keeps it open (the owner is at the GUI); the new
  // pattern applies from the next plug-in. A config written while locked
  // replaced everything, so its own pattern decides. A pattern entry in
  // progress is dropped, since the pattern it checks against may have
  // changed.
  if (lock_locked()) {
    lock_init();
  } else {
    state = LOCK_OPEN;
    relockFails = 0;
  }
}

uint8_t lock_state(void) { return state; }

uint8_t lock_locked(void) { return state != LOCK_OPEN && state != LOCK_RELOCK; }

uint8_t lock_flags(void) {
  __data uint8_t flags = 0;
  if (storage_lock_len()) {
    flags |= LOCK_FLAG_SET;
  }
  if (lock_locked()) {
    flags |= LOCK_FLAG_LOCKED;
  }
  if (state == LOCK_BLOCKED) {
    flags |= LOCK_FLAG_BLOCKED;
  }
  return flags;
}

uint8_t lock_start_entry(void) {
  if (state == LOCK_LOCKED) {
    state = LOCK_UNLOCKING;
  } else if (state == LOCK_OPEN && storage_lock_len()) {
    state = LOCK_RELOCK;
  } else {
    return 0;
  }
  enteredLen = 0;
  lastInputAt = hal_ms();
  return 1;
}

uint8_t lock_entering(void) {
  return state == LOCK_UNLOCKING || state == LOCK_RELOCK;
}

static void lockNow(void) {
  state = LOCK_LOCKED;
  unlockFails = 0;
  relockFails = 0;
}

void lock_task(void) {
  __data uint16_t now = hal_ms();
  __data uint16_t idle = now - lastInputAt;
  __data uint8_t minutes = storage_autolock_minutes();

  // An entry left unfinished is cancelled without counting as a wrong try
  if (state == LOCK_UNLOCKING && idle >= LOCK_UNLOCK_TIMEOUT_MS) {
    state = LOCK_LOCKED;
  } else if (state == LOCK_RELOCK && idle >= LOCK_RELOCK_TIMEOUT_MS) {
    state = LOCK_OPEN;
  }

  // Auto-lock counts only while open with a pattern; anything else starts
  // the time over
  if (state != LOCK_OPEN || !minutes || !storage_lock_len()) {
    lock_activity();
    return;
  }
  while ((uint16_t)(now - idleTickAt) >= 1000) {
    idleTickAt += 1000;
    if (++idleSeconds == 60) {
      idleSeconds = 0;
      idleMinutes++;
    }
  }
  if (idleMinutes >= minutes) {
    lockNow();
  }
}

void lock_input(__data uint8_t slot) {
  __data uint8_t len = storage_lock_len();
  __xdata uint8_t *steps = storage_lock_steps();
  __data uint8_t match = 1;

  // Outside a pattern entry (started by holding the knob) inputs are ignored
  if (!lock_entering()) {
    return;
  }
  lastInputAt = hal_ms();
  entered[enteredLen++] = slot;
  if (enteredLen < len) {
    return;
  }

  // A full-length try: compare it all
  enteredLen = 0;
  for (__data uint8_t i = 0; i < len; i++) {
    if (entered[i] != steps[i]) {
      match = 0;
    }
  }
  if (state == LOCK_RELOCK) {
    // The right pattern locks; wrong ones go back to open, and the fifth
    // wrong one in a row locks anyway
    if (match || ++relockFails >= LOCK_MAX_FAILS) {
      lockNow();
    } else {
      state = LOCK_OPEN;
    }
    return;
  }
  if (match) {
    state = LOCK_OPEN;
    unlockFails = 0;
    relockFails = 0;
    return;
  }
  state = ++unlockFails >= LOCK_MAX_FAILS ? LOCK_BLOCKED : LOCK_LOCKED;
}
