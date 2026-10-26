#ifndef __MK_LOCK_H__
#define __MK_LOCK_H__

#include <stdint.h>

// Input lock: with a stored lock pattern the keyboard starts locked, types
// nothing and refuses READ/TEST/BOOT until the pattern is entered on the keys
// and the knob (docs/PROTOCOL.md "잠금 패턴").

#define LOCK_OPEN 0
#define LOCK_LOCKED 1
#define LOCK_BLOCKED 2 // too many wrong tries, until replugged

// HELLO flag bits
#define LOCK_FLAG_SET 0x01     // a lock pattern is stored
#define LOCK_FLAG_LOCKED 0x02  // inputs are locked right now
#define LOCK_FLAG_BLOCKED 0x04 // too many wrong tries

void lock_init(void);           // after storage_init()
void lock_config_changed(void); // after a successful COMMIT
uint8_t lock_state(void);
uint8_t lock_flags(void);
void lock_input(__data uint8_t slot); // a key/knob input while not open
uint8_t lock_wrong_flash(void);       // 1 shortly after a wrong try

#endif
