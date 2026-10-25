# macro_keyboard: 본 펌웨어 v1.0

6키 + 노브 1개 CH552G 미니 키보드용 펌웨어입니다. 키와 노브 동작마다 저장된 문자열(매크로)을 HID 키보드 입력으로 출력하고, [gui](../../gui/) 설정 프로그램과 [PROTOCOL.md](../../docs/PROTOCOL.md) v1 규격으로 통신합니다.

## 기능

| 항목 | 내용 |
|---|---|
| USB 구성 | 인터페이스 0: HID 키보드, 인터페이스 1: 설정용 Vendor HID (64바이트) |
| 슬롯 | 키 A~F, 노브 시계 방향/반시계 방향/누르기 (9개) |
| 저장 | DataFlash 128바이트. 헤더와 슬롯 길이 정보 26바이트를 빼면 **9개 슬롯 합계 102자** |
| 매크로 | `{ENTER}` `{TAB}` `{UP}` `{F5}` 등 키 이름, `{CTRL+C}` 같은 조합키, `{DELAY:n}`, `{{` `}}` |
| Caps Lock | 켜져 있어도 영문 대소문자가 쓴 그대로 입력되도록 보정 |
| 연속 입력 | 출력 중에 누른 키는 최대 8개까지 순서대로 대기 |

### LED (WS2812 1개)

| 색 | 의미 |
|---|---|
| 어두운 파랑 | 대기 중 |
| 초록 | 문자열 출력 중 |
| 흰색 (0.3초) | 설정 저장 완료 |
| 빨강 | 부트로더로 들어가는 중 |

### 부트로더 진입 (펌웨어 업데이트)

- **키 D를 누른 채 USB 연결**: ROM 부트로더(P1.5)
- **노브를 누른 채 USB 연결**: 펌웨어가 부트로더로 점프 (키 D 방법이 안 될 때의 예비 방법)
- GUI의 BOOT 명령도 지원합니다(아직 GUI 화면에는 버튼이 없음).

## 빌드

Arduino IDE + CH55xDuino 0.0.26 (Windows는 [TROUBLESHOOTING 1-1](../../docs/TROUBLESHOOTING.md)의 `sdcc.sh` 패치 필요).

| Tools 메뉴 | 값 |
|---|---|
| Board | CH552 Board |
| Clock Source | 24 MHz (internal), 5V |
| USB Settings | **USER CODE w/ 266B USB ram** ⚠️ test_pinmap(148B)과 다릅니다 |
| Bootloader pin | **P1.5 pull-down** |

**Sketch → Export Compiled Binary**를 누르면 `build\CH55xDuino.mcs51.ch552\macro_keyboard.ino.hex`가 생깁니다.

확인 결과(2026-10-26): 프로그램 9827바이트(68%), 전역 변수 445바이트(58%).

## 업로드

저장소 폴더에서 실행하고, **키 D를 누른 채** 키보드를 연결합니다.

```powershell
powershell -ExecutionPolicy Bypass -File tools\flash.ps1 -Hex firmware\macro_keyboard\build\CH55xDuino.mcs51.ch552\macro_keyboard.ino.hex
```

업로드 후 LED가 **어두운 파랑**으로 켜지면 펌웨어가 실행 중인 것입니다. 처음에는 DataFlash에 이전 제조사 설정이 남아 있어도 형식이 맞지 않으므로 **모든 슬롯이 비어 있는 상태**로 시작합니다.

## 동작 테스트

### 1. 연결 확인

1. GUI를 실행합니다: `gui\.venv\Scripts\python -m gui`
2. 상단에 `● 연결됨 · 펌웨어 v1.0 · 용량 128바이트`가 보이면 설정 통신이 되는 것입니다.
3. 처음에는 "설정 없음"으로 빈 슬롯 9개가 표시됩니다.

### 2. 테스트 문자열 넣기

아래 표의 문자열을 GUI에서 슬롯마다 입력하고 **[장치에 저장]**을 누릅니다(9개 합계 85자, 전체 111 / 128바이트). LED가 흰색으로 잠깐 빛나면 저장된 것입니다.

| 슬롯 | 테스트 문자열 | 확인하는 것 |
|---|---|---|
| 키 A | `Hello, World!{ENTER}` | 대소문자, 기호, Enter |
| 키 B | `abc{DELAY:1000}def` | 1초 쉬었다가 이어서 입력 |
| 키 C | `{{OK}}` | 중괄호 입력 → `{OK}` |
| 키 D | `{CTRL+A}` | 조합키 (전체 선택) |
| 키 E | `{CTRL+C}` | 조합키 (복사) |
| 키 F | `{CTRL+V}` | 조합키 (붙여넣기) |
| 노브 시계 방향 | `{DOWN}` | 한 칸마다 아래 화살표 |
| 노브 반시계 방향 | `{UP}` | 한 칸마다 위 화살표 |
| 노브 누르기 | `{ENTER}` | Enter |

### 3. 키보드로 확인

1. **메모장**을 열고 **영문 입력 모드**로 둡니다.
2. 키 A → `Hello, World!` 입력 후 줄바꿈
3. 키 B → `abc` 입력, 1초 뒤 `def`
4. 키 C → `{OK}`
5. 키 D(전체 선택) → 키 E(복사) → 메모장 끝을 클릭 → 키 F(붙여넣기)
6. 노브를 돌려 커서가 위/아래로 움직이는지, 노브를 눌러 줄바꿈이 되는지 확인
7. **Caps Lock을 켜고** 키 A를 다시 눌러도 `Hello, World!`가 그대로 나오는지 확인
8. USB를 뺐다가 다시 꽂고, GUI의 **[장치에서 읽기]**로 저장한 문자열이 그대로 남아 있는지 확인

GUI의 **[테스트 입력]**으로 키를 누르지 않고 선택한 슬롯을 입력해 볼 수도 있습니다(3초 카운트다운 뒤 포커스된 창에 입력됨).

### 4. 용량 확인

GUI 아래쪽 막대에 `N자 입력 · M자 더 입력 가능 (사용 / 128 바이트)`가 표시됩니다. 128바이트를 넘으면 빨간색으로 바뀌고 저장 버튼이 꺼집니다.

## 문제가 생기면

| 증상 | 확인할 것 |
|---|---|
| 업로드 후 키보드로 인식되지 않음 | 장치 관리자에서 "알 수 없는 장치"가 보이면 USB Settings가 **266B**였는지 확인하고 다시 빌드 |
| GUI가 "연결 안 됨" | 장치 관리자의 HID 장치에 `Mini Macro Kbd`가 두 개(키보드, 공급업체 정의 장치) 있는지 확인. 다른 GUI 창이 장치를 잡고 있지 않은지 확인 |
| 영문 대신 한글이 입력됨 | 한/영 키로 영문 모드로 전환 ([TROUBLESHOOTING 3-1](../../docs/TROUBLESHOOTING.md)) |
| 다시 업로드해야 함 | 키 D 또는 노브를 누른 채 연결 |

더 자세한 내용은 [docs/TROUBLESHOOTING.md](../../docs/TROUBLESHOOTING.md)를 보세요.

## 코드 구성

| 파일 | 내용 |
|---|---|
| `macro_keyboard.ino` | 키/노브 입력, LED, 부트로더 점프, 메인 루프 |
| `src/config.h` | 핀, 버전, 용량 |
| `src/protocol.c/.h` | Vendor HID 명령 처리 (HELLO/READ/WRITE/COMMIT/TEST/BOOT) |
| `src/storage.c/.h` | DataFlash 블롭 저장, CRC 검사, 슬롯 찾기 |
| `src/macro.c/.h` | 매크로 해석과 비동기 출력 (키 누름/뗌, DELAY) |
| `src/usb/` | USB 디스크립터, 요청 처리, 엔드포인트 (CH55xDuino qmkCompatibleKeyboard 예제 기반, LGPL-2.1) |

`firmware/host_test/run.py`로 `storage.c`와 `macro.c`를 PC(gcc)에서 검사할 수 있습니다. GUI의 인코더로 만든 블롭을 저장하고, 각 슬롯이 보내는 HID 키 코드를 확인합니다.

```powershell
gui\.venv\Scripts\python firmware\host_test\run.py
```
