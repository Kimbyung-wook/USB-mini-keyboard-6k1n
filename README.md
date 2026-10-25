# USB-mini-keyboard-6k1n

상용 CH552G 미니 매크로 키보드(키 6개 + 노브 1개)에 커스텀 펌웨어를 올려서, 키마다 **긴 문자열**을 HID 키보드 입력으로 출력하고 PC의 GUI 프로그램에서 문자열을 확인하고 수정하는 프로젝트입니다. 펌웨어 업로드, 설정, 문자열 출력을 모두 USB 포트 하나로 처리합니다.

## 현재 상태

| 항목 | 상태 |
|---|---|
| 하드웨어 조사 (핀 매핑, LED, 부트로더) | ✅ 완료 (`firmware/test_pinmap`으로 확인) |
| 설정 통신 규격 | ✅ [docs/PROTOCOL.md](docs/PROTOCOL.md) |
| 설정 GUI | ✅ 가상 장치(`--mock`)로 동작 확인, 실제 장치와는 아직 미검증 |
| 본 펌웨어 (규격 구현, 문자열 저장, 매크로 출력) | ⏳ 예정 |

## 하드웨어 요약

| 입력 | GPIO |
|---|---|
| 키 A / B / C (윗줄) | P1.1 / P1.7 / P1.6 |
| 키 D / E / F (아랫줄) | P1.5 / P1.4 / P3.2 |
| 노브 회전 | P3.0 / P3.1 |
| 노브 누르기 | P3.3 |
| LED | P3.4, WS2812 (GRB) |

- MCU: CH552G (Flash 16KB, RAM 1KB + 256B, DataFlash 128B), ROM 부트로더 2.5.0
- 부트로더 진입: **키 D를 누른 채 USB 연결** (제조사 펌웨어가 있을 때는 키 E)

## 폴더 구조

| 경로 | 내용 |
|---|---|
| [PLAN.md](PLAN.md) | 전체 계획, 하드웨어 조사 기록, 단계별 진행 |
| [docs/PROTOCOL.md](docs/PROTOCOL.md) | 펌웨어와 GUI가 공유하는 Vendor HID 설정 통신 규격 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 빌드 오류, 업로드 실패와 복구 등 실제로 겪은 문제와 해결 방법 |
| [firmware/test_pinmap/](firmware/test_pinmap/) | 하드웨어 확인용 테스트 펌웨어. **새 장치를 구하면 먼저 이걸로 점검** |
| [gui/](gui/) | PySide6 설정 프로그램 |
| [tools/](tools/) | `flash.ps1`(부트로더 대기 후 자동 업로드), `usb_monitor.ps1`(USB 장치 감지 기록) |

## 빠른 시작

**펌웨어 빌드**: Arduino IDE + CH55xDuino 0.0.26. 보드 설정과 Windows 빌드 오류 패치는 [firmware/test_pinmap/README.md](firmware/test_pinmap/README.md)를 보세요.

**펌웨어 업로드**

```powershell
powershell -ExecutionPolicy Bypass -File tools\flash.ps1 -Hex <빌드한 .hex 파일>
```

스크립트를 실행한 뒤 키 D를 누른 채 키보드를 연결합니다.

**GUI 실행**: 설치 방법은 [gui/README.md](gui/README.md)를 보세요.

```powershell
gui\.venv\Scripts\python -m gui --mock
```

## 라이선스 참고

`firmware/test_pinmap/src/userUsbHidKeyboard/`의 USB 코드는 [CH55xDuino](https://github.com/DeqingSun/ch55xduino) HidKeyboard 예제에서 가져왔습니다(LGPL-2.1).
