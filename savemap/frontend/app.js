const API_BASE = '/v1';

const CATEGORY_LABELS = {
  free: '무료',
  discount: '할인',
  closing_soon: '마감임박',
  free_parking: '무료주차',
  local_benefit: '지역혜택',
};

let currentCategory = '';

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function apiFetch(path, options = {}) {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await resp.json().catch(() => null);
  if (!resp.ok) {
    const message = data?.detail?.message || data?.detail || `요청 실패 (${resp.status})`;
    throw new Error(message);
  }
  return data;
}

// --- RPG 희귀도 등급 (절약률 기준) ---
function getRarityTier(savingsRate) {
  if (savingsRate >= 50) return { cls: 'rarity-legendary', label: '✨ 레전더리' };
  if (savingsRate >= 30) return { cls: 'rarity-epic', label: '💜 에픽' };
  if (savingsRate >= 10) return { cls: 'rarity-rare', label: '💎 레어' };
  if (savingsRate > 0) return { cls: 'rarity-uncommon', label: '🍀 언커먼' };
  return { cls: 'rarity-common', label: '일반' };
}

// --- XP / 레벨 뱃지 ---
async function loadXpBadge() {
  try {
    const xp = await apiFetch('/users/me/xp');
    const pct = Math.round((xp.xp_into_level / xp.xp_per_level) * 100);
    document.getElementById('xp-ring').style.setProperty('--xp-pct', `${pct}%`);
    document.getElementById('xp-level').textContent = `Lv.${xp.level}`;
    document.getElementById('xp-title').textContent = xp.title;
    document.getElementById('xp-sub').textContent = `${xp.xp_into_level}/${xp.xp_per_level} XP`;
  } catch (err) {
    // XP 뱃지는 부가 정보라 실패해도 나머지 화면에 영향 없음
    console.warn('XP 정보를 불러오지 못했습니다:', err.message);
  }
}
loadXpBadge();

// --- 하단 네비게이션 (화면 전환) ---
document.querySelectorAll('.nav-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(`screen-${btn.dataset.screen}`).classList.add('active');
  });
});

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
document.getElementById('use-location-btn').addEventListener('click', () => {
  if (!navigator.geolocation) {
    alert('이 브라우저는 위치 정보를 지원하지 않습니다.');
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;
      document.getElementById('s-lat').value = lat.toFixed(6);
      document.getElementById('s-lng').value = lng.toFixed(6);
      if (kakaoMap) kakaoMap.setCenter(new kakao.maps.LatLng(lat, lng));
      runSearch();
    },
    () => alert('위치를 가져올 수 없습니다.')
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

  const infoWindow = new kakao.maps.InfoWindow({ zIndex: 1 });

  results.forEach((r) => {
    const pos = new kakao.maps.LatLng(r.lat, r.lng);
    bounds.extend(pos);
    const marker = new kakao.maps.Marker({ map: kakaoMap, position: pos });
    kakao.maps.event.addListener(marker, 'click', () => {
      infoWindow.setContent(
        `<div style="padding:8px 10px;font-size:12px;min-width:140px;">
          <strong>${escapeHtml(r.place_name)}</strong><br/>
          ${r.final_price.toLocaleString()}원 ${r.savings_rate > 0 ? `(${r.savings_rate}% 절약)` : ''}
        </div>`
      );
      infoWindow.open(kakaoMap, marker);
    });
    mapMarkers.push(marker);
  });

  kakaoMap.setBounds(bounds);
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
  resultsEl.innerHTML = '<p class="empty-msg">검색 중...</p>';

  try {
    const data = await apiFetch(`/search?${params.toString()}`);
    renderMapMarkers(parseFloat(lat), parseFloat(lng), data.results);

    if (data.results.length === 0) {
      countEl.textContent = '주변에 절약 정보가 없어요';
      resultsEl.innerHTML = '<p class="empty-msg">반경을 넓혀서 다시 찾아보세요.</p>';
      return;
    }

    countEl.textContent = `주변 절약 정보 ${data.results.length}개`;
    resultsEl.innerHTML = data.results
      .map((r) => {
        const tier = getRarityTier(r.savings_rate);
        return `
      <div class="result-card ${tier.cls}">
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
          ${r.savings_rate > 0 ? `<span class="savings-rate">${r.savings_rate}% 절약</span>` : ''}
        </div>
        <div class="meta-line">신뢰도 ${(r.trust_score * 100).toFixed(0)}% · 점수 ${r.score}</div>
      </div>`;
      })
      .join('');
  } catch (err) {
    countEl.textContent = '검색 실패';
    resultsEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}

initMap(36.9925, 127.113);
runSearch();

// --- 제보 ---
document.getElementById('report-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const image_url = document.getElementById('r-image-url').value;
  const lat = document.getElementById('r-lat').value;
  const lng = document.getElementById('r-lng').value;

  const payload = { image_url };
  if (lat && lng) {
    payload.lat = parseFloat(lat);
    payload.lng = parseFloat(lng);
  }

  const resultEl = document.getElementById('report-result');
  resultEl.innerHTML = '<p class="empty-msg">AI가 사진을 분석 중입니다...</p>';

  try {
    const data = await apiFetch('/reports', { method: 'POST', body: JSON.stringify(payload) });
    resultEl.innerHTML = `
      <div class="result-card">
        <div class="result-header">
          <span class="badge">${CATEGORY_LABELS[data.ai_category] || data.ai_category || '분류 실패'}</span>
        </div>
        <div class="place-name">${escapeHtml(data.ocr_title || '(제목 인식 실패)')}</div>
        <div class="price-line">
          ${data.ocr_price != null ? `<span class="final-price">${data.ocr_price.toLocaleString()}원</span>` : ''}
        </div>
        <div class="meta-line">
          위치 ${data.has_location ? '인식됨' : '미확인'} · 상태: ${data.status}
        </div>
      </div>`;
    e.target.reset();
  } catch (err) {
    resultEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
});

// --- 사업자: 매장 ---
document.getElementById('place-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const payload = {
    name: document.getElementById('p-name').value,
    address: document.getElementById('p-address').value || null,
    lat: parseFloat(document.getElementById('p-lat').value),
    lng: parseFloat(document.getElementById('p-lng').value),
  };
  try {
    const place = await apiFetch('/merchant/places', { method: 'POST', body: JSON.stringify(payload) });
    alert(`매장 등록 완료! 매장 ID: ${place.id} (혜택 등록 시 이 ID를 사용하세요)`);
    document.getElementById('o-place-id').value = place.id;
    e.target.reset();
    loadPlaces();
  } catch (err) {
    alert(`매장 등록 실패: ${err.message}`);
  }
});

async function loadPlaces() {
  const listEl = document.getElementById('places-list');
  listEl.innerHTML = '<p class="empty-msg">불러오는 중...</p>';
  try {
    const places = await apiFetch('/merchant/places');
    listEl.innerHTML = places.length
      ? places.map((p) => `<div class="list-row">#${p.id} ${escapeHtml(p.name)} ${p.address ? '- ' + escapeHtml(p.address) : ''}</div>`).join('')
      : '<p class="empty-msg">등록된 매장이 없습니다.</p>';
  } catch (err) {
    listEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
}
document.getElementById('load-places-btn').addEventListener('click', loadPlaces);

// --- 사업자: 혜택 ---
document.getElementById('offer-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const ttl = document.getElementById('o-ttl').value;
  const payload = {
    place_id: parseInt(document.getElementById('o-place-id').value, 10),
    title: document.getElementById('o-title').value,
    category: document.getElementById('o-category').value,
    base_price: parseFloat(document.getElementById('o-base-price').value) || null,
    store_discount: parseFloat(document.getElementById('o-discount').value) || null,
    ttl_sec: ttl ? parseInt(ttl, 10) : null,
  };
  try {
    await apiFetch('/merchant/offers', { method: 'POST', body: JSON.stringify(payload) });
    alert('혜택 등록 완료!');
    e.target.reset();
    loadOffers();
  } catch (err) {
    alert(`혜택 등록 실패: ${err.message}`);
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
        <button class="btn-delete-inline" data-id="${o.id}">삭제</button>
      </div>`
          )
          .join('')
      : '<p class="empty-msg">등록된 혜택이 없습니다.</p>';

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

// initial load
loadPlaces();
loadOffers();
