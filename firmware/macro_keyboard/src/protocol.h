#ifndef __MK_PROTOCOL_H__
#define __MK_PROTOCOL_H__

// Vendor HID protocol v1 (docs/PROTOCOL.md)

#define PROTO_VERSION 1
#define PROTO_MAX_CHUNK 56

#define CMD_HELLO 0x01
#define CMD_READ 0x02
#define CMD_WRITE 0x03
#define CMD_COMMIT 0x04
#define CMD_TEST 0x05
#define CMD_BOOT 0x06

#define ST_OK 0
#define ST_BAD_CMD 1
#define ST_BAD_ARG 2
#define ST_BAD_CRC 3
#define ST_TOO_BIG 4
#define ST_FLASH_ERR 5
#define ST_BUSY 6

#define PROTO_EVT_NONE 0
#define PROTO_EVT_BOOT 1  // host asked to jump to the bootloader
#define PROTO_EVT_SAVED 2 // a new config was committed

// Handle one pending request, if any; returns a PROTO_EVT_* value
uint8_t protocol_poll(void);

#endif
