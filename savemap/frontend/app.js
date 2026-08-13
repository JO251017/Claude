const API_BASE = '/v1';

// RPG 요소(레벨/칭호/XP 노출)는 잠시 비활성화 — 기본 베이스 구조 완성 후 다시
// 입힌다(사용자 지시, 2026-08-12). 백엔드는 XP_REWARD(app/domain/enums.py)를
// 그대로 계속 적립하고, 화면에서만 안 보여준다.

const CATEGORY_LABELS = {
  free: '무료',
  discount: '할인',
  closing_soon: '마감임박',
  free_parking: '무료주차',
  local_benefit: '지역혜택',
};

const ASSET_CATEGORY_LABELS = {
  cafe: '카페',
  food: '음식',
  shopping: '쇼핑',
  transport: '교통',
  culture: '문화',
  etc: '기타',
};

// 라인 아이콘 세트 (이모지 대체용, currentColor로 테마 색상 상속)
const ICON_SVG_ATTRS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';
const ICONS = {
  sprout: `<svg ${ICON_SVG_ATTRS}><path d="M12 21V10"/><path d="M12 10c0-3-2.5-5-6-5 0 3.5 2.5 6 6 6"/><path d="M12 13c0-3 2.5-5 6-5 0 3.5-2.5 6-6 6"/></svg>`,
  compass: `<svg ${ICON_SVG_ATTRS}><circle cx="12" cy="12" r="9"/><path d="M14.5 9.5 13 13l-3.5 1.5L11 11z"/></svg>`,
  backpack: `<svg ${ICON_SVG_ATTRS}><rect x="5" y="8" width="14" height="13" rx="3"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/><path d="M9 13h6"/></svg>`,
  map: `<svg ${ICON_SVG_ATTRS}><path d="M9 4 4 6v14l5-2 6 2 5-2V4l-5 2-6-2Z"/><path d="M9 4v14"/><path d="M15 6v14"/></svg>`,
  medal: `<svg ${ICON_SVG_ATTRS}><circle cx="12" cy="15" r="6"/><path d="M9 3 12 9l3-6"/><path d="M12 12v6"/></svg>`,
  shield: `<svg ${ICON_SVG_ATTRS}><path d="M12 3 5 6v6c0 5 3 8 7 9 4-1 7-4 7-9V6z"/><path d="m9.5 12 1.8 1.8L15 10"/></svg>`,
  crown: `<svg ${ICON_SVG_ATTRS}><path d="m4 8 3 3 5-6 5 6 3-3-1.5 10h-13Z"/><path d="M6 20h12"/></svg>`,
  swap: `<svg ${ICON_SVG_ATTRS}><path d="M7 7h11l-3-3"/><path d="M17 17H6l3 3"/></svg>`,
  user: `<svg ${ICON_SVG_ATTRS}><circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-4 3-6.5 7-6.5s7 2.5 7 6.5"/></svg>`,
  people: `<svg ${ICON_SVG_ATTRS}><circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3.5 20c0-3.5 2.5-6 5.5-6s5.5 2.5 5.5 6"/><path d="M15 14.5c2.5 0 4.5 2 4.5 5.5"/></svg>`,
  pin: `<svg ${ICON_SVG_ATTRS}><path d="M12 21s7-6.5 7-12a7 7 0 0 0-14 0c0 5.5 7 12 7 12Z"/><circle cx="12" cy="9" r="2.5"/></svg>`,
  refresh: `<svg ${ICON_SVG_ATTRS}><path d="M4 12a8 8 0 0 1 14-5.3L21 9"/><path d="M21 4v5h-5"/><path d="M20 12a8 8 0 0 1-14 5.3L3 15"/><path d="M3 20v-5h5"/></svg>`,
  check: `<svg ${ICON_SVG_ATTRS}><path d="m5 12 5 5 9-11"/></svg>`,
};

// --- 아바타 성장(다마고치식, 2-4, 2026-08-13) ---
// 예전엔 절약금액 레벨(compute_savings_level) 기준이었다. 사용자 지시: "다마고치
// 키우기 같은 형식 — 맵에서 가게 인증이나 추천기능을 통해 아바타가 성장하는
// 구조로 가". 그래서 이제 발견(discovered_place_count) + 방문(visit_count) +
// 추천(recommend_count) — 이미 실제 행동에서 결정론적으로 계산되는 세 칭호(2-2)의
// 원본 카운트를 그대로 합산한 값 하나("성장치")로 단계를 정한다. 별도로 지어낸
// 점수는 없다.
const AVATAR_GROWTH_STAGES = [
  { minScore: 0, icon: 'sprout', name: '씨앗' },
  { minScore: 10, icon: 'compass', name: '새싹 탐험가' },
  { minScore: 25, icon: 'backpack', name: '배낭 여행자' },
  { minScore: 60, icon: 'map', name: '지도 마스터' },
  { minScore: 100, icon: 'medal', name: '메달리스트' },
  { minScore: 180, icon: 'shield', name: '수호자' },
  { minScore: 300, icon: 'crown', name: 'SaveMap 전설' },
];

function avatarGrowthStageFor(growthScore) {
  let stageIndex = 0;
  AVATAR_GROWTH_STAGES.forEach((stage, i) => {
    if (growthScore >= stage.minScore) stageIndex = i;
  });
  const stage = AVATAR_GROWTH_STAGES[stageIndex];
  const next = AVATAR_GROWTH_STAGES[stageIndex + 1] || null;
  return {
    stageIndex,
    stageNumber: stageIndex + 1,
    totalStages: AVATAR_GROWTH_STAGES.length,
    name: stage.name,
    icon: stage.icon,
    isMaxStage: next === null,
    progressPct: next
      ? Math.min(100, Math.round(((growthScore - stage.minScore) / (next.minScore - stage.minScore)) * 100))
      : 100,
    remainingToNext: next ? Math.max(next.minScore - growthScore, 0) : 0,
  };
}

// 성장 단계가 오를수록 아바타 주변 장식(별)이 하나씩 늘어난다 — 다마고치처럼
// "몸집/장식이 늘어나는" 느낌을 레이어드 SVG 대신 가볍게 구현.
function characterAvatarHtmlFor(stageIndex) {
  const stage = AVATAR_GROWTH_STAGES[stageIndex];
  const decos = [];
  if (stageIndex >= 2) decos.push('<span class="avatar-deco avatar-deco--1" aria-hidden="true">⭐</span>');
  if (stageIndex >= 4) decos.push('<span class="avatar-deco avatar-deco--2" aria-hidden="true">⭐</span>');
  if (stageIndex >= 6) decos.push('<span class="avatar-deco avatar-deco--3" aria-hidden="true">✨</span>');
  return ICONS[stage.icon] + decos.join('');
}

// 발견/방문/추천 성공 직후 아바타가 살짝 반응한다(다마고치의 "먹이 주면 바로
// 반응" 감각) — 별도 API 호출 없이 이미 성공한 응답 시점에 클래스만 토글.
function triggerAvatarGrowthFeedback() {
  const el = document.getElementById('character-avatar');
  if (!el) return;
  el.classList.remove('avatar-bounce');
  void el.offsetWidth; // 리플로우를 강제해서 애니메이션을 처음부터 다시 재생
  el.classList.add('avatar-bounce');
}

let merchantPlaces = [];

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatWon(amount) {
  return `₩${Math.round(amount || 0).toLocaleString()}`;
}

// --- 절약 토스트(5번 항목, 2026-08-13) ---
// 발견/추천/인증 성공 직후 "지금 절약하고 있다"는 걸 짧게 체감시킨다. 문구에는
// 항상 실제 응답값만 쓴다(지어낸 숫자 없음) — 인증 성공 시 amount는 서버가 계산한
// 실제 절약액이고, 발견/추천은 금액이 없는 행동이라 금액 없이 완료만 알린다.
function showSavingsToast(text) {
  const toast = document.createElement('div');
  toast.className = 'savings-toast';
  toast.textContent = text;
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('savings-toast--show'));
  setTimeout(() => {
    toast.classList.remove('savings-toast--show');
    setTimeout(() => toast.remove(), 300);
  }, 1800);
}

async function apiFetch(path, options = {}) {
  const headers = { 'Content-Type': 'application/json' };
  const token = await getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const resp = await fetch(`${API_BASE}${path}`, {
    headers,
    ...options,
  });
  const data = await resp.json().catch(() => null);
  if (!resp.ok) {
    const message = data?.detail?.message || data?.detail || `요청 실패 (${resp.status})`;
    throw new Error(message);
  }
  return data;
}

// --- Supabase Auth (SaveMap 전체에서 공용으로 사용하는 로그인 상태) ---
const supabaseClient =
  window.supabase && window.SAVEMAP_CONFIG?.supabaseUrl && window.SAVEMAP_CONFIG?.supabaseAnonKey
    ? window.supabase.createClient(window.SAVEMAP_CONFIG.supabaseUrl, window.SAVEMAP_CONFIG.supabaseAnonKey)
    : null;

async function getAccessToken() {
  if (!supabaseClient) return null;
  const { data } = await supabaseClient.auth.getSession();
  return data?.session?.access_token || null;
}

function toggleGuard(loginId, authedId, session) {
  const loginEl = document.getElementById(loginId);
  const authedEl = document.getElementById(authedId);
  if (!loginEl || !authedEl) return;
  if (session) {
    loginEl.classList.add('hidden');
    authedEl.classList.remove('hidden');
  } else {
    loginEl.classList.remove('hidden');
    authedEl.classList.add('hidden');
  }
}

function renderAuthState(session) {
  toggleGuard('my-login', 'my-authed', session);
  toggleGuard('merchant-guard', 'merchant-authed', session);
  toggleGuard('exchange-login', 'exchange-authed', session);

  const emailEl = document.getElementById('auth-user-email');
  loadSavingsBadge();

  if (session) {
    if (emailEl) emailEl.textContent = session.user.email;
    loadMyProfile();
    loadPlaces().then(loadMenuItems);
    loadOffers();
    loadMyAssets();
  }
  loadAssets();
}

if (supabaseClient) {
  supabaseClient.auth.getSession().then(({ data }) => renderAuthState(data.session));
  supabaseClient.auth.onAuthStateChange((_event, session) => renderAuthState(session));

  document.getElementById('auth-login-btn').addEventListener('click', async () => {
    const email = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value;
    const msgEl = document.getElementById('auth-msg');
    if (!email || !password) {
      msgEl.innerHTML = '<p class="error-msg">이메일과 비밀번호를 입력해주세요.</p>';
      return;
    }
    msgEl.innerHTML = '<p class="empty-msg">로그인 중...</p>';
    const { error } = await supabaseClient.auth.signInWithPassword({ email, password });
    msgEl.innerHTML = error ? `<p class="error-msg">${escapeHtml(error.message)}</p>` : '';
  });

  document.getElementById('auth-signup-btn').addEventListener('click', async () => {
    const email = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value;
    const msgEl = document.getElementById('auth-msg');
    if (!email || !password) {
      msgEl.innerHTML = '<p class="error-msg">이메일과 비밀번호를 입력해주세요.</p>';
      return;
    }
    if (password.length < 6) {
      msgEl.innerHTML = '<p class="error-msg">비밀번호는 6자 이상이어야 합니다.</p>';
      return;
    }
    msgEl.innerHTML = '<p class="empty-msg">가입 처리 중...</p>';
    const { error } = await supabaseClient.auth.signUp({ email, password });
    msgEl.innerHTML = error
      ? `<p class="error-msg">${escapeHtml(error.message)}</p>`
      : '<p class="empty-msg">가입 확인 이메일을 보냈습니다. 메일함을 확인해주세요.</p>';
  });

  document.getElementById('auth-logout-btn').addEventListener('click', async () => {
    await supabaseClient.auth.signOut();
  });
} else {
  console.warn('Supabase 설정이 없어 로그인을 사용할 수 없습니다 (/config.js 확인 필요).');
  // 로그인 없이도 공개 데이터(절약 레벨 기본값, 교환 가능한 자산 목록)는 정상적으로 보여야 한다.
  loadSavingsBadge();
  loadAssets();
}

// --- 하단 네비게이션 (화면 전환) + data-goto 바로가기 버튼 공용 ---
function switchScreen(name) {
  document.querySelectorAll('.nav-btn').forEach((b) => b.classList.toggle('active', b.dataset.screen === name));
  document.querySelectorAll('.screen').forEach((s) => s.classList.toggle('active', s.id === `screen-${name}`));
}

document.querySelectorAll('.nav-btn').forEach((btn) => {
  btn.addEventListener('click', () => switchScreen(btn.dataset.screen));
});

document.querySelectorAll('[data-goto]').forEach((btn) => {
  btn.addEventListener('click', () => switchScreen(btn.dataset.goto));
});

// --- RPG 희귀도 등급 (예상 절약률 기준, MAP 카드 표시용) ---
function getRarityTier(savingsRate) {
  if (savingsRate >= 50) return { cls: 'rarity-legendary', label: '레전더리' };
  if (savingsRate >= 30) return { cls: 'rarity-epic', label: '에픽' };
  if (savingsRate >= 10) return { cls: 'rarity-rare', label: '레어' };
  if (savingsRate > 0) return { cls: 'rarity-uncommon', label: '언커먼' };
  return { cls: 'rarity-common', label: '일반' };
}

// --- 절약 레벨 뱃지 (MAP 상단, "실제 절약금액" 기반 — XP 아님) ---
async function loadSavingsBadge() {
  const ringEl = document.getElementById('savings-ring');
  const levelEl = document.getElementById('savings-level');
  const titleEl = document.getElementById('savings-title');
  const subEl = document.getElementById('savings-sub');
  const token = await getAccessToken();

  if (!token) {
    ringEl.style.setProperty('--xp-pct', '0%');
    levelEl.textContent = 'Lv.1';
    titleEl.textContent = '절약 초보';
    subEl.textContent = '로그인하고 시작하기';
    return;
  }

  try {
    const s = await apiFetch('/users/me/savings-summary');
    ringEl.style.setProperty('--xp-pct', `${s.progress_pct}%`);
    levelEl.textContent = `Lv.${s.level}`;
    titleEl.textContent = s.title;
    subEl.textContent = `${formatWon(s.total_saved)} 절약`;
  } catch (err) {
    console.warn('절약 레벨 정보를 불러오지 못했습니다:', err.message);
  }
}

// --- MY: 나의 절약 탐험가 ---
async function loadMyProfile() {
  try {
    const s = await apiFetch('/users/me/savings-summary');

    // 아바타 성장(다마고치식, 2-4, 2026-08-13) — 발견+방문+추천 실제 카운트
    // 합산("성장치")으로 단계를 정한다. 절약금액 레벨과는 완전히 분리된 축.
    const growthScore = s.discovered_place_count + s.visit_count + s.recommend_count;
    const growth = avatarGrowthStageFor(growthScore);
    const avatarEl = document.getElementById('character-avatar');
    avatarEl.innerHTML = characterAvatarHtmlFor(growth.stageIndex);
    avatarEl.classList.toggle('avatar-halo', growth.isMaxStage);
    document.getElementById('my-title').textContent = growth.name;
    document.getElementById('my-level-badge').textContent = `성장 ${growth.stageNumber}/${growth.totalStages}단계`;
    document.getElementById('my-saving-bar').style.width = `${growth.progressPct}%`;
    document.getElementById('my-next-level-text').textContent = growth.isMaxStage
      ? '최고 성장 단계에 도달했어요!'
      : `다음 성장까지 ${growth.remainingToNext}`;

    // 절약 요약 재구조화(2-1, 2026-08-13) — all-time 누적 하나 대신 오늘 누적을
    // 메인으로, 주간/한달/연간을 나란히 보여준다.
    document.getElementById('my-today-saved').textContent = formatWon(s.today_saved);
    document.getElementById('my-weekly-saved').textContent = formatWon(s.weekly_saved);
    document.getElementById('my-monthly-saved').textContent = formatWon(s.monthly_saved);
    document.getElementById('my-yearly-saved').textContent = formatWon(s.yearly_saved);
    document.getElementById('my-cert-count').textContent = s.certification_count;

    // 칭호 3종(발견/방문/추천, 2-2, 2026-08-13) — 절약금액 레벨과 독립된 축이라
    // 별도 필드(explorer_*/visit_*/recommend_*)로 채운다. 셋 다 같은 문구 패턴
    // ("N / 다음까지 M")으로 통일해서 사용자가 세 지표를 한눈에 비교하게 한다.
    const titleProgressText = (count, unit, remaining) =>
      remaining == null ? `${count}${unit} · 최고 칭호` : `${count}${unit} · 다음까지 ${remaining}${unit}`;
    document.getElementById('my-explorer-title').textContent = s.explorer_title;
    document.getElementById('my-explorer-count').textContent = titleProgressText(
      s.discovered_place_count, '곳', s.explorer_remaining_to_next
    );
    document.getElementById('my-visit-title').textContent = s.visit_title;
    document.getElementById('my-visit-count').textContent = titleProgressText(
      s.visit_count, '회', s.visit_remaining_to_next
    );
    document.getElementById('my-recommend-title').textContent = s.recommend_title;
    document.getElementById('my-recommend-count').textContent = titleProgressText(
      s.recommend_count, '회', s.recommend_remaining_to_next
    );

    const badges = [];
    if (s.certification_count >= 1) badges.push('첫 절약 인증');
    if (s.total_saved >= 100_000) badges.push('10만원 절약 달성');
    if (s.total_saved >= 1_000_000) badges.push('절약왕 달성');
    document.getElementById('my-badges').innerHTML = badges.length
      ? badges.map((b) => `<span class="badge-pill">${b}</span>`).join('')
      : '<span class="empty-msg">아직 획득한 배지가 없어요. 절약 인증을 시작해보세요!</span>';
  } catch (err) {
    console.warn('내 프로필 정보를 불러오지 못했습니다:', err.message);
  }

  try {
    const assets = await apiFetch('/exchange/assets/mine');
    document.getElementById('my-asset-count').textContent = assets.length;
  } catch {
    // 자산 개수는 부가 정보라 실패해도 무시
  }

  // 사업자 콘솔 바로가기는 인증된 사용자에게만 보인다(2-3, 2026-08-13) — 서버도
  // require_merchant_verified로 실제 접근을 막지만, 인증 안 된 사용자가 버튼을
  // 눌렀다가 403을 만나는 것보단 애초에 안 보이는 게 낫다.
  try {
    const status = await apiFetch('/users/me/merchant-status');
    document.getElementById('merchant-console-btn').classList.toggle('hidden', !status.is_verified_merchant);
  } catch {
    // 조회 실패 시엔 안전하게 숨긴 상태를 유지
  }
}

// --- 바텀시트: 드래그로 높이를 자유롭게 조절 (기존엔 탭으로 두 단계만 토글되는
// 고정 높이였음 — 사용자 지시, 2026-08-13). 핸들을 눌러서 끌면 그 위치까지 실시간으로
// 따라오고, 끌지 않고 탭만 하면 기존처럼 기본/확장 두 단계를 토글한다.
const bottomSheet = document.getElementById('bottom-sheet');
const sheetToggleBtn = document.getElementById('sheet-toggle');

const SHEET_MIN_PX = 110; // 핸들 + 개수 표시만 보이는 최소 높이
const SHEET_DEFAULT_RATIO = 0.42;
const SHEET_EXPANDED_RATIO = 0.82;
const SHEET_MAX_RATIO = 0.88;

function sheetContainerHeight() {
  return bottomSheet.parentElement.clientHeight;
}

function setSheetHeightPx(px) {
  const maxPx = sheetContainerHeight() * SHEET_MAX_RATIO;
  bottomSheet.style.height = `${Math.min(Math.max(px, SHEET_MIN_PX), maxPx)}px`;
}

setSheetHeightPx(sheetContainerHeight() * SHEET_DEFAULT_RATIO);

let sheetDrag = null;

sheetToggleBtn.addEventListener('pointerdown', (e) => {
  sheetDrag = { startY: e.clientY, startHeight: bottomSheet.getBoundingClientRect().height, moved: false };
  bottomSheet.classList.add('dragging');
  sheetToggleBtn.setPointerCapture(e.pointerId);
});

sheetToggleBtn.addEventListener('pointermove', (e) => {
  if (!sheetDrag) return;
  const dy = sheetDrag.startY - e.clientY; // 위로 끌수록 커짐
  if (Math.abs(dy) > 6) sheetDrag.moved = true;
  setSheetHeightPx(sheetDrag.startHeight + dy);
});

function endSheetDrag() {
  if (!sheetDrag) return;
  bottomSheet.classList.remove('dragging');
  if (!sheetDrag.moved) {
    // 드래그 없이 탭만 했으면 기존 동작대로 기본/확장 두 단계를 토글한다.
    const container = sheetContainerHeight();
    const mid = (container * SHEET_DEFAULT_RATIO + container * SHEET_EXPANDED_RATIO) / 2;
    const isExpanded = bottomSheet.getBoundingClientRect().height > mid;
    setSheetHeightPx(container * (isExpanded ? SHEET_DEFAULT_RATIO : SHEET_EXPANDED_RATIO));
  }
  sheetDrag = null;
}

sheetToggleBtn.addEventListener('pointerup', endSheetDrag);
sheetToggleBtn.addEventListener('pointercancel', endSheetDrag);

// --- 내 위치 사용 ---
const useLocationBtn = document.getElementById('use-location-btn');
const useLocationLabel = document.getElementById('use-location-label');
useLocationBtn.addEventListener('click', () => {
  if (!navigator.geolocation) {
    alert('이 브라우저는 위치 정보를 지원하지 않습니다.');
    return;
  }
  const originalLabel = useLocationLabel.textContent;
  useLocationBtn.disabled = true;
  useLocationLabel.textContent = '위치 확인 중...';

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;
      document.getElementById('s-lat').value = lat.toFixed(6);
      document.getElementById('s-lng').value = lng.toFixed(6);
      if (kakaoMap) {
        kakaoMap.setCenter(new kakao.maps.LatLng(lat, lng));
        // "내 위치로 찾기"를 누르면 1km 이내로 보이도록 확대한다(사용자 지시,
        // 2026-08-13) — ZOOM_LEVEL_TO_KM에서 레벨 2가 1km에 해당한다.
        kakaoMap.setLevel(2);
        updateZoomRadiusBadge();
      }
      useLocationBtn.disabled = false;
      useLocationLabel.textContent = originalLabel;
      usedFallbackLocation = false;
      runSearch();
    },
    (err) => {
      useLocationBtn.disabled = false;
      useLocationLabel.textContent = originalLabel;
      const reasons = {
        1: '위치 접근 권한이 거부되었습니다. 브라우저 주소창 옆 자물쇠 아이콘에서 위치 권한을 허용해주세요.',
        2: '위치 정보를 확인할 수 없습니다.',
        3: '위치 확인 시간이 초과되었습니다.',
      };
      alert(reasons[err.code] || '위치를 가져올 수 없습니다.');
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
});

// --- 주소로 찾기 (1번 항목, 2026-08-13) ---
// KakaoClient.geocode()를 노출한 새 /geo/search를 호출한다. 성공하면 검색 위치로
// 지도를 옮기고 폴백 안내는 해제한다(이제 사용자가 직접 고른 진짜 위치니까).
const addressSearchInput = document.getElementById('address-search-input');
const addressSearchError = document.getElementById('address-search-error');
addressSearchInput.addEventListener('keydown', async (e) => {
  if (e.key !== 'Enter') return;
  const query = addressSearchInput.value.trim();
  if (!query) return;
  addressSearchError.classList.add('hidden');
  addressSearchError.textContent = '';
  addressSearchInput.disabled = true;
  try {
    const result = await apiFetch(`/geo/search?query=${encodeURIComponent(query)}`);
    if (!result.found) {
      addressSearchError.textContent = '주소를 찾을 수 없어요. 다르게 입력해보세요.';
      addressSearchError.classList.remove('hidden');
      return;
    }
    document.getElementById('s-lat').value = result.lat.toFixed(6);
    document.getElementById('s-lng').value = result.lng.toFixed(6);
    if (kakaoMap) kakaoMap.setCenter(new kakao.maps.LatLng(result.lat, result.lng));
    usedFallbackLocation = false;
    runSearch();
  } catch (err) {
    addressSearchError.textContent = err.message || '주소 검색에 실패했습니다.';
    addressSearchError.classList.remove('hidden');
  } finally {
    addressSearchInput.disabled = false;
  }
});

// --- 카카오 지도 ---
let kakaoMap = null;
let mapMarkers = [];
let mapLabels = [];
let originMarker = null;
const researchBtn = document.getElementById('research-btn');

// --- 줌 레벨 기반 반경 (7번 항목, 2026-08-13 / 세분화 2026-08-13 추가 지시) ---
// 드롭다운으로 반경을 고르는 대신, 지도를 줌인/줌아웃하면 카카오 지도의 레벨
// (숫자가 작을수록 확대)을 읽어 km로 매핑해 옆 배지에 보여준다. 처음엔 기존
// 드롭다운(1/3/5/10km)과 똑같은 큰 단위로 매핑했더니 "기존과 똑같은 숫자로
// 표현하면 이상하다"는 지적을 받았다 — 촘촘한 줌 레벨에서 큰 숫자가 계단식으로
// 튀어 보였기 때문. 저배율 구간은 1km씩 촘촘하게 늘리고, 완전히 축소하면
// 대한민국 국토 전체(남북 약 500km)가 다 보일 만큼 큰 값까지 확장한다.
// 정확한 레벨 구간은 실제 배포 후(이 샌드박스는 Kakao SDK 실행 환경이 없어
// 실측 불가) 조정이 필요할 수 있다.
//
// 이 배지는 순수하게 "지금 지도가 보여주는 범위"를 알려주는 시각적 지표다 —
// 실제 /search에 보내는 반경(currentRadiusKm)은 백엔드
// settings.search_max_radius_km(10km)를 넘을 수 없어 별도로 clamp한다(그렇지
// 않으면 국토 전체를 보는 줌에서 재검색이 400 에러로 실패한다).
const MAX_SEARCH_RADIUS_KM = 10; // app/core/config.py settings.search_max_radius_km과 일치
const ZOOM_LEVEL_TO_KM = [
  { maxLevel: 1, km: 1 },
  { maxLevel: 2, km: 1 },
  { maxLevel: 3, km: 2 },
  { maxLevel: 4, km: 3 },
  { maxLevel: 5, km: 4 },
  { maxLevel: 6, km: 5 },
  { maxLevel: 7, km: 6 },
  { maxLevel: 8, km: 8 },
  { maxLevel: 9, km: 10 },
  { maxLevel: 10, km: 20 },
  { maxLevel: 11, km: 50 },
  { maxLevel: 12, km: 100 },
  { maxLevel: 13, km: 250 },
  { maxLevel: 99, km: 500 }, // 완전 축소 — 대한민국 국토 전체가 보이는 수준
];
let currentRadiusKm = 3; // /search 호출용 (clamp됨)
let currentZoomDisplayKm = 3; // 배지 표시용 (clamp 안 됨, 실제 지도 축척)
const zoomRadiusBadge = document.getElementById('zoom-radius-badge');
const MAX_MAP_LEVEL = 14; // 이 레벨까지는 축소해도 재검색 반경 표시가 국토 전체 스케일까지 따라간다

function radiusKmForZoomLevel(level) {
  const match = ZOOM_LEVEL_TO_KM.find((row) => level <= row.maxLevel);
  return match ? match.km : 500;
}

function updateZoomRadiusBadge() {
  if (!kakaoMap) return;
  currentZoomDisplayKm = radiusKmForZoomLevel(kakaoMap.getLevel());
  currentRadiusKm = Math.min(currentZoomDisplayKm, MAX_SEARCH_RADIUS_KM);
  zoomRadiusBadge.textContent = `🔍 ${currentZoomDisplayKm}km`;
}

function initMap(lat, lng) {
  if (typeof kakao === 'undefined' || !kakao.maps) {
    document.getElementById('map').innerHTML =
      '<p class="empty-msg" style="padding-top:180px;">지도를 불러올 수 없습니다 (카카오맵 SDK 로드 실패)</p>';
    return;
  }
  kakaoMap = new kakao.maps.Map(document.getElementById('map'), {
    center: new kakao.maps.LatLng(lat, lng),
    level: 5,
  });
  // 기본 최대 축소 레벨이 국토 전체를 못 보여줄 수 있어 명시적으로 늘려준다
  // ("최대한 대한민국 국토가 보이도록 땡겨도 맞춰서" 사용자 지시).
  if (kakaoMap.setMaxLevel) kakaoMap.setMaxLevel(MAX_MAP_LEVEL);
  updateZoomRadiusBadge();

  kakao.maps.event.addListener(kakaoMap, 'dragend', () => researchBtn.classList.remove('hidden'));
  kakao.maps.event.addListener(kakaoMap, 'zoom_changed', () => {
    researchBtn.classList.remove('hidden');
    updateZoomRadiusBadge();
  });
}

researchBtn.addEventListener('click', () => {
  if (!kakaoMap) return;
  const center = kakaoMap.getCenter();
  document.getElementById('s-lat').value = center.getLat().toFixed(6);
  document.getElementById('s-lng').value = center.getLng().toFixed(6);
  researchBtn.classList.add('hidden');
  runSearch();
});

function clearMarkers() {
  mapMarkers.forEach((m) => m.setMap(null));
  mapMarkers = [];
  mapLabels.forEach((l) => l.setMap(null));
  mapLabels = [];
  if (originMarker) {
    originMarker.setMap(null);
    originMarker = null;
  }
}

// 다른 지도 앱들처럼 마커 아래에 상호명 라벨을 붙인다.
// treasure(절약 정보 있는 매장)는 "찾아가면 얼마나 아끼는지"까지 라벨에 바로 보여줘서
// 사용자가 지도만 보고도 방문(GPS 인증→XP) 동기를 갖게 한다.
function createLabelOverlay(pos, name, variant, onClick, opts = {}) {
  const el = document.createElement('div');
  const extraCls = [opts.tierCls, opts.unverified ? 'map-label--unverified' : ''].filter(Boolean).join(' ');
  el.className = `map-label map-label--${variant}${extraCls ? ' ' + extraCls : ''}`;
  el.innerHTML = `
    <span class="map-label-name">${opts.unverified ? '🙋 ' : ''}${escapeHtml(name)}</span>
    ${opts.savingsText ? `<span class="map-label-savings">${escapeHtml(opts.savingsText)}</span>` : ''}
  `;
  if (onClick) el.addEventListener('click', onClick);

  const overlay = new kakao.maps.CustomOverlay({
    map: kakaoMap,
    position: pos,
    content: el,
    yAnchor: 0,
    clickable: true,
    zIndex: variant === 'treasure' ? 2 : 1,
  });
  return overlay;
}

// "절약 보물" 마커: 매장 아이콘보다 "여기서 얼마를 아낄 수 있는가"를 먼저 보여준다.
function treasureMarkerImage() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26">
    <circle cx="13" cy="13" r="10" fill="#f59e0b" stroke="white" stroke-width="3"/>
  </svg>`;
  return new kakao.maps.MarkerImage('data:image/svg+xml;base64,' + btoa(svg), new kakao.maps.Size(26, 26));
}

// "절약 보물" 마커인데 발견/방문 인증이 0건인 매장 — 절약 정보 자체는 있지만
// 아무도 실제로 다녀가지 않았다는 뜻이라, 같은 금색 계열을 쓰되 속을 비운(점선
// 테두리) 스타일로 "아직 채워지지 않았다"를 표시한다(현장 활동 유도 기획안
// §3-A, 2026-08-13). 절약 정보 자체가 없는 discoveredMarkerImage()(회색, 카카오
// 로컬 검색으로만 발견된 곳)와는 다른 상태다.
function unverifiedTreasureMarkerImage() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26">
    <circle cx="13" cy="13" r="9" fill="white" stroke="#f59e0b" stroke-width="2.5" stroke-dasharray="3,2"/>
  </svg>`;
  return new kakao.maps.MarkerImage('data:image/svg+xml;base64,' + btoa(svg), new kakao.maps.Size(26, 26));
}

// 아직 절약 정보가 없는(카카오로만 발견된) 매장은 회색 마커로 구분한다.
function discoveredMarkerImage() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18">
    <circle cx="9" cy="9" r="7" fill="#94a3b8" stroke="white" stroke-width="2.5"/>
  </svg>`;
  return new kakao.maps.MarkerImage('data:image/svg+xml;base64,' + btoa(svg), new kakao.maps.Size(18, 18));
}

let lastResults = [];
let lastDiscovered = [];

function renderMapMarkers(originLat, originLng, results, discovered = []) {
  if (!kakaoMap) return;
  clearMarkers();

  const bounds = new kakao.maps.LatLngBounds();
  const originPos = new kakao.maps.LatLng(originLat, originLng);
  bounds.extend(originPos);

  // 내 위치(검색 기준점)는 파란 마커로 표현한다(사용자 지시, 2026-08-13) — 결과/
  // 발견 마커와 확실히 구분되도록. 검색이 다시 실행될 때마다(내 위치 버튼, 주소
  // 검색, 재검색 등 위치가 바뀔 때마다) 이 함수가 다시 그려서 항상 최신 위치를
  // 따라간다.
  originMarker = new kakao.maps.Marker({
    map: kakaoMap,
    position: originPos,
    image: new kakao.maps.MarkerImage(
      'data:image/svg+xml;base64,' +
        btoa('<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22"><circle cx="11" cy="11" r="8" fill="#2563eb" stroke="white" stroke-width="3"/></svg>'),
      new kakao.maps.Size(22, 22)
    ),
  });

  results.forEach((r) => {
    const pos = new kakao.maps.LatLng(r.lat, r.lng);
    bounds.extend(pos);
    // 발견/방문 인증이 하나도 없으면 "아직 아무도 안 가본 곳"으로 마커를 다르게
    // 표시한다 — 실제 카운트 기반이라 지어낼 게 없다(현장 활동 유도 기획안
    // §3-A, 2026-08-13).
    const isUnverified = r.discover_count === 0 && r.dining_count === 0;
    const marker = new kakao.maps.Marker({
      map: kakaoMap,
      position: pos,
      image: isUnverified ? unverifiedTreasureMarkerImage() : treasureMarkerImage(),
    });
    kakao.maps.event.addListener(marker, 'click', () => openOfferDetail(r));
    mapMarkers.push(marker);

    // 라벨의 핵심은 가격이 아니라 "AI 절약점수/절약률" — 데이터가 부족하면 지어내지
    // 않고 "계산 중"으로 표시한다.
    // RPG 희귀도 색상(getRarityTier)은 잠시 비활성화 — 기본 베이스 구조 완성 후
    // 다시 켠다(사용자 지시, 2026-08-12). tierCls를 안 넘기면 색상 없이 기본
    // 스타일로만 표시된다.
    const hasScore = r.report && r.report.score != null;
    const savingsText =
      r.total_savings > 0
        ? `${Math.round(r.savings_rate)}%↓ · 약 ${Math.round(r.total_savings).toLocaleString()}원 절약`
        : hasScore
          ? `AI 절약점수 ${r.report.score}점`
          : isUnverified
            ? '아직 미검증 · 가보면 첫 인증'
            : '절약 정보 계산 중';
    mapLabels.push(
      createLabelOverlay(pos, r.place_name, 'treasure', () => openOfferDetail(r), {
        savingsText,
        unverified: isUnverified,
      })
    );
  });

  discovered.forEach((d) => {
    const pos = new kakao.maps.LatLng(d.lat, d.lng);
    bounds.extend(pos);
    const marker = new kakao.maps.Marker({ map: kakaoMap, position: pos, image: discoveredMarkerImage() });
    const openDiscovered = () => openDiscoveredDetail(d);
    kakao.maps.event.addListener(marker, 'click', openDiscovered);
    mapMarkers.push(marker);
    mapLabels.push(createLabelOverlay(pos, d.place_name, 'discovered', openDiscovered));
  });

  kakaoMap.setBounds(bounds);
}

// --- 절약 정보 상세 (예상 절약 확인 + 절약 인증) ---
const detailOverlay = document.getElementById('offer-detail-overlay');
const detailContent = document.getElementById('detail-content');

document.getElementById('detail-close-btn').addEventListener('click', () => {
  detailOverlay.classList.add('hidden');
});

// --- AI 절약 리포트: SaveMap의 핵심 콘텐츠. 메뉴는 카카오맵의 역할이고, SaveMap은
// "얼마나 절약되고 얼마나 믿을 수 있는지"만 실제 데이터로 분석해 보여준다. ---
const CONFIDENCE_ICONS = { high: '🟢', medium: '🟡', low: '⚪' };

function confidenceStarsHtml(stars) {
  if (!stars) return '';
  return `<span class="report-stars">${'★'.repeat(stars)}${'☆'.repeat(5 - stars)}</span>`;
}

function savingsReportHtml(r) {
  const report = r.report;
  if (!report) return '';
  const icon = CONFIDENCE_ICONS[report.confidence_tier] || '⚪';

  if (report.confidence_tier === 'low' || report.score == null) {
    // score(신뢰도 점수)는 실제 방문/인증 같은 사람 신호가 있어야만 매기지만, 가격
    // 비교 자체(실측이든 AI 추정이든)는 이미 끝났을 수 있다 — 그 경우엔 "계산 중"으로
    // 뭉개지 않고 실제로 나온 숫자를 출처와 함께 그대로 보여준다.
    const hasEstimate = r.total_savings > 0;
    const sourceLabel = r.savings_source === 'ai' ? 'AI(Gemini) 추정 통상가' : '주변 매장 실측가';
    // 발견/방문 인증이 하나도 없는 완전 콜드스타트 매장은 "계산 중"이라는 수동적
    // 문구 대신 방문을 요청하는 문구로 바꾼다 — 실제 카운트 기반이라 지어낸 게
    // 아니다(현장 활동 유도 기획안 §3-B, 2026-08-13).
    const isUnverified = r.discover_count === 0 && r.dining_count === 0;
    return `
    <div class="ai-report ai-report--low">
      <div class="ai-report-title">💰 AI 절약 리포트</div>
      ${hasEstimate ? `
      <div class="ai-report-hero ai-report-hero--estimate">
        <div class="ai-report-rate">🤖 ${sourceLabel} 대비 <strong>${Math.round(r.savings_rate)}% 저렴</strong></div>
        <div class="ai-report-amount">예상 절약 <strong>약 ${Math.round(r.total_savings).toLocaleString()}원</strong></div>
      </div>` : isUnverified ? `
      <div class="ai-report-calc ai-report-calc--invite">🙋 아직 아무도 확인 안 한 곳이에요 · 아래 "발견하기"를 누르면 첫 인증자가 돼요</div>` : `
      <div class="ai-report-calc">절약 정보를 계산하는 중입니다.</div>`}
      <div class="report-confidence">${icon} ${escapeHtml(report.confidence_label)}</div>
      ${
        // 아직 아무 신호도 없는 완전 콜드스타트 상태에선 "부족한 것 3가지"를 줄줄이
        // 나열해봤자 전부 같은 얘기("데이터가 없다")라 화면만 길어진다 — 이 경우엔
        // one_line 한 줄로 충분하고, 실제로 뭔가 근거가 있을 때(AI/실측 추정 등)만
        // 근거 목록을 보여준다.
        hasEstimate && report.reasons.length ? `
      <div class="report-reasons">
        ${report.reasons.map((reason) => `<div class="report-reason">✓ ${escapeHtml(reason)}</div>`).join('')}
      </div>` : ''
      }
      ${report.one_line ? `<p class="report-one-line">"${escapeHtml(report.one_line)}"</p>` : ''}
    </div>`;
  }

  return `
    <div class="ai-report">
      <div class="ai-report-title">💰 AI 절약 리포트</div>
      ${r.total_savings > 0 ? `
      <div class="ai-report-hero">
        <div class="ai-report-rate">평균보다 <strong>${Math.round(r.savings_rate)}% 저렴</strong></div>
        <div class="ai-report-amount">예상 절약 <strong>약 ${Math.round(r.total_savings).toLocaleString()}원</strong></div>
      </div>` : `
      <div class="ai-report-hero">
        <div class="ai-report-rate">현재 확인된 추가 절약 없음</div>
      </div>`}
      <div class="ai-report-scores">
        <div class="ai-report-cell"><span class="cell-label">절약 등급</span><span class="cell-value grade">${escapeHtml(report.grade)}</span></div>
        <div class="ai-report-cell"><span class="cell-label">AI 절약점수</span><span class="cell-value">${report.score}점</span></div>
      </div>
      <div class="report-confidence">${icon} ${escapeHtml(report.confidence_label)} ${confidenceStarsHtml(report.confidence_stars)}</div>
      <div class="report-reasons">
        <div class="report-reasons-title">판단 근거</div>
        ${report.reasons.map((reason) => `<div class="report-reason">✓ ${escapeHtml(reason)}</div>`).join('')}
      </div>
      ${report.one_line ? `<p class="report-one-line">"${escapeHtml(report.one_line)}"</p>` : ''}
    </div>`;
}

const STATUS_LABELS = { open: '🟢 영업중', closed: '🔴 휴무', temp_closed: '🟠 임시 휴무' };

// 사람이 읽는 상대시간("3일 전 확인됨") — last_verified_at을 그대로 노출하지
// 않고 변환만 한다(10번 항목, 2026-08-13). 지어낸 값 아님, ISO 문자열 그대로 계산.
function relativeTimeFromNow(isoString) {
  if (!isoString) return null;
  const then = new Date(isoString).getTime();
  if (Number.isNaN(then)) return null;
  const diffMin = Math.floor((Date.now() - then) / 60000);
  if (diffMin < 1) return '방금 확인됨';
  if (diffMin < 60) return `${diffMin}분 전 확인됨`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전 확인됨`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return `${diffDay}일 전 확인됨`;
  return `${Math.floor(diffDay / 30)}개월 전 확인됨`;
}

function openOfferDetail(r) {
  const shortCategory = r.category_name ? r.category_name.split(' > ').pop() : '';
  const kakaoUrl = r.kakao_url || `https://map.kakao.com/link/search/${encodeURIComponent(r.place_name)}`;
  const statusLabel = STATUS_LABELS[r.business_status] || '';
  // 무료주차 배지(10번 항목) — offer.category가 free_parking일 때만, 실제 등록된
  // 조건 그대로.
  const freeParkingBadge = r.category === 'free_parking' ? '<span class="badge badge--parking">🅿️ 무료주차</span>' : '';
  // 기준가 vs 실제가 숫자 나란히 표시(10번 항목) — 둘 다 있고 서로 다를 때만.
  const priceCompareHtml =
    r.base_price > 0 && r.final_price > 0 && r.base_price !== r.final_price
      ? `<div class="price-compare-row">
          <span class="price-compare-base">기준가 ${Math.round(r.base_price).toLocaleString()}원</span>
          <span class="price-compare-arrow">→</span>
          <span class="price-compare-final">실제가 ${Math.round(r.final_price).toLocaleString()}원</span>
        </div>`
      : '';
  const lastVerifiedText = relativeTimeFromNow(r.last_verified_at);

  detailContent.innerHTML = `
    <div class="badge-group">
      <span class="badge">${escapeHtml(shortCategory || CATEGORY_LABELS[r.category] || r.category)}</span>
      ${statusLabel ? `<span class="status-tag">${statusLabel}</span>` : ''}
      ${freeParkingBadge}
    </div>
    <h2 class="place-name">${escapeHtml(r.place_name)}</h2>
    <div class="meta-line">현재 위치에서 ${r.distance_m.toFixed(0)}m${r.address ? ' · ' + escapeHtml(r.address) : ''}</div>
    ${r.phone ? `<a class="store-info-line store-info-tel" href="tel:${escapeHtml(r.phone)}">${escapeHtml(r.phone)}</a>` : ''}
    ${lastVerifiedText ? `<div class="last-verified-line">🕐 ${lastVerifiedText}</div>` : ''}
    ${priceCompareHtml}

    ${r.signature_menu ? `
    <div class="menu-highlight-card">
      <div class="menu-highlight-label">대표메뉴 · 실제 등록 가격</div>
      <div class="menu-highlight-row">
        <span class="menu-highlight-name">${escapeHtml(r.signature_menu.name)}</span>
        <span class="menu-highlight-price">${Math.round(r.signature_menu.price).toLocaleString()}원</span>
      </div>
      <button type="button" class="btn-primary menu-highlight-btn" id="detail-kakao-btn">카카오맵에서 전체 메뉴 보기</button>
    </div>` : `
    <div class="menu-highlight-card menu-highlight-card--empty">
      <div class="menu-highlight-label">등록된 대표메뉴 없음</div>
      <button type="button" class="btn-primary menu-highlight-btn" id="detail-kakao-btn">카카오맵에서 메뉴 확인하기</button>
    </div>`}

    ${savingsReportHtml(r)}

    <div class="proof-counts">
      <span class="proof-item">👀 관심 <strong>${r.discover_count}</strong></span>
      <span class="proof-item">🔥 식사 인증 <strong>${r.dining_count}</strong></span>
      <span class="proof-item" id="detail-recommend-count">👍 추천 <strong>${r.recommend_count || 0}</strong></span>
    </div>

    <div class="detail-actions">
      <button type="button" class="btn-secondary" id="detail-directions-btn">길찾기</button>
    </div>

    <!-- 현장 인증 통합(10번 항목, 2026-08-13) — 예전엔 "발견하기"(관심 표시)와
         "영수증/직접 인증"이 서로 다른 섹션으로, 추천은 위 detail-actions에
         따로 있었다. 사용자 확정(2-2): "영수증 인증을 방문횟수로 해, 기존
         영수증 인증은 숨기고 방문횟수에서 참고하도록" — 발견/추천/인증 세
         행동을 "현장에서 할 수 있는 3가지 행동" 하나의 흐름으로 묶는다.
         백엔드 API(submit_status_update/certify 계열)는 변경 없음, 호출
         순서와 문구만 재구성했다. -->
    <div class="onsite-verify-section">
      <div class="onsite-verify-title">📍 현장에서 할 수 있는 3가지 행동</div>
      <div class="onsite-actions-row">
        <button type="button" class="onsite-action-btn" id="detail-discover-btn">
          <span class="onsite-action-icon">📍</span><span>발견하기</span>
        </button>
        <button type="button" class="onsite-action-btn" id="detail-recommend-btn">
          <span class="onsite-action-icon">👍</span><span>추천</span>
        </button>
        <button type="button" class="onsite-action-btn" id="detail-receipt-btn">
          <span class="onsite-action-icon">🧾</span><span>인증</span>
        </button>
      </div>
      <p class="subtitle onsite-verify-hint">발견하기는 매장 반경 50m 이내에서만, 한 매장당 최초 1회만 인정돼요.</p>
      <div id="detail-recommend-msg"></div>
      <div id="detail-visit-msg"></div>
      <p class="interest-count" id="detail-interest-count"></p>
      <button type="button" class="btn-text" id="detail-report-closed-btn">혹시 휴무인가요?</button>
      <div id="detail-closed-row" class="hidden">
        <div class="visit-buttons">
          <button type="button" class="btn-visit" data-status="closed">휴무</button>
          <button type="button" class="btn-visit" data-status="temp_closed">임시 휴무</button>
        </div>
      </div>
      <input type="file" id="detail-receipt-input" accept="image/*" capture="environment" class="hidden" />
      <button type="button" class="btn-text" id="detail-simple-certify-btn">영수증 없이 직접 입력해서 인증</button>
      <div id="detail-certify-msg"></div>
    </div>

    <div class="verify-row">
      <span class="verify-label">이 정보 아직 유효한가요?</span>
      <div class="verify-buttons">
        <button type="button" class="btn-verify" data-verdict="available">아직 있어요</button>
        <button type="button" class="btn-verify btn-verify-negative" data-verdict="sold_out">없어졌어요</button>
      </div>
      <div id="detail-verify-msg"></div>
    </div>
  `;
  detailOverlay.classList.remove('hidden');

  document.getElementById('detail-kakao-btn').addEventListener('click', () => {
    window.open(kakaoUrl, '_blank', 'noopener');
  });
  document.getElementById('detail-directions-btn').addEventListener('click', () => {
    window.open(`https://map.kakao.com/link/to/${encodeURIComponent(r.place_name)},${r.lat},${r.lng}`, '_blank');
  });
  document.getElementById('detail-recommend-btn').addEventListener('click', (e) => recommendPlace(r, e.currentTarget));

  document.getElementById('detail-discover-btn').addEventListener('click', (e) => submitStatusUpdate(r, 'open', e.currentTarget));
  document.getElementById('detail-report-closed-btn').addEventListener('click', () => {
    document.getElementById('detail-closed-row').classList.remove('hidden');
  });
  document.getElementById('detail-receipt-btn').addEventListener('click', () => document.getElementById('detail-receipt-input').click());
  document.getElementById('detail-receipt-input').addEventListener('change', (e) => certifyWithReceipt(r, e.target));
  document.getElementById('detail-simple-certify-btn').addEventListener('click', () => certifyOffer(r));

  detailContent.querySelectorAll('.btn-verify').forEach((btn) => {
    btn.addEventListener('click', () => verifyOffer(r.offer_id, btn.dataset.verdict, btn));
  });

  detailContent.querySelectorAll('#detail-closed-row .btn-visit').forEach((btn) => {
    btn.addEventListener('click', () => submitStatusUpdate(r, btn.dataset.status, btn));
  });
}

// --- AI 절약 플랜: 개별 매장을 나열만 하던 것과 별개로, 예산을 넣으면 실제 후보
// 중에서 예산 안에 드는 코스를 짜서 "오늘 이 코스로 총 OO원 절약"을 구체적으로
// 보여준다 (SaveMap 기획서의 원래 핵심 차별화 기능, 2026-08-12 구현). 각 스톱은
// /search 결과와 똑같은 모양이라 기존 openOfferDetail을 그대로 재사용한다. ---
const routePlanOverlay = document.getElementById('route-plan-overlay');
const routePlanContent = document.getElementById('route-plan-content');
let lastRouteStops = [];

document.getElementById('ai-route-cta').addEventListener('click', openRoutePlanSheet);
document.getElementById('route-plan-close-btn').addEventListener('click', () => {
  routePlanOverlay.classList.add('hidden');
});

// Step1 "무엇을 할까요?" — 할인/무료/마감세일 같은 절약 수단(Category)이 아니라
// 사용자가 실제로 하고 싶은 일. Place.category_name에서 실제로 구분 가능한 것부터만
// 넣는다(사용자 지시, 2026-08-13) — 쇼핑/문화·여가/가족활동은 지금 데이터로 매핑할
// 근거가 없어서 아직 넣지 않는다.
const ROUTE_ACTIVITIES = [
  { value: 'dining', label: '🍚 식사' },
  { value: 'cafe', label: '☕ 커피' },
  { value: 'dessert', label: '🍰 디저트' },
];

// Step2 "어떤 조건이 중요할까요?" — 실제 build_route 정렬 로직에 그대로 반영된다
// (app/engine/route_planner.py의 RoutePreference). 첫 항목(균형있게)은 preference를
// 아예 안 보내는 것(=기존 기본 랭킹 점수) — 장식이 아니라 실제 선택지다.
const ROUTE_PREFERENCES = [
  { value: '', label: '균형있게' },
  { value: 'cheapest', label: '💰 최대한 저렴하게' },
  { value: 'verified', label: '✅ 검증된 정보 우선' },
  { value: 'recent', label: '🕐 최신 정보 우선' },
  { value: 'distance', label: '📍 이동거리 최소화' },
];

function routePlanFormHtml() {
  const activityChips = ROUTE_ACTIVITIES.map(
    (a) => `<button type="button" class="chip route-activity-chip" data-value="${a.value}">${a.label}</button>`
  ).join('');
  const preferenceChips = ROUTE_PREFERENCES.map(
    (p, i) =>
      `<button type="button" class="chip route-preference-chip${i === 0 ? ' active' : ''}" data-value="${p.value}">${p.label}</button>`
  ).join('');

  // Step①/②/③이 굵은 라벨 텍스트로만 구분돼 있어 "조건별로 정리가 잘 안 된다"는
  // 지적을 받았다(6번 항목, 2026-08-13) — 각 Step을 원형 번호 배지 + 테두리가 있는
  // 카드(.route-step-card)로 감싸 시각적으로 명확히 분리한다.
  return `
    <h2 class="place-name">🤖 AI 절약 플랜</h2>
    <div class="meta-line">뭘 하고 싶은지 알려주면, 실제 후보 중에서 가장 절약되는 코스를 짜드려요.</div>

    <div class="route-step-card">
      <div class="route-step-header">
        <span class="route-step-number">1</span>
        <span class="route-step-title">무엇을 할까요?</span>
      </div>
      <div class="chip-group">${activityChips}</div>
      <div class="field-hint">여러 개 선택 가능 · 비워두면 모든 활동에서 찾아요.</div>
    </div>

    <div class="route-step-card">
      <div class="route-step-header">
        <span class="route-step-number">2</span>
        <span class="route-step-title">어떤 조건이 중요할까요?</span>
      </div>
      <div class="chip-group">${preferenceChips}</div>
      <div class="field-hint" style="margin-top:10px;">
        <label class="checkbox-label">
          <input type="checkbox" id="route-parking-input" /> 🅿️ 무료주차 필요
        </label>
      </div>
    </div>

    <div class="route-step-card">
      <div class="route-step-header">
        <span class="route-step-number">3</span>
        <span class="route-step-title">예산 / 인원</span>
      </div>
      <div class="form-row">
        <input type="number" id="route-budget-input" min="1000" step="1000" value="30000" aria-label="예산" />
        <input type="number" id="route-party-input" min="1" max="20" value="1" aria-label="인원" />
      </div>
    </div>

    <button type="button" class="btn-primary" id="route-plan-submit-btn">코스 만들기</button>
    <div id="route-plan-msg"></div>
  `;
}

function openRoutePlanSheet() {
  routePlanContent.innerHTML = routePlanFormHtml();
  routePlanOverlay.classList.remove('hidden');
  document.getElementById('route-plan-submit-btn').addEventListener('click', submitRoutePlan);
  routePlanContent.querySelectorAll('.route-activity-chip').forEach((chip) => {
    chip.addEventListener('click', () => chip.classList.toggle('active'));
  });
  routePlanContent.querySelectorAll('.route-preference-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      routePlanContent.querySelectorAll('.route-preference-chip').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
    });
  });
}

async function submitRoutePlan() {
  const msgEl = document.getElementById('route-plan-msg');
  const btn = document.getElementById('route-plan-submit-btn');
  const budget = parseFloat(document.getElementById('route-budget-input').value);
  const partySize = parseInt(document.getElementById('route-party-input').value, 10) || 1;
  const activities = Array.from(routePlanContent.querySelectorAll('.route-activity-chip.active')).map(
    (c) => c.dataset.value
  );
  const activePreferenceChip = routePlanContent.querySelector('.route-preference-chip.active');
  const preference = activePreferenceChip && activePreferenceChip.dataset.value ? activePreferenceChip.dataset.value : null;
  const freeParkingRequired = document.getElementById('route-parking-input').checked;

  if (!budget || budget <= 0) {
    msgEl.innerHTML = '<p class="error-msg">예산을 입력해주세요.</p>';
    return;
  }

  const lat = parseFloat(document.getElementById('s-lat').value);
  const lng = parseFloat(document.getElementById('s-lng').value);

  btn.disabled = true;
  btn.textContent = '코스를 짜는 중...';
  msgEl.innerHTML = '';

  try {
    // 요청 스키마: context(누구와/얼마나 등 상황)와 constraints(반드시 지켜야 하는
    // 조건)를 별도 그룹으로 나눈다 — "SaveMap 구조 재설계 제안서"(2026-08-13) §3
    // 반영. free_parking_required는 정렬 기준(preference)과 달리 후보를 아예
    // 걸러내는 하드 조건이라 constraints에 속한다.
    const payload = {
      lat,
      lng,
      context: { party_size: partySize },
      constraints: { budget, free_parking_required: freeParkingRequired },
    };
    if (activities.length) payload.activities = activities;
    if (preference) payload.preference = preference;
    const data = await apiFetch('/route/suggest', { method: 'POST', body: JSON.stringify(payload) });
    // 결과 화면에 "이 조건으로 만들었어요"를 다시 보여주기 위한 요약(6번 항목) —
    // 백엔드가 이미 아는 값을 그대로 다시 조립할 뿐, 새 API 호출은 없다.
    renderRoutePlanResult(data, routeConditionSummary({ activities, preference, freeParkingRequired, partySize }));
  } catch (err) {
    msgEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
    btn.disabled = false;
    btn.textContent = '코스 만들기';
  }
}

// "선택한 조건" 요약 문자열들(6번 항목) — 제출 시점의 activities/preference/
// 무료주차/인원을 사람이 읽는 칩 문구로 조립한다. 백엔드 _build_context_note와
// 비슷한 방식이지만 프론트에서 이미 갖고 있는 값으로 직접 만든다(새 API 불필요).
function routeConditionSummary({ activities, preference, freeParkingRequired, partySize }) {
  const chips = [];
  if (activities.length) {
    const labels = activities.map((v) => ROUTE_ACTIVITIES.find((a) => a.value === v)?.label || v);
    chips.push(labels.join(' + '));
  } else {
    chips.push('모든 활동');
  }
  const prefLabel = ROUTE_PREFERENCES.find((p) => p.value === (preference || ''))?.label;
  if (prefLabel) chips.push(prefLabel);
  if (freeParkingRequired) chips.push('🅿️ 무료주차 필수');
  chips.push(`👥 ${partySize}명`);
  return chips;
}

function renderRoutePlanResult(data, conditionChips = []) {
  lastRouteStops = data.stops;

  // 코스를 못 만들었으면(예산 안에 후보가 없음) 지어내지 않고 그 사실 그대로 안내한다
  // (summary가 이미 route_planner의 결정론적 안내 문구를 담고 있다).
  if (!data.fits_budget) {
    routePlanContent.innerHTML = `
      <h2 class="place-name">🤖 AI 절약 플랜</h2>
      <p class="empty-msg">${escapeHtml(data.summary)}</p>
      <button type="button" class="btn-secondary" id="route-plan-retry-btn">조건 바꿔서 다시 시도</button>
    `;
    document.getElementById('route-plan-retry-btn').addEventListener('click', openRoutePlanSheet);
    return;
  }

  const stopsHtml = data.stops
    .map((s, i) => {
      const priceLabel = s.final_price > 0 ? formatWon(s.final_price) : '무료';
      // savings_source: "region"=주변 매장 실측가 비교, "ai"=Gemini 추정 통상가 비교,
      // null=비교 대상 없음 — 실측처럼 보이지 않게 항상 출처를 그대로 밝힌다
      // (검색 결과 카드의 sourceLabel 표기와 동일한 원칙).
      let savingsNote = '';
      if (s.savings_rate > 0) {
        const sourceLabel = s.savings_source === 'ai' ? 'AI 추정' : '실측';
        savingsNote = ` · ${sourceLabel} 대비 ${Math.round(s.savings_rate)}% 저렴`;
      }
      // 거리 + 실측/AI 출처 배지(6번 항목) — RouteStopItem에 이미 있던 필드를
      // 결과 카드에 추가 노출("결과 카드가 얇다"는 지난 감사 지적과 직접 연결).
      const sourceBadge = s.savings_source
        ? `<span class="route-stop-source-badge route-stop-source-badge--${s.savings_source}">${s.savings_source === 'ai' ? '🤖 AI 추정' : '📊 실측'}</span>`
        : '';
      return `
      <div class="route-stop-card" data-idx="${i}">
        <div class="route-stop-order">${s.order}</div>
        <div class="route-stop-info">
          <div class="route-stop-name">${escapeHtml(s.place_name)}</div>
          <div class="route-stop-price">${priceLabel}${savingsNote}</div>
          <div class="route-stop-meta">📍 ${Math.round(s.distance_m)}m${sourceBadge}</div>
        </div>
      </div>`;
    })
    .join('');

  const conditionSummaryHtml = conditionChips.length
    ? `<div class="route-condition-summary">${conditionChips.map((c) => `<span class="route-condition-chip">${escapeHtml(c)}</span>`).join('')}</div>`
    : '';

  routePlanContent.innerHTML = `
    <h2 class="place-name">🤖 AI 절약 플랜</h2>
    <div class="ai-report-hero">
      <div class="ai-report-rate">오늘 이 코스로 총 <strong>${formatWon(data.total_savings)}</strong> 절약!</div>
      <div class="ai-report-amount">총 지출 ${formatWon(data.total_spend)} · 예산 ${formatWon(data.budget)} 중 ${formatWon(data.remaining_budget)} 남음</div>
    </div>
    ${conditionSummaryHtml}
    <p class="report-one-line">"${escapeHtml(data.summary)}"</p>
    <div class="route-stop-list">${stopsHtml}</div>
    <button type="button" class="btn-secondary" id="route-plan-retry-btn">조건 바꿔서 다시 만들기</button>
  `;

  document.getElementById('route-plan-retry-btn').addEventListener('click', openRoutePlanSheet);
  routePlanContent.querySelectorAll('.route-stop-card').forEach((card) => {
    card.addEventListener('click', () => {
      routePlanOverlay.classList.add('hidden');
      openOfferDetail(lastRouteStops[Number(card.dataset.idx)]);
    });
  });
}

async function recommendPlace(r, btn) {
  const msgEl = document.getElementById('detail-recommend-msg');
  const token = await getAccessToken();
  if (!token) {
    msgEl.innerHTML = '<p class="error-msg">추천은 로그인 후 이용할 수 있어요. MY 탭에서 로그인해주세요.</p>';
    return;
  }
  btn.disabled = true;
  try {
    const data = await apiFetch(`/places/${r.place_id}/recommendations`, { method: 'POST' });
    document.getElementById('detail-recommend-count').innerHTML = `👍 추천 <strong>${data.recommend_count}</strong>`;
    msgEl.innerHTML = data.is_new
      ? `<p class="empty-msg">${ICONS.check} 추천했어요! AI 절약 리포트 신뢰도에 반영돼요.</p>`
      : `<p class="empty-msg">이미 추천한 매장이에요.</p>`;
    // 새 추천일 때만 실제 recommend_count가 늘어나므로 아바타 성장치도 그때만
    // 갱신한다(2-4) — 중복 추천 클릭으로 지어낸 성장은 없다.
    if (data.is_new) {
      triggerAvatarGrowthFeedback();
      loadMyProfile();
      showSavingsToast('👍 추천 완료!');
    }
  } catch (err) {
    msgEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
    btn.disabled = false;
  }
}

// --- 아직 가격 정보 없는(카카오로만 발견된) 매장 상세: 그냥 구경만 하고 나가지 않도록
// 두 가지 길을 준다 — (1) 누구든 실제 가격표/메뉴판 사진을 찍어서 바로 제보 (카카오/
// 네이버 어디도 메뉴를 API로 안 주고, 크롤링은 원칙상 안 쓰므로 이게 유일한 실제 데이터
// 경로), (2) 사장님 본인이면 사업자 콘솔에서 정식 등록. 둘 다 SaveMap의 핵심 루프
// (등록→비교→방문 인증→XP)로 이어진다. 발견 소스가 음식점·카페 외 마트·편의점으로도
// 넓어졌으므로(2026-08-13) 문구는 업종을 특정하지 않는다. ---
function openDiscoveredDetail(d) {
  const shortCategory = d.category_name ? d.category_name.split(' > ').pop() : '';
  detailContent.innerHTML = `
    <div class="badge-group">
      <span class="badge">${escapeHtml(shortCategory || '발견된 장소')}</span>
      <span class="tier-tag" style="--tier-color:#94a3b8">가격 정보 없음</span>
    </div>
    <h2 class="place-name">${escapeHtml(d.place_name)}</h2>
    <div class="meta-line">
      현재 위치에서 ${d.distance_m.toFixed(0)}m${d.address ? ' · ' + escapeHtml(d.address) : ''}
    </div>
    ${d.phone ? `<a class="store-info-line store-info-tel" href="tel:${escapeHtml(d.phone)}">${escapeHtml(d.phone)}</a>` : ''}
    <p class="empty-msg" style="margin:10px 0; text-align:left;">
      아직 SaveMap에 가격 정보가 없는 매장이에요. 가격표나 메뉴판 사진을 찍어서
      알려주시면 다른 사람들도 이곳의 절약 정보를 바로 볼 수 있어요.
    </p>
    <div class="detail-actions">
      <button type="button" class="btn-primary" id="discovered-report-btn">📷 사진 찍어서 알려주기</button>
    </div>
    <input type="file" id="discovered-menu-input" accept="image/*" capture="environment" class="hidden" />
    <p id="discovered-menu-status" class="subtitle"></p>
    <div id="discovered-menu-results"></div>

    <div class="detail-actions">
      <button type="button" class="btn-secondary" id="discovered-kakao-btn">카카오맵에서 매장 정보 보기</button>
      <button type="button" class="btn-text" id="discovered-register-btn">사장님이신가요? 매장 정식 등록하기</button>
    </div>
  `;
  detailOverlay.classList.remove('hidden');

  document.getElementById('discovered-kakao-btn').addEventListener('click', () => {
    if (d.kakao_url) window.open(d.kakao_url, '_blank', 'noopener');
  });
  document.getElementById('discovered-register-btn').addEventListener('click', () => {
    detailOverlay.classList.add('hidden');
    prefillMerchantPlace(d);
    switchScreen('merchant');
  });
  document.getElementById('discovered-report-btn').addEventListener('click', () => {
    document.getElementById('discovered-menu-input').click();
  });
  document.getElementById('discovered-menu-input').addEventListener('change', (e) => analyzeDiscoveredMenuPhoto(d, e.target));
}

// --- 발견된 매장의 메뉴판 사진을 아무 사용자나 올려서 제보. 사진 한 장에서 여러 메뉴를
// 한 번에 인식하는 기존 사업자용 AI(/merchant/menu-items/analyze, 소유권 확인 없음 —
// 로그인만 필요)를 그대로 재사용하고, 저장만 제보 전용 엔드포인트로 나눈다. ---
async function analyzeDiscoveredMenuPhoto(d, fileInput) {
  const file = fileInput.files[0];
  if (!file) return;
  const statusEl = document.getElementById('discovered-menu-status');
  const resultsEl = document.getElementById('discovered-menu-results');
  resultsEl.innerHTML = '';

  const token = await getAccessToken();
  if (!token) {
    statusEl.textContent = '메뉴 제보는 로그인 후 이용할 수 있어요. MY 탭에서 로그인해주세요.';
    fileInput.value = '';
    return;
  }

  statusEl.textContent = 'AI가 메뉴판을 읽고 있어요...';
  const form = new FormData();
  form.append('image', file);
  const headers = { Authorization: `Bearer ${token}` };

  try {
    const resp = await fetch(`${API_BASE}/merchant/menu-items/analyze`, { method: 'POST', headers, body: form });
    const data = await resp.json().catch(() => null);
    if (!resp.ok) {
      throw new Error(data?.detail?.message || data?.detail || `분석 실패 (${resp.status})`);
    }

    const items = data.items || [];
    statusEl.textContent = items.length
      ? `${items.length}개 메뉴를 찾았어요. 확인하고 제보해주세요.`
      : '메뉴를 찾지 못했어요. 더 선명한 사진으로 다시 시도해보세요.';

    resultsEl.innerHTML = items.length
      ? `
      <div class="menu-photo-list">
        ${items
          .map(
            (m, i) => `
          <div class="menu-photo-row">
            <input type="checkbox" class="mp-check" data-idx="${i}" checked />
            <input type="text" class="mp-name" data-idx="${i}" value="${escapeHtml(m.name)}" />
            <input type="text" class="mp-price" data-idx="${i}" value="${Math.round(m.price)}" />
          </div>`
          )
          .join('')}
      </div>
      <button type="button" class="btn-primary" id="discovered-menu-confirm-btn">선택한 메뉴 제보하기</button>`
      : '';

    if (items.length) {
      document.getElementById('discovered-menu-confirm-btn').addEventListener('click', () => confirmDiscoveredMenuReport(d));
    }
  } catch (err) {
    statusEl.textContent = '';
    resultsEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  } finally {
    fileInput.value = '';
  }
}

async function confirmDiscoveredMenuReport(d) {
  const statusEl = document.getElementById('discovered-menu-status');
  const confirmBtn = document.getElementById('discovered-menu-confirm-btn');
  confirmBtn.disabled = true;

  const toSave = [];
  document.querySelectorAll('#discovered-menu-results .menu-photo-row').forEach((row) => {
    if (!row.querySelector('.mp-check').checked) return;
    const name = row.querySelector('.mp-name').value.trim();
    const price = parseFloat(row.querySelector('.mp-price').value);
    if (!name || Number.isNaN(price) || price < 0) return;
    toSave.push({ name, price });
  });

  if (!toSave.length) {
    statusEl.textContent = '제보할 메뉴를 선택해주세요.';
    confirmBtn.disabled = false;
    return;
  }

  statusEl.textContent = '제보 중...';
  let success = 0;
  let listed = 0;
  let totalXp = 0;
  for (const item of toSave) {
    try {
      const saved = await apiFetch('/places/menu-reports', {
        method: 'POST',
        body: JSON.stringify({
          place_id: d.place_id || null,
          kakao_place_id: d.kakao_place_id || null,
          place_name: d.place_name,
          address: d.address || null,
          phone: d.phone || null,
          category_name: d.category_name || null,
          lat: d.lat,
          lng: d.lng,
          name: item.name,
          price: item.price,
        }),
      });
      success++;
      if (saved.listed_on_map) listed++;
      totalXp += saved.xp_awarded || 0;
    } catch {
      // 개별 실패는 건너뛰고 계속 진행, 완료 후 성공 개수로 안내
    }
  }

  statusEl.textContent = listed
    ? `${success}/${toSave.length}개 메뉴 제보 완료! 그중 ${listed}개는 지도에 절약 정보로 바로 떴어요. 감사합니다!`
    : `${success}/${toSave.length}개 메뉴 제보 완료! 감사합니다.`;
  document.getElementById('discovered-menu-results').innerHTML = '';
  if (totalXp > 0) loadSavingsBadge();
}

function prefillMerchantPlace(d) {
  document.getElementById('p-name').value = d.place_name;
  document.getElementById('p-address').value = d.address || '';
  document.getElementById('p-phone').value = d.phone || '';
  document.getElementById('p-kakao-place-id').value = d.kakao_place_id || '';
  document.getElementById('p-lat').value = d.lat;
  document.getElementById('p-lng').value = d.lng;
  document.getElementById('p-location-status').textContent =
    '지도에서 선택한 매장 위치가 자동 입력됐어요. 실제 매장과 다르면 다시 설정해주세요.';
  document.getElementById('p-menu-name').focus();
}

async function submitStatusUpdate(r, status, btn) {
  const msgEl = document.getElementById('detail-visit-msg');
  if (!navigator.geolocation) {
    msgEl.innerHTML = '<p class="error-msg">이 브라우저는 위치 정보를 지원하지 않습니다.</p>';
    return;
  }
  const buttons = new Set([btn, ...btn.parentElement.querySelectorAll('.btn-visit')]);
  buttons.forEach((b) => (b.disabled = true));
  msgEl.innerHTML = '<p class="empty-msg">위치 확인 중...</p>';

  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      try {
        const data = await apiFetch(`/places/${r.place_id}/status-updates`, {
          method: 'POST',
          body: JSON.stringify({
            status,
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            accuracy_m: pos.coords.accuracy,
          }),
        });
        document.getElementById('detail-interest-count').textContent = `누적 발견 ${data.interest_count}회`;
        msgEl.innerHTML = `<p class="empty-msg">${ICONS.check} 확인 감사합니다!</p>`;
        // 발견하기도 아바타 성장치(발견+방문+추천 합산, 2-4)에 들어간다. 휴무/임시
        // 휴무 제보는 같은 API를 쓰지만 "절약 행동"은 아니라 토스트는 발견(open)일
        // 때만 띄운다.
        triggerAvatarGrowthFeedback();
        loadMyProfile();
        if (status === 'open') showSavingsToast('🧭 발견 완료!');
      } catch (err) {
        msgEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
      } finally {
        buttons.forEach((b) => (b.disabled = false));
      }
    },
    () => {
      msgEl.innerHTML = '<p class="error-msg">위치를 가져올 수 없습니다. 위치 권한을 허용해주세요.</p>';
      buttons.forEach((b) => (b.disabled = false));
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

async function verifyOffer(offerId, verdict, btn) {
  const msgEl = document.getElementById('detail-verify-msg');
  const buttons = btn.parentElement.querySelectorAll('.btn-verify');
  buttons.forEach((b) => (b.disabled = true));
  try {
    await apiFetch(`/offers/${offerId}/verify`, {
      method: 'POST',
      body: JSON.stringify({ verdict }),
    });
    msgEl.innerHTML = `<p class="empty-msg">${ICONS.check} 확인 감사합니다! 신뢰도에 반영됐어요.</p>`;
  } catch (err) {
    msgEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
    buttons.forEach((b) => (b.disabled = false));
  }
}

function certifyResultHtml(cert, isFirst) {
  // isFirst: 인증 시도 당시(방문 인증 이전) 그 매장의 dining_count가 0이었는지 —
  // 실제 이전 카운트를 그대로 참조하므로 지어낸 사회적 증거가 아니다(현장 활동
  // 유도 기획안 §3-F, 2026-08-13).
  const firstLine = isFirst
    ? '<p class="empty-msg empty-msg--first">🙋 이 매장의 첫 절약 인증이에요!</p>'
    : '';
  return `
    ${firstLine}
    <p class="empty-msg">${ICONS.check} 인증 완료! +${Math.round(cert.amount).toLocaleString()}원 절약
    (누적 ${formatWon(cert.total_saved)})</p>`;
}

async function certifyOffer(r) {
  const msgEl = document.getElementById('detail-certify-msg');
  const token = await getAccessToken();
  if (!token) {
    msgEl.innerHTML = '<p class="error-msg">인증은 로그인 후 이용할 수 있어요. MY 탭에서 로그인해주세요.</p>';
    return;
  }

  const input = prompt('실제로 얼마에 구매하셨나요? (원)', Math.round(r.final_price));
  if (input === null) return;
  const actualPrice = parseFloat(input);
  if (Number.isNaN(actualPrice) || actualPrice < 0) {
    msgEl.innerHTML = '<p class="error-msg">올바른 금액을 입력해주세요.</p>';
    return;
  }

  msgEl.innerHTML = '<p class="empty-msg">인증 처리 중...</p>';
  try {
    const cert = await apiFetch(`/offers/${r.offer_id}/certify`, {
      method: 'POST',
      body: JSON.stringify({ method: 'simple', actual_price: actualPrice }),
    });
    msgEl.innerHTML = certifyResultHtml(cert, r.dining_count === 0);
    loadSavingsBadge();
    triggerAvatarGrowthFeedback();
    loadMyProfile();
    // 실제 서버가 계산한 절약액(cert.amount)만 문구에 쓴다 — 지어낸 숫자 없음.
    showSavingsToast(`💰 +${Math.round(cert.amount).toLocaleString()}원 절약 확정!`);
  } catch (err) {
    msgEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}

// --- 영수증 사진으로 인증: 사진 증거가 있는 인증이라 자기신고(simple)보다 XP를 더
// 준다 (백엔드가 실제로 사진을 다시 OCR해서 금액을 검증하므로 지어낼 수 없다). ---
async function certifyWithReceipt(r, fileInput) {
  const file = fileInput.files[0];
  if (!file) return;
  const msgEl = document.getElementById('detail-certify-msg');

  const token = await getAccessToken();
  if (!token) {
    msgEl.innerHTML = '<p class="error-msg">인증은 로그인 후 이용할 수 있어요. MY 탭에서 로그인해주세요.</p>';
    fileInput.value = '';
    return;
  }

  msgEl.innerHTML = '<p class="empty-msg">영수증을 확인하고 있어요...</p>';
  const form = new FormData();
  form.append('image', file);
  try {
    const analyzeResp = await fetch(`${API_BASE}/reports/analyze`, { method: 'POST', body: form });
    const analyzed = await analyzeResp.json().catch(() => null);
    if (!analyzeResp.ok) {
      throw new Error(analyzed?.detail?.message || analyzed?.detail || `분석 실패 (${analyzeResp.status})`);
    }

    const confirmMsg = analyzed.ocr_price
      ? `영수증에서 ${Math.round(analyzed.ocr_price).toLocaleString()}원을 인식했어요. 이 매장 방문 인증에 사용할까요?`
      : '영수증에서 금액을 정확히 읽지 못했어요. 그래도 인증에 사용할까요?';
    if (!confirm(confirmMsg)) {
      msgEl.innerHTML = '';
      return;
    }

    msgEl.innerHTML = '<p class="empty-msg">인증 처리 중...</p>';
    const cert = await apiFetch(`/offers/${r.offer_id}/certify`, {
      method: 'POST',
      body: JSON.stringify({
        method: 'receipt',
        receipt_image_url: analyzed.image_url,
        actual_price: analyzed.ocr_price ?? null,
      }),
    });
    msgEl.innerHTML = certifyResultHtml(cert, r.dining_count === 0);
    loadSavingsBadge();
    triggerAvatarGrowthFeedback();
    loadMyProfile();
    // 실제 서버가 계산한 절약액(cert.amount)만 문구에 쓴다 — 지어낸 숫자 없음.
    showSavingsToast(`💰 +${Math.round(cert.amount).toLocaleString()}원 절약 확정!`);
  } catch (err) {
    msgEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  } finally {
    fileInput.value = '';
  }
}

// --- 검색 실행 ---
async function runSearch() {
  const lat = document.getElementById('s-lat').value;
  const lng = document.getElementById('s-lng').value;
  const radius = currentRadiusKm;

  const params = new URLSearchParams({ lat, lng, radius_km: radius });

  const resultsEl = document.getElementById('search-results');
  const countEl = document.getElementById('sheet-count');
  resultsEl.innerHTML = '<p class="empty-msg">주변 절약 기회를 찾는 중...</p>';

  // 자동 위치 확인이 실패/거부돼 하드코딩된 평택시청 좌표로 대체된 경우에만 —
  // 왜 이 위치가 나왔는지 숨기지 않는다. 위치가 바뀌면(내 위치 버튼, 주소검색,
  // 지도 재검색) usedFallbackLocation을 그때그때 해제해서 한 번만 보이게 한다.
  const fallbackNoticeHtml = usedFallbackLocation
    ? '<p class="location-fallback-notice">📍 위치 권한이 없어 평택시청 기준으로 보여드려요</p>'
    : '';

  try {
    const data = await apiFetch(`/search?${params.toString()}`);
    lastResults = data.results;
    lastDiscovered = data.discovered_places || [];
    renderMapMarkers(parseFloat(lat), parseFloat(lng), data.results, lastDiscovered);

    if (data.results.length === 0 && lastDiscovered.length === 0) {
      countEl.textContent = '주변에 절약 기회가 없어요';
      resultsEl.innerHTML = `${fallbackNoticeHtml}<p class="empty-msg">반경을 넓혀서 다시 찾아보세요.</p>`;
      return;
    }

    countEl.textContent = data.results.length > 0
      ? `지금 잡을 수 있는 절약 ${data.results.length}개`
      : `주변에서 ${lastDiscovered.length}곳 발견`;

    const offerCardsHtml = data.results
      .map((r, i) => {
        const report = r.report;
        const shortCategory = r.category_name ? r.category_name.split(' > ').pop() : '';
        const statusLabel = STATUS_LABELS[r.business_status] || '';
        const hasScore = report && report.score != null;
        // 신뢰도 점수는 없어도(실제 방문 신호 부족) 가격 비교 자체는 이미 끝난
        // 경우가 흔하다 — 그걸 무조건 "계산 중"으로 뭉개지 않고, 있는 숫자는
        // 출처(AI 추정 vs 실측)를 밝히고 보여준다.
        const hasEstimate = !hasScore && r.total_savings > 0;
        // 발견/방문 인증이 0건이면 완전 콜드스타트 매장 — "계산 중"이 아니라
        // "가보면 첫 인증자가 된다"는 행동 요청으로 카드 문구를 바꾼다(현장 활동
        // 유도 기획안 §3-B, 2026-08-13).
        const isUnverified = !hasScore && !hasEstimate && r.discover_count === 0 && r.dining_count === 0;
        return `
      <div class="result-card" data-idx="${i}">
        <div class="result-header">
          <div class="badge-group">
            <span class="badge">${escapeHtml(shortCategory || CATEGORY_LABELS[r.category] || r.category)}</span>
            ${statusLabel ? `<span class="status-tag">${statusLabel}</span>` : ''}
          </div>
          <span class="distance">${r.distance_m.toFixed(0)}m</span>
        </div>
        <div class="place-name">${escapeHtml(r.place_name)}</div>
        ${r.signature_menu ? `<div class="signature-menu signature-menu--card">대표메뉴 ${escapeHtml(r.signature_menu.name)} ${Math.round(r.signature_menu.price).toLocaleString()}원</div>` : ''}
        ${hasScore
          ? `<div class="card-score-line">
              ${confidenceStarsHtml(report.confidence_stars)}
              <span class="card-score">AI 절약점수 <strong>${report.score}점</strong></span>
              <span class="card-grade">${escapeHtml(report.grade)}</span>
            </div>
            ${r.total_savings > 0
              ? `<div class="card-savings-line">평균보다 <strong>${Math.round(r.savings_rate)}% 저렴</strong> · 예상 절약 <strong>약 ${Math.round(r.total_savings).toLocaleString()}원</strong></div>`
              : ''}`
          : hasEstimate
            ? `<div class="card-score-line card-score-line--ai">🤖 ${r.savings_source === 'ai' ? 'AI 추정' : '실측 비교'} <strong>${Math.round(r.savings_rate)}% 저렴</strong></div>
              <div class="card-savings-line">예상 절약 <strong>약 ${Math.round(r.total_savings).toLocaleString()}원</strong> · 방문 데이터가 쌓이면 신뢰도가 표시돼요</div>`
            : isUnverified
              ? `<div class="card-score-line card-score-line--unverified">🙋 아직 아무도 확인 안 한 곳 · 가보시면 첫 인증자가 돼요</div>`
              : `<div class="card-score-line card-score-line--calc">⚪ 절약 정보를 계산하는 중입니다</div>`}
        <div class="card-proof-line">👀 관심 ${r.discover_count} · 🔥 방문 인증 ${r.dining_count}${r.recommend_count ? ` · 👍 추천 ${r.recommend_count}` : ''}</div>
      </div>`;
      })
      .join('');

    const discoveredHtml = lastDiscovered.length
      ? `
      <div class="discovered-section">
        <div class="discovered-header">주변에서 발견한 곳 ${lastDiscovered.length}곳 (아직 절약 정보 없음)</div>
        ${lastDiscovered
          .map((d, i) => {
            const shortCategory = d.category_name ? d.category_name.split(' > ').pop() : '';
            return `
          <div class="discovered-card" data-idx="${i}">
            <div class="discovered-name">${escapeHtml(d.place_name)}</div>
            <div class="discovered-meta">${shortCategory ? escapeHtml(shortCategory) + ' · ' : ''}${d.distance_m.toFixed(0)}m</div>
            <div class="discovered-cta">가격 정보 없음 · 눌러서 등록하기</div>
          </div>`;
          })
          .join('')}
      </div>`
      : '';

    resultsEl.innerHTML = fallbackNoticeHtml + offerCardsHtml + discoveredHtml;

    resultsEl.querySelectorAll('.result-card').forEach((card) => {
      card.addEventListener('click', () => openOfferDetail(lastResults[Number(card.dataset.idx)]));
    });

    resultsEl.querySelectorAll('.discovered-card').forEach((card) => {
      card.addEventListener('click', () => openDiscoveredDetail(lastDiscovered[Number(card.dataset.idx)]));
    });
  } catch (err) {
    countEl.textContent = '검색 실패';
    resultsEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}

// --- 첫 로드: GPS로 실제 위치를 자동으로 잡는다 (2026-08-13) ---
// 기존엔 "내 위치" 버튼을 눌러야만 geolocation을 물어봐서, 안 누르면 항상
// 하드코딩된 평택시청 좌표로만 보였다(사용자 리포트: "자꾸 평택시청으로만 나옴").
// 페이지 로드 시 위치 확인을 먼저 시도하고, 실패/거부/타임아웃일 때만 평택시청
// 으로 폴백한다 — 그 사실을 숨기지 않고 결과 목록 위에 짧게 알린다.
const PYEONGTAEK_FALLBACK = { lat: 36.9925, lng: 127.113 };
let usedFallbackLocation = false;

function getGeolocationOnce(timeoutMs) {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve(null);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: timeoutMs }
    );
  });
}

async function initialLoad() {
  // 위치 확인은 최대 6초까지만 기다린다 — 그 이상 걸리면 폴백 좌표로라도
  // 화면을 띄운다(무한 대기 방지).
  const GEOLOCATION_HARD_CAP_MS = 6000;
  const hardCap = new Promise((resolve) => setTimeout(() => resolve(null), GEOLOCATION_HARD_CAP_MS));

  const located = await Promise.race([getGeolocationOnce(5000), hardCap]);
  const { lat, lng } = located || PYEONGTAEK_FALLBACK;
  usedFallbackLocation = !located;

  if (located) {
    document.getElementById('s-lat').value = lat.toFixed(6);
    document.getElementById('s-lng').value = lng.toFixed(6);
  }

  initMap(lat, lng);
  await runSearch().catch(() => {});
}

initialLoad();

// --- COMMUNITY: 제보 (사진 한 장 → AI 자동 분석 → 확인 후 등록) ---
let reportImageUrl = null;
let reportLat = null;
let reportLng = null;

const reportPhotoInput = document.getElementById('r-photo-input');
const reportCaptureStatus = document.getElementById('report-capture-status');
const reportCaptureSection = document.getElementById('report-capture');
const reportConfirmSection = document.getElementById('report-confirm');
const reportResultEl = document.getElementById('report-result');

reportPhotoInput.addEventListener('change', () => {
  const file = reportPhotoInput.files[0];
  if (!file) return;
  reportResultEl.innerHTML = '';
  reportCaptureStatus.textContent = '위치 확인 중...';

  if (!navigator.geolocation) {
    analyzeReportPhoto(file);
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      reportLat = pos.coords.latitude;
      reportLng = pos.coords.longitude;
      analyzeReportPhoto(file);
    },
    () => {
      reportLat = null;
      reportLng = null;
      analyzeReportPhoto(file);
    },
    { enableHighAccuracy: true, timeout: 8000 }
  );
});

async function analyzeReportPhoto(file) {
  reportCaptureStatus.textContent = 'AI가 사진을 분석하고 있어요...';

  const form = new FormData();
  form.append('image', file);
  if (reportLat != null) form.append('lat', reportLat);
  if (reportLng != null) form.append('lng', reportLng);

  const token = await getAccessToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const resp = await fetch(`${API_BASE}/reports/analyze`, { method: 'POST', headers, body: form });
    const data = await resp.json().catch(() => null);
    if (!resp.ok) {
      const message = data?.detail?.message || data?.detail || `분석 실패 (${resp.status})`;
      throw new Error(message);
    }

    reportImageUrl = data.image_url;
    document.getElementById('report-preview-img').src = data.image_url;
    document.getElementById('r-title').value = data.ocr_title || '';
    document.getElementById('r-price').value = data.ocr_price != null ? data.ocr_price : '';
    document.getElementById('r-category').value = data.ai_category || '';
    document.getElementById('report-location-status').textContent =
      reportLat != null ? '현재 위치 자동 설정 완료' : '위치를 확인하지 못했어요 (제보는 계속 가능해요)';

    reportCaptureSection.classList.add('hidden');
    reportConfirmSection.classList.remove('hidden');
    reportCaptureStatus.textContent = '';
  } catch (err) {
    reportCaptureStatus.textContent = '';
    reportResultEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}

function resetReportForm() {
  reportConfirmSection.classList.add('hidden');
  reportCaptureSection.classList.remove('hidden');
  reportPhotoInput.value = '';
  reportImageUrl = null;
  reportLat = null;
  reportLng = null;
}

document.getElementById('report-cancel-btn').addEventListener('click', resetReportForm);

document.getElementById('report-confirm-btn').addEventListener('click', async () => {
  if (!reportImageUrl) return;
  const title = document.getElementById('r-title').value.trim();
  if (!title) {
    alert('제목을 입력해주세요.');
    document.getElementById('r-title').focus();
    return;
  }
  const priceVal = document.getElementById('r-price').value;
  const payload = {
    image_url: reportImageUrl,
    lat: reportLat,
    lng: reportLng,
    title,
    price: priceVal ? parseFloat(priceVal) : null,
    category: document.getElementById('r-category').value || null,
  };

  const btn = document.getElementById('report-confirm-btn');
  btn.disabled = true;
  try {
    await apiFetch('/reports', { method: 'POST', body: JSON.stringify(payload) });
    reportResultEl.innerHTML = `<p class="empty-msg">${ICONS.check} 제보 완료! 검토 후 지도에 반영됩니다.</p>`;
    resetReportForm();
    loadRecentReports();
  } catch (err) {
    reportResultEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  } finally {
    btn.disabled = false;
  }
});

async function loadRecentReports() {
  const listEl = document.getElementById('recent-reports-list');
  listEl.innerHTML = '<p class="empty-msg">불러오는 중...</p>';
  try {
    const reports = await apiFetch('/reports/recent');
    listEl.innerHTML = reports.length
      ? reports
          .map(
            (r) => `
      <div class="list-row">
        [${CATEGORY_LABELS[r.ai_category] || r.ai_category || '분류중'}] ${escapeHtml(r.ocr_title || '(제목 인식 중)')}
        ${r.ocr_price != null ? ` - ${r.ocr_price.toLocaleString()}원` : ''}
        <span class="tier-tag ${r.status === 'pending' ? 'tier-pending' : ''}">${r.status === 'pending' ? '확인 필요' : r.status}</span>
      </div>`
          )
          .join('')
      : '<p class="empty-msg">아직 제보된 정보가 없습니다.</p>';
  } catch (err) {
    listEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}
document.getElementById('load-recent-reports-btn').addEventListener('click', loadRecentReports);
loadRecentReports();

// --- EXCHANGE: 절약 자산 등록/교환 ---
document.getElementById('asset-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const title = document.getElementById('a-title').value.trim();
  if (!title) {
    alert('자산명을 입력해주세요.');
    document.getElementById('a-title').focus();
    return;
  }
  const expiresRaw = document.getElementById('a-expires').value;
  const payload = {
    category: document.getElementById('a-category').value,
    title,
    condition_text: document.getElementById('a-condition').value || null,
    estimated_value: parseFloat(document.getElementById('a-value').value) || null,
    expires_at: expiresRaw ? new Date(expiresRaw).toISOString() : null,
  };
  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  try {
    await apiFetch('/exchange/assets', { method: 'POST', body: JSON.stringify(payload) });
    e.target.reset();
    loadMyAssets();
    loadAssets();
    loadMyProfile();
  } catch (err) {
    alert(`등록 실패: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
  }
});

function assetCard(a, { own } = {}) {
  const expiresText = a.expires_at ? `사용기한 ${new Date(a.expires_at).toLocaleDateString()}` : '기한 없음';
  return `
    <div class="result-card">
      <div class="result-header">
        <span class="badge">${ASSET_CATEGORY_LABELS[a.category] || a.category}</span>
        ${a.estimated_value ? `<span class="distance">예상 절약 ${formatWon(a.estimated_value)}</span>` : ''}
      </div>
      <div class="place-name">${escapeHtml(a.title)}</div>
      ${a.condition_text ? `<div class="meta-line">${escapeHtml(a.condition_text)}</div>` : ''}
      <div class="meta-line">${expiresText}</div>
      ${
        own
          ? `<button type="button" class="btn-text btn-delete-inline" data-id="${a.id}">삭제</button>`
          : `<button type="button" class="btn-secondary" disabled>교환 요청 (준비 중)</button>`
      }
    </div>`;
}

async function loadMyAssets() {
  const listEl = document.getElementById('my-assets-list');
  listEl.innerHTML = '<p class="empty-msg">불러오는 중...</p>';
  try {
    const assets = await apiFetch('/exchange/assets/mine');
    document.getElementById('exchange-my-count').textContent = assets.length;
    document.getElementById('exchange-my-value').textContent = formatWon(
      assets.reduce((sum, a) => sum + (a.estimated_value || 0), 0)
    );
    listEl.innerHTML = assets.length
      ? assets.map((a) => assetCard(a, { own: true })).join('')
      : '<p class="empty-msg">등록한 절약 자산이 없습니다.</p>';
    listEl.querySelectorAll('.btn-delete-inline').forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          await apiFetch(`/exchange/assets/${btn.dataset.id}`, { method: 'DELETE' });
          loadMyAssets();
          loadAssets();
          loadMyProfile();
        } catch (err) {
          alert(`삭제 실패: ${err.message}`);
        }
      });
    });
  } catch (err) {
    listEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}
document.getElementById('load-my-assets-btn').addEventListener('click', loadMyAssets);

async function loadAssets() {
  const listEl = document.getElementById('assets-list');
  listEl.innerHTML = '<p class="empty-msg">불러오는 중...</p>';
  try {
    const assets = await apiFetch('/exchange/assets');
    listEl.innerHTML = assets.length
      ? assets.map((a) => assetCard(a, { own: false })).join('')
      : '<p class="empty-msg">교환 가능한 절약 자산이 아직 없습니다.</p>';
  } catch (err) {
    listEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}
document.getElementById('load-assets-btn').addEventListener('click', loadAssets);

// --- 사업자: 매장 ---
document.getElementById('p-use-location-btn').addEventListener('click', (e) => {
  const btn = e.target;
  const statusEl = document.getElementById('p-location-status');
  if (!navigator.geolocation) {
    statusEl.textContent = '이 브라우저는 위치 정보를 지원하지 않습니다.';
    return;
  }
  btn.disabled = true;
  statusEl.textContent = '위치 확인 중...';
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      document.getElementById('p-lat').value = pos.coords.latitude;
      document.getElementById('p-lng').value = pos.coords.longitude;
      statusEl.textContent = '현재 위치로 설정 완료';
      btn.disabled = false;
    },
    () => {
      statusEl.textContent = '위치를 가져올 수 없습니다. 다시 시도해주세요.';
      btn.disabled = false;
    },
    { enableHighAccuracy: true, timeout: 8000 }
  );
});

// 매장 등록과 첫 메뉴 가격 등록을 한 폼, 한 번의 제출로 처리한다 — 매장만 등록하고
// 메뉴가 없으면 지도 검색(offer 기반)에 절대 안 뜨는데, 예전엔 이걸 별도 폼/버튼으로
// 나눠놔서 등록이 "끝났다"고 착각하고 메뉴 단계를 건너뛰기 쉬웠다.
document.getElementById('place-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = document.getElementById('p-name').value.trim();
  const lat = parseFloat(document.getElementById('p-lat').value);
  const lng = parseFloat(document.getElementById('p-lng').value);
  const menuName = document.getElementById('p-menu-name').value.trim();
  const menuPrice = parseFloat(document.getElementById('p-menu-price').value);

  if (!name) {
    alert('매장명을 입력해주세요.');
    document.getElementById('p-name').focus();
    return;
  }
  if (Number.isNaN(lat) || Number.isNaN(lng)) {
    alert('먼저 "현재 위치로 매장 위치 설정" 버튼을 눌러주세요.');
    return;
  }
  if (!menuName) {
    alert('메뉴명을 입력해주세요.');
    document.getElementById('p-menu-name').focus();
    return;
  }
  if (Number.isNaN(menuPrice) || menuPrice < 0) {
    alert('메뉴 가격을 올바르게 입력해주세요.');
    document.getElementById('p-menu-price').focus();
    return;
  }

  const payload = {
    name,
    address: document.getElementById('p-address').value || null,
    phone: document.getElementById('p-phone').value || null,
    kakao_place_id: document.getElementById('p-kakao-place-id').value || null,
    lat,
    lng,
  };
  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  try {
    const place = await apiFetch('/merchant/places', { method: 'POST', body: JSON.stringify(payload) });
    const item = await apiFetch('/merchant/menu-items', {
      method: 'POST',
      body: JSON.stringify({ place_id: place.id, name: menuName, price: menuPrice }),
    });
    alert(menuSavingsMessage(item));
    e.target.reset();
    document.getElementById('p-location-status').textContent = '매장에서 이 버튼을 눌러 위치를 자동으로 설정하세요.';
    loadPlaces();
  } catch (err) {
    alert(`등록 실패: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
  }
});

async function loadPlaces() {
  const listEl = document.getElementById('places-list');
  const selectEl = document.getElementById('o-place-id');
  const menuSelectEl = document.getElementById('mi-place-id');
  const menuPhotoSelectEl = document.getElementById('mi-photo-place-id');
  listEl.innerHTML = '<p class="empty-msg">불러오는 중...</p>';
  try {
    const places = await apiFetch('/merchant/places');
    listEl.innerHTML = places.length
      ? places.map((p) => `<div class="list-row">#${p.id} ${escapeHtml(p.name)} ${p.address ? '- ' + escapeHtml(p.address) : ''}</div>`).join('')
      : '<p class="empty-msg">등록된 매장이 없습니다.</p>';

    const options = places.length
      ? places.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('')
      : '<option value="">매장을 먼저 등록해주세요</option>';
    selectEl.innerHTML = options;
    menuSelectEl.innerHTML = options;
    menuPhotoSelectEl.innerHTML = options;

    merchantPlaces = places;
  } catch (err) {
    listEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}
document.getElementById('load-places-btn').addEventListener('click', loadPlaces);

// --- 사업자: 메뉴판 사진 한 번에 등록 (AI가 메뉴명·가격을 통째로 읽어옴) ---
document.getElementById('mi-photo-input').addEventListener('change', async () => {
  const fileInput = document.getElementById('mi-photo-input');
  const file = fileInput.files[0];
  if (!file) return;

  const placeId = parseInt(document.getElementById('mi-photo-place-id').value, 10);
  const statusEl = document.getElementById('mi-photo-status');
  const resultsEl = document.getElementById('mi-photo-results');
  resultsEl.innerHTML = '';

  if (Number.isNaN(placeId)) {
    statusEl.textContent = '먼저 매장을 선택해주세요.';
    fileInput.value = '';
    return;
  }

  statusEl.textContent = 'AI가 메뉴판을 읽고 있어요...';
  const form = new FormData();
  form.append('image', file);
  const token = await getAccessToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const resp = await fetch(`${API_BASE}/merchant/menu-items/analyze`, { method: 'POST', headers, body: form });
    const data = await resp.json().catch(() => null);
    if (!resp.ok) {
      const message = data?.detail?.message || data?.detail || `분석 실패 (${resp.status})`;
      throw new Error(message);
    }

    const items = data.items || [];
    statusEl.textContent = items.length
      ? `${items.length}개 메뉴를 찾았어요. 확인하고 등록해주세요.`
      : '메뉴를 찾지 못했어요. 더 선명한 사진으로 다시 시도해보세요.';

    resultsEl.innerHTML = items.length
      ? `
      <div class="menu-photo-list">
        ${items
          .map(
            (m, i) => `
          <div class="menu-photo-row">
            <input type="checkbox" class="mp-check" data-idx="${i}" checked />
            <input type="text" class="mp-name" data-idx="${i}" value="${escapeHtml(m.name)}" />
            <input type="text" class="mp-price" data-idx="${i}" value="${Math.round(m.price)}" />
          </div>`
          )
          .join('')}
      </div>
      <button type="button" class="btn-primary" id="mi-photo-confirm-btn">선택한 메뉴 일괄 등록</button>`
      : '';

    if (items.length) {
      document.getElementById('mi-photo-confirm-btn').addEventListener('click', () => confirmMenuPhotoResults(placeId));
    }
  } catch (err) {
    statusEl.textContent = '';
    resultsEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  } finally {
    fileInput.value = '';
  }
});

async function confirmMenuPhotoResults(placeId) {
  const statusEl = document.getElementById('mi-photo-status');
  const confirmBtn = document.getElementById('mi-photo-confirm-btn');
  confirmBtn.disabled = true;

  const toSave = [];
  document.querySelectorAll('.menu-photo-row').forEach((row) => {
    if (!row.querySelector('.mp-check').checked) return;
    const name = row.querySelector('.mp-name').value.trim();
    const price = parseFloat(row.querySelector('.mp-price').value);
    if (!name || Number.isNaN(price) || price < 0) return;
    toSave.push({ name, price });
  });

  if (!toSave.length) {
    statusEl.textContent = '등록할 메뉴를 선택해주세요.';
    confirmBtn.disabled = false;
    return;
  }

  statusEl.textContent = '등록 중...';
  let success = 0;
  let listed = 0;
  for (const item of toSave) {
    try {
      const saved = await apiFetch('/merchant/menu-items', {
        method: 'POST',
        body: JSON.stringify({ place_id: placeId, name: item.name, price: item.price }),
      });
      success++;
      if (saved.listed_on_map) listed++;
    } catch {
      // 개별 등록 실패는 건너뛰고 계속 진행, 완료 후 성공 개수로 안내
    }
  }

  statusEl.textContent = listed
    ? `${success}/${toSave.length}개 메뉴 등록 완료! 그중 ${listed}개는 지역 평균보다 저렴해서 지도에 절약 정보로 떴어요.`
    : `${success}/${toSave.length}개 메뉴 등록 완료! 아직 지도에 뜬 항목은 없어요 — 지역 평균보다 저렴하거나 비교할 주변 매장이 더 모이면 자동으로 떠요.`;
  document.getElementById('mi-photo-results').innerHTML = '';
  loadMenuItems();
}

// --- 사업자: 혜택 ---
document.getElementById('offer-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const placeId = parseInt(document.getElementById('o-place-id').value, 10);
  const title = document.getElementById('o-title').value.trim();
  const ttl = document.getElementById('o-ttl').value;

  if (Number.isNaN(placeId)) {
    alert('매장을 선택해주세요. (매장이 없다면 먼저 매장을 등록해주세요)');
    return;
  }
  if (!title) {
    alert('혜택 제목을 입력해주세요.');
    document.getElementById('o-title').focus();
    return;
  }

  const payload = {
    place_id: placeId,
    title,
    category: document.getElementById('o-category').value,
    base_price: parseFloat(document.getElementById('o-base-price').value) || null,
    store_discount: parseFloat(document.getElementById('o-discount').value) || null,
    ttl_sec: ttl ? parseInt(ttl, 10) : null,
  };
  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  try {
    await apiFetch('/merchant/offers', { method: 'POST', body: JSON.stringify(payload) });
    alert('혜택 등록 완료!');
    e.target.reset();
    loadOffers();
  } catch (err) {
    alert(`혜택 등록 실패: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
  }
});

async function loadOffers() {
  const listEl = document.getElementById('offers-list');
  listEl.innerHTML = '<p class="empty-msg">불러오는 중...</p>';
  try {
    const offers = await apiFetch('/merchant/offers');
    listEl.innerHTML = offers.length
      ? offers
          .map(
            (o) => `
      <div class="list-row">
        #${o.id} [${CATEGORY_LABELS[o.category] || o.category}/${o.layer}] ${escapeHtml(o.title)}
        ${o.base_price != null ? ` - ${o.base_price.toLocaleString()}원` : ''}
        ${o.store_discount != null ? ` (할인 ${o.store_discount.toLocaleString()}원)` : ''}
        <button class="btn-text btn-end-inline" data-id="${o.id}">종료하기</button>
        <button class="btn-delete-inline" data-id="${o.id}">삭제</button>
      </div>`
          )
          .join('')
      : '<p class="empty-msg">등록된 혜택이 없습니다.</p>';

    listEl.querySelectorAll('.btn-end-inline').forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (!confirm('이 혜택을 지금 종료 처리할까요? 지도에서 바로 사라집니다.')) return;
        try {
          await apiFetch(`/merchant/offers/${btn.dataset.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ expires_at: new Date().toISOString() }),
          });
          loadOffers();
        } catch (err) {
          alert(`종료 처리 실패: ${err.message}`);
        }
      });
    });

    listEl.querySelectorAll('.btn-delete-inline').forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          await apiFetch(`/merchant/offers/${btn.dataset.id}`, { method: 'DELETE' });
          loadOffers();
        } catch (err) {
          alert(`삭제 실패: ${err.message}`);
        }
      });
    });
  } catch (err) {
    listEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}
document.getElementById('load-offers-btn').addEventListener('click', loadOffers);

// --- 사업자: 메뉴 가격 ---
document.getElementById('menu-item-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const placeId = parseInt(document.getElementById('mi-place-id').value, 10);
  const name = document.getElementById('mi-name').value.trim();
  const price = parseFloat(document.getElementById('mi-price').value);

  if (Number.isNaN(placeId)) {
    alert('매장을 선택해주세요. (매장이 없다면 먼저 매장을 등록해주세요)');
    return;
  }
  if (!name) {
    alert('메뉴명을 입력해주세요.');
    document.getElementById('mi-name').focus();
    return;
  }
  if (Number.isNaN(price) || price < 0) {
    alert('가격을 올바르게 입력해주세요.');
    document.getElementById('mi-price').focus();
    return;
  }

  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  try {
    const item = await apiFetch('/merchant/menu-items', {
      method: 'POST',
      body: JSON.stringify({ place_id: placeId, name, price }),
    });
    alert(menuSavingsMessage(item));
    e.target.reset();
    loadMenuItems();
  } catch (err) {
    alert(`메뉴 등록 실패: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
  }
});

// --- 메뉴 가격 등록 결과가 실제로 지도에 절약 정보로 뜨는지, 안 뜬다면 왜인지를
// 그 자리에서 알려준다 (지어내지 않기: 비교 표본이 2곳 미만이면 절약을 단정하지 않음). ---
function menuSavingsMessage(item) {
  const basis = item.benchmark_source === 'region'
    ? `지역 평균(${Math.round(item.benchmark_price).toLocaleString()}원)`
    : item.benchmark_source === 'ai'
      ? `AI 추정 통상가(약 ${Math.round(item.benchmark_price).toLocaleString()}원)`
      : null;

  if (item.listed_on_map) {
    return `메뉴 등록 완료! "${item.name}"이(가) ${basis}보다 ${Math.round(item.savings_amount)}원(${item.savings_rate}%) 저렴해서 지도에 절약 정보로 떴어요.`;
  }
  if (basis) {
    return `메뉴 등록 완료! 다만 ${basis}보다 저렴하진 않아서 아직 지도엔 절약 정보로 뜨지 않아요.`;
  }
  return `메뉴 등록 완료! 비교 기준을 찾지 못해서(주변 등록 ${item.sample_count}곳) 절약 계산이 아직 안 돼요.`;
}

async function loadMenuItems() {
  const listEl = document.getElementById('menu-items-list');
  listEl.innerHTML = '<p class="empty-msg">불러오는 중...</p>';
  if (!merchantPlaces.length) {
    listEl.innerHTML = '<p class="empty-msg">등록된 매장이 없습니다.</p>';
    return;
  }
  try {
    const perPlace = await Promise.all(
      merchantPlaces.map((p) =>
        apiFetch(`/merchant/places/${p.id}/menu-items`).then((items) => ({ place: p, items }))
      )
    );
    const rows = perPlace.flatMap(({ place, items }) =>
      items.map((m) => {
        const status = m.listed_on_map
          ? `<span class="menu-status menu-status--on">지도에 절약 정보로 표시 중 (-${Math.round(m.savings_amount)}원${m.benchmark_source === 'ai' ? ', AI 추정' : ''})</span>`
          : m.benchmark_source
            ? `<span class="menu-status menu-status--off">비교 기준보다 비싸거나 같음</span>`
            : `<span class="menu-status menu-status--pending">비교 기준 없음 (주변 등록 ${m.sample_count}곳)</span>`;
        return `
      <div class="list-row">
        [${escapeHtml(place.name)}] ${escapeHtml(m.name)} - ${m.price.toLocaleString()}원
        <button class="btn-delete-inline" data-id="${m.id}">삭제</button>
        <br />${status}
      </div>`;
      })
    );
    listEl.innerHTML = rows.length ? rows.join('') : '<p class="empty-msg">등록된 메뉴가 없습니다.</p>';

    listEl.querySelectorAll('.btn-delete-inline').forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          await apiFetch(`/merchant/menu-items/${btn.dataset.id}`, { method: 'DELETE' });
          loadMenuItems();
        } catch (err) {
          alert(`삭제 실패: ${err.message}`);
        }
      });
    });
  } catch (err) {
    listEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}
document.getElementById('load-menu-items-btn').addEventListener('click', loadMenuItems);

// 매장/혜택/절약 자산 목록은 로그인 상태(renderAuthState)에서 로드됩니다.
