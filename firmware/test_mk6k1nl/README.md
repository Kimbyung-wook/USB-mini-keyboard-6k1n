# test_mk6k1nl: MK6K1NL 하드웨어 확인용 테스트 펌웨어

> 확인한 핀 배치는 [docs/PINMAP.md](../../docs/PINMAP.md)에 다이어그램으로 정리되어 있습니다.

**MK6K1NL**(6키 + 노브 1개, CH552G, 키마다 LED)의 키 핀과 LED를 확인하는 펌웨어입니다. **LED가 몇 개이고 어느 순서로 이어져 있는지** 보고, 키 핀도 [test_pinmap](../test_pinmap/README.md)처럼 함께 확인합니다. 본 펌웨어의 보드 파일은 `firmware/macro_keyboard/src/boards/mk6k1nl.h`입니다.

| 보드 | 생김새 | 테스트 펌웨어 |
|---|---|---|
| MK6K1N | 6키 + 노브, 눈에 보이는 LED 1개 | [test_pinmap](../test_pinmap/README.md) |
| **MK6K1NL** | 6키 + 노브, **키마다 LED** | 이 펌웨어 |

CH552G는 키 6개, 노브(P3.0/P3.1/P3.3), LED 데이터(P3.4)로 핀을 모두 씁니다. 그래서 키마다 있는 LED도 **P3.4의 WS2812 체인에 이어져 있다고** 보고, 체인 위치를 하나씩 켜 봅니다. 위치는 넉넉하게 24개까지 신호를 보냅니다.

## 동작

노브를 누를 때마다 모드가 바뀌고 `MODE: …`가 입력됩니다.

| 모드 | LED | 입력 |
|---|---|---|
| **WALK** (처음) | 한 위치만 흰색. 노브를 시계 방향으로 돌리면 다음 위치, 반대로 돌리면 이전 위치 | `LED n` |
| **AUTO** | 켜진 위치가 1초마다 다음으로. 위치마다 빨강 → 초록 → 파랑 차례 | `LED n` |
| **COLOR** | 모든 위치가 0.5초마다 빨강 → 초록 → 파랑 → 흰색 | 없음 |
| **OFF** | 모두 꺼짐 | 없음 |
| **RAW** | 모두 꺼짐 | 인코더 두 선이 바뀔 때마다 `AB xy`(x = A/P3.0, y = B/P3.1, 1 = 높음), 키를 누르고 뗄 때 `P1.6` / `P1.6 up` |
| **RAW+LED** | 누르고 있는 키의 LED만 초록 | RAW와 같음 (LED가 인코더를 흔드는지 보기) |

- 키를 누르면 그 키의 GPIO 이름(예: `P1.5`)이 입력됩니다.
- 노브를 누른 채 꽂으면 부트로더로 들어갑니다. 업로드 때 진입 핀이 P1.5로 기록되므로 키 D(P1.5)를 누른 채 꽂아도 됩니다.
- 켜진 위치 중 마지막 번호 + 1이 체인의 LED 수입니다.
- 메모장 등을 **영문 입력 상태**로 두고 보세요(한글 상태면 `MODE`가 `ㅡㅒㅇㄸ`로 입력됨).

## 빌드와 업로드

Board options: CH552 Board, 24 MHz (internal) 5V, USB Settings: **USER CODE w/ 148B USB ram**, Bootloader pin: **P1.5 pull-down**

```powershell
& "$env:LOCALAPPDATA\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" compile --fqbn CH55xDuino:mcs51:ch552:usb_settings=user148,bootloader_pin=p15 --output-dir firmware\test_mk6k1nl\build firmware\test_mk6k1nl
powershell -ExecutionPolicy Bypass -File tools\flash.ps1 -Hex firmware\test_mk6k1nl\build\test_mk6k1nl.ino.hex
```

처음 올릴 때(제조사 펌웨어)는 키를 눌러서는 부트로더에 들어갈 수 없어서 **D+ 풀업**이 필요합니다(아래 결과 표). 한 번 올리면 진입 핀이 P1.5로 기록되어, 그다음부터는 키 D나 노브를 누른 채 꽂으면 됩니다.

확인 결과(2026-10-31): 프로그램 7311바이트(50%), 전역 변수 244바이트(RAW 모드 포함).

## MK6K1NL 첫 장치의 결과 (2026-10-31)

| 확인 항목 | 결과 |
|---|---|
| 칩 | CH552, 부트로더 2.5.0, 칩 고유 ID `5E-E0-6E-BF` |
| 제조사 펌웨어 | USB ID `1189:8890` |
| 부트로더 진입 (제조사 펌웨어) | 키를 누른 채 꽂아도 들어가지 않음. **D+ 풀업**(12번–16번 핀, 1.5~2kΩ)으로 진입 ([TROUBLESHOOTING 2-3](../../docs/TROUBLESHOOTING.md#2-3-다운로드-실패-후-장치가-전혀-인식되지-않음-복구)) |
| 키 A~F | `P1.1` / `P1.7` / `P1.6` / `P1.5` / `P1.4` / `P3.2` (MK6K1N과 같음) |
| 노브 신호 (RAW) | 한 칸마다 시계 방향 `11 → 10 → 00 → 01 → 11`, 반시계 방향 `11 → 01 → 00 → 10 → 11`. 칸에서 쉴 때 `11` (MK6K1N과 같음) |
| 키 C를 누를 때 `CCW` | 본 펌웨어에서 키 C(노브 옆)를 누르면 `CCW`가 입력됨. RAW에서 노브가 칸 사이(`AB 10`)에 걸려 있었고, 키 C를 누르는 흔들림으로 B선이 `10`↔`11`을 오가면 반시계 한 칸으로 처리되던 것. 노브를 칸에 두거나 잡고 누르면 `AB`가 바뀌지 않음. v1.5.0에서 한 칸 중 같은 방향 2단계 이상만 회전으로 세도록 고침 |
| 노브 | 이 펌웨어는 회전을 입력하지 않아서, 본 펌웨어 v1.5.0(MK6K1NL)에 슬롯마다 이름을 넣어 확인: 시계 방향 `CW`, 반시계 방향 `CCW`, 누르기 `PRESS` (MK6K1N과 같음, 2026-10-31) |
| LED 수 | **6개**, 키마다 하나 (P3.4 체인) |
| 체인 순서 | 0 = A, 1 = B, 2 = C, 3 = D, 4 = E, 5 = F (윗줄 왼쪽부터, 그다음 아랫줄) |
| 색 순서 | AUTO에서 A/D 빨강, B/E 초록, C/F 파랑. COLOR에서 6개 모두 빨강 → 초록 → 파랑 → 흰색 반복: **GRB** (MK6K1N과 같음) |
| 6번 이후 위치 | 켜지는 LED 없음 |
| OFF | 6개 모두 꺼짐 |
