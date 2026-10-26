// Host test driver for firmware/macro_keyboard/src/{storage,macro,lock}.c.
// Usage: host_test <blob.bin> [caps]
//        host_test <blob.bin> lock <inputs>...
//        host_test <blob.bin> tail <blob2.bin>
// Stages and commits the blob in 56-byte chunks, then types every slot and
// prints the key reports, e.g. "slot 0: 02:0b 00:08 D50 ...".
// "lock": each argument is a sequence of input numbers (0-8) entered on the
// keyboard, "H" for holding the knob (starts a pattern entry), "t" for
// waiting out the entry timeout and "w" for a 6 s pause;
// prints the lock state after each. "tail": commits blob2 over the blob and counts the
// DataFlash bytes past blob2 that are not blank.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "Arduino.h"
#include "../macro_keyboard/src/config.h"
#include "../macro_keyboard/src/lock.h"
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

static size_t readFile(const char *path, uint8_t *buf, size_t size) {
  FILE *f = fopen(path, "rb");
  size_t n;
  if (!f) {
    fprintf(stderr, "cannot open %s\n", path);
    exit(2);
  }
  n = fread(buf, 1, size, f);
  fclose(f);
  return n;
}

// WRITE in 56-byte chunks, then COMMIT; prints both statuses
static uint8_t writeBlob(uint8_t *blob, size_t n) {
  uint8_t st = ST_OK;
  for (size_t off = 0; off < n && st == ST_OK; off += PROTO_MAX_CHUNK) {
    uint8_t len = (uint8_t)((n - off) > PROTO_MAX_CHUNK ? PROTO_MAX_CHUNK : n - off);
    st = storage_stage_write((uint16_t)off, len, blob + off);
  }
  printf("write status %u\n", st);
  if (st == ST_OK) {
    st = storage_commit((uint16_t)n, blob[6] | (blob[7] << 8));
    printf("commit status %u\n", st);
  }
  return st;
}

static void runLock(int count, char **inputs) {
  static const char *names[] = {"open", "locked", "blocked", "unlocking", "relock"};
  lock_init();
  printf("lock %s flags %u\n", names[lock_state()], lock_flags());
  for (int i = 0; i < count; i++) {
    for (const char *s = inputs[i]; *s; s++) {
      now += 100;
      if (*s == 'H') {
        lock_start_entry(); // the knob was held for LOCK_HOLD_MS
      } else if (*s == 't') {
        now += LOCK_UNLOCK_TIMEOUT_MS;
        lock_task();
      } else if (*s == 'w') {
        now += 6000;
        lock_task();
      } else {
        lock_input((uint8_t)(*s - '0'));
      }
    }
    printf("lock %s flags %u\n", names[lock_state()], lock_flags());
  }
}

int main(int argc, char **argv) {
  static uint8_t blob[512];
  size_t n;

  if (argc < 2) {
    fprintf(stderr, "usage: host_test blob.bin [caps | lock <inputs>... | tail blob2.bin]\n");
    return 2;
  }
  n = readFile(argv[1], blob, sizeof(blob));
  if (argc > 2 && !strcmp(argv[2], "caps")) keyboardLedStatus = 0x02;

  memset(eeprom, 0xFF, sizeof(eeprom)); // blank DataFlash
  storage_init();
  printf("blank slot0 len %u\n", storage_slot_len(0));

  if (writeBlob(blob, n) != ST_OK) return 0;

  // Reload from "DataFlash" as after a power cycle
  storage_init();

  if (argc > 2 && !strcmp(argv[2], "lock")) {
    runLock(argc - 3, argv + 3);
    return 0;
  }
  if (argc > 3 && !strcmp(argv[2], "tail")) {
    static uint8_t blob2[512];
    size_t n2 = readFile(argv[3], blob2, sizeof(blob2));
    int dirty = 0;
    writeBlob(blob2, n2);
    for (size_t i = n2; i < sizeof(eeprom); i++) dirty += eeprom[i] != 0xFF;
    printf("tail dirty %d\n", dirty);
    return 0;
  }

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
