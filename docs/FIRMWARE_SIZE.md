# 펌웨어 크기 줄이기 제안

- 대상: CH552G 매크로 키보드 펌웨어(`firmware/macro_keyboard`)의 플래시 사용량
- 이 문서는 **제안**과 진행 기록. 문서 작성 시 저장소 코드는 바꾸지 않았음
- 코드 위치는 2026-10-31 코드(펌웨어 1.6.0) 기준으로 확인함. 경로는 따로 적지 않으면 `firmware/macro_keyboard/` 아래

## 요약

- **현재 크기 (1.6.0)**: MK6K1N 8,694바이트, MK6K1NL 8,915바이트
- **분석 당시 크기 (v1.2.0)**: **11,585바이트 / 14,336바이트 (81%)**, RAM(xdata) 498바이트
  - 실제 빌드로 측정한 값
  - README의 11,587바이트와 2바이트 차이는 빌드 날짜 숫자 때문
- **시험 빌드 (제안 1~9 모두 적용)**: **7,585바이트(53%)**, 약 4,000바이트(35%) 감소
  - 컴파일·링크 성공, `host_test` 모두 통과
  - **실제 장치에는 올려 보지 않았음**
- 효과가 큰 순서
  1. 코어 `main.c`를 대신하는 작은 `main` 만들기 (−862)
  2. `digitalRead`/`pinMode`/`digitalWrite` 대신 포트를 직접 읽고 쓰기 (−662)
  3. USB 제어 요청 처리(EP0) 정리 (−576)
  4. 나눗셈·곱셈 라이브러리와 범용 포인터 없애기 (−468)
  5. 설정 통신 버퍼를 고정 주소로 다루기 (−394)
  6. 자주 쓰는 변수를 내부 RAM(`__data`)에 두기 (−347~−384)
- 컴파일러 옵션만으로는 거의 줄지 않음: `--opt-code-size` 0바이트, `--noinduction` −26~−38바이트

## 측정 방법

- **도구**: `tools/build_fw.ps1`과 같은 조건
  - arduino-cli, FQBN `CH55xDuino:mcs51:ch552:usb_settings=user266,bootloader_pin=p15`
  - 같은 방식의 `-DFW_BUILD_*` 플래그(`compiler.c.extra_flags` / `compiler.cpp.extra_flags`)
  - CH55xDuino 0.0.26, SDCC build 13407
- **빌드 위치**: 저장소의 `firmware/macro_keyboard/build`를 덮어쓰지 않도록 스케치를 임시 폴더에 복사하고 `--build-path`를 따로 지정함
- **함수별 크기**: SDCC의 `.rst` 목록 파일(주소·기계어가 함께 나오는 파일)에서 함수마다 바이트 수를 더함
- **모듈별 합계·라이브러리 크기**: `.map` 파일에서 확인
- **제안별 절감량**: **원래 코드에 그 제안 하나만 적용해서** 측정
  - 여러 개를 함께 적용하면 합계가 조금 달라짐
  - 예: 1번과 4번을 함께 해야만 빠지는 라이브러리가 있어 합치면 더 줄어듦

### 빌드 설정에서 알아 둘 점

- **`--model-large`**: CH55xDuino는 모든 코드를 이 모드로 컴파일함
  - **따로 지정하지 않은 전역 변수, 지역 변수, 함수 인자가 모두 외부 RAM(xdata)에 놓임**
  - 8051은 xdata 접근마다 `DPTR`에 주소를 넣고 `MOVX`를 써야 해서 코드가 길어짐
  - 이 펌웨어가 커진 가장 큰 이유
- **`__data` 영역**: 직접 주소 내부 RAM(0x00~0x7F), 128바이트뿐
  - 레지스터 뱅크와 기존 `__data` 변수 때문에 남은 자리는 약 47바이트
  - 넘치면 링크 오류: `Could not get N consecutive bytes in internal RAM for area DSEG`
  - 더 필요하면 `__idata`(0x80~0xFF, 스택과 같이 씀) 사용

## 현재 크기 내역 (v1.2.0 측정값)

- 분석 당시 코드 기준. 이후 `macro_keyboard.ino`의 키·노브·LED 코드는 `src/input.c`, `src/led.c`, `src/hal/ch552/hal_ch552.c`로 나뉘었음

### 모듈별

| 구분 | 모듈 | 바이트 | 비고 |
|---|---|---:|---|
| 우리 코드 | `macro.c` | 2,213 | 문자열 표 319바이트 포함 (`keyNames` 189, `asciiMap` 95, `modNames` 28, `"DELAY:"` 7) |
| 우리 코드 | `USBhandler.c` | 1,458 | `USB_EP0_SETUP` 하나가 1,032 |
| 우리 코드 | `macro_keyboard.ino` | 1,455 | |
| 우리 코드 | `storage.c` | 1,432 | |
| 우리 코드 | `protocol.c` | 1,006 | `protocol_poll` 한 함수 |
| 우리 코드 | `lock.c` | 547 | |
| 우리 코드 | `hid.c` | 351 | |
| 우리 코드 | `USBconstant.c` | 254 | USB 디스크립터(상수) |
| **우리 코드 합계** | | **8,716** | 75% |
| 코어 | `wiring_digital.c` | 540 | `pinMode` 183, `digitalWrite` 117, `digitalRead` 80, 핀 변환 표 160 |
| 코어 | `main.c` | 483 | 쓰지 않는 UART0/UART1/INT0/INT1/터치키 인터럽트 처리 402 포함 |
| 코어 | `wiring.c` | 478 | `millis` 61, `micros` 103, `delay` 177, `delayMicroseconds` 59, `init` 53, 타이머 인터럽트 25 |
| 코어 | `HardwareSerial0ISR.c` + `HardwareSerial1ISR.c` | 284 | 시리얼을 안 쓰는데 `main.c` 때문에 딸려 옴 |
| 코어 | `WInterrupts.c` | 120 | `attachInterrupt` 등, 역시 `main.c` 때문에 딸려 옴 |
| 코어 | `eeprom.c` | 70 | DataFlash 읽기/쓰기 (필요) |
| 라이브러리 | `WS2812` (P3.4) | 36 | 필요 |
| SDCC 계산 라이브러리 | `_modulong` | 194 | 32비트 나머지: `millis() % 3000` |
| SDCC 계산 라이브러리 | `_mulint` | 158 | 16비트 곱셈: `tokDelay * 10`, LED 위치 `i * 3` |
| SDCC 계산 라이브러리 | `_moduint` + `_modsint` | 237 | 16비트 나머지: `% QUEUE_SIZE`, 시리얼 인터럽트 |
| SDCC 계산 라이브러리 | `_gptrget` | 28 | 범용 포인터 읽기: `nameEquals(const char *name)` |
| 기타 | 시작 코드, 인터럽트 벡터, 변수 초기값 | 233 | |
| **전체** | | **11,585** | |

### 큰 함수 (상위 15개)

- 바이트는 v1.2.0 측정값. "현재 위치"는 1.6.0 코드에서 그 일을 하는 함수

| 함수 (당시) | 현재 위치 | 바이트 |
|---|---|---:|
| `USB_EP0_SETUP` | `src/hal/ch552/usb/USBhandler.c:33` | 1,032 |
| `protocol_poll` | `src/protocol.c:30` | 1,006 |
| `parseBraced` | `src/macro.c:180` | 589 |
| `parseBlob` | `parseStage`로 바뀜, `src/storage.c:40` | 534 |
| `storage_commit` | `src/storage.c:163` | 420 |
| `macro_task` | `src/macro.c:294` | 354 |
| `nextToken` | `src/macro.c:249` | 324 |
| `updateLed` | `led_task`로 바뀜, `src/led.c:99` | 249 |
| `scanKeys` | `scanSwitches` `src/input.c:68` + 포트 읽기 `hal_switches` `src/hal/ch552/hal_ch552.c:31` | 244 |
| `lock_input` | `src/lock.c:120` | 231 |
| `showColor` | `src/led.c:63`(키 LED 보드), `:70`(그 외) + 프레임 `hal_leds` `src/hal/ch552/hal_ch552.c:53` | 223 |
| `USBInterrupt` | `src/hal/ch552/usb/USBhandler.c:349` | 216 |
| `_modulong` (라이브러리) | 1단계 뒤 빠짐 | 194 |
| `pinMode` (코어) | 3단계 뒤 빠짐 (`wiring_digital.c`) | 183 |
| `delay` (코어) | 코어 `wiring.c` | 177 |

## 제안 (절감량 대비 위험이 낮은 순)

- **근거**: "측정" = 실제로 고쳐서 빌드한 값, "추정" = 빌드하지 않은 어림값
- **1.6.0 상태**: 코드에서 확인한 적용 여부

| 순위 | 제안 | 절감 | 근거 | 위험 | 작업량 | 1.6.0 상태 |
|---:|---|---:|---|---|---|---|
| 1 | 코어 `main.c` 대신 작은 `main` 사용 | −862 | 측정 | 중간-낮음 | 작음 | 적용 |
| 2 | 포트 직접 읽기/쓰기 | −662 | 측정 | 낮음 | 작음 | 적용 |
| 3 | 나눗셈·곱셈·범용 포인터 없애기 | −468 | 측정 | 낮음 | 작음 | 적용 |
| 4 | 설정 통신 버퍼를 고정 주소로 | −394 | 측정 | 낮음 | 아주 작음 | 적용 |
| 5 | 자주 쓰는 변수를 `__data`/`__idata`로 | −347~−384 | 측정 | 낮음 | 작음 | 적용 |
| 6 | USB EP0 처리 정리 | −576 | 측정 | 중간 | 중간 | 미적용 |
| 7 | 저장 코드 정리 | −142~−248 | 측정 | 낮음-중간 | 중간 | 적용 |
| 8 | `millis()`를 한 번만 읽기 + 색 표 | −114 | 측정 | 낮음 | 작음 | 적용 |
| 9 | 0 초기값 지우기, `--noinduction` | −17, −26~−38 | 측정 | 낮음 | 아주 작음 | 0 초기값만 적용 |
| 10 | 코어 `wiring.c` 대신 자체 1 ms 타이머 | −300~−400 | 추정 | 중간-높음 | 중간 | 미적용 |
| 11 | 기타 작은 것들 | 각 −14~−60 | 추정 | 낮음 | 작음 | 미적용 |

### 1. 코어 `main.c` 대신 작은 `main` 사용 (−862바이트, RAM −81바이트)

- **어디**: CH55xDuino 코어 `cores/ch55xduino/main.c`
  - USB·타이머 인터럽트 외에 UART0, UART1, INT0, INT1, 터치키 인터럽트 처리가 들어 있음
  - 그 때문에 `HardwareSerial0ISR`, `HardwareSerial1ISR`, `WInterrupts`, `weakOverrideGPIO/Timer2`가 함께 링크됨
  - 시리얼 수신/송신 버퍼 64바이트 등도 RAM 차지
  - 이 펌웨어는 그중 어느 것도 쓰지 않음
- **무엇을**: 스케치 안에 작은 `main` 파일을 두고 아래를 직접 정의함 (링커는 필요한 이름이 이미 있으면 코어 `main.c`를 가져오지 않음)
  - `main()` (`init(); setup(); for(;;) loop();`)
  - USB 인터럽트 함수 `DeviceUSBInterrupt` (`__interrupt(INT_NO_USB)`, 안에서 `USBInterrupt()` 호출)
  - 타이머0 인터럽트 선언 `void Timer0Interrupt(void) __interrupt(INT_NO_TMR0) __using(1);` (본체는 코어 `wiring.c`)
    - SDCC는 `main()`이 있는 파일에서 인터럽트 벡터 표를 만듦 → 쓰는 인터럽트는 이 파일에서 선언해야 함
  - `millis()`가 쓰는 `timer0_overflow_count`(`__idata __at(0x08)`, 4바이트)와 `timer0_overflow_count_5th_byte`(`__idata __at(0x0C)`): 코어와 같은 주소여야 함
  - `__sdcc_external_startup()` (0 반환)
- **현재 위치**: 적용됨 (4단계), `src/hal/ch552/main_min.c`
  - `DeviceUSBInterrupt` `:16`, `timer0_overflow_count*` `:21-22`, `Timer0Interrupt` 선언 `:26`, `main()` `:28-34`, `__sdcc_external_startup` `:36`
- **확인한 것**: 시험 빌드에서 벡터 표가 0x0B(타이머0)와 0x43(USB)에만 점프를 넣고 나머지는 `reti`로 채움
- **위험**
  - CH55xDuino 버전이 바뀌어 코어 `main.c`나 `init()` 동작이 바뀌면 이 파일도 맞춰야 함
  - 나중에 `Serial`이나 `attachInterrupt`를 쓰면 다시 코어 `main.c` 필요
  - 동작 자체(키 입력, USB, LED)는 바뀌지 않음
- **확인 방법**
  - 빌드 크기
  - `.map`에 `main.c.rel`과 `HardwareSerial*`이 없는지
  - 장치: USB 연결, 키 입력, `millis` 기반 동작(디바운스, 3초 길게 누르기, 잠금 시간 초과), BOOT 명령

### 2. 포트 직접 읽기/쓰기 (−662바이트)

- **어디 (당시 → 현재)**: 적용됨 (3단계)
  - `keyPins` 표 → `switchBits` `src/hal/ch552/hal_ch552.c:14` (값은 `BOARD_SWITCH_BITS`, `src/boards/ch552_6k1n.h:36-39`)
  - `readEncoder` → `hal_encoder` `src/hal/ch552/hal_ch552.c:43-46`
  - `scanKeys`의 `digitalRead` → `hal_switches` `src/hal/ch552/hal_ch552.c:31-41`
  - `setup`의 `pinMode`/`digitalWrite` → `hal_init` `src/hal/ch552/hal_ch552.c:16-24`
  - 노브 눌림 확인(부트로더) → `hal_boot_held` `src/hal/ch552/hal_ch552.c:26-29`
- **무엇을**: 핀 번호를 표에서 찾아 바꾸는 코어 함수 대신 포트 레지스터를 직접 씀
  - 키 A~E는 P1, 키 F와 노브 스위치·엔코더·LED는 P3
  - 키 읽기: `__code uint8_t keyMask[7] = {0x02, 0x80, 0x40, 0x20, 0x10, 0x04, 0x08};` 그리고 `pressed = !((i < 5 ? P1 : P3) & keyMask[i]);`
  - 엔코더: `p = P3; return ((p & 1) << 1) | ((p >> 1) & 1);` (P3.0 = A, P3.1 = B, 기존과 같은 비트 순서)
  - 설정: `P1_MOD_OC |= 0xF2; P1_DIR_PU |= 0xF2;`(풀업 입력), `P3_MOD_OC = (P3_MOD_OC | 0x0F) & ~0x10; P3_DIR_PU |= 0x1F; P3 &= ~0x10;`(P3.0~3.3 풀업 입력, P3.4 LED 출력 Low)
  - `setup()`의 `keyStable[i] = 0` 같은 초기화는 삭제 가능: 전역 변수는 시작할 때 0으로 지워짐
- **결과**: `wiring_digital.c` 전체(540바이트)가 빠지고 호출하는 쪽 코드도 짧아짐
- **위험**
  - 핀 배치를 잘못 옮기면 키가 바뀜
  - `PIN_*` 정의와 표를 함께 고치고, `PIN_*`에서 마스크를 만드는 매크로를 두면 실수가 줄어듦
    - 현재: `PIN_*`는 `src/boards/ch552_6k1n.h:22-31`(당시 `config.h`), 마스크 매크로 `PIN_BIT`는 `src/config.h:42`, 포트 검사 `#error`는 `src/boards/ch552_6k1n.h:43-50`
  - CH552 "풀업 입력"(quasi-bidirectional) 설정 값은 코어 `pinMode(INPUT_PULLUP)`과 같은 레지스터 조합
  - CH55xDuino의 `pinModeFast`/`digitalReadFast` 매크로(`wiring_digital_fast.h`)를 써도 됨
- **확인 방법**
  - 장치: 키 6개, 노브 누름, 노브 양방향 회전, LED 색, "노브를 누른 채 연결하면 부트로더"를 하나씩 확인
  - `firmware/test_pinmap`으로 핀 대응 재확인

### 3. 나눗셈·곱셈·범용 포인터 없애기 (−468바이트)

- 8051에는 16/32비트 곱셈·나눗셈 명령이 없음 → 이런 연산을 쓰면 SDCC가 라이브러리 함수를 붙임
- 모두 적용됨 (1단계)

| 당시 코드 | 바꿀 것 | 현재 위치 | 측정 절감 |
|---|---|---|---:|
| `% QUEUE_SIZE` (부호 있는 int 나머지) | `& (QUEUE_SIZE - 1)` (QUEUE_SIZE는 8) | `src/macro.c:287`, `:308` | −70 |
| `tokDelay * 10` | `(tokDelay << 3) + (tokDelay << 1)` | `src/macro.c:193` | −154 (아래와 합계) |
| `set_pixel_for_GRB_LED(ledData, i, ...)` (안에서 `i * 3`) | 포인터를 하나씩 올리며 G, R, B 저장 | `src/hal/ch552/hal_ch552.c:53-64`(키 LED 보드), `:66-74`(그 외) | (위와 합계) |
| `const char *name` (범용 포인터) | `__code const char *name` | `src/macro.c:123-124` (`nameEquals`) | −68 |
| `millis() % LOCKED_BLINK_PERIOD` (32비트 나머지) | 16비트 `blinkAt`: `now - blinkAt >= 3000`이면 새 주기, `now - blinkAt < 100`이면 빨강 | `src/led.c:122-129` | −176 |

- `_mulint`, `_modulong`, `_gptrget`이 빠짐
- `_modsint`/`_moduint`는 시리얼 인터럽트도 쓰고 있어 **1번과 함께 해야** 빠짐 (함께 하면 237바이트 더 줄어듦)
- **위험**: 낮음
  - 깜빡임은 여전히 3초마다 0.1초 (시작 위상만 달라짐)
  - 큐 크기를 2의 거듭제곱이 아닌 값으로 바꾸면 `&`가 틀림 → `QUEUE_SIZE` 옆에 주석이나 `#if` 검사
  - 현재: `src/macro.c:83-86`에 주석과 `#error` 검사 있음
- **확인 방법**
  - `host_test` (매크로 문법, `{DELAY:50}` 길이 검사 포함)
  - 장치: 잠금 상태 LED 깜빡임
  - `.map`에 `__mulint`/`__modulong`/`__gptrget`이 없는지

### 4. 설정 통신 버퍼를 고정 주소로 (−394바이트)

- **어디**: 당시 `src/protocol.c:14-25`
  - `req`/`res` 포인터가 지역 변수 → 레지스터에 담긴 포인터에 매번 오프셋을 더해서 씀 (`res[4] = ...` 한 줄에 약 11바이트)
- **무엇을**: 두 버퍼는 항상 `Ep2Buffer`(OUT)와 `Ep2Buffer + 64`(IN) → 고정 주소 배열로 선언해서 씀
  ```c
  extern __xdata __at (EP2_ADDR) uint8_t Ep2Buffer[];
  extern __xdata __at (EP2_ADDR + 64) uint8_t Ep2InBuffer[];
  #define req Ep2Buffer
  #define res Ep2InBuffer
  ```
  - `res[4] = FW_MAJOR`가 `mov dptr,#주소 / mov a,#값 / movx` 6바이트가 됨
  - `vendor_request()`/`vendor_response()`는 쓰지 않게 되므로 삭제 가능
  - 위 선언은 `hid.h`에 두는 편이 깔끔하다고 제안함
- **현재 위치**: 적용됨 (1단계)
  - 선언은 `hid.h` 대신 `src/hal/ch552/hal_ch552.h:36-40` (`HAL_REQ`/`HAL_RES`), 정의는 `src/hal/ch552/usb/USBhandler.c:15-16`
  - `src/protocol.c:11-12`에서 `#define req HAL_REQ`, `#define res HAL_RES`
  - `vendor_request()`/`vendor_response()`는 코드에 없음 (삭제됨)
- **위험**: 낮음. 버퍼 주소는 이미 `USBconstant.h`의 `EP2_ADDR`로 고정됨
- **확인 방법**: GUI로 HELLO(버전·빌드 날짜 표시), READ, WRITE/COMMIT(저장), TEST, BOOT를 한 번씩. 같은 seq 값이 돌아오는지
- **더 줄이기 (추정 −50~−100, 미적용)**: HELLO 응답 14바이트 중 `lock_flags()`를 뺀 나머지는 상수 → `__code` 표에서 반복문으로 복사
  - 현재 HELLO 처리: `src/protocol.c:53-74`. 응답이 보드 정보(`boardInfo`, 이미 `__code` 표 복사)와 칩 UID까지 늘어났고, 앞부분 `res[3]`~`res[16]`은 여전히 한 바이트씩 씀

### 5. 자주 쓰는 변수를 내부 RAM에 (−347바이트, 스케치 변수까지 −384)

- **어디 (당시 → 현재)**: 적용됨 (2단계)
  - `src/macro.c:88-105` → `src/macro.c:88-112` (`queue`, `queueHead`, `queueCount`, `active`, `text`, `textLen`, `pos`, `tokMods`, `tokKey`, `tokDelay` 등, 모두 `__data`)
  - `src/lock.c:9-14` → `src/lock.c:9-19` (`state`, `entered`, `enteredLen` 등, 모두 `__data`)
  - `macro_keyboard.ino`의 LED·노브 시간 변수 → `src/led.c:27-44`, `src/input.c:28-35` (모두 `__idata`)
- **무엇을**
  - `macro.c`의 `static __xdata` → `static __data`, `static __xdata uint8_t *text;` → `static __xdata uint8_t *__data text;` (가리키는 곳은 xdata, 포인터 자체는 내부 RAM): **−249**
  - `lock.c`의 `static __xdata` → `static __data`: **−98**
  - 스케치의 `ledColor`, `savedAt`, `pressAt`, `knobDownAt` 등 → `__data` 자리가 모자라 `__idata`로: **−37**
    - `__data`로 하면 −75지만, 위 두 개와 같이 하면 내부 RAM이 넘침
  - 후보지만 자리가 없으면 그대로 둠: `storage.c`의 `slotOffset`/`slotLength`(`src/storage.c:17-18`), `hid.c`의 바쁨 표시(`UpPoint1_Busy`, `src/hal/ch552/usb/hid.c:22`) — 현재도 `__xdata`
- **위험**: 낮음. 다만 내부 RAM 여유가 줄어듦
  - 시험 빌드(1~9 모두 적용)에서 스택에 쓸 수 있는 자리: 175바이트 → 121바이트
  - 이 펌웨어는 재귀나 큰 지역 배열이 없어 충분함
  - 앞으로 `__data` 변수를 늘리다 링크 오류(`area DSEG`)가 나면 `__idata`로 옮김
  - `host_test` 스텁에 `#define __idata` 필요: 당시 `stub/Arduino.h`에는 `__xdata`, `__data`, `__code`, `__at`만 있었음
    - 현재 스텁은 `firmware/host_test/stub/hal_host.h`, `__idata`도 있음(`:12`)
- **확인 방법**
  - 빌드 후 `.mem` 파일의 "Stack starts at ... with N bytes available"
  - `host_test`
  - 장치: 긴 매크로, 연속 입력(큐 8개)

### 6. USB EP0 처리 정리 (−576바이트)

- **어디 (현재, 미적용)**
  - `SetupLen`: `src/hal/ch552/usb/USBhandler.c:23` (지금은 `__data uint16_t`)
  - `USB_EP0_SETUP`: `src/hal/ch552/usb/USBhandler.c:33-312`
  - `USB_EP0_IN`: `src/hal/ch552/usb/USBhandler.c:314-338`
  - `USBInterrupt`의 분배: `src/hal/ch552/usb/USBhandler.c:349-484`
- **무엇을**
  - 셋업 패킷을 `UsbSetupBuf->필드` 대신 고정 주소 `Ep0Buffer[0..7]`로 읽기
  - CLEAR_FEATURE(`:151`) / SET_FEATURE(`:211`)를 하나로 합치고, 실제로 있는 엔드포인트(0x81, 0x01, 0x82, 0x02)만 처리
    - 지금은 쓰지 않는 EP3/EP4까지 16가지 경우가 있음
    - 장치 대상 기능(원격 깨우기)은 설정 디스크립터에 원격 깨우기 비트가 없으므로 항상 STALL이면 됨
    - 지금도 결과는 STALL이지만, 실행 중에 디스크립터를 읽어 확인하는 코드가 있음(`:157`, `:217`)
  - 디스크립터를 8바이트씩 보내는 반복문이 `SETUP`(`:120-132`)과 `IN`(`:317-325`)에 두 번 있음 → 함수 하나(`descrChunk`)로
  - `SetupLen`을 `uint16_t` → `uint8_t`
    - 가장 긴 디스크립터가 73바이트 → 호스트가 요청한 길이가 255를 넘으면 255로 잘라 두면 충분
  - `USBInterrupt`: 쓰지 않는 엔드포인트·SOF까지 20가지 경우를 나누는 `switch` 대신, 쓰는 7가지(EP0 SETUP/IN/OUT, EP1 IN/OUT, EP2 IN/OUT)만 비교. −111
- **측정**: EP0 부분만 −426, `USBInterrupt` −110, `SetupLen` 8비트 −40, 합계 −576
- **덤**: SET_FEATURE `case 0x01:`에 `break`가 없어 STALL을 설정한 뒤 요청을 실패로 응답함 → 정리하면서 바르게 됨
  - 현재도 그대로: `src/hal/ch552/usb/USBhandler.c:266-269`
- **위험**: 중간
  - USB 열거(장치 인식)가 깨지면 키보드도 GUI도 동작하지 않음
  - 복구는 됨: 키 D(P1.5)를 누른 채 연결하는 ROM 부트로더로 진입 가능
- **확인 방법**
  - Windows에서 장치 인식 (키보드 + Vendor HID 두 인터페이스)
  - `tools/usb_monitor.ps1`
  - Linux가 있다면 `lsusb -v`로 디스크립터 비교
  - 가능하면 USB-IF USBCV의 HID/Chapter 9 검사
  - 다른 PC·허브에서도 재연결 시험

### 7. 저장 코드 정리 (−142바이트, 고정 배열 방식까지 −248바이트)

- **어디 (당시 → 현재)**: 적용됨 (5단계)
  - `crc16_ccitt` → `src/storage.c:20`
  - `parseBlob` → `parseStage` `src/storage.c:40`
  - `loadSlots` → `loadStage` `src/storage.c:97` (부팅 때 읽기는 `storage_init` `:113-119`)
  - `storage_commit` → `src/storage.c:163-199`
- **무엇을 (1단계, −142)**
  - 포인터 인자를 `__data` 지역 포인터로 옮겨 쓰기 (`__xdata uint8_t *__data p = 인자;`)
  - 블롭이 최대 128바이트 → `pos`, `len`, `payloadLen`을 8비트로
    - 길이의 위 바이트가 0이 아니면 바로 실패 처리 (원래도 결국 실패하던 경우라 결과는 같음)
  - `storage_commit`의 "쓰기 반복문"과 "확인 반복문"을 하나로: 먼저 `stage[totalLen..127]`을 0xFF로 채우고, 다른 바이트만 쓰고 바로 확인
    - 현재: `src/storage.c:183-195`
- **무엇을 (2단계, 추가 −106)**
  - `parseBlob`이 포인터 대신 항상 고정 배열 `stage[]`를 읽게 함
  - 부팅 때도 DataFlash를 `stage[]`로 읽어 검사한 뒤 `blob[]`에 복사
  - 고정 배열 + 8비트 위치가 포인터보다 훨씬 짧음
- **동작 차이**: 쓰기 중 오류 시
  - 원래: 끝까지 다 쓰고 나서 실패를 알림
  - 바꾼 뒤: 첫 오류에서 멈춤
  - 어느 쪽이든 CRC가 맞지 않아 빈 설정으로 읽히므로 결과는 같음
- **위험**: 낮음-중간 (설정이 날아가면 안 되는 부분)
  - `host_test`가 잘 덮고 있음: 128바이트 블롭, 129바이트 거부, CRC 오류, 잘못된 잠금 패턴, 뒷부분 지우기
- **확인 방법**
  - `host_test` 전체 통과 (시험 빌드에서 확인함)
  - 장치: 저장 → 다시 연결 → READ로 같은 내용이 오는지

### 8. `millis()`를 한 번만 읽기 + 색 표 (−114바이트)

- **어디 (당시 → 현재)**: 적용됨 (5단계)
  - `showColor`, `updateLed` → `src/led.c:63`/`:70`, `led_task` `src/led.c:99`
  - `scanKeys` → `scanSwitches` `src/input.c:68`
- **무엇을**
  - `loop()` 처음에 `now16 = (uint16_t)millis();`를 한 번 저장(`__data`)하고, LED·키 검사는 이 값을 씀
    - 현재: 변수 `src/input.c:11`, 저장 `macro_keyboard.ino:66` (`now16 = hal_ms();`, `setup()`은 `:59`), `hal_ms()`는 `src/hal/ch552/hal_ch552.h:13`
  - `showColor`의 if-else 6개 → `__code uint8_t colorRGB[6][3]` 표
    - 현재: `hal_palette` `src/led.c:18-25`
- **주의**: `scanKeys` 안에서 `uint16_t now = now16;`처럼 지역 변수로 받으면 large 모델 때문에 오히려 커짐 (측정: −6바이트에 그침). 전역 `now16`을 직접 써야 −114
- **위험**: 낮음. 한 번의 `loop()` 동안 시간이 고정될 뿐
- **확인 방법**: LED 색 전환(파랑/초록/흰색/보라/빨강), 디바운스, 3초 길게 누르기

### 9. 아주 작은 것들 (측정)

- **0 초기값 지우기 (−17)**: 적용됨 (1단계)
  - 대상 예: `uint8_t ledColor = COLOR_OFF;`, `static __xdata uint8_t queueHead = 0;`, `volatile __xdata uint8_t UpPoint1_Busy = 0;`
  - 이유: 전역 변수는 시작할 때 어차피 0으로 지워지는데, 초기값을 쓰면 그 값을 플래시에 따로 저장하고 복사함
  - 현재: `src/led.c:27`, `src/macro.c:89`, `src/hal/ch552/usb/hid.c:22` 모두 초기값 없음
- **`--noinduction` (원래 코드에서 −26, 1~8 적용 후 −38)**: 미적용 (`tools/build_fw.ps1:58-59`의 `$flags`에 없음)
  - `tools/build_fw.ps1`의 `$flags`에 추가
  - 반복문 안의 곱셈을 덧셈으로 바꾸는 최적화를 끔 (이 코드에서는 그 최적화가 xdata 변수를 늘려 오히려 손해)
  - RAM은 1~3바이트 늘어남
  - 코어도 같은 옵션으로 다시 컴파일됨
  - 동작은 바뀌지 않지만, 옵션을 바꾼 뒤에는 장치 시험을 한 번 해 둠

### 10. 코어 `wiring.c` 대신 자체 1 ms 타이머 (추정 −300~−400바이트)

- **어디**: 코어 `wiring.c`(478바이트). `millis()` 하나 때문에 `micros`, `delay`, `delayMicroseconds`, `init`까지 한 모듈이 통째로 들어옴
- **무엇을** (미적용)
  - 1번의 `main_min.c`(`src/hal/ch552/main_min.c:29`)에서 `init()`을 부르지 않고 직접 클록(24 MHz, `SAFE_MOD`/`CLOCK_CFG`)과 타이머0을 설정
  - 타이머 인터럽트에서 16비트 밀리초 카운터만 올림 (지금 펌웨어는 시간을 모두 16비트로만 비교함)
  - `delayMicroseconds`/`delay`를 쓰는 곳을 밀리초 카운터나 짧은 반복문으로 바꿈
    - `waitIdle`의 250 ms 제한: `src/hal/ch552/usb/hid.c:62-75` (`delayMicroseconds(5)` × 50000)
    - 부트로더 점프 전 100 ms: `hal_enter_bootloader` `src/hal/ch552/hal_ch552.c:86-87` (당시 `jumpToBootloader`)
    - `setup`의 `delay(20)`: `hal_boot_held` `src/hal/ch552/hal_ch552.c:27`
    - `init`의 RC 안정화 5 ms (코어 `wiring.c`)
- **위험**: 중간-높음
  - 클록 설정을 잘못하면 USB가 동작하지 않음
  - 부트로더 점프는 인터럽트를 끈 뒤 기다리므로 타이머를 쓸 수 없음 → 반복문 시간을 직접 맞춰야 함
  - 1~9를 하고도 공간이 더 필요할 때만 권함
- **확인 방법**
  - 오실로스코프나 로직 분석기 없이: `{DELAY:1000}`이 1초인지 스톱워치로, 3초 길게 누르기와 10초 시간 초과를 시계로 확인
  - USB 인식, BOOT 명령, 노브 누른 채 연결

### 11. 기타 작은 것들 (추정)

- 모두 미적용
- **F1~F12 이름을 규칙으로 (−40~−60)**
  - `keyNames`(`src/macro.c:68`)는 한 항목이 7바이트(이름 6 + 코드 1), F1~F12가 12개(84바이트)
  - "F" 뒤 숫자 n(1~12)이면 코드 `0x3A + n - 1`로 계산 → 표가 줄고 코드가 30~40바이트 늘어 차이만큼 줄어듦
- **`asciiMap`의 글자·숫자를 규칙으로 (−30~−50)**
  - `asciiMap`: `src/macro.c:15`
  - `a`~`z` → `0x04 + (c - 'a')`, `A`~`Z`는 같은 값 + Shift, `1`~`9` → `0x1E + (c - '1')`, `0` → `0x27`
  - 나머지 기호 33개만 표로 남김
- **같은 USB 문자열 같이 쓰기 (−14)**
  - `SerialDescriptor`(`src/hal/ch552/usb/USBconstant.c:195`)와 `ManufacturerDescriptor`(`:202`)는 내용("MK6K1N")이 같음
  - 문자열 번호 1과 3에 같은 배열을 돌려주면 됨 (선택 위치: `src/hal/ch552/usb/USBhandler.c:87-95`)
  - 시리얼 문자열 내용은 그대로 → Windows가 장치를 새로 인식하지 않음
- **`lock_input` 정리 (−30~−60)**
  - `lock_input`: `src/lock.c:120`
  - 5번을 하면 이미 231 → 177바이트
  - 비교 반복문을 `storage_lock_steps()` 포인터(`src/lock.c:122`) 대신 `blob[]` 고정 배열과 오프셋으로 읽으면 조금 더 줄어듦
- **디바운스 시간을 8비트로 (−20~−40, RAM −7)**
  - 당시 `scanKeys`, 현재 `scanSwitches`의 `keyChangedAt` (`src/input.c:21`, 비교 `:79`, 지금은 `uint16_t`)
  - 20 ms 비교에는 8비트 시간으로 충분 (255 ms 넘게 루프가 멈추면 최대 20 ms 늦어질 뿐)

## 권하지 않는 것

| 방법 | 이유 |
|---|---|
| `--model-small` | 코어와 SDCC 라이브러리가 large 모델로 만들어져 섞이면 링크가 안 되거나 위험함. 내부 RAM이 128바이트뿐이라 `blob`/`stage`(각 128바이트) 같은 버퍼는 어차피 xdata에 둬야 함. 대신 5번처럼 필요한 변수만 골라 `__data`로 옮기는 편이 나음 |
| `--opt-code-size`, `--max-allocs-per-node`, `--peep-return` | 원래 코드와 1~9 적용 코드 모두에서 측정 결과 0바이트 |
| `--stack-auto` | 모든 지역 변수를 스택으로 옮김 → 이 칩에서는 보통 더 커짐 |
| LED 출력 리포트(Caps Lock) 없애기, 시리얼 문자열 없애기 | Caps Lock 상태는 대문자 입력에 씀. 시리얼 문자열을 바꾸면 Windows가 다른 장치로 인식함. 크기에 비해 손해가 큼 |

## 권하는 순서

- 원칙: 위험이 낮고 확인이 쉬운 것부터, 한 번에 하나씩 고치고 매번 빌드 크기와 시험 결과를 기록함

1. **3번(계산 라이브러리) + 4번(통신 버퍼) + 9번(0 초기값)**: 코드 몇 줄, `host_test`로 대부분 확인. 약 −880
2. **5번(내부 RAM 변수)**: 스텁에 `__idata` 추가 (당시 `stub/Arduino.h`, 현재 `firmware/host_test/stub/hal_host.h`에 이미 있음). 약 −350
3. **2번(포트 직접)**: 장치에서 키·노브·LED를 한 번 확인. 약 −660
4. **1번(작은 `main`)**: 장치에서 전체 기능 확인. 약 −860 (3번과 함께라 실제로는 약 −1,100)
5. **8번, 7번(저장 코드)**: `host_test` + 저장/읽기 확인. 약 −360
6. **6번(USB EP0)**: 여러 PC에서 인식 시험을 충분히 한 뒤에. 약 −580
7. 그래도 더 필요하면 9번의 `--noinduction`, 11번, 마지막으로 10번

각 단계 뒤 확인할 것:

- **빌드**: `tools/build_fw.ps1` 출력의 프로그램 크기. `--build-path`로 빌드했다면 `.mem` 파일의 ROM 크기와 남은 스택 크기
- **호스트 시험**: `gui\.venv\Scripts\python firmware\host_test\run.py` ("all passed")
- **장치**: README의 확인 절차 (6개 키 입력, 노브 회전·누름, 저장 시 흰색, 잠금/해제/재잠금, BOOT, 노브 누른 채 연결)

## 진행 기록

| 단계 | 적용한 제안 | 플래시 | 전역 변수 | 확인 |
|---|---|---:|---:|---|
| 시작 (v1.2.0) | — | 11,587 | 498 | 장치 확인 |
| 1단계 | 3번(계산 라이브러리), 4번(통신 버퍼), 9번(0 초기값) | 10,745 (−842) | 503 | 빌드, `host_test` 통과, 장치 확인(2026-10-26) |
| 2단계 | 5번(`macro.c`·`lock.c` 상태 → `__data`, 스케치 변수 → `__idata`) | 10,323 (−422) | 446 | 빌드, `host_test` 통과, 스택 여유 184 → 119바이트, 장치 확인(2026-10-26) |
| 3단계 | 2번(포트 직접 읽기/쓰기, 핀 배치는 `config.h`의 `#error` 검사로 고정) | 9,665 (−658) | 445 | 빌드, `host_test` 통과, `wiring_digital.c` 빠짐, 장치 확인(2026-10-26) |
| 4단계 | 1번(`src/main_min.c`가 코어 `main.c`를 대신함) | 8,566 (−1,099) | 364 | 빌드, `host_test` 통과, 벡터 표는 0x0B(타이머0)·0x43(USB)만 연결, 시리얼 인터럽트와 `_modsint`/`_moduint` 빠짐, 장치 확인(2026-10-26, 업데이트 모드 진입 포함) |
| 5단계 | 8번(`millis()`를 `loop()`마다 한 번만 읽기 + 색 표, −158), 7번(저장 코드: 항상 `stage[]`를 8비트 위치로 검사, 쓰기·확인 반복문 합침, −256) | 8,151 (−415) | 357 | 빌드, `host_test` 41개 통과, 스택 여유 129바이트, 장치 확인(2026-10-26) |

- 표의 경로는 당시 기준
  - `src/main_min.c` → 현재 `src/hal/ch552/main_min.c`
  - 3단계의 `#error` 검사 → 현재 `src/boards/ch552_6k1n.h:43-50`
- 1단계 뒤 `_mulint`, `_modulong`, `_gptrget`은 빠짐. `_modsint`/`_moduint`는 코어 시리얼 인터럽트가 쓰고 있어 1번(작은 `main`) 때 빠짐
- 잠금 상태의 빨간 깜빡임은 16비트 `blinkAt`으로 잼 (`src/led.c:122-129`)
  - 주기가 지나면 그때부터 새 주기를 시작 → 오래 열려 있다가 잠겨도 몰아서 깜빡이지 않음
- 현재(1.6.0) 크기는 MK6K1N 8,694바이트, MK6K1NL 8,915바이트

## 시험 빌드 결과 (측정)

| 단계 | 플래시 | 원래 대비 | xdata RAM | 스택 여유 |
|---|---:|---:|---:|---:|
| 원래 코드 | 11,585 | — | 498 | 175 |
| 1~6, 8, 9(0 초기값), 7번 1단계 | 7,691 | −3,894 | 358 | 121 |
| + 7번 2단계(고정 배열) | 7,585 | −4,000 | 356 | — |
| (참고) 위에 `--noinduction` | 약 7,550 | 약 −4,040 | +1 | — |

- 시험 빌드는 컴파일·링크가 되고 `host_test`가 모두 통과함 (저장·매크로·잠금 코드)
- USB, GPIO, LED, 타이머 부분은 장치에서 확인하지 않음
- 개별 제안 절감량의 합(약 3,600)보다 합친 결과가 더 많이 줄어든 이유: 1번과 3번을 함께 해야 `_modsint`/`_moduint`(237바이트)가 빠짐
