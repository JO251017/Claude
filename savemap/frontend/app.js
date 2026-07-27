const API_BASE = '/v1';

const CATEGORY_LABELS = {
  free: '무료',
  discount: '할인',
  closing_soon: '마감임박',
  free_parking: '무료주차',
  local_benefit: '지역혜택',
};

// --- Tabs ---
document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
  });
});

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

// --- 검색 ---
document.getElementById('use-location-btn').addEventListener('click', () => {
  if (!navigator.geolocation) {
    alert('이 브라우저는 위치 정보를 지원하지 않습니다.');
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      document.getElementById('s-lat').value = pos.coords.latitude.toFixed(6);
      document.getElementById('s-lng').value = pos.coords.longitude.toFixed(6);
    },
    () => alert('위치를 가져올 수 없습니다.')
  );
});

document.getElementById('search-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const lat = document.getElementById('s-lat').value;
  const lng = document.getElementById('s-lng').value;
  const radius = document.getElementById('s-radius').value;
  const category = document.getElementById('s-category').value;

  const params = new URLSearchParams({ lat, lng, radius_km: radius });
  if (category) params.set('category', category);

  const resultsEl = document.getElementById('search-results');
  resultsEl.innerHTML = '<p class="empty-msg">검색 중...</p>';

  try {
    const data = await apiFetch(`/search?${params.toString()}`);
    if (data.results.length === 0) {
      resultsEl.innerHTML = '<p class="empty-msg">주변에 절약 정보가 없습니다.</p>';
      return;
    }
    resultsEl.innerHTML = data.results
      .map(
        (r) => `
      <div class="result-card">
        <div class="result-header">
          <span class="badge">${CATEGORY_LABELS[r.category] || r.category}</span>
          <span class="distance">${r.distance_m.toFixed(0)}m</span>
        </div>
        <div class="place-name">${escapeHtml(r.place_name)}</div>
        <div class="price-line">
          <span class="final-price">${r.final_price.toLocaleString()}원</span>
          ${r.total_savings > 0 ? `<span class="base-price">${r.base_price.toLocaleString()}원</span>` : ''}
          ${r.savings_rate > 0 ? `<span class="savings-rate">${r.savings_rate}% 절약</span>` : ''}
        </div>
        <div class="meta-line">신뢰도 ${(r.trust_score * 100).toFixed(0)}% · 점수 ${r.score}</div>
      </div>`
      )
      .join('');
  } catch (err) {
    resultsEl.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
  }
});

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
