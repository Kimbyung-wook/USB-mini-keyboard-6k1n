#ifndef __MK_HID_H__
#define __MK_HID_H__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void USBInit(void);

// Keyboard (interface 0)
uint8_t kb_ready(void); // configured by a host
uint8_t kb_busy(void);  // last report not yet collected by the host
void kb_cancel(void);   // withdraw a report the host does not collect
uint8_t kb_send(__data uint8_t modifiers, __data uint8_t keycode);

// Vendor HID (interface 1)
uint8_t vendor_has_request(void);
uint8_t vendor_in_busy(void); // last response not yet collected by the host
uint8_t vendor_send(void); // send the response and accept the next request
// The request is Ep2Buffer (64 bytes received from the host) and the
// response Ep2InBuffer (64 bytes to fill before vendor_send), see USBhandler.c

#ifdef __cplusplus
} // extern "C"
#endif

#endif
