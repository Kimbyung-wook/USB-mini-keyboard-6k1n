#ifndef __MK_MACRO_H__
#define __MK_MACRO_H__

#include <stdint.h>

// Types slot texts using the macro syntax in docs/PROTOCOL.md.
// Non-blocking: call macro_task() from loop().

uint8_t macro_enqueue(__data uint8_t slot); // 0 when the slot is empty or the queue is full
uint8_t macro_busy(void);
void macro_task(void);

#endif
