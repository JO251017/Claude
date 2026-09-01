# 펫 캐릭터 이미지 에셋 (`frontend/assets/pet/`)

2026-09-01, 새 펫 캐릭터 이미지 지시서(공식 디자인 확정) 반영. 이 폴더에
아래 규칙대로 파일을 넣으면 앱이 **코드 수정 없이** 자동으로 인식해서 쓴다
(`frontend/app.js`의 `petAssetUrl`/`avatarImageHtml`/`avatarFaceImageHtml`).

## 필수 — 단계별 기본 이미지 (10장)

```
lv1.png ~ lv10.png
```

10단계 순서/이름 (사용자가 전달한 "[개별 PNG 파일 세트]" 참조 이미지 1~10번
패널 순서 그대로, `app.js`의 `AVATAR_GROWTH_STAGES`와 반드시 일치해야 함):

| 파일 | 단계 | 이름 |
|---|---|---|
| lv1.png | 1 | 아기 백구 |
| lv2.png | 2 | 꼬마 백구 |
| lv3.png | 3 | 똑똑한 백구 |
| lv4.png | 4 | 탐험가 백구 |
| lv5.png | 5 | 쓸모 전문가 백구 |
| lv6.png | 6 | 절약 고수 백구 |
| lv7.png | 7 | 동네 보물사냥꾼 백구 |
| lv8.png | 8 | 쓸모 마스터 I |
| lv9.png | 9 | 쓸모 마스터 II |
| lv10.png | 10 | 전설의 쓸모 백구 |

권장 규격: 정사각형에 가까운 비율, 배경 투명 PNG(또는 WebP — 확장자만
`.webp`로 바꾸면 동일하게 동작하도록 코드를 고치면 됨, 현재는 `.png` 고정).
모바일 우선 표시 크기는 32px(지도 마커)/88×100px(MY탭 무대) 두 군데뿐이라
원본은 그보다 넉넉히 큰 해상도(예: 512×512)로 주면 확대해도 흐려지지 않는다.

## 선택 — 표정/포즈 오버레이

```
lv{N}_{state}.png   (N = 1~10)
```

- 표정(6종, C안): `normal`(=기본 lv{N}.png라 파일 안 만들어도 됨), `happy`,
  `excited`, `proud`, `surprised`, `sleepy`
- 포즈(5종, D안): `walking`, `jumping`, `sleeping`, `celebrating`

예: `lv3_happy.png`, `lv7_sleepy.png`. 특정 단계에 특정 상태 파일이 없으면
자동으로 `lv{N}.png`(기본)로 대체되고, 그것도 없으면(에셋 아직 미전달)
기존 절차적 SVG 렌더러로 자동 전환된다 — 파일이 하나도 없는 지금도 앱은
정상 작동한다.

## 어디에 쓰이는지

- MY탭 무대 아바타(`renderAvatarSpriteFrame`) — `lv{N}.png` + 표정 오버레이
- 지도 위 "내 위치" 마커(`originAvatarOverlayContent`) — `lv{N}.png`를
  CSS로 얼굴 부분만 크롭해서 표시(전용 얼굴 크롭 에셋 없음)
- **옷장 미리보기는 제외** — 목줄/리본 색상 커스터마이징은 PNG로 표현할
  방법이 없어서 그 화면만 기존 SVG를 계속 쓴다(의도적 결정, `app.js`
  `renderClosetPreview` 주석 참고).

## 파일이 하나도 없을 때

전부 기존 SVG(절차적 픽셀아트 강아지)로 자동 대체되어 표시된다 — 화면이
깨지거나 빈 이미지가 뜨지 않는다.
