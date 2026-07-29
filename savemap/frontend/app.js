const API_BASE = '/v1';

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

// (가정) 레벨 구간별 캐릭터 아바타. 실제 AI 3D 캐릭터 생성 전 단계의 임시(Mock) 표현.
const CHARACTER_AVATARS = [
  { minLevel: 1, icon: 'sprout' },
  { minLevel: 2, icon: 'compass' },
  { minLevel: 3, icon: 'backpack' },
  { minLevel: 4, icon: 'map' },
  { minLevel: 5, icon: 'medal' },
  { minLevel: 6, icon: 'shield' },
  { minLevel: 7, icon: 'crown' },
];

function characterAvatarFor(level) {
  let icon = CHARACTER_AVATARS[0].icon;
  for (const tier of CHARACTER_AVATARS) {
    if (level >= tier.minLevel) icon = tier.icon;
  }
  return ICONS[icon];
}

let currentCategory = '';

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

// --- 정보 신뢰도(최신 상태) 표시 ---
function freshnessInfo(lastVerifiedAt, count) {
  if (!lastVerifiedAt || !count) return { cls: 'fresh-none', label: '확인된 정보 없음' };
  const diffMin = (Date.now() - new Date(lastVerifiedAt).getTime()) / 60000;
  if (diffMin < 30) return { cls: 'fresh-now', label: '방금 확인됨' };
  if (diffMin < 120) return { cls: 'fresh-recent', label: `${Math.round(diffMin)}분 전 확인` };
  if (diffMin < 24 * 60) return { cls: 'fresh-today', label: `${Math.round(diffMin / 60)}시간 전 확인` };
  return { cls: 'fresh-stale', label: '오래된 정보 · 확인이 필요해요' };
}

function formatExpiry(iso) {
  const d = new Date(iso);
  const now = new Date();
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return d.toDateString() === now.toDateString()
    ? `오늘 ${hh}:${mm}까지`
    : `${d.getMonth() + 1}/${d.getDate()} ${hh}:${mm}까지`;
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
    loadPlaces();
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
    document.getElementById('character-avatar').innerHTML = characterAvatarFor(s.level);
    document.getElementById('my-level-badge').textContent = `Lv.${s.level}`;
    document.getElementById('my-title').textContent = s.title;
    document.getElementById('my-total-saved').textContent = formatWon(s.total_saved);
    document.getElementById('my-saving-bar').style.width = `${s.progress_pct}%`;
    document.getElementById('my-next-level-text').textContent =
      s.next_threshold == null
        ? '최고 레벨 구간입니다'
        : `다음 레벨까지 ${formatWon(s.remaining_to_next)}`;
    document.getElementById('my-cert-count').textContent = s.certification_count;

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
}

// --- 바텀시트 펼치기/접기 ---
const bottomSheet = document.getElementById('bottom-sheet');
document.getElementById('sheet-toggle').addEventListener('click', () => {
  bottomSheet.classList.toggle('expanded');
});

// --- 카테고리 칩 ---
document.querySelectorAll('.chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.chip').forEach((c) => c.classList.remove('active'));
    chip.classList.add('active');
    currentCategory = chip.dataset.category;
    runSearch();
  });
});

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
      if (kakaoMap) kakaoMap.setCenter(new kakao.maps.LatLng(lat, lng));
      useLocationBtn.disabled = false;
      useLocationLabel.textContent = originalLabel;
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

document.getElementById('s-radius').addEventListener('change', runSearch);

// --- 카카오 지도 ---
let kakaoMap = null;
let mapMarkers = [];
let originMarker = null;
const researchBtn = document.getElementById('research-btn');

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

  kakao.maps.event.addListener(kakaoMap, 'dragend', () => researchBtn.classList.remove('hidden'));
  kakao.maps.event.addListener(kakaoMap, 'zoom_changed', () => researchBtn.classList.remove('hidden'));
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
  if (originMarker) {
    originMarker.setMap(null);
    originMarker = null;
  }
}

// "절약 보물" 마커: 매장 아이콘보다 "여기서 얼마를 아낄 수 있는가"를 먼저 보여준다.
function treasureMarkerImage() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26">
    <circle cx="13" cy="13" r="10" fill="#f59e0b" stroke="white" stroke-width="3"/>
  </svg>`;
  return new kakao.maps.MarkerImage('data:image/svg+xml;base64,' + btoa(svg), new kakao.maps.Size(26, 26));
}

let lastResults = [];

function renderMapMarkers(originLat, originLng, results) {
  if (!kakaoMap) return;
  clearMarkers();

  const bounds = new kakao.maps.LatLngBounds();
  const originPos = new kakao.maps.LatLng(originLat, originLng);
  bounds.extend(originPos);

  originMarker = new kakao.maps.Marker({
    map: kakaoMap,
    position: originPos,
    image: new kakao.maps.MarkerImage(
      'data:image/svg+xml;base64,' +
        btoa('<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22"><circle cx="11" cy="11" r="8" fill="#0d9488" stroke="white" stroke-width="3"/></svg>'),
      new kakao.maps.Size(22, 22)
    ),
  });

  results.forEach((r) => {
    const pos = new kakao.maps.LatLng(r.lat, r.lng);
    bounds.extend(pos);
    const marker = new kakao.maps.Marker({ map: kakaoMap, position: pos, image: treasureMarkerImage() });
    kakao.maps.event.addListener(marker, 'click', () => openOfferDetail(r));
    mapMarkers.push(marker);
  });

  kakaoMap.setBounds(bounds);
}

// --- 절약 정보 상세 (예상 절약 확인 + 절약 인증) ---
const detailOverlay = document.getElementById('offer-detail-overlay');
const detailContent = document.getElementById('detail-content');

document.getElementById('detail-close-btn').addEventListener('click', () => {
  detailOverlay.classList.add('hidden');
});

function openOfferDetail(r) {
  const tier = getRarityTier(r.savings_rate);
  const fresh = freshnessInfo(r.last_verified_at, r.verification_count);
  detailContent.innerHTML = `
    <div class="badge-group">
      <span class="badge">${CATEGORY_LABELS[r.category] || r.category}</span>
      <span class="tier-tag">${tier.label}</span>
    </div>
    <h2 class="place-name">${escapeHtml(r.place_name)}</h2>
    <div class="price-line">
      <span class="final-price">${r.final_price.toLocaleString()}원</span>
      ${r.total_savings > 0 ? `<span class="base-price">${r.base_price.toLocaleString()}원</span>` : ''}
    </div>
    ${r.total_savings > 0 ? `<div class="expected-savings">예상 절약 ${Math.round(r.total_savings).toLocaleString()}원</div>` : ''}
    <div class="meta-line">
      현재 위치에서 ${r.distance_m.toFixed(0)}m ·
      <span class="fresh-dot ${fresh.cls}"></span>${fresh.label}${r.expires_at ? ` · ${formatExpiry(r.expires_at)}` : ''}
    </div>
    <div class="detail-actions">
      <button type="button" class="btn-secondary" id="detail-directions-btn">길찾기</button>
      <button type="button" class="btn-primary" id="detail-certify-btn">절약 인증하기</button>
    </div>
    <div id="detail-certify-msg"></div>

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

  document.getElementById('detail-directions-btn').addEventListener('click', () => {
    window.open(`https://map.kakao.com/link/to/${encodeURIComponent(r.place_name)},${r.lat},${r.lng}`, '_blank');
  });

  document.getElementById('detail-certify-btn').addEventListener('click', () => certifyOffer(r));

  detailContent.querySelectorAll('.btn-verify').forEach((btn) => {
    btn.addEventListener('click', () => verifyOffer(r.offer_id, btn.dataset.verdict, btn));
  });
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

async function certifyOffer(r) {
  const msgEl = document.getElementById('detail-certify-msg');
  const token = await getAccessToken();
  if (!token) {
    msgEl.innerHTML = '<p class="error-msg">절약 인증은 로그인 후 이용할 수 있어요. MY 탭에서 로그인해주세요.</p>';
    return;
  }

  const input = prompt('실제로 얼마에 구매하셨나요? (원)', Math.round(r.final_price));
  if (input === null) return;
  const actualPrice = parseFloat(input);
  if (Number.isNaN(actualPrice) || actualPrice < 0) {
    msgEl.innerHTML = '<p class="error-msg">올바른 금액을 입력해주세요.</p>';
    return;
  }

  msgEl.innerHTML = '<p class="empty-msg">절약 인증 처리 중...</p>';
  try {
    const cert = await apiFetch(`/offers/${r.offer_id}/certify`, {
      method: 'POST',
      body: JSON.stringify({ method: 'simple', actual_price: actualPrice }),
    });
    msgEl.innerHTML = `
      <p class="empty-msg">${ICONS.check} 절약 인증 완료! +${Math.round(cert.amount).toLocaleString()}원
      (누적 ${formatWon(cert.total_saved)}, Lv.${cert.level} ${escapeHtml(cert.title)})</p>`;
    loadSavingsBadge();
    loadMyProfile();
  } catch (err) {
    msgEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}

// --- 홈 히어로: "내 주변에서 최대 X원 절약 가능" ---
let lastRegionLabel = '';
let lastRegionCoords = null;

async function updateRegionLabel(lat, lng) {
  if (lastRegionCoords && Math.abs(lastRegionCoords.lat - lat) < 0.01 && Math.abs(lastRegionCoords.lng - lng) < 0.01) {
    return lastRegionLabel;
  }
  try {
    const res = await fetch(`${API_BASE}/geo/reverse?lat=${lat}&lng=${lng}`);
    const data = await res.json();
    lastRegionLabel = data.region || '';
    lastRegionCoords = { lat, lng };
  } catch {
    lastRegionLabel = '';
  }
  return lastRegionLabel;
}

function renderSavingsHero(results) {
  const heroEl = document.getElementById('savings-hero');
  const prefix = lastRegionLabel ? `${lastRegionLabel} · ` : '';
  if (!results || results.length === 0) {
    heroEl.textContent = `${prefix}내 주변 절약 정보를 찾고 있어요`;
    return;
  }
  const maxSavings = Math.max(...results.map((r) => r.total_savings || 0));
  heroEl.textContent =
    maxSavings > 0
      ? `${prefix}내 주변에서 최대 ${Math.round(maxSavings).toLocaleString()}원 절약 가능`
      : `${prefix}내 주변 절약 정보를 확인해보세요`;
}

// --- 검색 실행 ---
async function runSearch() {
  const lat = document.getElementById('s-lat').value;
  const lng = document.getElementById('s-lng').value;
  const radius = document.getElementById('s-radius').value;

  const params = new URLSearchParams({ lat, lng, radius_km: radius });
  if (currentCategory) params.set('category', currentCategory);

  const resultsEl = document.getElementById('search-results');
  const countEl = document.getElementById('sheet-count');
  resultsEl.innerHTML = '<p class="empty-msg">주변 절약 기회를 찾는 중...</p>';

  updateRegionLabel(parseFloat(lat), parseFloat(lng)).then(() => renderSavingsHero(lastResults));

  try {
    const data = await apiFetch(`/search?${params.toString()}`);
    lastResults = data.results;
    renderMapMarkers(parseFloat(lat), parseFloat(lng), data.results);
    renderSavingsHero(data.results);

    if (data.results.length === 0) {
      countEl.textContent = '주변에 절약 기회가 없어요';
      resultsEl.innerHTML = '<p class="empty-msg">반경을 넓혀서 다시 찾아보세요.</p>';
      return;
    }

    countEl.textContent = `지금 잡을 수 있는 절약 ${data.results.length}개`;
    resultsEl.innerHTML = data.results
      .map((r, i) => {
        const tier = getRarityTier(r.savings_rate);
        const fresh = freshnessInfo(r.last_verified_at, r.verification_count);
        return `
      <div class="result-card ${tier.cls}" data-idx="${i}">
        <div class="result-header">
          <div class="badge-group">
            <span class="badge">${CATEGORY_LABELS[r.category] || r.category}</span>
            <span class="tier-tag">${tier.label}</span>
          </div>
          <span class="distance">${r.distance_m.toFixed(0)}m</span>
        </div>
        <div class="place-name">${escapeHtml(r.place_name)}</div>
        <div class="price-line">
          <span class="final-price">${r.final_price.toLocaleString()}원</span>
          ${r.total_savings > 0 ? `<span class="base-price">${r.base_price.toLocaleString()}원</span>` : ''}
          ${r.total_savings > 0 ? `<span class="savings-rate">예상 절약 ${Math.round(r.total_savings).toLocaleString()}원</span>` : ''}
        </div>
        <div class="meta-line">
          <span class="fresh-dot ${fresh.cls}"></span>${fresh.label}${r.expires_at ? ` · ${formatExpiry(r.expires_at)}` : ''}
        </div>
      </div>`;
      })
      .join('');

    resultsEl.querySelectorAll('.result-card').forEach((card) => {
      card.addEventListener('click', () => openOfferDetail(lastResults[Number(card.dataset.idx)]));
    });
  } catch (err) {
    countEl.textContent = '검색 실패';
    resultsEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}

initMap(36.9925, 127.113);
runSearch();

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

document.getElementById('place-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = document.getElementById('p-name').value.trim();
  const lat = parseFloat(document.getElementById('p-lat').value);
  const lng = parseFloat(document.getElementById('p-lng').value);

  if (!name) {
    alert('매장명을 입력해주세요.');
    document.getElementById('p-name').focus();
    return;
  }
  if (Number.isNaN(lat) || Number.isNaN(lng)) {
    alert('먼저 "현재 위치로 매장 위치 설정" 버튼을 눌러주세요.');
    return;
  }

  const payload = { name, address: document.getElementById('p-address').value || null, lat, lng };
  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  try {
    await apiFetch('/merchant/places', { method: 'POST', body: JSON.stringify(payload) });
    alert('매장 등록 완료! 아래 혜택 등록에서 매장을 선택할 수 있어요.');
    e.target.reset();
    document.getElementById('p-location-status').textContent = '매장에서 이 버튼을 눌러 위치를 자동으로 설정하세요.';
    loadPlaces();
  } catch (err) {
    alert(`매장 등록 실패: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
  }
});

async function loadPlaces() {
  const listEl = document.getElementById('places-list');
  const selectEl = document.getElementById('o-place-id');
  listEl.innerHTML = '<p class="empty-msg">불러오는 중...</p>';
  try {
    const places = await apiFetch('/merchant/places');
    listEl.innerHTML = places.length
      ? places.map((p) => `<div class="list-row">#${p.id} ${escapeHtml(p.name)} ${p.address ? '- ' + escapeHtml(p.address) : ''}</div>`).join('')
      : '<p class="empty-msg">등록된 매장이 없습니다.</p>';

    selectEl.innerHTML = places.length
      ? places.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('')
      : '<option value="">매장을 먼저 등록해주세요</option>';
  } catch (err) {
    listEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}
document.getElementById('load-places-btn').addEventListener('click', loadPlaces);

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

// 매장/혜택/절약 자산 목록은 로그인 상태(renderAuthState)에서 로드됩니다.
