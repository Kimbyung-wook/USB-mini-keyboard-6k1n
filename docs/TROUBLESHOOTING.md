# 문제 해결 (Troubleshooting)

2026-10-25 첫 장치를 개조하면서 실제로 겪은 문제와 해결 방법입니다. 증상으로 찾아보세요.

| 증상 | 바로 가기 |
|---|---|
| `sdcc.sh: line 94: syntax error: unexpected "("` | [1-1](#1-1-sdccsh-94번째-줄-문법-오류-ch55xduino-0026-windows) |
| `sketch_merged.cpp: The system cannot find the file specified` | [1-2](#1-2-sketch_mergedcpp를-찾을-수-없음-ch55xduino-0025) |
| `#error "This sketch needs to be compiled with a USER USB setting"` | [1-3](#1-3-user-usb-setting-오류) |
| 부트로더가 금방 사라져서 업로드 버튼을 누를 시간이 없음 | [2-2](#2-2-부트로더가-약-5초-만에-사라짐) |
| 다운로드 실패 후 키를 누르고 꽂아도 아무 장치도 안 나타남 | [2-3](#2-3-다운로드-실패-후-장치가-전혀-인식되지-않음-복구) |
| 입력이 `ㅖ1.1`처럼 한글로 나옴 | [3-1](#3-1-영문-대신-한글이-입력됨) |
| 노브 방향이 반대 | [3-2](#3-2-노브-회전-방향이-반대) |

## 진단 도구

| 도구 | 용도 |
|---|---|
| `tools/usb_monitor.ps1 -Seconds 180` | 지정 시간 동안 새로 붙거나 떨어지는 USB/HID 장치를 기록. 꽂았을 때 Windows가 **무엇이라도** 감지하는지 확인 |
| `tools/usb_monitor.ps1 -History` | 부트로더(`4348:55E0`)와 펌웨어(`1209:C55D`) 장치가 **마지막으로 연결/분리된 시각**과 드라이버. 몇 초만 나타났던 장치도 확인 가능 |
| `tools/flash.ps1 -Hex <파일>` | 부트로더가 나타나는 즉시 업로드(5초 제한 대응). 진입 핀도 함께 기록 |

PowerShell에서 스크립트 실행이 막혀 있으면 `powershell -ExecutionPolicy Bypass -File tools\flash.ps1 -Hex ...`처럼 실행합니다.

---

## 1. 빌드

### 1-1. `sdcc.sh` 94번째 줄 문법 오류 (CH55xDuino 0.0.26, Windows)

**증상**

```
Arduino15/packages/CH55xDuino/tools/MCS51Tools/2026.07.10/wrapper/sdcc.sh: line 94: syntax error: unexpected "(" (expecting "fi")
```

**원인**: Windows에서는 wrapper 스크립트를 CH55xDuino에 들어 있는 **busybox sh**가 실행하는데, 0.0.26의 `sdcc.sh`가 bash 전용 배열 문법(`FILTERED_ARGS=()`, `"${FILTERED_ARGS[@]}"`)을 씁니다. GitHub 최신 소스(2026-07-10)도 같은 상태입니다.

**해결**: `%LOCALAPPDATA%\Arduino15\packages\CH55xDuino\tools\MCS51Tools\2026.07.10\wrapper\sdcc.sh`를 `sdcc.sh.orig`로 백업하고, `if [ "$MARK" = "re12" ]; then` 블록의 배열 부분을 아래처럼 바꿉니다.

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

그리고 아래 `case "$SRC"` 안의 `"${FILTERED_ARGS[@]}"` 세 곳을 모두 `"$@"`로 바꿉니다.

- 같은 파일의 `[[ ... ]]` 문법은 busybox에서도 동작하므로 그대로 둡니다.
- CH55xDuino를 다시 설치하거나 업데이트하면 수정이 사라지니 다시 적용해야 합니다.
- 확인: test_pinmap 빌드 성공(프로그램 6372바이트, 전역 변수 169바이트).

### 1-2. `sketch_merged.cpp`를 찾을 수 없음 (CH55xDuino 0.0.25)

**증상**

```
open C:\Users\...\Temp\572861346\sketch_merged.cpp: The system cannot find the file specified.
```

**원인**: Arduino IDE에 들어 있는 arduino-cli가 1.5 이상(확인 당시 1.5.1)이면 빌드 방식이 바뀌는데, 0.0.25는 이를 지원하지 않습니다. 0.0.26이 이 문제를 고친 버전입니다.

**해결**: 다운그레이드하지 말고 **0.0.26을 쓰고 [1-1](#1-1-sdccsh-94번째-줄-문법-오류-ch55xduino-0026-windows)의 패치를 적용**합니다.

### 1-3. USER USB setting 오류

**증상**

```
test_pinmap.ino:18:2: error: #error "This sketch needs to be compiled with a USER USB setting"
```

**원인**: Tools → USB Settings가 기본값 `Default CDC`입니다. `USER_USB_RAM`은 코드가 아니라 이 메뉴 설정으로 정의됩니다.

**해결**: Tools 메뉴를 아래처럼 맞춥니다. 코드에 `#define USER_USB_RAM`을 직접 넣지 마세요(메모리 배치가 맞지 않아 USB가 동작하지 않을 수 있음).

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

- 제조사 펌웨어 시절 WCHISPTool은 `Download Cfg Pin = P1.5`로 표시했지만 키 D로는 진입되지 않았습니다. 제조사 펌웨어와 함께 있을 때는 키 E를 쓰세요.
- 부트로더 버전은 WCHISPTool 로그 창이나 업로더 출력의 `BTVER` / `Bootloader:`에서 확인합니다(첫 장치는 2.5.0).
- ROM 부트로더는 펌웨어를 덮어써도 지워지지 않습니다.

### 2-2. 부트로더가 약 5초 만에 사라짐

**증상**: 부트로더로 인식된 뒤 업로드를 시작하기 전에 장치가 사라집니다(`usb_monitor.ps1 -History`로 보면 연결 23:32:35, 분리 23:32:40처럼 약 5초).

**해결**: `tools/flash.ps1`을 먼저 실행해 두고 키보드를 꽂습니다. 부트로더가 나타나는 즉시 업로드가 시작됩니다.

```powershell
.\tools\flash.ps1 -Hex firmware\test_pinmap\build\CH55xDuino.mcs51.ch552\test_pinmap.ino.hex
```

### 2-3. 다운로드 실패 후 장치가 전혀 인식되지 않음 (복구)

**증상**: WCHISPTool의 자동 다운로드가 `fail`로 끝난 뒤, 그냥 꽂아도, 키 E를 누르고 꽂아도 **아무 장치도 나타나지 않습니다**(알 수 없는 장치조차 없음).

**진단**

1. `usb_monitor.ps1 -History`: 부트로더가 다운로드 시각(23:17:11~23:17:20, 약 9초)에만 기록되고 그 뒤로는 없었습니다.
2. `usb_monitor.ps1 -Seconds 300`을 켜고 그냥 꽂기와 키를 누른 채 꽂기를 각 2회 했지만 기록이 전혀 없었습니다.
3. 해석: Flash에 펌웨어가 일부만 써져서 USB를 켜지 못하고 있었고, **실패한 다운로드 과정에서 진입 핀 설정이 P3.6으로 바뀐** 것으로 판단했습니다. 실패 당시 WCHISPTool 로그는 남아 있지 않아서 정확한 실패 원인은 알 수 없습니다.

**복구**

1. 가변저항(최대 2kΩ)의 가운데 핀과 바깥 핀 하나를 쓰고, 멀티미터로 **1.5~2kΩ**에 맞춥니다. **0Ω 근처는 금지**입니다(D+가 3.3V에 직결됨).
2. USB를 뺀 상태에서 칩 **12번 핀(D+)과 16번 핀(3V3)** 사이에 연결합니다. 사이의 13(D-), 14(GND), 15(5V)번 핀에 닿지 않게 조심합니다.
3. `tools/flash.ps1 -Hex <파일>`을 실행해 두고 USB를 꽂습니다. 기본값 `-BootPin P15`가 **진입 핀을 P1.5로 되돌립니다.**
4. 성공 로그 예:

   ```
   Found Device CH552
   Bootloader: 2.5.0
   Write 6372 bytes from bin file.  ... Write complete!!!
   Verify chip                      ... Verify complete!!!
   Reset OK
   ```

5. 저항을 떼고, 다음부터는 키 D로 진입합니다.

**예방**

- WCHISPTool 대신 CH55xDuino 업로더(`tools/flash.ps1` 또는 Arduino IDE Upload)를 씁니다.
- WCHISPTool을 써야 한다면 자동 다운로드를 끄고, 칩 모델(CH552)과 설정 값을 확인한 뒤 수동으로 다운로드하고, 실패하면 로그를 저장해 둡니다.

### 2-4. Arduino IDE Upload가 진입 핀을 바꿈

CH55xDuino의 업로더는 업로드할 때 **Tools → Bootloader pin 값을 칩에 기록**합니다. 기본값은 `P3.6 (D+) pull-up`이라, 기본값 그대로 올리면 키 D로 진입할 수 없게 되고 [2-3](#2-3-다운로드-실패-후-장치가-전혀-인식되지-않음-복구)의 풀업 방법이 필요해집니다. 반드시 **P1.5 pull-down**으로 맞추고 올리세요.

### 2-5. Windows 드라이버

- WCHISPTool을 설치하면 부트로더 장치에 WCH 드라이버(`CH375_A64`)가 붙습니다.
- CH55xDuino의 vnproch55x는 이 드라이버로 문제없이 동작했습니다(`CH375 open OK`). Zadig로 드라이버를 바꿀 필요가 없습니다.

---

## 3. 동작

### 3-1. 영문 대신 한글이 입력됨

**증상**: `P1.1` 대신 `ㅖ1.1`이 입력됩니다.

**원인**: HID 키보드는 문자가 아니라 **키 위치**를 보냅니다. `P`를 보내려고 Shift+P를 누르는데, Windows 입력기가 한글 모드면 두벌식 Shift+P인 `ㅖ`가 됩니다. 숫자와 기호는 한/영 상태와 상관없이 그대로 나옵니다.

**해결**: 한/영 키로 영문 모드로 바꿉니다(작업 표시줄 입력기 표시가 "A"). 최종 펌웨어에서도 같은 문제가 있으므로, 출력 전에 한/영 전환키를 보내는 매크로 같은 대책을 검토합니다.

### 3-2. 노브 회전 방향이 반대

test_pinmap에서 시계 방향으로 돌리면 `CCW`가 나옵니다. 인코더 A/B 핀(P3.0/P3.1) 판정이 반대이므로 본 펌웨어에서 방향을 뒤집습니다. 한 칸에 한 번씩 출력되는 것은 정상입니다.

### 3-3. 제조사 펌웨어에서 LED가 꺼짐

제조사 펌웨어에서 설정을 바꾼 뒤 LED가 켜지지 않았지만, test_pinmap의 WS2812 모드에서는 정상적으로 켜졌습니다. 하드웨어 고장이 아니라 제조사 펌웨어 설정 문제였습니다.

### 3-4. 도통 테스트에서 LED 제어선이 안 보임

LED 데이터선(P3.4, 칩 11번 핀)은 도통 테스트에서 "미연결"로 보였습니다. 중간에 저항이 있으면 도통 모드가 반응하지 않기 때문으로 보입니다. 아무 데도 연결되지 않은 것처럼 보이는 GPIO도 test_pinmap으로 확인하세요.
