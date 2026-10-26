// clang-format off
#include <Arduino.h>
#include "config.h"
#include "macro.h"
#include "storage.h"
#include "usb/hid.h"
// clang-format on

extern __xdata uint8_t keyboardLedStatus; // bit 1: Caps Lock

#define MOD_CTRL 0x01
#define MOD_SHIFT 0x02
#define MOD_ALT 0x04
#define MOD_WIN 0x08

#define SHIFT_FLAG 0x80

// US layout HID usage for ASCII 0x20..0x7E; SHIFT_FLAG = needs Shift
static __code uint8_t asciiMap[95] = {
    0x2c,              // ' '
    0x1e | SHIFT_FLAG, // !
    0x34 | SHIFT_FLAG, // "
    0x20 | SHIFT_FLAG, // #
    0x21 | SHIFT_FLAG, // $
    0x22 | SHIFT_FLAG, // %
    0x24 | SHIFT_FLAG, // &
    0x34,              // '
    0x26 | SHIFT_FLAG, // (
    0x27 | SHIFT_FLAG, // )
    0x25 | SHIFT_FLAG, // *
    0x2e | SHIFT_FLAG, // +
    0x36,              // ,
    0x2d,              // -
    0x37,              // .
    0x38,              // /
    0x27, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, // 0-9
    0x33 | SHIFT_FLAG, // :
    0x33,              // ;
    0x36 | SHIFT_FLAG, // <
    0x2e,              // =
    0x37 | SHIFT_FLAG, // >
    0x38 | SHIFT_FLAG, // ?
    0x1f | SHIFT_FLAG, // @
    // A-Z
    0x04 | SHIFT_FLAG, 0x05 | SHIFT_FLAG, 0x06 | SHIFT_FLAG, 0x07 | SHIFT_FLAG,
    0x08 | SHIFT_FLAG, 0x09 | SHIFT_FLAG, 0x0a | SHIFT_FLAG, 0x0b | SHIFT_FLAG,
    0x0c | SHIFT_FLAG, 0x0d | SHIFT_FLAG, 0x0e | SHIFT_FLAG, 0x0f | SHIFT_FLAG,
    0x10 | SHIFT_FLAG, 0x11 | SHIFT_FLAG, 0x12 | SHIFT_FLAG, 0x13 | SHIFT_FLAG,
    0x14 | SHIFT_FLAG, 0x15 | SHIFT_FLAG, 0x16 | SHIFT_FLAG, 0x17 | SHIFT_FLAG,
    0x18 | SHIFT_FLAG, 0x19 | SHIFT_FLAG, 0x1a | SHIFT_FLAG, 0x1b | SHIFT_FLAG,
    0x1c | SHIFT_FLAG, 0x1d | SHIFT_FLAG,
    0x2f,              // [
    0x31,              // backslash
    0x30,              // ]
    0x23 | SHIFT_FLAG, // ^
    0x2d | SHIFT_FLAG, // _
    0x35,              // `
    // a-z
    0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10,
    0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d,
    0x2f | SHIFT_FLAG, // {
    0x31 | SHIFT_FLAG, // |
    0x30 | SHIFT_FLAG, // }
    0x35 | SHIFT_FLAG, // ~
};

typedef struct {
  char name[6];
  uint8_t code;
} KeyName;

static __code KeyName keyNames[] = {
    {"ENTER", 0x28}, {"TAB", 0x2b},  {"ESC", 0x29},   {"BS", 0x2a},
    {"DEL", 0x4c},   {"SPACE", 0x2c}, {"UP", 0x52},    {"DOWN", 0x51},
    {"LEFT", 0x50},  {"RIGHT", 0x4f}, {"HOME", 0x4a},  {"END", 0x4d},
    {"PGUP", 0x4b},  {"PGDN", 0x4e},  {"INS", 0x49},   {"F1", 0x3a},
    {"F2", 0x3b},    {"F3", 0x3c},    {"F4", 0x3d},    {"F5", 0x3e},
    {"F6", 0x3f},    {"F7", 0x40},    {"F8", 0x41},    {"F9", 0x42},
    {"F10", 0x43},   {"F11", 0x44},   {"F12", 0x45},
};
#define KEY_NAME_COUNT (sizeof(keyNames) / sizeof(keyNames[0]))

static __code KeyName modNames[] = {
    {"CTRL", MOD_CTRL}, {"SHIFT", MOD_SHIFT}, {"ALT", MOD_ALT}, {"WIN", MOD_WIN},
};

#define QUEUE_SIZE 8 // power of two: positions wrap with & (QUEUE_SIZE - 1)
#if QUEUE_SIZE & (QUEUE_SIZE - 1)
#error QUEUE_SIZE must be a power of two
#endif
static __xdata uint8_t queue[QUEUE_SIZE];
static __xdata uint8_t queueHead;
static __xdata uint8_t queueCount;

// Current playback
static __xdata uint8_t active;
static __xdata uint8_t *text;
static __xdata uint8_t textLen;
static __xdata uint8_t pos;
static __xdata uint8_t needRelease;
static __xdata uint8_t delaying;
static __xdata uint16_t delayMs;
static __xdata uint32_t delayStart;

// Result of parsing one token
static __xdata uint8_t tokMods;
static __xdata uint8_t tokKey;
static __xdata uint16_t tokDelay;

#define TOK_NONE 0  // nothing to send (invalid token, skipped)
#define TOK_KEY 1   // tokMods + tokKey
#define TOK_DELAY 2 // tokDelay ms

static uint8_t upper(uint8_t c) {
  return (c >= 'a' && c <= 'z') ? c - 'a' + 'A' : c;
}

// Case-insensitive compare of text[start, end) with a NUL-terminated name
static uint8_t nameEquals(__data uint8_t start, __data uint8_t end,
                          __code const char *name) {
  __data uint8_t i = 0;
  while (start < end) {
    if (name[i] == 0 || upper(text[start]) != name[i]) {
      return 0;
    }
    start++;
    i++;
  }
  return name[i] == 0;
}

static uint8_t lookupKeyName(__data uint8_t start, __data uint8_t end) {
  for (__data uint8_t i = 0; i < KEY_NAME_COUNT; i++) {
    if (nameEquals(start, end, keyNames[i].name)) {
      return keyNames[i].code;
    }
  }
  return 0;
}

static uint8_t lookupModName(__data uint8_t start, __data uint8_t end) {
  for (__data uint8_t i = 0; i < 4; i++) {
    if (nameEquals(start, end, modNames[i].name)) {
      return modNames[i].code;
    }
  }
  return 0;
}

// A printable character as (modifiers, keycode); keycode 0 when unsupported
static void setChar(__data uint8_t c, uint8_t combo) {
  __data uint8_t m;
  tokMods = 0;
  tokKey = 0;
  if (c < 0x20 || c > 0x7e) {
    return;
  }
  m = asciiMap[c - 0x20];
  tokKey = m & ~SHIFT_FLAG;
  if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')) {
    if (combo) {
      return; // {CTRL+C} means Ctrl + the C key, without Shift
    }
    // With Caps Lock on, Shift gives lowercase: invert it for letters
    if (((m & SHIFT_FLAG) != 0) != ((keyboardLedStatus & 0x02) != 0)) {
      tokMods = MOD_SHIFT;
    }
    return;
  }
  if (m & SHIFT_FLAG) {
    tokMods = MOD_SHIFT;
  }
}

// Parse the content of {...} at text[start, end)
static uint8_t parseBraced(__data uint8_t start, __data uint8_t end) {
  __data uint8_t keyStart;
  __data uint8_t modsEnd;
  __data uint8_t mods = 0;

  // {DELAY:n}
  if (end - start > 6 && nameEquals(start, start + 6, "DELAY:")) {
    tokDelay = 0;
    for (__data uint8_t i = start + 6; i < end; i++) {
      if (text[i] < '0' || text[i] > '9') {
        return TOK_NONE;
      }
      // x10 as shifts: no 16-bit multiply library
      tokDelay = (tokDelay << 3) + (tokDelay << 1) + (text[i] - '0');
      if (tokDelay > 10000) {
        return TOK_NONE;
      }
    }
    return tokDelay ? TOK_DELAY : TOK_NONE;
  }

  // Split "MOD+MOD+key". "{CTRL++}" means Ctrl + the '+' character.
  if (end - start >= 3 && text[end - 1] == '+' && text[end - 2] == '+') {
    keyStart = end - 1;
    modsEnd = end - 2;
  } else {
    keyStart = start;
    modsEnd = start;
    for (__data uint8_t i = start; i < end; i++) {
      if (text[i] == '+') {
        modsEnd = i;
        keyStart = i + 1;
      }
    }
  }

  // Modifiers in text[start, modsEnd)
  {
    __data uint8_t segStart = start;
    for (__data uint8_t i = start; i <= modsEnd && modsEnd > start; i++) {
      if (i == modsEnd || text[i] == '+') {
        __data uint8_t m = lookupModName(segStart, i);
        if (m == 0) {
          return TOK_NONE;
        }
        mods |= m;
        segStart = i + 1;
      }
    }
  }

  // Final key in text[keyStart, end)
  if (keyStart >= end) {
    return TOK_NONE;
  }
  if (end - keyStart == 1) {
    setChar(text[keyStart], mods != 0);
  } else {
    tokMods = 0;
    tokKey = lookupKeyName(keyStart, end);
  }
  if (tokKey == 0) {
    return TOK_NONE;
  }
  tokMods |= mods;
  return TOK_KEY;
}

// Parse the next token at pos and advance past it
static uint8_t nextToken(void) {
  __data uint8_t c = text[pos];

  if (c == '{') {
    if (pos + 1 < textLen && text[pos + 1] == '{') {
      pos += 2;
      setChar('{', 0);
      return TOK_KEY;
    }
    for (__data uint8_t j = pos + 1; j < textLen; j++) {
      if (text[j] == '}') {
        __data uint8_t start = pos + 1;
        pos = j + 1;
        return parseBraced(start, j);
      }
    }
    pos = textLen; // unclosed brace: stop
    return TOK_NONE;
  }
  if (c == '}') {
    pos += (pos + 1 < textLen && text[pos + 1] == '}') ? 2 : 1;
    setChar('}', 0);
    return TOK_KEY;
  }
  pos++;
  if (c == '\n') {
    tokMods = 0;
    tokKey = 0x28; // Enter
    return TOK_KEY;
  }
  setChar(c, 0);
  return tokKey ? TOK_KEY : TOK_NONE;
}

uint8_t macro_enqueue(__data uint8_t slot) {
  if (storage_slot_len(slot) == 0 || queueCount >= QUEUE_SIZE) {
    return 0;
  }
  queue[(queueHead + queueCount) & (QUEUE_SIZE - 1)] = slot;
  queueCount++;
  return 1;
}

uint8_t macro_busy(void) { return active || queueCount; }

void macro_task(void) {
  if (!active) {
    __data uint8_t slot;
    if (queueCount == 0) {
      return;
    }
    slot = queue[queueHead];
    queueHead = (queueHead + 1) & (QUEUE_SIZE - 1);
    queueCount--;
    text = storage_slot_text(slot);
    textLen = storage_slot_len(slot);
    pos = 0;
    needRelease = 0;
    delaying = 0;
    active = textLen != 0;
    return;
  }

  if (delaying) {
    if (millis() - delayStart < delayMs) {
      return;
    }
    delaying = 0;
  }
  if (kb_busy()) {
    return;
  }
  if (needRelease) {
    kb_send(0, 0);
    needRelease = 0;
    return;
  }
  if (pos >= textLen) {
    active = 0;
    return;
  }

  switch (nextToken()) {
  case TOK_KEY:
    kb_send(tokMods, tokKey);
    needRelease = 1;
    break;
  case TOK_DELAY:
    delayMs = tokDelay;
    delayStart = millis();
    delaying = 1;
    break;
  default:
    break;
  }
}
