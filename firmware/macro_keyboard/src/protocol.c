// clang-format off
#include <Arduino.h>
#include "config.h"
#include "protocol.h"
#include "storage.h"
#include "lock.h"
#include "macro.h"
#include "usb/hid.h"
// clang-format on

#define U16(lo, hi) ((uint16_t)(lo) | ((uint16_t)(hi) << 8))

uint8_t protocol_poll(void) {
  __xdata uint8_t *req;
  __xdata uint8_t *res;
  __data uint8_t cmd;
  __data uint8_t status = ST_OK;
  __data uint8_t event = PROTO_EVT_NONE;

  // The response buffer is reused, so wait until the last one was collected
  if (!vendor_has_request() || vendor_in_busy()) {
    return PROTO_EVT_NONE;
  }
  req = vendor_request();
  res = vendor_response();
  cmd = req[0];

  for (__data uint8_t i = 0; i < 64; i++) {
    res[i] = 0;
  }
  res[0] = cmd | 0x80;
  res[1] = req[1]; // seq

  switch (cmd) {
  case CMD_HELLO:
    res[3] = PROTO_VERSION;
    res[4] = FW_MAJOR;
    res[5] = FW_MINOR;
    res[6] = SLOT_COUNT;
    res[7] = BLOB_CAPACITY & 0xFF;
    res[8] = BLOB_CAPACITY >> 8;
    res[9] = lock_flags();
    res[10] = FW_PATCH;
    res[11] = FW_BUILD_YEAR & 0xFF;
    res[12] = FW_BUILD_YEAR >> 8;
    res[13] = FW_BUILD_MONTH;
    res[14] = FW_BUILD_DAY;
    res[15] = FW_BUILD_HOUR;
    res[16] = FW_BUILD_MINUTE;
    break;

  case CMD_READ: {
    __data uint16_t offset = U16(req[2], req[3]);
    __data uint8_t len = req[4];
    if (lock_state() != LOCK_OPEN) {
      status = ST_LOCKED;
      break;
    }
    if (len == 0 || len > PROTO_MAX_CHUNK || offset + len > BLOB_CAPACITY) {
      status = ST_BAD_ARG;
      break;
    }
    res[3] = req[2];
    res[4] = req[3];
    res[5] = len;
    for (__data uint8_t i = 0; i < len; i++) {
      res[6 + i] = storage_read_byte(offset + i);
    }
    break;
  }

  // WRITE/COMMIT work while locked: a new config replaces everything
  // (the old one is blanked), so it gives nothing away and lets an owner
  // who forgot the pattern start over
  case CMD_WRITE:
    if (macro_busy()) {
      status = ST_BUSY;
    } else {
      status = storage_stage_write(U16(req[2], req[3]), req[4], req + 5);
    }
    break;

  case CMD_COMMIT:
    if (macro_busy()) {
      status = ST_BUSY;
    } else {
      status = storage_commit(U16(req[2], req[3]), U16(req[4], req[5]));
      if (status == ST_OK) {
        lock_config_changed();
        event = PROTO_EVT_SAVED;
      }
    }
    break;

  case CMD_TEST:
    if (lock_state() != LOCK_OPEN) {
      status = ST_LOCKED;
    } else if (req[2] >= SLOT_COUNT) {
      status = ST_BAD_ARG;
    } else if (macro_busy()) {
      status = ST_BUSY;
    } else {
      macro_enqueue(req[2]); // an empty slot simply types nothing
    }
    break;

  case CMD_BOOT:
    if (lock_state() != LOCK_OPEN) {
      status = ST_LOCKED;
    } else {
      event = PROTO_EVT_BOOT;
    }
    break;

  default:
    status = ST_BAD_CMD;
    break;
  }

  res[2] = status;
  vendor_send();
  return event;
}
