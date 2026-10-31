# 문제 해결 (Troubleshooting)

- 2026-10-25 첫 장치 개조 중 실제로 겪은 문제와 해결 방법
- 증상으로 찾기

| 증상 | 바로 가기 |
|---|---|
| `sdcc.sh: line 94: syntax error: unexpected "("` | [1-1](#1-1-sdccsh-94번째-줄-문법-오류-ch55xduino-0026-windows) |
| `sketch_merged.cpp: The system cannot find the file specified` | [1-2](#1-2-sketch_mergedcpp를-찾을-수-없음-ch55xduino-0025) |
| `#error "This sketch needs to be compiled with a USER USB setting"` | [1-3](#1-3-user-usb-setting-오류) |
| 부트로더가 금방 사라져서 업로드 버튼을 누를 시간이 없음 | [2-2](#2-2-부트로더가-약-5초-만에-사라짐) |
| 다운로드 실패 후 키를 누르고 꽂아도 아무 장치도 안 나타남 | [2-3](#2-3-다운로드-실패-후-장치가-전혀-인식되지-않음-복구) |
| 입력이 `ㅖ1.1`처럼 한글로 나옴 | [3-1](#3-1-영문-대신-한글이-입력됨) |
| 노브 방향이 반대 | [3-2](#3-2-노브-회전-방향이-반대) |
| 본 펌웨어에서 LED가 안 켜짐 | [3-4](#3-4-본-펌웨어에서-led가-켜지지-않음-v10-첫-빌드) |
| 키 C를 누르면 `CCW`/`CW`가 입력됨 (MK6K1NL) | [3-6](#3-6-키-c를-누르면-ccwcw가-입력됨-mk6k1nl-v150-이전-빌드) |
| MK6K1NL 제조사 펌웨어에서 업데이트 모드 진입 안 됨 | [3-7](#3-7-mk6k1nl-제조사-펌웨어에서-업데이트-모드로-들어가지-않음) |
| LED가 꺼져 있거나(가끔 빨강) 빨강이고, 키를 눌러도 아무것도 입력되지 않음 | 고장 아님. 잠금 상태(꺼짐 + 가끔 빨강) 또는 패턴 입력 중(빨강, 노브 2초 누르기 뒤). [macro_keyboard README의 "잠금"](../firmware/macro_keyboard/README.md#잠금) |

## 진단 도구

| 도구 | 용도 |
|---|---|
| `tools/usb_monitor.ps1 -Seconds 180` | 지정 시간 동안 새로 붙거나 떨어지는 USB/HID 장치 기록. 꽂았을 때 Windows가 **무엇이라도** 감지하는지 확인 |
| `tools/usb_monitor.ps1 -History` | 부트로더(`4348:55E0`)와 펌웨어(`1209:C55D`) 장치의 **마지막 연결/분리 시각**과 드라이버. 몇 초만 나타났던 장치도 확인 가능 |
| `tools/flash.ps1 -Hex <파일>` | 부트로더가 나타나는 즉시 업로드(5초 제한 대응). 진입 핀도 함께 기록 |

- PowerShell 스크립트 실행이 막혀 있으면: `powershell -ExecutionPolicy Bypass -File tools\flash.ps1 -Hex ...`

---

## 1. 빌드

### 1-1. `sdcc.sh` 94번째 줄 문법 오류 (CH55xDuino 0.0.26, Windows)

**증상**

```
Arduino15/packages/CH55xDuino/tools/MCS51Tools/2026.07.10/wrapper/sdcc.sh: line 94: syntax error: unexpected "(" (expecting "fi")
```

**원인**

- Windows에서는 wrapper 스크립트를 CH55xDuino 내장 **busybox sh**가 실행함
- 0.0.26의 `sdcc.sh`가 bash 전용 배열 문법(`FILTERED_ARGS=()`, `"${FILTERED_ARGS[@]}"`)을 씀
- GitHub 최신 소스(2026-07-10)도 같은 상태

**조치**

1. `%LOCALAPPDATA%\Arduino15\packages\CH55xDuino\tools\MCS51Tools\2026.07.10\wrapper\sdcc.sh`를 `sdcc.sh.orig`로 백업
2. `if [ "$MARK" = "re12" ]; then` 블록의 배열 부분을 아래로 교체

   ```sh
   	# POSIX sh version (busybox sh on Windows has no arrays): rotate through
   	# the positional parameters once, re-appending only the kept arguments.
   	skip_next=0
   	argc=$#
   	while [ $argc -gt 0 ]; do
   		arg=$1
   		shift
   		argc=$((argc - 1))
   		if [ $skip_next -eq 1 ]; then
   			skip_next=0
   			continue
   		fi
   		case "$arg" in
   			-c|-MMD|-MF)
   				skip_next=1
   				continue
   				;;
   		esac
   		set -- "$@" "$arg"
   	done
   ```

3. 아래 `case "$SRC"` 안의 `"${FILTERED_ARGS[@]}"` 세 곳을 모두 `"$@"`로 교체

**참고**

- 같은 파일의 `[[ ... ]]` 문법은 busybox에서도 동작하므로 그대로 둠
- CH55xDuino 재설치·업데이트 시 수정이 사라짐 → 다시 적용
- 확인: test_pinmap 빌드 성공(프로그램 6372바이트, 전역 변수 169바이트)

### 1-2. `sketch_merged.cpp`를 찾을 수 없음 (CH55xDuino 0.0.25)

| 구분 | 내용 |
|---|---|
| 증상 | `open C:\Users\...\Temp\572861346\sketch_merged.cpp: The system cannot find the file specified.` |
| 원인 | Arduino IDE 내장 arduino-cli 1.5 이상(확인 당시 1.5.1)에서 빌드 방식이 바뀜. 0.0.25는 미지원, 0.0.26에서 수정됨 |
| 조치 | 다운그레이드하지 않음. **0.0.26 사용 + [1-1](#1-1-sdccsh-94번째-줄-문법-오류-ch55xduino-0026-windows) 패치 적용** |

### 1-3. USER USB setting 오류

| 구분 | 내용 |
|---|---|
| 증상 | `test_pinmap.ino:18:2: error: #error "This sketch needs to be compiled with a USER USB setting"` |
| 원인 | Tools → USB Settings가 기본값 `Default CDC`. `USER_USB_RAM`은 코드가 아니라 이 메뉴 설정으로 정의됨 |
| 조치 | Tools 메뉴를 아래 표대로 설정. 코드에 `#define USER_USB_RAM` 직접 넣지 않음(메모리 배치가 안 맞아 USB 동작 안 할 수 있음) |

| 항목 | 값 |
|---|---|
| Board | CH552 Board |
| Clock Source | 24 MHz (internal), 5V |
| USB Settings | **USER CODE w/ 148B USB ram** |
| Bootloader pin | **P1.5 pull-down** |

---

## 2. 업로드와 부트로더

### 2-1. 부트로더 진입 방법 정리

| 상황 | 진입 방법 |
|---|---|
| 제조사 펌웨어가 있을 때 | **키 E를 누른 채 연결** (제조사 펌웨어가 부팅 때 키 E를 보고 점프하는 기능으로 추정) |
| 진입 핀 설정 = P1.5 (현재) | **키 D를 누른 채 연결** (키 D = P1.5, ROM 부트로더가 직접 확인) |
| 진입 핀 설정 = P3.6 | 칩 12번 핀(D+)과 16번 핀(3V3) 사이에 **1.5~2kΩ 풀업**을 연결한 채로 연결 |

- 제조사 펌웨어 시절 WCHISPTool 표시는 `Download Cfg Pin = P1.5`였지만 키 D로 진입 안 됨 → 제조사 펌웨어일 때는 키 E 사용
- 부트로더 버전: WCHISPTool 로그 창 또는 업로더 출력의 `BTVER` / `Bootloader:`에서 확인(첫 장치는 2.5.0)
- ROM 부트로더는 펌웨어를 덮어써도 지워지지 않음

### 2-2. 부트로더가 약 5초 만에 사라짐

| 구분 | 내용 |
|---|---|
| 증상 | 부트로더로 인식된 뒤 업로드 시작 전에 장치가 사라짐. `usb_monitor.ps1 -History` 기준 연결 23:32:35, 분리 23:32:40처럼 약 5초 |
| 조치 | `tools/flash.ps1`을 먼저 실행해 두고 키보드를 꽂음. 부트로더가 나타나는 즉시 업로드 시작 |

```powershell
.\tools\flash.ps1 -Hex firmware\test_pinmap\build\CH55xDuino.mcs51.ch552\test_pinmap.ino.hex
```

### 2-3. 다운로드 실패 후 장치가 전혀 인식되지 않음 (복구)

**증상**

- WCHISPTool 자동 다운로드가 `fail`로 끝난 뒤, 그냥 꽂아도 키 E를 누르고 꽂아도 **아무 장치도 안 나타남**(알 수 없는 장치조차 없음)

**진단**

1. `usb_monitor.ps1 -History`: 부트로더가 다운로드 시각(23:17:11~23:17:20, 약 9초)에만 기록되고 이후 없음
2. `usb_monitor.ps1 -Seconds 300` 켜고 그냥 꽂기·키 누른 채 꽂기 각 2회 → 기록 전혀 없음
3. 해석
   - Flash에 펌웨어가 일부만 써져 USB를 못 켜는 상태
   - **실패한 다운로드 과정에서 진입 핀 설정이 P3.6으로 바뀐** 것으로 판단
   - 실패 당시 WCHISPTool 로그가 없어 정확한 실패 원인은 모름

**복구**

1. 가변저항(최대 2kΩ)의 가운데 핀과 바깥 핀 하나 사용, 멀티미터로 **1.5~2kΩ**에 맞춤
   - **0Ω 근처 금지**(D+가 3.3V에 직결됨)
2. USB를 뺀 상태에서 칩 **12번 핀(D+)과 16번 핀(3V3)** 사이에 연결
   - 사이의 13(D-), 14(GND), 15(5V)번 핀에 닿지 않게 주의
3. `tools/flash.ps1 -Hex <파일>` 실행해 두고 USB 꽂음
   - 기본값 `-BootPin P15`가 **진입 핀을 P1.5로 되돌림**
4. 성공 로그 예:

   ```
   Found Device CH552
   Bootloader: 2.5.0
   Write 6372 bytes from bin file.  ... Write complete!!!
   Verify chip                      ... Verify complete!!!
   Reset OK
   ```

5. 저항을 떼고, 다음부터는 키 D로 진입

**예방**

- WCHISPTool 대신 CH55xDuino 업로더(`tools/flash.ps1` 또는 Arduino IDE Upload) 사용
- WCHISPTool을 꼭 써야 하면
  - 자동 다운로드 끔
  - 칩 모델(CH552)과 설정 값 확인 후 수동 다운로드
  - 실패하면 로그 저장

### 2-4. Arduino IDE Upload가 진입 핀을 바꿈

| 구분 | 내용 |
|---|---|
| 증상 | 기본 설정으로 올린 뒤 키 D로 진입 안 됨 → [2-3](#2-3-다운로드-실패-후-장치가-전혀-인식되지-않음-복구)의 풀업 방법 필요 |
| 원인 | CH55xDuino 업로더가 업로드 때 **Tools → Bootloader pin 값을 칩에 기록**함. 기본값이 `P3.6 (D+) pull-up` |
| 조치 | 반드시 **P1.5 pull-down**으로 맞추고 업로드 |

### 2-5. Windows 드라이버

- WCHISPTool 설치 시 부트로더 장치에 WCH 드라이버(`CH375_A64`)가 붙음
- CH55xDuino의 vnproch55x는 이 드라이버로 문제없이 동작함(`CH375 open OK`)
- Zadig로 드라이버를 바꿀 필요 없음

---

## 3. 동작

### 3-1. 영문 대신 한글이 입력됨

| 구분 | 내용 |
|---|---|
| 증상 | `P1.1` 대신 `ㅖ1.1` 입력됨 |
| 원인 | HID 키보드는 문자가 아니라 **키 위치**를 보냄. `P` = Shift+P인데, Windows 입력기가 한글 모드면 두벌식 Shift+P인 `ㅖ`가 됨. 숫자·기호는 한/영과 무관하게 그대로 나옴 |
| 조치 | 한/영 키로 영문 모드 전환(작업 표시줄 입력기 표시 "A") |
| 남은 과제 | 최종 펌웨어도 같은 문제. 출력 전에 한/영 전환키를 보내는 매크로 같은 대책 검토 |

### 3-2. 노브 회전 방향이 반대

| 구분 | 내용 |
|---|---|
| 증상 | test_pinmap에서 시계 방향으로 돌리면 `CCW` 출력 |
| 원인 | 인코더 A/B 핀(P3.0/P3.1) 판정이 반대 |
| 조치 | 본 펌웨어에서 방향을 뒤집음 |

- 한 칸에 한 번씩 출력되는 것은 정상

### 3-3. 제조사 펌웨어에서 LED가 꺼짐

| 구분 | 내용 |
|---|---|
| 증상 | 제조사 펌웨어에서 설정을 바꾼 뒤 LED가 안 켜짐 |
| 원인 | 하드웨어 고장 아님, 제조사 펌웨어 설정 문제 |
| 근거 | test_pinmap의 WS2812 모드에서는 정상적으로 켜짐 |

### 3-4. 본 펌웨어에서 LED가 켜지지 않음 (v1.0 첫 빌드)

**증상**

- test_pinmap에서는 LED가 켜졌는데, macro_keyboard v1.0 첫 빌드를 올리면 전혀 안 켜짐

**원인 후보** (셋을 한꺼번에 고쳐서 어느 것이 결정적이었는지는 미확인)

| | test_pinmap (켜짐) | v1.0 첫 빌드 (안 켜짐) |
|---|---|---|
| 데이터를 보내는 LED 수 | 8개분 | 1개분 |
| 보내는 빈도 | 0.5초마다 | 색이 바뀔 때 한 번 |
| 밝기 | 40 | 대기 파랑 12 |

- 가장 유력한 원인: **LED 수**
  - WS2812는 체인 앞에서부터 데이터를 나눠 받음 → 보이는 LED가 체인의 첫 번째가 아니면 1개분 데이터로는 안 켜짐
  - "LED는 하나"라는 관찰은 8개분을 같은 색으로 보낸 상태에서 한 것

**조치 (2026-10-26)**

- `macro_keyboard.ino`의 `showColor` 수정
  - 8개분 모두에 같은 색 전송
  - 0.2초마다 다시 전송
  - 밝기 40으로 올림
- 업로드 후 파랑으로 켜지는 것 확인

### 3-5. 도통 테스트에서 LED 제어선이 안 보임

| 구분 | 내용 |
|---|---|
| 증상 | LED 데이터선(P3.4, 칩 11번 핀)이 도통 테스트에서 "미연결"로 보임 |
| 원인 | 중간에 저항이 있으면 도통 모드가 반응하지 않는 것으로 보임 |
| 조치 | 아무 데도 연결 안 된 것처럼 보이는 GPIO도 test_pinmap으로 확인 |

### 3-6. 키 C를 누르면 `CCW`/`CW`가 입력됨 (MK6K1NL, v1.5.0 이전 빌드)

**증상**

- 노브 바로 옆 키 C를 누르면 `C` 대신, 또는 `C`와 함께 노브 회전(`CCW`, 가끔 `CW`) 입력됨
- 키 C의 LED는 정상으로 켜짐

**진단**

- [test_mk6k1nl](../firmware/test_mk6k1nl/README.md) RAW 모드로 노브 신호 기록
- 노브가 칸 사이에 걸쳐 `AB 10`에서 쉬고 있었음
- 키 C를 누르는 흔들림에 B 접점이 `10 ↔ 11`을 오감
- 이전 펌웨어는 `11`에 닿을 때 방향 값이 0이 아니면 한 칸으로 셈 → 한 단계 흔들림이 회전으로 입력됨
- 노브를 칸에 두거나 손으로 잡고 누르면 신호 변화 없음

**조치**

- 펌웨어 v1.5.0(최종 빌드)부터 한 칸(4단계) 중 **같은 방향으로 2단계 이상** 움직여야 회전으로 셈(`ENC_MIN_STEPS`)
- 두 보드 모두 적용
- 노브 신호: [PINMAP 노브 신호](PINMAP.md#노브-신호) 참고

### 3-7. MK6K1NL 제조사 펌웨어에서 업데이트 모드로 들어가지 않음

**증상**

- 새 MK6K1NL(제조사 펌웨어, USB ID `1189:8890`)은 키를 하나씩 또는 여러 개 누른 채 꽂아도 업데이트 모드 진입 안 됨

**조치**

1. 업로더 대기를 먼저 켬
   - `tools\flash.ps1`, 또는
   - GUI 펌웨어 업데이트 창에서 **장입할 보드**를 MK6K1NL로 고르고 [장입]
2. [2-3](#2-3-다운로드-실패-후-장치가-전혀-인식되지-않음-복구)처럼 **12번(D+)–16번(3V3) 사이에 1.5~2kΩ**을 대고 꽂음
3. 한 번 올리면 진입 핀이 P1.5로 기록됨 → 다음부터는 키 D나 노브를 누른 채 꽂으면 됨
