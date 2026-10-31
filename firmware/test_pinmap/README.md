# test_pinmap: 하드웨어 확인용 테스트 펌웨어

> 확인한 핀 배치 다이어그램: [docs/PINMAP.md](../../docs/PINMAP.md)

- **대상**: 6키 + 노브 1개 CH552G 미니 키보드 **MK6K1N**(눈에 보이는 LED 1개)
- **확인 항목**: 핀 매핑, LED
- **쓰는 때**: **비슷한 장치를 새로 구했을 때**, 본 펌웨어를 올리기 전에 먼저 확인
- 키마다 LED가 있는 **MK6K1NL**은 [test_mk6k1nl](../test_mk6k1nl/README.md)로 확인

## 새 장치 점검 절차

1. **제조사 펌웨어로 부트로더 진입 확인**
   - 키 E(또는 다른 키)를 누른 채 연결 → WCHISPTool에 `CH552`와 `BTVER`가 보이는지 확인
   - 이 단계에서는 **다운로드하지 않음**
   - 칩 모델, 부트로더 버전, Download Cfg Pin 기록
2. **업로드**
   - `tools/flash.ps1 -Hex <test_pinmap.hex>`를 실행해 둔 뒤, 1번에서 찾은 방법으로 부트로더 진입
   - 진입 핀은 P1.5로 기록됨
3. **테스트**: [테스트 방법](#테스트-방법)대로 키, 노브, LED를 확인하고 결과 표 채움
4. **첫 장치와 비교**
   - 아래 표와 같으면 같은 본 펌웨어를 그대로 사용 가능
   - 다르면 핀 설정을 장치별로 나눠야 함
5. 다음부터 부트로더는 **키 D를 누른 채 연결**로 진입(키 D가 P1.5인 경우)

- 문제가 생기면 [docs/TROUBLESHOOTING.md](../../docs/TROUBLESHOOTING.md) 참고

### 첫 장치의 결과 (기준, 2026-10-25)

| 입력 | 출력 |
|---|---|
| 키 A / B / C | `P1.1` / `P1.7` / `P1.6` |
| 키 D / E / F | `P1.5` / `P1.4` / `P3.2` |
| 노브 시계 방향 한 칸 | `CCW` (방향 판정이 반대, 본 펌웨어에서 보정) |
| 노브 반시계 방향 한 칸 | `CW` |
| 노브 누르기 | `P3.3` |
| LED | `LED: WS2812` 모드에서 빨→초→파→흰 (색 순서 GRB), 눈에 보이는 LED 1개 |
| 부트로더 | BTVER 2.5.0, 제조사 펌웨어 때는 키 E, 업로드 후에는 키 D |

> 이 펌웨어는 노브 인코더를 P3.0/P3.1로 가정함. 새 장치에서 노브 회전에 반응이 없고 대신 GPIO 이름이 찍히면 인코더가 다른 핀에 연결된 것.

## 동작

| 입력 | 결과 |
|---|---|
| 키 누르기 | 그 키가 연결된 GPIO 이름 입력 (예: `P1.5`) |
| 노브 돌리기 | `CW` 또는 `CCW` 입력 (인코더를 P3.0/P3.1로 가정) |
| 노브 누르기 | `P3.3` 입력, LED 테스트 모드 전환 후 모드 이름 입력 |

- **감시 범위**: 키 6개로 추정한 핀만이 아니라 **남는 GPIO 전부**(P1.1, P1.4~P1.7, P3.2~P3.4)
- **LED 테스트 모드**(P3.4): 노브를 누를 때마다 `LED: OFF` → `LED: WS2812` → `LED: GPIO` → `LED: OFF` 순서로 바뀜

| 모드 | 동작 |
|---|---|
| `WS2812` | 0.5초마다 빨강 → 초록 → 파랑 → 흰색 (LED 8개분 신호 전송, 어둡게) |
| `GPIO` | 0.5초 간격으로 P3.4를 켜고 끔 |
| `OFF` | P3.4를 입력으로 되돌리고 다른 키처럼 감시 |

## 빌드 환경 (Arduino IDE)

1. Arduino IDE → **File → Preferences → Additional boards manager URLs**에 추가:
   ```
   https://raw.githubusercontent.com/DeqingSun/ch55xduino/ch55xduino/package_ch55xduino_mcs51_index.json
   ```
2. **Boards Manager**에서 `CH55xDuino MCS51 plain C core (non-C++)` 설치
3. **Tools** 메뉴 설정:
   - Board: **CH552 Board**
   - Clock Source: **24 MHz (internal), 5V**
   - USB Settings: **USER CODE w/ 148B USB ram**
   - Bootloader pin: **P1.5 pull-down**
4. `test_pinmap.ino`를 열고 **Sketch → Verify/Compile**

> ⚠️ **Bootloader pin 기본값은 `P3.6 (D+) pull-up`.** Arduino IDE의 Upload 버튼으로 올리면 이 값이 칩에 기록됨.
> - 기본값 그대로 올리면 **키 D로 부트로더에 들어갈 수 없게 됨**
> - 그 뒤에는 D+(12번 핀)와 3V3(16번 핀) 사이에 1.5~2kΩ 풀업을 연결해야 진입 가능

### Windows 빌드 오류 (CH55xDuino 0.0.26)

- **증상**: `sdcc.sh: line 94: syntax error: unexpected "("`
- **원인**: 패키지 버그. Windows에서 wrapper 스크립트를 busybox sh가 실행하는데, 0.0.26의 `sdcc.sh`가 bash 전용 배열 문법을 씀
- **0.0.25로 내리기는 안 됨**: Arduino IDE에 들어 있는 arduino-cli 1.5 이상에서 `sketch_merged.cpp` 오류
- **수정 파일**: `%LOCALAPPDATA%\Arduino15\packages\CH55xDuino\tools\MCS51Tools\2026.07.10\wrapper\sdcc.sh` (원본은 `sdcc.sh.orig`로 백업)
- **수정 내용**:
  - 93번째 줄 `if [ "$MARK" = "re12" ]` 블록의 `FILTERED_ARGS` 배열을 `set --`로 인수 목록을 다시 만드는 방식으로 교체
  - `"${FILTERED_ARGS[@]}"`를 `"$@"`로 변경
- 패키지를 다시 설치하거나 업데이트하면 수정이 사라짐 → 다시 적용
- 확인 결과(2026-10-25): 프로그램 6372바이트(44%), 전역 변수 169바이트로 빌드 성공

## 업로드 (`tools/flash.ps1` 권장)

1. Arduino IDE에서 **Sketch → Export Compiled Binary** → `build\CH55xDuino.mcs51.ch552\test_pinmap.ino.hex` 생성
2. 저장소 폴더에서 실행:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\flash.ps1 -Hex firmware\test_pinmap\build\CH55xDuino.mcs51.ch552\test_pinmap.ino.hex
   ```

3. 키 D를 누른 채(제조사 펌웨어가 있으면 키 E) USB 연결
   - 부트로더가 나타나는 즉시 업로드되고 진입 핀이 P1.5로 기록됨

- 업로드 후 원래 펌웨어는 사라짐
- 부트로더는 ROM에 있으므로 언제든 키 D를 누른 채 연결해서 다시 업로드 가능

### WCHISPTool로 올릴 때 (비권장)

- 첫 장치에서 WCHISPTool 자동 다운로드가 실패하고 진입 핀이 바뀌어 복구가 필요했음([TROUBLESHOOTING 2-3](../../docs/TROUBLESHOOTING.md#2-3-다운로드-실패-후-장치가-전혀-인식되지-않음-복구))
- 꼭 써야 한다면 자동 다운로드를 끄고 수동으로:

1. 위와 같이 `.hex` 파일 만들기
2. 키보드를 뺀 상태에서 **키 D를 누른 채 USB 연결** → 부트로더 진입(약 5초 동안만 유지)
   - 제조사 펌웨어가 남아 있을 때는 키 E로 진입
3. WCHISPTool에서 칩 `CH552`, 위의 `.hex` 파일을 선택하고 **Download**
4. ⚠️ **Download Cfg Pin(P1.5) 등 설정 값은 바꾸지 않음**
5. 업로드가 끝나면 USB 다시 연결

### Arduino IDE의 Upload 버튼

- Upload method: USB. `tools/flash.ps1`과 같은 업로더(vnproch55x) 사용, WCHISPTool이 설치한 WCH 드라이버로 동작
- 업로드할 때 **Bootloader pin 설정이 칩에 기록됨** → 반드시 `P1.5 pull-down`으로 맞춰 둠
- 부트로더 대기 시간(약 5초) 안에 업로드가 시작되도록 타이밍을 맞춰야 함

### WCHISPTool 다운로드 실패 기록 (2026-10-25)

- WCHISPTool 자동 다운로드 실패 뒤 부트로더 진입 핀이 P3.6으로 바뀌어 키로 진입 불가
- D+–3V3 풀업으로 진입 → CH55xduino의 업로더(`vnproch55x -r 2 -t CH552 -c 1 <hex>`, `-c 1` = P1.5)로 복구
- 앞으로는 이 업로더(또는 Arduino IDE Upload + Bootloader pin P1.5) 권장

## 테스트 방법

1. **메모장**을 열고 커서를 둠
2. Windows 입력기를 **영문 모드**로 둠(한글 모드면 `P1.1`이 `ㅖ1.1`로 입력됨)
3. 윗면 기준으로 키를 **A → B → C → D → E → F** 순서로 하나씩 누름
4. 노브를 **시계 방향으로 몇 칸**, **반시계 방향으로 몇 칸** 돌림
5. 노브를 눌러 LED 모드를 바꿔 가며, 어느 모드에서 LED가 켜지는지 확인
6. 메모장에 입력된 결과를 그대로 알려줌

### 결과 기록

| 확인 항목 | 결과 |
|---|---|
| A | |
| B | |
| C | |
| D | |
| E | |
| F | |
| 노브 시계 방향 | `CW` / `CCW` / 없음 |
| 노브 반시계 방향 | |
| 노브 누르기 | |
| LED: WS2812 모드 | 켜짐(색 변화) / 꺼짐 |
| LED: GPIO 모드 | 점멸 / 꺼짐 |

- 노브 한 칸에 `CW`가 두 번씩 나오거나 두 칸에 한 번만 나오면 → 인코더의 칸당 펄스 수가 다른 것이니 알려줌
- WS2812 모드에서 색 순서가 다르게 보이면(예: 빨강 대신 초록) → LED의 색 순서(GRB/RGB)가 다른 것
