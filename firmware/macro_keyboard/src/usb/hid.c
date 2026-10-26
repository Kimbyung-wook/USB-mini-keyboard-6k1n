// Endpoint handling, adapted from the CH55xduino qmkCompatibleKeyboard example
// (LGPL-2.1)

// clang-format off
#include <stdint.h>
#include "include/ch5xx.h"
#include "include/ch5xx_usb.h"
#include "USBconstant.h"
#include "USBhandler.h"
#include "hid.h"
// clang-format on

// clang-format off
extern __xdata __at (EP1_ADDR) uint8_t Ep1Buffer[];
extern __xdata __at (EP2_ADDR) uint8_t Ep2Buffer[];
// clang-format on

void delayMicroseconds(uint16_t us);

__xdata uint8_t keyboardLedStatus;

volatile __xdata uint8_t UpPoint1_Busy;
volatile __xdata uint8_t UpPoint2_Busy;
volatile __xdata uint8_t vendorRequestPending;

void USBInit() {
  USBDeviceCfg();         // Device mode configuration
  USBDeviceEndPointCfg(); // Endpoint configuration
  USBDeviceIntCfg();      // Interrupt configuration
  UEP0_T_LEN = 0;
  UEP1_T_LEN = 0; // Pre-use send length must be cleared
  UEP2_T_LEN = 0;
}

void USB_EP1_IN() {
  UEP1_T_LEN = 0;
  UEP1_CTRL = UEP1_CTRL & ~MASK_UEP_T_RES | UEP_T_RES_NAK; // Default NAK
  UpPoint1_Busy = 0;
}

void USB_EP2_IN() {
  UEP2_T_LEN = 0;
  UEP2_CTRL = UEP2_CTRL & ~MASK_UEP_T_RES | UEP_T_RES_NAK; // Default NAK
  UpPoint2_Busy = 0;
}

void USB_EP1_OUT() {
  if (U_TOG_OK) { // Discard unsynchronized packets
    keyboardLedStatus = Ep1Buffer[0];
  }
}

void USB_EP2_OUT() {
  if (U_TOG_OK) { // Discard unsynchronized packets
    // NAK further requests until the main loop has answered this one, so the
    // OUT buffer is not overwritten while it is being processed
    UEP2_CTRL = UEP2_CTRL & ~MASK_UEP_R_RES | UEP_R_RES_NAK;
    vendorRequestPending = 1;
  }
}

static uint8_t waitIdle(volatile __xdata uint8_t *busy) {
  __data uint16_t waitWriteCount = 0;
  while (*busy) { // wait for 250ms or give up
    waitWriteCount++;
    delayMicroseconds(5);
    if (waitWriteCount >= 50000) {
      // The IN transfer never completed (e.g. bus reset while it was
      // queued). Drop it so later sends are not blocked forever.
      *busy = 0;
      return 0;
    }
  }
  return 1;
}

uint8_t kb_busy(void) { return UpPoint1_Busy; }

uint8_t kb_send(__data uint8_t modifiers, __data uint8_t keycode) {
  if (UsbConfig == 0) {
    return 0;
  }
  if (!waitIdle(&UpPoint1_Busy)) {
    return 0;
  }

  Ep1Buffer[64 + 0] = modifiers;
  Ep1Buffer[64 + 1] = 0;
  Ep1Buffer[64 + 2] = keycode;
  for (__data uint8_t i = 3; i < 8; i++) {
    Ep1Buffer[64 + i] = 0;
  }

  __data uint8_t usbIntCopy = USB_INT_EN;
  USB_INT_EN &= ~bUIE_TRANSFER; // Disable USB interrupts
  UEP1_T_LEN = KEYBOARD_EPSIZE;
  UpPoint1_Busy = 1;
  UEP1_CTRL = UEP1_CTRL & ~MASK_UEP_T_RES | UEP_T_RES_ACK; // upload data
  USB_INT_EN = usbIntCopy;
  return 1;
}

uint8_t vendor_has_request(void) { return vendorRequestPending; }

uint8_t vendor_in_busy(void) { return UpPoint2_Busy; }

uint8_t vendor_send(void) {
  __data uint8_t ok = 0;

  if (UsbConfig != 0 && waitIdle(&UpPoint2_Busy)) {
    __data uint8_t usbIntCopy = USB_INT_EN;
    USB_INT_EN &= ~bUIE_TRANSFER; // Disable USB interrupts
    UEP2_T_LEN = VENDOR_EPSIZE;
    UpPoint2_Busy = 1;
    UEP2_CTRL = UEP2_CTRL & ~MASK_UEP_T_RES | UEP_T_RES_ACK; // upload data
    USB_INT_EN = usbIntCopy;
    ok = 1;
  }

  // Accept the next request
  vendorRequestPending = 0;
  UEP2_CTRL = UEP2_CTRL & ~MASK_UEP_R_RES | UEP_R_RES_ACK;
  return ok;
}
