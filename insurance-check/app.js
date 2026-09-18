/* ════════════════════════════════════════════════════════════
   내 보험료 30초 분석 — MVP
   프레임워크·외부 라이브러리 없이 동작합니다.
   모든 계산은 브라우저 안에서만 이루어지며 서버로 전송되지 않습니다.
   (상세 분석 신청만 CONFIG.LEAD_ENDPOINT 설정 시 전송)
   ════════════════════════════════════════════════════════════ */
'use strict';

var InsuranceCheck = (function () {

  /* ───────────────────────────────────────────
     CONFIG
     ─────────────────────────────────────────── */
  var CONFIG = {
    // 여기에 수집 주소를 넣으면 상세 분석 신청 내용을 JSON 으로 POST 합니다.
    // (예: Google Apps Script 웹앱 URL, Supabase Edge Function, 자체 API)
    // 비워두면 아무 곳에도 전송하지 않고 완료 화면만 표시합니다. ← MVP 기본값
    LEAD_ENDPOINT: '',

    MIN_AGE: 18,
    MAX_AGE: 100,
    MIN_PREMIUM: 1000,
    MAX_PREMIUM: 5000000,
    COUNT_UP_MS: 600
  };

  var STEPS = ['step1', 'step2', 'step3', 'step4', 'step5'];
  var TOTAL_STEPS = STEPS.length;

  var COVERAGES = [
    { id: 'medical', label: '실손',      group: '의료비' },
    { id: 'cancer',  label: '암',        group: '중대질병' },
    { id: 'brain',   label: '뇌혈관',    group: '중대질병' },
    { id: 'heart',   label: '심혈관',    group: '중대질병' },
    { id: 'disease', label: '질병',      group: '일반보장' },
    { id: 'injury',  label: '상해',      group: '일반보장' },
    { id: 'driver',  label: '운전자',    group: '일상위험' },
    { id: 'death',   label: '사망',      group: '가족·자산' },
    { id: 'pension', label: '연금/저축', short: '연금', group: '가족·자산' }
  ];
  var GROUP_ORDER = ['의료비', '중대질병', '일반보장', '일상위험', '가족·자산'];
  var UNKNOWN = 'unknown';
  var UNKNOWN_LABEL = '잘 모르겠음';

  var COUNT_LABEL = { '1': '1개', '2': '2개', '3': '3개', '4': '4개', '5': '5개', '6plus': '6개 이상' };

  var MSG = {
    ageEmpty:      '나이를 입력해주세요.',
    ageTooYoung:   '만 18세 이상을 대상으로 하는 서비스입니다.',
    ageRange:      '나이를 다시 확인해주세요. (18~100세)',
    genderEmpty:   '성별을 선택해주세요.',
    premiumEmpty:  '보험료를 입력해주세요.',
    premiumZero:   '0원보다 큰 금액을 입력해주세요.',
    premiumMin:    '월 보험료는 1,000원 이상으로 입력해주세요.',
    premiumMax:    '월 보험료는 500만원 이하로 입력해주세요.',
    countEmpty:    '보험 개수를 선택해주세요.',
    coverageEmpty: '하나 이상 선택해주세요. 잘 모르겠다면 "잘 모르겠음"을 선택하셔도 됩니다.',
    renewalEmpty:  '하나를 선택해주세요.',
    nameEmpty:     '이름을 입력해주세요.',
    channelEmpty:  '원하는 상담 방식을 선택해주세요.',
    contactEmpty:  '연락처를 입력해주세요.',
    contactFormat: '연락처를 다시 확인해주세요. (숫자 10~11자리)',
    consentEmpty:  '개인정보 수집 · 이용 동의가 필요합니다.',
    sendFail:      '전송에 실패했습니다. 잠시 후 다시 시도해주세요. 입력하신 내용은 그대로 남아 있습니다.'
  };

  /* ───────────────────────────────────────────
     상태 (브라우저 메모리에만 존재)
     ─────────────────────────────────────────── */
  var state = {
    age: null,
    gender: null,
    monthlyPremium: null,
    policyCount: null,
    coverages: [],
    renewal: null
  };

  var lead = { channel: null };

  function resetState() {
    state.age = null;
    state.gender = null;
    state.monthlyPremium = null;
    state.policyCount = null;
    state.coverages = [];
    state.renewal = null;
    lead.channel = null;
  }

  /* ═══════════════════════════════════════════
     Calc — 계산과 표기
     ═══════════════════════════════════════════ */
  var numberFmt = new Intl.NumberFormat('ko-KR'); // 포매터는 1회만 생성해 재사용

  var Calc = {
    calculateAnnualPremium: function (monthly) {
      return Calc.safeNumber(monthly) * 12;
    },
    calculateTenYearPremium: function (monthly) {
      return Calc.safeNumber(monthly) * 120;
    },
    /** NaN / Infinity / 음수가 화면에 닿지 않도록 마지막 방어선 */
    safeNumber: function (n) {
      var v = Number(n);
      if (!Number.isFinite(v) || v < 0) return 0;
      return v;
    },
    formatNumber: function (n) {
      return numberFmt.format(Calc.safeNumber(Math.round(n)));
    },
    formatCurrency: function (n) {
      return Calc.formatNumber(n) + '원';
    },
    /** 10,000 단위 반올림 표기 — "344만원" */
    formatManwon: function (n) {
      var v = Calc.safeNumber(n);
      if (v < 10000) return Calc.formatCurrency(v);
      return numberFmt.format(Math.round(v / 10000)) + '만원';
    },
    isExactManwon: function (n) {
      var v = Calc.safeNumber(n);
      return v >= 10000 && v % 10000 === 0;
    },
    /** 입력 문자열에서 숫자만 추출 (콤마·공백·기호 제거) */
    digitsOf: function (str) {
      return String(str == null ? '' : str).replace(/\D/g, '');
    },
    withCommas: function (digits) {
      var clean = String(digits).replace(/^0+(?=\d)/, '');
      return clean.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    },
    policyCountLabel: function (code) {
      return COUNT_LABEL[code] || '';
    },
    /** 결과 요약 문장 — 입력값에 따라 동적으로 생성 */
    buildSummarySentence: function (monthly) {
      var m = Calc.safeNumber(monthly);
      var annual = Calc.calculateAnnualPremium(m);
      var monthlyText = Calc.isExactManwon(m) ? Calc.formatManwon(m) : Calc.formatCurrency(m);
      return '지금 입력하신 보험료를 기준으로 보면 매달 ' + monthlyText +
             ', 1년에 약 ' + Calc.formatManwon(annual) + '을 보험에 지출하고 있습니다.';
    }
  };

  /* ═══════════════════════════════════════════
     Validate — 입력값 검증
     ═══════════════════════════════════════════ */
  var Validate = {
    age: function (raw) {
      var digits = Calc.digitsOf(raw);
      if (!digits) return { ok: false, message: MSG.ageEmpty };
      var v = parseInt(digits, 10);
      if (!Number.isFinite(v)) return { ok: false, message: MSG.ageEmpty };
      if (v < CONFIG.MIN_AGE) return { ok: false, message: MSG.ageTooYoung };
      if (v > CONFIG.MAX_AGE) return { ok: false, message: MSG.ageRange };
      return { ok: true, value: v };
    },
    premium: function (raw) {
      var text = String(raw == null ? '' : raw).trim();
      if (!text) return { ok: false, message: MSG.premiumEmpty };
      var negative = /^-/.test(text);
      var digits = Calc.digitsOf(text);
      if (!digits) return { ok: false, message: MSG.premiumEmpty };
      var v = parseInt(digits, 10);
      if (!Number.isFinite(v)) return { ok: false, message: MSG.premiumEmpty };
      if (negative || v === 0) return { ok: false, message: v === 0 ? MSG.premiumEmpty : MSG.premiumZero };
      if (v < CONFIG.MIN_PREMIUM) return { ok: false, message: MSG.premiumMin };
      if (v > CONFIG.MAX_PREMIUM) return { ok: false, message: MSG.premiumMax };
      return { ok: true, value: v };
    },
    policyCount: function (code) {
      if (!code || !COUNT_LABEL[code]) return { ok: false, message: MSG.countEmpty };
      return { ok: true, value: code };
    },
    coverages: function (list) {
      if (!Array.isArray(list) || list.length === 0) {
        return { ok: false, message: MSG.coverageEmpty };
      }
      return { ok: true, value: list };
    },
    renewal: function (v) {
      if (['yes', 'no', 'unknown'].indexOf(v) === -1) return { ok: false, message: MSG.renewalEmpty };
      return { ok: true, value: v };
    },
    name: function (raw) {
      var v = String(raw == null ? '' : raw).trim();
      if (!v) return { ok: false, message: MSG.nameEmpty };
      return { ok: true, value: v.slice(0, 20) };
    },
    contact: function (raw) {
      var text = String(raw == null ? '' : raw).trim();
      if (!text) return { ok: false, message: MSG.contactEmpty };
      var digits = Calc.digitsOf(text);
      if (digits.length < 10 || digits.length > 11) {
        return { ok: false, message: MSG.contactFormat };
      }
      return { ok: true, value: digits };
    }
  };

  /* ═══════════════════════════════════════════
     Analysis — "확인해볼 항목" 생성
     판단하지 않고 확인을 권유하는 문구만 생성합니다.
     ═══════════════════════════════════════════ */
  var NEED = '확인 필요';
  var INFO = '참고';

  var Analysis = {
    /** 선택한 보장 영역의 대분류별 커버 현황 */
    groupSummary: function (selected) {
      var map = {};
      GROUP_ORDER.forEach(function (g) { map[g] = { on: 0, total: 0 }; });
      COVERAGES.forEach(function (c) {
        map[c.group].total += 1;
        if (selected.indexOf(c.id) !== -1) map[c.group].on += 1;
      });
      return GROUP_ORDER.map(function (g) {
        return { group: g, on: map[g].on, total: map[g].total };
      });
    },

    generateAnalysis: function (s) {
      var items = [];
      var cov = Array.isArray(s.coverages) ? s.coverages : [];
      var has = function (id) { return cov.indexOf(id) !== -1; };
      var countNum = s.policyCount === '6plus' ? 6 : parseInt(s.policyCount, 10) || 0;

      items.push({
        title: '보험별 보장기간',
        status: NEED,
        note: '가입한 보험이 각각 언제까지 보장되는지는 보험증권의 보험기간 항목에서 확인할 수 있습니다.'
      });

      if (countNum >= 3) {
        items.push({
          title: '보장 중복 여부',
          status: NEED,
          note: '가입한 보험이 여러 개라면 보장 중복 여부를 확인해볼 수 있습니다.'
        });
      }

      if (s.renewal === 'yes') {
        items.push({
          title: '갱신형 보험료 변동 조건',
          status: NEED,
          note: '갱신형 보험의 향후 보험료 변동 조건을 확인해보세요.'
        });
      } else if (s.renewal === 'unknown') {
        items.push({
          title: '갱신형 여부',
          status: NEED,
          note: '갱신형인지 비갱신형인지는 보험증권의 보험기간 · 납입기간 항목에서 확인할 수 있습니다.'
        });
      } else if (s.renewal === 'no') {
        items.push({
          title: '갱신 구조',
          status: INFO,
          note: '갱신형이 없다고 선택하셨습니다. 실제 계약 형태는 보험증권에서 한 번 더 확인해보시면 좋습니다.'
        });
      }

      if (has(UNKNOWN) || cov.length === 0) {
        items.push({
          title: '현재 보장 구조',
          status: NEED,
          note: '보험증권을 확인하면 현재 보장 구조를 더 정확하게 파악할 수 있습니다.'
        });
      }

      if (has('driver')) {
        items.push({
          title: '운전자 관련 보장',
          status: NEED,
          note: '운전자 관련 보장은 자동차보험과 별도로 가입되어 있을 수 있으므로 현재 가입 내용을 확인해보세요.'
        });
      }

      if (has('medical')) {
        items.push({
          title: '실손의료보험 가입 시기',
          status: INFO,
          note: '실손의료보험은 가입 시기에 따라 자기부담금과 갱신 조건이 다릅니다. 언제 가입했는지 확인해보세요.'
        });
      }

      if (has('death')) {
        items.push({
          title: '사망보장 형태',
          status: INFO,
          note: '사망보장은 종신형인지 정기형인지에 따라 보장기간이 달라집니다. 어떤 형태인지 확인해보세요.'
        });
      }

      if (has('pension')) {
        items.push({
          title: '보장성 · 저축성 구분',
          status: INFO,
          note: '연금 · 저축 성격의 상품은 보장성 보험과 성격이 다릅니다. 두 가지가 어떻게 나뉘어 있는지 확인해보세요.'
        });
      }

      // 확인 필요 항목을 먼저 보여줍니다.
      return items.sort(function (a, b) {
        if (a.status === b.status) return 0;
        return a.status === NEED ? -1 : 1;
      });
    }
  };

  /* ───────────────────────────────────────────
     영업 문구 방지 가드 (개발·테스트용)
     스펙 17항을 코드 레벨에서 강제합니다.
     ─────────────────────────────────────────── */
  var BANNED = [/비싸/, /비쌉/, /저렴/, /해지/, /갈아타/, /손해/, /잘못/, /추천/,
                /줄여드/, /절약/, /가입하세/, /최저가/, /무조건/];

  function auditCopy() {
    var texts = [];
    Object.keys(MSG).forEach(function (k) { texts.push(MSG[k]); });

    // 가능한 모든 입력 조합의 분석 문구를 검사합니다.
    ['yes', 'no', 'unknown'].forEach(function (renewal) {
      ['1', '3', '6plus'].forEach(function (count) {
        var covSets = [[UNKNOWN], COVERAGES.map(function (c) { return c.id; })];
        covSets.forEach(function (cov) {
          Analysis.generateAnalysis({ renewal: renewal, policyCount: count, coverages: cov })
            .forEach(function (it) { texts.push(it.title, it.note, it.status); });
        });
      });
    });
    [1000, 287000, 300000, 5000000].forEach(function (m) {
      texts.push(Calc.buildSummarySentence(m));
    });

    var hits = [];
    texts.forEach(function (t) {
      BANNED.forEach(function (re) {
        if (re.test(t)) hits.push({ pattern: String(re), text: t });
      });
    });
    return hits;
  }

  /* ═══════════════════════════════════════════
     DOM 유틸
     ═══════════════════════════════════════════ */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function setText(el, text) { if (el) el.textContent = text; }

  function setError(fieldId, message) {
    var errEl = document.getElementById(fieldId + '-err');
    if (errEl) errEl.textContent = message || '';
    var input = document.getElementById(fieldId);
    if (input && input.tagName === 'INPUT') {
      if (message) input.setAttribute('aria-invalid', 'true');
      else input.removeAttribute('aria-invalid');
    }
  }

  function clearErrors(scope) {
    $$('.err', scope || document).forEach(function (el) { el.textContent = ''; });
    $$('[aria-invalid]', scope || document).forEach(function (el) { el.removeAttribute('aria-invalid'); });
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /* ═══════════════════════════════════════════
     Render — 결과 화면 그리기
     ═══════════════════════════════════════════ */
  var rafIds = [];

  function cancelCountUps() {
    rafIds.forEach(function (id) { cancelAnimationFrame(id); });
    rafIds = [];
  }

  function animateNumber(el, target) {
    if (!el) return;
    var value = Calc.safeNumber(target);
    if (prefersReducedMotion()) {
      setText(el, Calc.formatNumber(value));
      return;
    }
    var start = performance.now();
    function frame(now) {
      var p = Math.min(1, (now - start) / CONFIG.COUNT_UP_MS);
      var eased = 1 - Math.pow(1 - p, 3);
      setText(el, Calc.formatNumber(value * eased));
      if (p < 1) rafIds.push(requestAnimationFrame(frame));
    }
    rafIds.push(requestAnimationFrame(frame));
  }

  var Render = {
    premiumPreview: function (raw) {
      var box = $('#premium-preview');
      var result = Validate.premium(raw);
      if (!result.ok) { box.hidden = true; return; }
      var m = result.value;
      box.hidden = false;
      setText($('#pv-month'), Calc.formatCurrency(m));
      setText($('#pv-year'), Calc.formatCurrency(Calc.calculateAnnualPremium(m)));
      setText($('#pv-ten'), Calc.formatCurrency(Calc.calculateTenYearPremium(m)));
    },

    coverageChoices: function () {
      var wrap = $('#coverage-choices');
      wrap.textContent = '';
      var list = COVERAGES.concat([{ id: UNKNOWN, label: UNKNOWN_LABEL }]);
      list.forEach(function (c) {
        var label = document.createElement('label');
        label.className = 'choice';
        label.dataset.value = c.id;

        var input = document.createElement('input');
        input.type = 'checkbox';
        input.className = 'sr-only';
        input.value = c.id;
        input.name = 'coverage';

        var span = document.createElement('span');
        span.textContent = c.label;

        label.appendChild(input);
        label.appendChild(span);
        wrap.appendChild(label);
      });
    },

    coverageMap: function () {
      var map = $('#coverage-map');
      var groupsEl = $('#coverage-groups');
      map.textContent = '';

      var selected = state.coverages.filter(function (id) { return id !== UNKNOWN; });

      if (selected.length === 0) {
        var p = document.createElement('p');
        p.className = 'coverage-empty';
        p.textContent = '선택하신 보장 영역이 없어 구성 표시는 생략했습니다. 보험증권을 확인하면 현재 어떤 보장을 가지고 있는지 파악할 수 있습니다.';
        map.appendChild(p);
        groupsEl.textContent = '';
        groupsEl.hidden = true;
        return;
      }
      groupsEl.hidden = false;

      COVERAGES.forEach(function (c) {
        var on = selected.indexOf(c.id) !== -1;

        var row = document.createElement('div');
        row.className = 'bar-row ' + (on ? 'is-on' : 'is-off');

        var label = document.createElement('span');
        label.className = 'bar-label';
        label.textContent = c.short || c.label;

        var track = document.createElement('div');
        track.className = 'bar-track';
        track.setAttribute('role', 'img');
        track.setAttribute('aria-label', c.label + ' ' + (on ? '선택함' : '선택하지 않음'));

        var fill = document.createElement('div');
        fill.className = 'bar-fill';
        track.appendChild(fill);

        row.appendChild(label);
        row.appendChild(track);
        map.appendChild(row);

        // 모든 바의 길이는 동일합니다. 가입 여부만 표시하며 보험료 배분이 아닙니다.
        if (on) {
          if (prefersReducedMotion()) {
            fill.style.width = '100%';
          } else {
            requestAnimationFrame(function () { fill.style.width = '100%'; });
          }
        }
      });

      groupsEl.textContent = '';
      Analysis.groupSummary(selected).forEach(function (g) {
        var chip = document.createElement('span');
        chip.className = 'group-chip';
        chip.textContent = g.group + ' ' + g.on + '/' + g.total;
        groupsEl.appendChild(chip);
      });
    },

    coverageTags: function () {
      var wrap = $('#coverage-tags');
      wrap.textContent = '';
      var labelOf = {};
      COVERAGES.forEach(function (c) { labelOf[c.id] = c.label; });
      labelOf[UNKNOWN] = UNKNOWN_LABEL;

      if (state.coverages.length === 0) {
        var none = document.createElement('span');
        none.className = 'tag tag-muted';
        none.textContent = '선택한 보장 없음';
        wrap.appendChild(none);
        return;
      }
      state.coverages.forEach(function (id) {
        var tag = document.createElement('span');
        tag.className = 'tag' + (id === UNKNOWN ? ' tag-muted' : '');
        tag.textContent = labelOf[id] || id;
        wrap.appendChild(tag);
      });
    },

    checklist: function () {
      var ul = $('#checklist');
      ul.textContent = '';
      Analysis.generateAnalysis(state).forEach(function (item) {
        var li = document.createElement('li');
        li.className = 'check-item';

        var head = document.createElement('div');
        head.className = 'check-head';

        var title = document.createElement('span');
        title.className = 'check-title';
        title.textContent = item.title;

        var badge = document.createElement('span');
        badge.className = 'check-badge' + (item.status === INFO ? ' is-info' : '');
        badge.textContent = item.status;

        var note = document.createElement('p');
        note.className = 'check-note';
        note.textContent = item.note;

        head.appendChild(title);
        head.appendChild(badge);
        li.appendChild(head);
        li.appendChild(note);
        ul.appendChild(li);
      });
    },

    result: function () {
      cancelCountUps();
      var m = Calc.safeNumber(state.monthlyPremium);
      var annual = Calc.calculateAnnualPremium(m);
      var ten = Calc.calculateTenYearPremium(m);

      animateNumber($('#hero-monthly'), m);
      animateNumber($('#stat-month'), m);
      animateNumber($('#stat-year'), annual);
      animateNumber($('#stat-ten'), ten);

      setText($('#stat-count'), Calc.policyCountLabel(state.policyCount) || '—');
      setText($('#hero-sentence'), Calc.buildSummarySentence(m));

      Render.coverageMap();
      Render.coverageTags();
      Render.checklist();
    }
  };

  /* ═══════════════════════════════════════════
     Nav — 화면 전환 / 진행률 / 뒤로가기
     ═══════════════════════════════════════════ */
  var currentScreen = 'intro';

  // 화면마다 개인정보 처리 안내를 다르게 보여줍니다.
  // 결과 확인까지는 전송이 전혀 없고, 신청 화면에서만 연락처를 받기 때문입니다.
  var FOOT_NOTE = {
    lead: '이름과 연락처는 상세 분석 신청에만 사용되며, 동의하신 경우에만 전달됩니다.',
    done: '이름과 연락처는 상세 분석 신청에만 사용되며, 동의하신 경우에만 전달됩니다.'
  };
  var FOOT_DEFAULT = '입력한 정보는 브라우저 안에서만 계산되며, 어디에도 전송·저장되지 않습니다.';

  function updateProgress(screenName) {
    var progress = $('#progress');
    var idx = STEPS.indexOf(screenName);
    if (idx === -1) { progress.hidden = true; return; }

    progress.hidden = false;
    var step = idx + 1;
    $$('#progress-dots .dot').forEach(function (dot, i) {
      dot.classList.toggle('is-done', i < idx);
      dot.classList.toggle('is-current', i === idx);
    });
    var dots = $('#progress-dots');
    dots.setAttribute('aria-valuenow', String(step));
    dots.setAttribute('aria-valuetext', TOTAL_STEPS + '단계 중 ' + step + '단계');
    setText($('#progress-text'), step + ' / ' + TOTAL_STEPS);
  }

  var Nav = {
    showScreen: function (name, opts) {
      opts = opts || {};
      var target = $('[data-screen="' + name + '"]');
      if (!target) return;

      cancelCountUps();
      $$('[data-screen]').forEach(function (el) { el.hidden = true; });
      target.hidden = false;
      currentScreen = name;

      updateProgress(name);
      setText($('#foot-note'), FOOT_NOTE[name] || FOOT_DEFAULT);

      if (!opts.fromHistory) {
        try {
          history.pushState({ screen: name }, '');
        } catch (e) {
          // file:// 등 일부 환경에서는 pushState 가 막힐 수 있습니다. 동작에는 영향이 없습니다.
        }
      }

      window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });

      var focusTarget = $('[tabindex="-1"]', target);
      if (focusTarget) focusTarget.focus({ preventScroll: true });
    },

    showStep: function (n) {
      var idx = Math.max(1, Math.min(TOTAL_STEPS, n));
      Nav.showScreen(STEPS[idx - 1]);
    },

    currentStepIndex: function () {
      return STEPS.indexOf(currentScreen); // -1 이면 스텝 화면이 아님
    },

    next: function () {
      var idx = Nav.currentStepIndex();
      if (idx === -1) return;
      if (!validateStep(idx + 1)) return;
      if (idx + 1 < TOTAL_STEPS) {
        Nav.showStep(idx + 2);
      } else {
        // showScreen() 이 진행 중인 카운트업을 취소하므로 화면 전환을 먼저 합니다.
        Nav.showScreen('result');
        Render.result();
      }
    },

    back: function () {
      var idx = Nav.currentStepIndex();
      if (idx <= 0) { Nav.showScreen('intro'); return; }
      Nav.showStep(idx);
    }
  };

  /* ───────────────────────────────────────────
     스텝별 검증
     ─────────────────────────────────────────── */
  function validateStep(step) {
    if (step === 1) {
      var age = Validate.age($('#age').value);
      setError('age', age.ok ? '' : age.message);
      var genderOk = !!state.gender;
      setError('gender', genderOk ? '' : MSG.genderEmpty);
      if (!age.ok) { $('#age').focus(); return false; }
      if (!genderOk) return false;
      state.age = age.value;
      return true;
    }

    if (step === 2) {
      var p = Validate.premium($('#premium').value);
      setError('premium', p.ok ? '' : p.message);
      if (!p.ok) { $('#premium').focus(); return false; }
      state.monthlyPremium = p.value;
      return true;
    }

    if (step === 3) {
      var c = Validate.policyCount(state.policyCount);
      setError('policyCount', c.ok ? '' : c.message);
      return c.ok;
    }

    if (step === 4) {
      var cov = Validate.coverages(state.coverages);
      setError('coverages', cov.ok ? '' : cov.message);
      return cov.ok;
    }

    if (step === 5) {
      var r = Validate.renewal(state.renewal);
      setError('renewal', r.ok ? '' : r.message);
      return r.ok;
    }
    return false;
  }

  /* ═══════════════════════════════════════════
     라디오 그룹 (성별 / 보험 개수 / 갱신형 / 상담 방식)
     ═══════════════════════════════════════════ */
  function setRadioValue(group, value) {
    var field = group.dataset.field;
    $$('[role="radio"]', group).forEach(function (btn) {
      var on = btn.dataset.value === value;
      btn.setAttribute('aria-checked', on ? 'true' : 'false');
      btn.tabIndex = on ? 0 : -1;
    });
    if (field === 'channel') lead.channel = value;
    else state[field] = value;
    setError(field, '');
  }

  function initRadioGroup(group) {
    // 아무것도 선택되지 않았을 때는 첫 항목만 탭 이동 대상
    var radios = $$('[role="radio"]', group);
    radios.forEach(function (btn, i) { btn.tabIndex = i === 0 ? 0 : -1; });

    group.addEventListener('click', function (e) {
      var btn = e.target.closest('[role="radio"]');
      if (!btn || !group.contains(btn)) return;
      setRadioValue(group, btn.dataset.value);
    });

    group.addEventListener('keydown', function (e) {
      var keys = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'];
      if (keys.indexOf(e.key) === -1) return;
      var btn = e.target.closest('[role="radio"]');
      if (!btn) return;
      e.preventDefault();
      var list = $$('[role="radio"]', group);
      var i = list.indexOf(btn);
      var forward = e.key === 'ArrowRight' || e.key === 'ArrowDown';
      var nextIdx = (i + (forward ? 1 : -1) + list.length) % list.length;
      var nextBtn = list[nextIdx];
      setRadioValue(group, nextBtn.dataset.value);
      nextBtn.focus();
    });
  }

  /* ═══════════════════════════════════════════
     보장 선택 (복수 선택 + "잘 모르겠음" 배타 처리)
     ═══════════════════════════════════════════ */
  function syncCoverageUI() {
    $$('#coverage-choices .choice').forEach(function (label) {
      var input = $('input', label);
      var on = state.coverages.indexOf(input.value) !== -1;
      input.checked = on;
      label.classList.toggle('is-on', on);
    });
  }

  function initCoverage() {
    Render.coverageChoices();
    var wrap = $('#coverage-choices');

    wrap.addEventListener('change', function (e) {
      var input = e.target;
      if (!input || input.type !== 'checkbox') return;
      var id = input.value;

      if (input.checked) {
        if (id === UNKNOWN) {
          // "잘 모르겠음"을 고르면 다른 선택은 해제합니다.
          state.coverages = [UNKNOWN];
        } else {
          state.coverages = state.coverages.filter(function (v) { return v !== UNKNOWN; });
          if (state.coverages.indexOf(id) === -1) state.coverages.push(id);
        }
      } else {
        state.coverages = state.coverages.filter(function (v) { return v !== id; });
      }

      syncCoverageUI();
      setError('coverages', '');
    });
  }

  /* ═══════════════════════════════════════════
     Lead — 상세 분석 신청
     ═══════════════════════════════════════════ */
  function formatPhone(digits) {
    var d = digits.slice(0, 11);
    if (d.length < 4) return d;
    if (d.length < 8) return d.slice(0, 3) + '-' + d.slice(3);
    if (d.length <= 10) return d.slice(0, 3) + '-' + d.slice(3, 6) + '-' + d.slice(6);
    return d.slice(0, 3) + '-' + d.slice(3, 7) + '-' + d.slice(7);
  }

  var Lead = {
    prefill: function () {
      var countEl = $('#lead-count');
      var premiumEl = $('#lead-premium');
      if (countEl && !countEl.value) countEl.value = Calc.policyCountLabel(state.policyCount);
      if (premiumEl && !premiumEl.value && state.monthlyPremium) {
        premiumEl.value = Calc.withCommas(String(state.monthlyPremium));
      }
    },

    validate: function () {
      var ok = true;
      var firstInvalid = null;

      var name = Validate.name($('#lead-name').value);
      setError('lead-name', name.ok ? '' : name.message);
      if (!name.ok) { ok = false; firstInvalid = firstInvalid || $('#lead-name'); }

      var channelOk = !!lead.channel;
      setError('lead-channel', channelOk ? '' : MSG.channelEmpty);
      if (!channelOk) ok = false;

      var contact = Validate.contact($('#lead-contact').value);
      setError('lead-contact', contact.ok ? '' : contact.message);
      if (!contact.ok) { ok = false; firstInvalid = firstInvalid || $('#lead-contact'); }

      var premium = Validate.premium($('#lead-premium').value);
      setError('lead-premium', premium.ok ? '' : premium.message);
      if (!premium.ok) { ok = false; firstInvalid = firstInvalid || $('#lead-premium'); }

      var consentEl = $('#lead-consent');
      setError('lead-consent', consentEl.checked ? '' : MSG.consentEmpty);
      if (!consentEl.checked) { ok = false; firstInvalid = firstInvalid || consentEl; }

      if (firstInvalid) firstInvalid.focus();

      return ok ? {
        name: name.value,
        channel: lead.channel,
        contact: contact.value,
        policyCount: String($('#lead-count').value || '').trim(),
        monthlyPremium: premium.value
      } : null;
    },

    payload: function (form) {
      return {
        name: form.name,
        contactChannel: form.channel,
        contact: form.contact,
        policyCount: form.policyCount,
        monthlyPremium: form.monthlyPremium,
        annualPremium: Calc.calculateAnnualPremium(form.monthlyPremium),
        tenYearPremium: Calc.calculateTenYearPremium(form.monthlyPremium),
        age: state.age,
        gender: state.gender,
        coverages: state.coverages.slice(),
        renewal: state.renewal,
        submittedAt: new Date().toISOString()
      };
    },

    submit: function (e) {
      e.preventDefault();
      var btn = $('#lead-submit');
      if (btn.disabled) return; // 이중 제출 방지

      setError('lead-form', '');
      var form = Lead.validate();
      if (!form) return;

      var endpoint = CONFIG.LEAD_ENDPOINT;
      if (!endpoint) {
        Lead.done(false);
        return;
      }

      btn.disabled = true;
      var original = btn.textContent;
      btn.textContent = '보내는 중…';

      fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Lead.payload(form))
      })
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          Lead.done(true);
        })
        .catch(function () {
          setError('lead-form', MSG.sendFail);
        })
        .finally(function () {
          btn.disabled = false;
          btn.textContent = original;
        });
    },

    done: function (sent) {
      setText($('#done-note'), sent ? '' :
        '※ 현재 버전은 신청 내용을 어디에도 저장하거나 전송하지 않습니다. 실제 운영 시 app.js 의 LEAD_ENDPOINT 설정이 필요합니다.');
      Nav.showScreen('done');
    }
  };

  /* ═══════════════════════════════════════════
     입력 필드 이벤트
     ═══════════════════════════════════════════ */
  /** 숫자만 남기고 천 단위 콤마를 붙이면서 커서 위치를 유지합니다. */
  function attachCommaFormatter(input, onChange) {
    input.addEventListener('input', function () {
      var caret = input.selectionStart;
      var before = input.value;
      // 음수 부호는 지우지 않고 유지합니다. 값이 조용히 바뀌지 않도록 하고,
      // 검증 단계에서 "0원보다 큰 금액을 입력해주세요." 로 안내합니다.
      var negative = /^\s*-/.test(before);
      var digitsBeforeCaret = before.slice(0, caret).replace(/\D/g, '').length;

      var digits = Calc.digitsOf(before).slice(0, 10);
      var formatted = digits ? Calc.withCommas(digits) : '';
      var next = (negative && (digits || caret > 0) ? '-' : '') + formatted;
      input.value = next;

      // 커서를 원래 있던 자릿수 뒤로 되돌립니다.
      var pos = next.charAt(0) === '-' ? 1 : 0, seen = 0;
      while (pos < next.length && seen < digitsBeforeCaret) {
        if (/\d/.test(next[pos])) seen += 1;
        pos += 1;
      }
      try { input.setSelectionRange(pos, pos); } catch (e) { /* type=tel 등 예외 무시 */ }

      if (onChange) onChange(next);
    });
  }

  function attachDigitsOnly(input, maxLen) {
    input.addEventListener('input', function () {
      var digits = Calc.digitsOf(input.value).slice(0, maxLen);
      if (input.value !== digits) input.value = digits;
    });
  }

  function attachEnterToNext(input) {
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); Nav.next(); }
    });
  }

  /* ═══════════════════════════════════════════
     초기화
     ═══════════════════════════════════════════ */
  function init() {
    // 라디오 그룹
    $$('[role="radiogroup"]').forEach(initRadioGroup);

    // 보장 선택
    initCoverage();

    // 나이
    var ageEl = $('#age');
    attachDigitsOnly(ageEl, 3);
    ageEl.addEventListener('input', function () { setError('age', ''); });
    attachEnterToNext(ageEl);

    // 보험료
    var premiumEl = $('#premium');
    attachCommaFormatter(premiumEl, function (v) {
      setError('premium', '');
      Render.premiumPreview(v);
    });
    attachEnterToNext(premiumEl);

    // 신청 폼 입력
    attachCommaFormatter($('#lead-premium'), function () { setError('lead-premium', ''); });
    var contactEl = $('#lead-contact');
    contactEl.addEventListener('input', function () {
      contactEl.value = formatPhone(Calc.digitsOf(contactEl.value));
      setError('lead-contact', '');
    });
    $('#lead-name').addEventListener('input', function () { setError('lead-name', ''); });
    $('#lead-consent').addEventListener('change', function () { setError('lead-consent', ''); });
    $('#lead-form').addEventListener('submit', Lead.submit);

    // 전역 버튼 액션
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;
      var action = btn.dataset.action;

      if (action === 'start') Nav.showStep(1);
      else if (action === 'next') Nav.next();
      else if (action === 'back') Nav.back();
      else if (action === 'to-lead') { Lead.prefill(); Nav.showScreen('lead'); }
      else if (action === 'back-to-result') Nav.showScreen('result');
      else if (action === 'restart') restart();
    });

    // 브라우저 뒤로가기
    window.addEventListener('popstate', function (e) {
      var name = (e.state && e.state.screen) || 'intro';
      Nav.showScreen(name, { fromHistory: true });
    });

    try { history.replaceState({ screen: 'intro' }, ''); } catch (err) { /* noop */ }

    Nav.showScreen('intro', { fromHistory: true });
  }

  function restart() {
    resetState();
    $('#age').value = '';
    $('#premium').value = '';
    $('#premium-preview').hidden = true;
    $$('[role="radio"]').forEach(function (btn) { btn.setAttribute('aria-checked', 'false'); });
    $$('[role="radiogroup"]').forEach(function (g) {
      $$('[role="radio"]', g).forEach(function (btn, i) { btn.tabIndex = i === 0 ? 0 : -1; });
    });
    syncCoverageUI();
    $('#lead-form').reset();
    clearErrors();
    Nav.showScreen('intro');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  /* 테스트 · 확장을 위한 공개 API */
  return {
    CONFIG: CONFIG,
    state: state,
    Calc: Calc,
    Validate: Validate,
    Analysis: Analysis,
    Nav: Nav,
    auditCopy: auditCopy,
    COVERAGES: COVERAGES
  };
})();

if (typeof window !== 'undefined') window.InsuranceCheck = InsuranceCheck;
