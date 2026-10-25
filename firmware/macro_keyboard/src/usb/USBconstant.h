#ifndef __USB_CONST_DATA_H__
#define __USB_CONST_DATA_H__

// clang-format off
#include <stdint.h>
#include "include/ch5xx.h"
#include "include/ch5xx_usb.h"
#include "usbCommonDescriptors/StdDescriptors.h"
#include "usbCommonDescriptors/HIDClassCommon.h"
// clang-format on

// USB RAM layout ("USER CODE w/ 266B USB ram"):
// EP0 8 bytes, EP1 and EP2 each 64 bytes OUT + 64 bytes IN
#define EP0_ADDR 0
#define EP1_ADDR 10
#define EP2_ADDR 138

#define KEYBOARD_EPADDR 0x81
#define KEYBOARD_LED_EPADDR 0x01
#define KEYBOARD_EPSIZE 8
#define VENDOR_IN_EPADDR 0x82
#define VENDOR_OUT_EPADDR 0x02
#define VENDOR_EPSIZE 64

typedef struct {
  USB_Descriptor_Configuration_Header_t Config;

  // Interface 0: boot keyboard
  USB_Descriptor_Interface_t HID_Interface;
  USB_HID_Descriptor_HID_t HID_KeyboardHID;
  USB_Descriptor_Endpoint_t HID_ReportINEndpoint;
  USB_Descriptor_Endpoint_t HID_ReportOUTEndpoint;

  // Interface 1: vendor HID for configuration
  USB_Descriptor_Interface_t HID_VendorInterface;
  USB_HID_Descriptor_HID_t HID_VendorHID;
  USB_Descriptor_Endpoint_t HID_VendorINEndpoint;
  USB_Descriptor_Endpoint_t HID_VendorOUTEndpoint;
} USB_Descriptor_Configuration_t;

extern __code USB_Descriptor_Device_t DeviceDescriptor;
extern __code USB_Descriptor_Configuration_t ConfigurationDescriptor;
extern __code uint8_t KeyboardReportDescriptor[];
extern __code uint8_t VendorReportDescriptor[];
extern __code uint8_t LanguageDescriptor[];
extern __code uint16_t SerialDescriptor[];
extern __code uint16_t ProductDescriptor[];
extern __code uint16_t ManufacturerDescriptor[];

#endif
