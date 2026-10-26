// Adapted from the CH55xduino qmkCompatibleKeyboard example (LGPL-2.1)
#include "USBconstant.h"
#include "../config.h"

// Device descriptor
__code USB_Descriptor_Device_t DeviceDescriptor = {
    .Header = {.Size = sizeof(USB_Descriptor_Device_t), .Type = DTYPE_Device},

    .USBSpecification = VERSION_BCD(1, 1, 0),
    .Class = 0x00,
    .SubClass = 0x00,
    .Protocol = 0x00,

    .Endpoint0Size = DEFAULT_ENDP0_SIZE,

    .VendorID = USB_VID,
    .ProductID = USB_PID,
    .ReleaseNumber = VERSION_BCD(FW_MAJOR, FW_MINOR, FW_PATCH),

    .ManufacturerStrIndex = 1,
    .ProductStrIndex = 2,
    .SerialNumStrIndex = 3,

    .NumberOfConfigurations = 1};

__code USB_Descriptor_Configuration_t ConfigurationDescriptor = {
    .Config = {.Header = {.Size = sizeof(USB_Descriptor_Configuration_Header_t),
                          .Type = DTYPE_Configuration},

               .TotalConfigurationSize = sizeof(USB_Descriptor_Configuration_t),
               .TotalInterfaces = 2,

               .ConfigurationNumber = 1,
               .ConfigurationStrIndex = NO_DESCRIPTOR,

               .ConfigAttributes = (USB_CONFIG_ATTR_RESERVED),

               .MaxPowerConsumption = USB_CONFIG_POWER_MA(100)},

    .HID_Interface = {.Header = {.Size = sizeof(USB_Descriptor_Interface_t),
                                 .Type = DTYPE_Interface},

                      .InterfaceNumber = 0,
                      .AlternateSetting = 0x00,

                      .TotalEndpoints = 2,

                      .Class = HID_CSCP_HIDClass,
                      .SubClass = HID_CSCP_BootSubclass,
                      .Protocol = HID_CSCP_KeyboardBootProtocol,

                      .InterfaceStrIndex = NO_DESCRIPTOR},

    .HID_KeyboardHID = {.Header = {.Size = sizeof(USB_HID_Descriptor_HID_t),
                                   .Type = HID_DTYPE_HID},

                        .HIDSpec = VERSION_BCD(1, 1, 0),
                        .CountryCode = 0x00,
                        .TotalReportDescriptors = 1,
                        .HIDReportType = HID_DTYPE_Report,
                        .HIDReportLength = sizeof(KeyboardReportDescriptor)},

    .HID_ReportINEndpoint = {.Header = {.Size =
                                            sizeof(USB_Descriptor_Endpoint_t),
                                        .Type = DTYPE_Endpoint},

                             .EndpointAddress = KEYBOARD_EPADDR,
                             .Attributes =
                                 (EP_TYPE_INTERRUPT | ENDPOINT_ATTR_NO_SYNC |
                                  ENDPOINT_USAGE_DATA),
                             .EndpointSize = KEYBOARD_EPSIZE,
                             .PollingIntervalMS = 1},

    .HID_ReportOUTEndpoint = {.Header = {.Size =
                                             sizeof(USB_Descriptor_Endpoint_t),
                                         .Type = DTYPE_Endpoint},

                              .EndpointAddress = KEYBOARD_LED_EPADDR,
                              .Attributes =
                                  (EP_TYPE_INTERRUPT | ENDPOINT_ATTR_NO_SYNC |
                                   ENDPOINT_USAGE_DATA),
                              .EndpointSize = KEYBOARD_EPSIZE,
                              .PollingIntervalMS = 10},

    .HID_VendorInterface = {.Header = {.Size =
                                           sizeof(USB_Descriptor_Interface_t),
                                       .Type = DTYPE_Interface},

                            .InterfaceNumber = 1,
                            .AlternateSetting = 0x00,

                            .TotalEndpoints = 2,

                            .Class = HID_CSCP_HIDClass,
                            .SubClass = HID_CSCP_NonBootSubclass,
                            .Protocol = HID_CSCP_NonBootProtocol,

                            .InterfaceStrIndex = NO_DESCRIPTOR},

    .HID_VendorHID = {.Header = {.Size = sizeof(USB_HID_Descriptor_HID_t),
                                 .Type = HID_DTYPE_HID},

                      .HIDSpec = VERSION_BCD(1, 1, 0),
                      .CountryCode = 0x00,
                      .TotalReportDescriptors = 1,
                      .HIDReportType = HID_DTYPE_Report,
                      .HIDReportLength = sizeof(VendorReportDescriptor)},

    .HID_VendorINEndpoint = {.Header = {.Size =
                                            sizeof(USB_Descriptor_Endpoint_t),
                                        .Type = DTYPE_Endpoint},

                             .EndpointAddress = VENDOR_IN_EPADDR,
                             .Attributes =
                                 (EP_TYPE_INTERRUPT | ENDPOINT_ATTR_NO_SYNC |
                                  ENDPOINT_USAGE_DATA),
                             .EndpointSize = VENDOR_EPSIZE,
                             .PollingIntervalMS = 1},

    .HID_VendorOUTEndpoint = {.Header = {.Size =
                                             sizeof(USB_Descriptor_Endpoint_t),
                                         .Type = DTYPE_Endpoint},

                              .EndpointAddress = VENDOR_OUT_EPADDR,
                              .Attributes =
                                  (EP_TYPE_INTERRUPT | ENDPOINT_ATTR_NO_SYNC |
                                   ENDPOINT_USAGE_DATA),
                              .EndpointSize = VENDOR_EPSIZE,
                              .PollingIntervalMS = 1},
};

// Boot keyboard, no report ID: [modifiers, reserved, key1..key6]
__code uint8_t KeyboardReportDescriptor[] = {
    0x05, 0x01, // USAGE_PAGE (Generic Desktop)
    0x09, 0x06, // USAGE (Keyboard)
    0xa1, 0x01, // COLLECTION (Application)
    0x05, 0x07, //   USAGE_PAGE (Keyboard)
    0x19, 0xe0, //   USAGE_MINIMUM (Keyboard LeftControl)
    0x29, 0xe7, //   USAGE_MAXIMUM (Keyboard Right GUI)
    0x15, 0x00, //   LOGICAL_MINIMUM (0)
    0x25, 0x01, //   LOGICAL_MAXIMUM (1)
    0x95, 0x08, //   REPORT_COUNT (8)
    0x75, 0x01, //   REPORT_SIZE (1)
    0x81, 0x02, //   INPUT (Data,Var,Abs)
    0x95, 0x01, //   REPORT_COUNT (1)
    0x75, 0x08, //   REPORT_SIZE (8)
    0x81, 0x03, //   INPUT (Cnst,Var,Abs)
    0x95, 0x06, //   REPORT_COUNT (6)
    0x75, 0x08, //   REPORT_SIZE (8)
    0x15, 0x00, //   LOGICAL_MINIMUM (0)
    0x25, 0xff, //   LOGICAL_MAXIMUM (255)
    0x05, 0x07, //   USAGE_PAGE (Keyboard)
    0x19, 0x00, //   USAGE_MINIMUM (Reserved (no event indicated))
    0x29, 0xe7, //   USAGE_MAXIMUM (Keyboard Right GUI)
    0x81, 0x00, //   INPUT (Data,Ary,Abs)
    0x05, 0x08, //   USAGE_PAGE (LEDs)
    0x19, 0x01, //   USAGE_MINIMUM (Num Lock)
    0x29, 0x05, //   USAGE_MAXIMUM (Kana)
    0x15, 0x00, //   LOGICAL_MINIMUM (0)
    0x25, 0x01, //   LOGICAL_MAXIMUM (1)
    0x95, 0x05, //   REPORT_COUNT (5)
    0x75, 0x01, //   REPORT_SIZE (1)
    0x91, 0x02, //   OUTPUT (Data,Var,Abs)
    0x95, 0x01, //   REPORT_COUNT (1)
    0x75, 0x03, //   REPORT_SIZE (3)
    0x91, 0x03, //   OUTPUT (Cnst,Var,Abs)
    0xc0        // END_COLLECTION
};

// Vendor-defined 64-byte IN/OUT reports, no report ID (docs/PROTOCOL.md)
__code uint8_t VendorReportDescriptor[] = {
    0x06, 0x00, 0xFF, // USAGE_PAGE (Vendor Defined 0xFF00)
    0x09, 0x01,       // USAGE (0x01)
    0xa1, 0x01,       // COLLECTION (Application)
    0x09, 0x02,       //   USAGE (0x02)
    0x15, 0x00,       //   LOGICAL_MINIMUM (0)
    0x26, 0xff, 0x00, //   LOGICAL_MAXIMUM (255)
    0x75, 0x08,       //   REPORT_SIZE (8)
    0x95, 0x40,       //   REPORT_COUNT (64)
    0x81, 0x02,       //   INPUT (Data,Var,Abs)
    0x09, 0x03,       //   USAGE (0x03)
    0x15, 0x00,       //   LOGICAL_MINIMUM (0)
    0x26, 0xff, 0x00, //   LOGICAL_MAXIMUM (255)
    0x75, 0x08,       //   REPORT_SIZE (8)
    0x95, 0x40,       //   REPORT_COUNT (64)
    0x91, 0x02,       //   OUTPUT (Data,Var,Abs)
    0xc0              // END_COLLECTION
};

// String Descriptors
__code uint8_t LanguageDescriptor[] = {0x04, 0x03, 0x09,
                                       0x04}; // Language Descriptor
// A serial different from test_pinmap ("CH55x kbd") gives Windows a fresh
// device instance, so it does not reuse the single-interface driver setup.
__code uint16_t SerialDescriptor[] = {
    (((6 + 1) * 2) | (DTYPE_String << 8)), 'M', 'K', '6', 'K', '1', 'N',
};
__code uint16_t ProductDescriptor[] = {
    (((14 + 1) * 2) | (DTYPE_String << 8)),
    'M', 'i', 'n', 'i', ' ', 'M', 'a', 'c', 'r', 'o', ' ', 'K', 'b', 'd',
};
__code uint16_t ManufacturerDescriptor[] = {
    (((6 + 1) * 2) | (DTYPE_String << 8)), 'M', 'K', '6', 'K', '1', 'N',
};
