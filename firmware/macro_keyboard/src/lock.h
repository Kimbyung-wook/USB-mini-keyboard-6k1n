#ifndef __MK_LOCK_H__
#define __MK_LOCK_H__

#include <stdint.h>

// Input lock: with a stored lock pattern the keyboard starts locked, types
// nothing and refuses READ/TEST/BOOT (docs/PROTOCOL.md "패턴 암호").
// Holding the knob for LOCK_HOLD_MS starts a pattern entry: on a locked
// keyboard the pattern unlocks it, on an open one the same pattern locks it
// again; five wrong re-lock tries lock it too. Outside an entry a locked
// keyboard ignores every input. States: README.md "잠금 상태도".

#define LOCK_OPEN 0
#define LOCK_LOCKED 1
#define LOCK_BLOCKED 2   // too many wrong tries, until replugged
#define LOCK_UNLOCKING 3 // locked, entering the pattern to unlock
#define LOCK_RELOCK 4    // open, entering the pattern to lock again

// HELLO flag bits
#define LOCK_FLAG_SET 0x01     // a lock pattern is stored
#define LOCK_FLAG_LOCKED 0x02  // inputs are locked right now
#define LOCK_FLAG_BLOCKED 0x04 // too many wrong tries

void lock_init(void);           // after storage_init()
void lock_config_changed(void); // after a successful COMMIT
uint8_t lock_state(void);
uint8_t lock_locked(void);      // locked, blocked or unlocking (RELOCK is still open)
uint8_t lock_flags(void);
uint8_t lock_start_entry(void); // knob held: 0 when there is nothing to enter
uint8_t lock_entering(void);    // UNLOCKING or RELOCK
void lock_task(void);           // from loop(): ends an entry left unfinished
void lock_input(__data uint8_t slot); // a key/knob input while not open

#endif
