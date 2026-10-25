// Host test driver for firmware/macro_keyboard/src/{storage,macro}.c.
// Usage: host_test <blob.bin> [capslock]
// Stages and commits the blob in 56-byte chunks, then types every slot and
// prints the key reports, e.g. "slot 0: 02:0b 00:08 D50 ...".
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "Arduino.h"
#include "../macro_keyboard/src/config.h"
#include "../macro_keyboard/src/macro.h"
#include "../macro_keyboard/src/protocol.h"
#include "../macro_keyboard/src/storage.h"

static uint8_t eeprom[128];
static uint32_t now = 0;
uint8_t keyboardLedStatus = 0;

static int pressed = 0; // a key is down and must be released next
static int errors = 0;
static uint32_t lastSend = 0;

uint32_t millis(void) { return now; }
uint8_t eeprom_read_byte(uint8_t addr) { return addr < 128 ? eeprom[addr] : 0; }
void eeprom_write_byte(uint8_t addr, uint8_t val) {
  if (addr < 128) eeprom[addr] = val;
}

uint8_t kb_busy(void) { return 0; }
uint8_t kb_send(uint8_t modifiers, uint8_t keycode) {
  // One loop iteration = 1 ms here; a long gap means a {DELAY:n} ran
  if (now - lastSend >= 10) printf(" D%u", (unsigned)(now - lastSend));
  lastSend = now;
  if (keycode == 0 && modifiers == 0) {
    if (!pressed) { printf(" !double-release"); errors++; }
    pressed = 0;
  } else {
    if (pressed) { printf(" !no-release"); errors++; }
    printf(" %02x:%02x", modifiers, keycode);
    pressed = 1;
  }
  return 1;
}

int main(int argc, char **argv) {
  static uint8_t blob[512];
  FILE *f;
  size_t n;
  uint8_t st = ST_OK;

  if (argc < 2 || !(f = fopen(argv[1], "rb"))) {
    fprintf(stderr, "usage: host_test blob.bin [capslock]\n");
    return 2;
  }
  n = fread(blob, 1, sizeof(blob), f);
  fclose(f);
  if (argc > 2) keyboardLedStatus = 0x02;

  memset(eeprom, 0xFF, sizeof(eeprom)); // blank DataFlash
  storage_init();
  printf("blank slot0 len %u\n", storage_slot_len(0));

  for (size_t off = 0; off < n && st == ST_OK; off += PROTO_MAX_CHUNK) {
    uint8_t len = (uint8_t)((n - off) > PROTO_MAX_CHUNK ? PROTO_MAX_CHUNK : n - off);
    st = storage_stage_write((uint16_t)off, len, blob + off);
  }
  printf("write status %u\n", st);
  if (st == ST_OK) {
    st = storage_commit((uint16_t)n, blob[6] | (blob[7] << 8));
    printf("commit status %u\n", st);
  }
  if (st != ST_OK) return 0;

  // Reload from "DataFlash" as after a power cycle
  storage_init();

  for (uint8_t slot = 0; slot < SLOT_COUNT; slot++) {
    printf("slot %u:", slot);
    if (!macro_enqueue(slot)) {
      printf(" (empty)\n");
      continue;
    }
    lastSend = now;
    while (macro_busy()) {
      macro_task();
      now++;
    }
    if (pressed) { printf(" !left-pressed"); errors++; }
    printf("\n");
  }
  printf("errors %d\n", errors);
  return 0;
}
