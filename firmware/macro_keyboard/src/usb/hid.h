#ifndef __MK_HID_H__
#define __MK_HID_H__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void USBInit(void);

// Keyboard (interface 0)
uint8_t kb_busy(void);
uint8_t kb_send(__data uint8_t modifiers, __data uint8_t keycode);

// Vendor HID (interface 1)
uint8_t vendor_has_request(void);
uint8_t vendor_in_busy(void); // last response not yet collected by the host
__xdata uint8_t *vendor_request(void);  // 64 bytes received from the host
__xdata uint8_t *vendor_response(void); // 64 bytes to fill before vendor_send
uint8_t vendor_send(void); // send the response and accept the next request

#ifdef __cplusplus
} // extern "C"
#endif

#endif
