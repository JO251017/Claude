# 미리 알림 (Reminder App)

바닐라 JS로 만든 브라우저 기반 알림 관리 웹앱.

## 프로젝트 구조

```
index.html   — 마크업 (폼, 카드 컨테이너, 알림 배너)
style.css    — 스타일 (반응형, 카드 색상 상태)
app.js       — 전체 로직
```

## 핵심 데이터

```js
// localStorage 키
STORAGE_KEY = 'reminders'

// 알림 객체 구조
{ id, title, datetime, note, done, notified }
```

## 주요 함수 (app.js)

| 함수 | 역할 |
|------|------|
| `renderReminders()` | 카드 목록 전체 재렌더링 |
| `toggleDone(id)` | 완료 토글 |
| `deleteReminder(id)` | 삭제 |
| `checkReminders()` | 만료 알림 폴링 (30초 간격) |
| `showNotification(title)` | 배너 + 브라우저 알림 표시 |
| `escapeHtml(str)` | XSS 방지용 이스케이프 |

## 카드 상태

- `upcoming` — 초록 테두리, 미완료·미만료
- `overdue` — 빨간 테두리, 미완료·기한 초과
- `done` — 회색, 완료

## 제약사항

- 빌드 도구 없음, 외부 의존성 없음
- 백엔드 없음 — 모든 데이터는 localStorage
- 한국어 UI (lang="ko", ko-KR 로케일)
