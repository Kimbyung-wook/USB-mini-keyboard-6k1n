// clang-format off
#include <Arduino.h>
#include "config.h"
#include "protocol.h"
#include "storage.h"
// clang-format on

// RAM copy of the stored blob, and the staging area filled by WRITE
static __xdata uint8_t blob[BLOB_CAPACITY];
static __xdata uint8_t stage[BLOB_CAPACITY];
static __xdata uint8_t stageLen = 0;

// Macro slots plus the lock pattern (SLOT_LOCK)
#define STORED_SLOTS (SLOT_COUNT + 1)
static __xdata uint8_t slotOffset[STORED_SLOTS];
static __xdata uint8_t slotLength[STORED_SLOTS];

uint16_t crc16_ccitt(__xdata uint8_t *data, __data uint16_t len) {
  // CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no xorout
  __data uint16_t crc = 0xFFFF;
  while (len--) {
    crc ^= (uint16_t)(*data++) << 8;
    for (__data uint8_t bit = 0; bit < 8; bit++) {
      if (crc & 0x8000) {
        crc = (crc << 1) ^ 0x1021;
      } else {
        crc <<= 1;
      }
    }
  }
  return crc;
}

// Check a blob and, with fill set, record the slot offsets/lengths.
// Returns 1 when valid.
static uint8_t parseBlob(__xdata uint8_t *b, __data uint16_t totalLen,
                         uint8_t fill) {
  __data uint16_t payloadLen;
  __data uint16_t pos;
  __data uint8_t count;

  if (totalLen < BLOB_HEADER_SIZE || totalLen > BLOB_CAPACITY) {
    return 0;
  }
  if (b[0] != 'M' || b[1] != 'K' || b[2] != 1) {
    return 0;
  }
  count = b[3];
  payloadLen = b[4] | ((uint16_t)b[5] << 8);
  if (BLOB_HEADER_SIZE + payloadLen != totalLen) {
    return 0;
  }
  if (crc16_ccitt(b + BLOB_HEADER_SIZE, payloadLen) !=
      (b[6] | ((uint16_t)b[7] << 8))) {
    return 0;
  }

  // Walk the slots: each is a uint16 length followed by its text
  pos = BLOB_HEADER_SIZE;
  for (__data uint8_t i = 0; i < count; i++) {
    __data uint16_t len;
    if (pos + 2 > totalLen) {
      return 0;
    }
    len = b[pos] | ((uint16_t)b[pos + 1] << 8);
    pos += 2;
    if (pos + len > totalLen) {
      return 0;
    }
    if (i == SLOT_LOCK) {
      // Empty (no lock) or LOCK_MIN_STEPS..LOCK_MAX_STEPS input numbers
      if (len != 0 && (len < LOCK_MIN_STEPS || len > LOCK_MAX_STEPS)) {
        return 0;
      }
      for (__data uint8_t j = 0; j < len; j++) {
        if (b[pos + j] >= SLOT_COUNT) {
          return 0;
        }
      }
    }
    if (fill && i < STORED_SLOTS) {
      slotOffset[i] = (uint8_t)pos;
      slotLength[i] = (uint8_t)len;
    }
    pos += len;
  }
  return pos == totalLen;
}

static void loadSlots(void) {
  __data uint16_t totalLen =
      BLOB_HEADER_SIZE + (blob[4] | ((uint16_t)blob[5] << 8));

  for (__data uint8_t i = 0; i < STORED_SLOTS; i++) {
    slotLength[i] = 0;
  }
  if (!parseBlob(blob, totalLen, 1)) {
    // Invalid or blank DataFlash (parsing may have filled some slots before
    // failing): every slot is empty and there is no lock
    for (__data uint8_t i = 0; i < STORED_SLOTS; i++) {
      slotLength[i] = 0;
    }
  }
}

void storage_init(void) {
  for (__data uint8_t i = 0; i < BLOB_CAPACITY; i++) {
    blob[i] = eeprom_read_byte(i);
  }
  loadSlots();
}

uint8_t storage_read_byte(__data uint8_t addr) { return eeprom_read_byte(addr); }

__xdata uint8_t *storage_slot_text(__data uint8_t slot) {
  return blob + slotOffset[slot];
}

uint8_t storage_slot_len(__data uint8_t slot) {
  if (slot >= SLOT_COUNT) {
    return 0;
  }
  return slotLength[slot];
}

uint8_t storage_lock_len(void) { return slotLength[SLOT_LOCK]; }

__xdata uint8_t *storage_lock_steps(void) { return blob + slotOffset[SLOT_LOCK]; }

uint8_t storage_stage_write(__data uint16_t offset, __data uint8_t len,
                            __xdata uint8_t *data) {
  if (len == 0 || len > PROTO_MAX_CHUNK) {
    return ST_BAD_ARG;
  }
  if (offset + len > BLOB_CAPACITY) {
    return ST_TOO_BIG;
  }
  // A transfer starts at offset 0 and continues without gaps
  if (offset == 0) {
    stageLen = 0;
  } else if (offset != stageLen) {
    return ST_BAD_ARG;
  }
  for (__data uint8_t i = 0; i < len; i++) {
    stage[offset + i] = data[i];
  }
  stageLen = offset + len;
  return ST_OK;
}

uint8_t storage_commit(__data uint16_t totalLen, __data uint16_t crc) {
  __data uint16_t payloadLen;

  if (totalLen > BLOB_CAPACITY) {
    return ST_TOO_BIG;
  }
  if (totalLen < BLOB_HEADER_SIZE || totalLen != stageLen) {
    return ST_BAD_ARG;
  }
  payloadLen = stage[4] | ((uint16_t)stage[5] << 8);
  if (BLOB_HEADER_SIZE + payloadLen != totalLen) {
    return ST_BAD_ARG;
  }
  if ((stage[6] | ((uint16_t)stage[7] << 8)) != crc ||
      crc16_ccitt(stage + BLOB_HEADER_SIZE, payloadLen) != crc) {
    return ST_BAD_CRC;
  }
  if (!parseBlob(stage, totalLen, 0)) {
    return ST_BAD_ARG;
  }

  // Program only the bytes that differ, to spare DataFlash write cycles
  // The rest is blanked so an old config can never be read back (READ
  // accepts any offset up to the capacity)
  for (__data uint8_t i = 0; i < BLOB_CAPACITY; i++) {
    __data uint8_t want = i < totalLen ? stage[i] : 0xFF;
    if (eeprom_read_byte(i) != want) {
      eeprom_write_byte(i, want);
    }
  }
  for (__data uint8_t i = 0; i < BLOB_CAPACITY; i++) {
    if (eeprom_read_byte(i) != (i < totalLen ? stage[i] : 0xFF)) {
      storage_init(); // keep using whatever is really stored
      return ST_FLASH_ERR;
    }
  }

  for (__data uint8_t i = 0; i < totalLen; i++) {
    blob[i] = stage[i];
  }
  stageLen = 0;
  loadSlots();
  return ST_OK;
}
