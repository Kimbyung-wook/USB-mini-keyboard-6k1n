#ifndef __MK_STORAGE_H__
#define __MK_STORAGE_H__

#include <stdint.h>

// Config blob (docs/PROTOCOL.md "설정 블롭 형식") kept in the 128-byte DataFlash,
// with a RAM copy used for typing.

void storage_init(void);

// Read raw blob bytes straight from DataFlash (for the READ command)
uint8_t storage_read_byte(__data uint8_t addr);

// Text of one slot in the RAM copy; length 0 when empty or the blob is invalid
__xdata uint8_t *storage_slot_text(__data uint8_t slot);
uint8_t storage_slot_len(__data uint8_t slot);

// Staging for WRITE/COMMIT. Return a protocol status code.
uint8_t storage_stage_write(__data uint16_t offset, __data uint8_t len,
                            __xdata uint8_t *data);
uint8_t storage_commit(__data uint16_t totalLen, __data uint16_t crc);

uint16_t crc16_ccitt(__xdata uint8_t *data, __data uint16_t len);

#endif
