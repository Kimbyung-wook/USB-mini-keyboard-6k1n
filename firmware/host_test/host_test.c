// Host test driver for firmware/macro_keyboard/src/{storage,macro,lock,
// input,led}.c, built against the host HAL (stub/hal_host.h).
// Usage: host_test <blob.bin> [caps]
//        host_test <blob.bin> lock <inputs>...
//        host_test <blob.bin> tail <blob2.bin>
//        host_test <blob.bin> stall|reset <n>
//        host_test <blob.bin> input <steps>...
// Stages and commits the blob in 56-byte chunks, then types every slot and
// prints the key reports, e.g. "slot 0: 02:0b 00:08 D50 ...".
// "lock": each argument is a sequence of input numbers (0-8) entered on the
// keyboard, "H" for holding the knob (starts a pattern entry), "t" for
// waiting out the entry timeout, "w" for a 6 s pause and "m" for one minute
// without input (auto-lock);
// prints the lock state after each. "tail": commits blob2 over the blob and counts the
// DataFlash bytes past blob2 that are not blank.
// "stall": from the n-th report on the host collects nothing (KVM switched
// away without a reset); "reset": a bus reset after the n-th report. Each
// types slot 0 with a second slot 0 queued, then slot 0 again once the
// host is back.
// "input": runs the whole loop (input, lock, macro, LEDs) 1 ms at a time
// against fake switches and knob lines. Steps: "p<i>"/"r<i>" press/release
// switch i (keys, then the knob switch), "e<AB>" set the knob lines (e.g.
// e10), "w<ms>" wait; a first step "s<AB>" sets the lines at
// power-up. Each step prints one line: "<step>:" then the key reports and
// the LED frames sent, "L<color>.<mask>.<maskColor>" (only changes).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../macro_keyboard/src/hal/hal.h"
#include "../macro_keyboard/src/input.h"
#include "../macro_keyboard/src/led.h"
#include "../macro_keyboard/src/lock.h"
#include "../macro_keyboard/src/macro.h"
#include "../macro_keyboard/src/protocol.h"
#include "../macro_keyboard/src/storage.h"

static uint8_t eeprom[128];
static uint32_t now = 0;
static uint8_t keyboardLedStatus = 0;
static uint8_t switches = 0;    // bit i = switch i pressed
static uint8_t encoderLines = 3; // A << 1 | B, at rest both high
static int ledLast = -1;        // last LED frame printed

uint16_t hal_ms(void) { return (uint16_t)now; }
uint8_t hal_switches(void) { return switches; }
uint8_t hal_encoder(void) { return encoderLines; }
uint8_t kb_caps_lock(void) { return keyboardLedStatus & 0x02; }
void hal_leds(uint8_t color, uint8_t mask, uint8_t maskColor) {
  int frame = color << 16 | mask << 8 | maskColor;
  if (frame != ledLast) printf(" L%u.%02x.%u", color, mask, maskColor);
  ledLast = frame;
}

static int pressed = 0; // a key is down and must be released next
static int errors = 0;
static uint32_t lastSend = 0;

uint8_t hal_store_read(uint8_t addr) { return addr < 128 ? eeprom[addr] : 0; }
void hal_store_write(uint8_t addr, uint8_t val) {
  if (addr < 128) eeprom[addr] = val;
}

static int sends = 0;
static int stallAt = 0;  // > 0: reports from this one on are not collected
static int resetAt = 0;  // > 0: bus reset after this report
static uint8_t busy = 0;
static uint8_t ready = 1;

uint8_t kb_ready(void) { return ready; }
uint8_t kb_busy(void) { return busy; }
void kb_cancel(void) {
  printf(" cancel");
  busy = 0;
}
uint8_t kb_send(uint8_t modifiers, uint8_t keycode) {
  sends++;
  if (resetAt && sends == resetAt) ready = 0;
  if (stallAt && sends >= stallAt) {
    printf(" lost"); // never collected: the host does not see it
    busy = 1;
    return 1;
  }
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
      } else if (*s == 'm') {
        for (int sec = 0; sec < 60; sec++) {
          now += 1000;
          lock_task();
        }
      } else {
        lock_activity(); // as input_action() in src/input.c
        lock_input((uint8_t)(*s - '0'));
      }
    }
    printf("lock %s flags %u\n", names[lock_state()], lock_flags());
  }
}

// Runs the queued slots until playback ends (at most 10 s)
static void play(void) {
  uint32_t start = now;
  lastSend = now;
  while (macro_busy() && now - start < 10000) {
    macro_task();
    now++;
  }
  if (macro_busy()) { printf(" !still-busy"); errors++; }
}

static void runStall(int reset, int n) {
  if (reset) resetAt = n; else stallAt = n;
  printf("slot 0:");
  macro_enqueue(0);
  macro_enqueue(0);
  play();
  printf("\n");
  // The host is back
  stallAt = 0;
  resetAt = 0;
  busy = 0;
  ready = 1;
  pressed = 0;
  printf("slot 1:");
  macro_enqueue(0);
  play();
  if (pressed) { printf(" !left-pressed"); errors++; }
  printf("\n");
  printf("errors %d\n", errors);
}

// The firmware's loop() without USB, 1 ms per pass
static void runLoop(uint32_t ms) {
  for (uint32_t i = 0; i < ms; i++) {
    now++;
    now16 = hal_ms();
    input_task();
    lock_task();
    macro_task();
    led_task();
  }
}

static void runInput(int count, char **steps) {
  int first = 0;
  if (count > 0 && steps[0][0] == 's') {      // knob lines at power-up
    encoderLines = (uint8_t)strtol(steps[0] + 1, NULL, 2);
    first = 1;
  }
  lock_init();
  input_init();
  printf("start:");
  runLoop(1);
  printf("\n");
  for (int i = first; i < count; i++) {
    const char *s = steps[i];
    uint32_t wait = 1;
    printf("%s:", s);
    lastSend = now;
    if (s[0] == 'p') switches |= 1 << atoi(s + 1);
    else if (s[0] == 'r') switches &= ~(1 << atoi(s + 1));
    else if (s[0] == 'e') encoderLines = (uint8_t)strtol(s + 1, NULL, 2);
    else if (s[0] == 'w') wait = (uint32_t)atoi(s + 1);
    runLoop(wait);
    printf("\n");
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
  if (argc > 2 && !strcmp(argv[2], "input")) {
    runInput(argc - 3, argv + 3);
    return 0;
  }
  if (argc > 3 && (!strcmp(argv[2], "stall") || !strcmp(argv[2], "reset"))) {
    runStall(!strcmp(argv[2], "reset"), atoi(argv[3]));
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
