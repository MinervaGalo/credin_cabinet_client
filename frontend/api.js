// Связь страниц с backend: находит элементы по существующим классам и заполняет их данными.
// Вёрстка страниц не меняется. Настройки - в константах ниже.

const API = '/api'; // core раздаёт и фронт, и API с одного адреса
const TOKEN_KEY = 'credit_token_'; // ключ в localStorage, к нему добавляется роль
// У фронта нет формы входа, поэтому он входит под демо-пользователями.
const DEMO_CREDS = {
    client: { email: 'anna@example.test', password: 'demo123' },
    analyst: { email: 'analyst@bank.test', password: 'demo123' },
};
// Предзаполнение встречного предложения: те же значения, что COUNTER_* в core/app/config.py.
const COUNTER_AMOUNT_FACTOR = 0.8;
const COUNTER_RATE_ADD = 1.5;
const BANK_PAGES = [
    'bank.html',
    'bank-review.html',
    'decision-approved.html',
    'decision-rejected.html',
    'decision-documents.html',
    'decision-counter.html',
];

const PAGE = location.pathname.split('/').pop() || 'index.html';
const QUERY = new URLSearchParams(location.search);
const ROLE = QUERY.get('role') || (BANK_PAGES.includes(PAGE) ? 'analyst' : 'client');
const IN_FRAME = window.parent !== window;

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) =>
    String(s ?? '').replace(
        /[&<>"']/g,
        (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
const ratePct = (r) => String(r).replace('.', ','); // 14.1 -> «14,1»
const money = (n) => (n == null ? '—' : Number(n).toLocaleString('ru-RU') + ' ₽');
const date = (iso) => (iso ? new Date(iso).toLocaleDateString('ru-RU') : '—');
const dateTime = (iso) =>
    iso ? new Date(iso).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : '';
const months = (n) => {
    const a = n % 100,
        b = n % 10;
    return n + ' ' + (a > 10 && a < 15 ? 'месяцев' : b === 1 ? 'месяц' : b > 1 && b < 5 ? 'месяца' : 'месяцев');
};
const STATUS_RU = {
    DRAFT: 'Черновик',
    SUBMITTED: 'Отправлена',
    DATA_ENRICHMENT: 'Сбор данных ФНС/БКИ',
    SCORING: 'Скоринг',
    MANUAL_REVIEW: 'Ручная проверка',
    DOCUMENTS_REQUESTED: 'Запрос документов',
    DECISION_MADE: 'Решение принято',
    AWAITING_SIGNING: 'Ожидает подписания',
    DISBURSED: 'Деньги выданы',
};

class ApiError extends Error {
    constructor(info, status) {
        super(info.message);
        this.info = info;
        this.status = status;
    }
}

async function getToken(role, fresh = false) {
    let t = !fresh && localStorage.getItem(TOKEN_KEY + role);
    if (t) return t;
    const r = await fetch(API + '/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(DEMO_CREDS[role]),
    });
    const j = await r.json();
    if (!r.ok) throw new ApiError(j.error || { message: 'Не удалось войти' }, r.status);
    localStorage.setItem(TOKEN_KEY + role, j.token);
    return j.token;
}

async function api(path, { method = 'GET', body, form, role = ROLE } = {}, retried = false) {
    const headers = { Authorization: 'Bearer ' + (await getToken(role, retried)) };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let r;
    try {
        r = await fetch(API + path, {
            method,
            headers,
            body: form || (body !== undefined ? JSON.stringify(body) : undefined),
        });
    } catch (e) {
        throw new ApiError({ message: 'Нет связи с сервером. Проверьте, что backend запущен', fields: [] }, 0);
    }
    if (r.status === 401 && !retried) {
        localStorage.removeItem(TOKEN_KEY + role);
        return api(path, { method, body, form, role }, true);
    }
    if (r.status === 204) return null;
    const j = await r.json().catch(() => ({}));
    if (!r.ok)
        throw new ApiError(j.error || { message: 'Что-то пошло не так, попробуйте ещё раз', fields: [] }, r.status);
    return j;
}

function errorHtml(err) {
    const i = err.info || { message: err.message };
    const fields = (i.fields || []).map((f) => `<li>${esc(f.message)}</li>`).join('');
    return `<div class="alert alert-error"><strong>${esc(i.message)}</strong>${i.hint ? `<br>${esc(i.hint)}` : ''}${fields ? `<ul style="margin:6px 0 0;padding-left:18px">${fields}</ul>` : ''}</div>`;
}
// Показывает сообщение в блоке, заменяя предыдущее.
function flash(host, html, before = null) {
    $$('.js-flash', host).forEach((e) => e.remove());
    const d = document.createElement('div');
    d.className = 'js-flash';
    d.innerHTML = html;
    before ? host.insertBefore(d, before) : host.appendChild(d);
}
function notifyParentChanged() {
    if (IN_FRAME) parent.postMessage({ type: 'popup-changed' }, location.origin);
}

async function hydrateHeader() {
    try {
        const me = await api('/me');
        const first = (me.full_name || '').split(' ')[0];
        const w = $('.welcome strong');
        if (w) w.textContent = 'Добрый день, ' + first;
        const c = $('.company-select span');
        if (c) c.textContent = me.company ? me.company.name : ROLE === 'analyst' ? 'Кабинет банка' : '—';
        const av = $('.avatar');
        if (av)
            av.textContent = me.full_name
                .split(' ')
                .map((x) => x[0])
                .join('')
                .slice(0, 2)
                .toUpperCase();
        if (ROLE === 'analyst') {
            const l = $('a.avatar');
            if (l) l.href += '?role=analyst';
        }
        return me;
    } catch (e) {
        return null;
    }
}

function chip(el, disp) {
    if (el) {
        el.className = 'status ' + disp.css;
        el.textContent = disp.label;
    }
}

function setProgress(track, disp) {
    if (!track) return;
    const final = ['approved', 'rejected'].includes(disp.css);
    $$('.progress-step', track).forEach((el, i) => {
        const n = i + 1,
            done = final || n < disp.step,
            cur = !final && n === disp.step;
        el.className = 'progress-step' + (done ? ' done' : cur ? ' current' : '');
        $('.progress-dot', el).textContent = done ? '✓' : String(n);
        $('small', el).textContent = done ? 'Завершено' : cur ? 'В процессе' : 'Ожидается';
    });
    if (final) {
        const last = $$('.progress-step small', track).pop();
        if (last) last.textContent = disp.css === 'rejected' ? 'Отказ' : 'Одобрено';
    }
    track.style.setProperty('--progress', final ? '100%' : (disp.step - 1) * 20 + 8 + '%');
}

function setInfo(root, label, value) {
    const it = $$('.info-item', root).find((i) => $('small', i).textContent.trim() === label);
    if (it) $('strong', it).textContent = value;
}
// items: [{title, state: 'done' | 'current' | 'todo', extra}]
function checkList(ul, items) {
    ul.innerHTML = items
        .map(
            (i) =>
                `<li><span class="checkmark ${i.state === 'todo' ? '' : i.state}">${i.state === 'done' ? '✓' : i.state === 'current' ? '!' : ''}</span>${esc(i.title)}${i.extra || ''}</li>`,
        )
        .join('');
}

function docRow(d) {
    const parsed =
        d.parsed_data && Object.keys(d.parsed_data).length
            ? ' · распознано: ' +
              Object.entries(d.parsed_data)
                  .map(
                      ([k, v]) =>
                          (({
                              revenue: 'выручка',
                              net_profit: 'чистая прибыль',
                              net_assets: 'чистые активы',
                              balance_total: 'баланс',
                          })[k] || k) +
                          ' ' +
                          money(v),
                  )
                  .join(', ')
            : '';
    const sub = [d.type_label, d.application_number && 'заявка ' + d.application_number, d.company_name]
        .filter(Boolean)
        .join(' · ');
    return `<div class="document-row"><span>▤</span><div><strong>${esc(d.filename)}</strong><small>${esc(sub + parsed)}${d.has_file ? '' : ' · демонстрационный документ'}</small></div>
        ${d.has_file ? `<div class="doc-actions"><a class="table-action" href="#" data-dl="${d.id}" data-name="${esc(d.filename)}">Скачать</a></div>` : ''}</div>`;
}
function bindDownloads(root = document) {
    $$('[data-dl]', root).forEach((a) =>
        a.addEventListener('click', async (e) => {
            e.preventDefault();
            try {
                const r = await fetch(API + '/documents/' + a.dataset.dl + '/download', {
                    headers: { Authorization: 'Bearer ' + (await getToken(ROLE)) },
                });
                if (!r.ok) throw new Error();
                const url = URL.createObjectURL(await r.blob());
                const l = document.createElement('a');
                l.href = url;
                l.download = a.dataset.name;
                l.click();
                URL.revokeObjectURL(url);
            } catch (_) {
                alert('Не удалось скачать файл');
            }
        }),
    );
}
function replaceDocRows(panel, docs, emptyText = 'Документов пока нет') {
    const rows = $$('.document-row', panel);
    const anchor = rows[0] ? rows[0].previousElementSibling : null;
    const hostBefore = rows.length ? rows[rows.length - 1].nextElementSibling : null;
    rows.forEach((r) => r.remove());
    const html = docs.length ? docs.map(docRow).join('') : `<p class="muted" style="font-size:12px">${emptyText}</p>`;
    const tmp = document.createElement('div');
    tmp.innerHTML = html;
    const parent = anchor || hostBefore ? (anchor ? anchor.parentNode : hostBefore.parentNode) : panel;
    [...tmp.children].forEach((c) => (anchor ? anchor.after(c) : parent.insertBefore(c, hostBefore)));
    bindDownloads(panel);
}

// Ссылки «Выбрать», «Оформить» и «Подробнее» получают id продукта, чтобы форма знала, что выбрано.
async function bindProducts() {
    let products = [];
    try {
        products = await api('/products', { role: 'client' });
    } catch (_) {
        return;
    }
    $$('.offer-card').forEach((card) => {
        const p = products.find((x) => x.name === $('h3', card).textContent.trim());
        if (!p) return;
        $$('a[href*="new-application.html"], a[href*="credit-details.html"]', card).forEach((a) => {
            const u = new URL(a.getAttribute('href'), location.href);
            u.searchParams.set('product', p.id);
            a.href = u.href;
        });
    });
}

function withId(href, id) {
    const u = new URL(href, location.href);
    u.searchParams.set('id', id);
    return u.href;
}

const pages = {};

pages['index.html'] = async () => {
    await bindProducts();
    const apps = await api('/applications');
    const card = $('.application-card');
    if (!apps.length) {
        if (card)
            card.innerHTML =
                '<h2>Заявок пока нет</h2><p class="muted">Нажмите «Новая заявка», чтобы подобрать кредит.</p>';
        return;
    }
    const a = apps.find((x) => ['review', 'docs', 'draft'].includes(x.display.css)) || apps[0]; // сначала то, что в работе
    $('.application-title h2').textContent = 'Заявка № ' + a.number;
    chip($('.application-title .status'), a.display);
    $('.application-date').textContent = 'Создана ' + date(a.created_at);
    setProgress($('.progress-track'), a.display);
    $('.loan-amount').textContent = money(a.requested_amount);
    const line = (label, value) => {
        const l = $$('.detail-line').find((x) => $$('span', x)[1].textContent.trim() === label);
        if (l) $('strong', l).textContent = value;
    };
    line('Срок', a.term_months ? months(a.term_months) : '—');
    line('Цель', a.purpose || '—');
    line('Продукт', a.product ? a.product.name : '—');
    const more = $('.inner-card a.button');
    if (more) more.href = withId('application-detail.html', a.id);
    const d = await api('/applications/' + a.id);
    const next = $('.next-card p');
    if (next) next.textContent = nextText(d);
    const ul = $('.next-card .check-list');
    if (ul)
        checkList(
            ul,
            d.timeline.map((t) => ({ title: t.title, state: t.state })),
        );
};

function nextText(a) {
    if (a.status === 'DOCUMENTS_REQUESTED')
        return (
            'Банку нужны документы: ' + (a.documents_request_comment || 'загрузите их в разделе «Подробнее о заявке»')
        );
    if (a.decision === 'REJECTED') return 'К сожалению, банк отказал: ' + (a.decision_reason || '');
    if (a.decision === 'COUNTER_OFFER')
        return `Банк предлагает ${money(a.approved_amount)} под ${ratePct(a.approved_rate)}% годовых. Откройте заявку, чтобы принять или отклонить.`;
    if (a.decision === 'APPROVED' && a.status === 'DECISION_MADE')
        return `Заявка одобрена: ${money(a.approved_amount)} под ${ratePct(a.approved_rate)}% годовых. Примите предложение в карточке заявки.`;
    if (a.status === 'AWAITING_SIGNING') return 'Ожидает подписания договора - сделайте это в карточке заявки.';
    if (a.status === 'DISBURSED') return 'Договор подписан, средства выданы.';
    if (a.status === 'DRAFT') return 'Это черновик - допишите данные и отправьте заявку в банк.';
    return 'Проверяем данные компании. Обычно это занимает несколько минут.';
}

pages['applications.html'] = async () => {
    const apps = await api('/applications');
    const tb = $('#applicationsTable tbody');
    tb.innerHTML = apps.length
        ? apps
              .map(
                  (a) => `<tr>
        <td><strong>${esc(a.number)}</strong></td><td>${esc(a.company ? a.company.name : '—')}</td><td>${money(a.requested_amount)}</td>
        <td>${date(a.created_at)}</td><td><span class="status ${a.display.css}">${esc(a.display.label)}</span></td>
        <td><a class="table-action" href="${withId('application-detail.html', a.id)}">Открыть →</a></td></tr>`,
              )
              .join('')
        : '<tr><td colspan="6">Заявок пока нет. Нажмите «Новая заявка».</td></tr>';
    window.applyTableFilters && window.applyTableFilters('applicationsTable');
};

pages['application-detail.html'] = async () => {
    let id = QUERY.get('id');
    if (!id) {
        const l = await api('/applications');
        if (!l.length) return;
        id = l[0].id;
    }
    const render = async () => {
        const a = await api('/applications/' + id);
        $('.page-heading h1').textContent = 'Заявка № ' + a.number;
        $('.page-heading p').textContent = (a.company ? a.company.name : '—') + ' · создана ' + date(a.created_at);
        chip($('.page-heading .status'), a.display);
        const left = $('.detail-layout > section'),
            right = $('.detail-layout > aside');
        setInfo(left, 'Компания', a.company ? a.company.name : '—');
        setInfo(left, 'ИНН', a.company ? a.company.inn : '—');
        setInfo(left, 'Сумма кредита', money(a.requested_amount));
        setInfo(left, 'Срок', a.term_months ? months(a.term_months) : '—');
        setInfo(left, 'Кредитный продукт', a.product ? a.product.name : '—');
        setInfo(left, 'Цель', a.purpose || '—');
        replaceDocRows(left, a.documents, 'Документы не приложены');
        checkList(
            $('.check-list', left),
            a.timeline.map((t) => ({ title: t.title, state: t.state })),
        );
        setProgress($('.progress-track', right), a.display);
        $('.application-status-description', right).textContent = nextText(a);
        const open = $('a.button-primary', right);
        open.href = withId('bank-review.html', a.id);
        $$('.js-actions', right).forEach((e) => e.remove());
        const box = document.createElement('div');
        box.className = 'js-actions';
        box.innerHTML =
            (a.actions.accept
                ? '<button class="button button-primary" data-act="accept" style="margin:10px 8px 0 0">Принять предложение</button>'
                : '') +
            (a.actions.sign
                ? '<button class="button button-primary" data-act="sign" style="margin:10px 8px 0 0">Подписать договор</button>'
                : '') +
            (a.actions.submit
                ? '<button class="button button-primary" data-act="submit" style="margin:10px 8px 0 0">Отправить в банк</button>'
                : '') +
            (a.actions.upload_documents
                ? `<div class="upload-row"><select id="docType"><option value="STATEMENT">Выписка по счёту</option><option value="BALANCE">Бухгалтерская отчётность</option><option value="INVOICE">Счёт</option><option value="OTHER">Другой документ</option></select>
                <label class="button button-secondary" style="cursor:pointer">Загрузить документ<input type="file" id="docFile" hidden accept=".pdf,.txt,.png,.jpg,.jpeg,.docx,.xlsx"></label></div>`
                : '');
        right.appendChild(box);
        $$('[data-act]', box).forEach((b) =>
            b.addEventListener('click', async () => {
                try {
                    await api(`/applications/${id}/${b.dataset.act}`, { method: 'POST' });
                    await new Promise((r) => setTimeout(r, 600));
                    await render();
                } catch (e) {
                    flash(box, errorHtml(e));
                }
            }),
        );
        const f = $('#docFile', box);
        if (f)
            f.addEventListener('change', async () => {
                const fd = new FormData();
                fd.append('file', f.files[0]);
                fd.append('type', $('#docType', box).value);
                try {
                    await api(`/applications/${id}/documents`, { method: 'POST', form: fd });
                    await render();
                } catch (e) {
                    flash(box, errorHtml(e));
                }
            });
    };
    await render();
};

pages['credits.html'] = bindProducts;

pages['documents.html'] = async () => {
    const panel = $('.detail-panel');
    const docs = await api('/documents');
    replaceDocRows(panel, docs, 'Документов пока нет');
    const hint = $('.form-hint', panel);
    if (hint)
        hint.textContent =
            'Загрузить документ можно в карточке заявки. Файлы, помеченные как демонстрационные, существуют только в списке.';
};

pages['bank.html'] = async () => {
    const [stats, rows] = await Promise.all([api('/bank/stats'), api('/bank/applications')]);
    const nums = $$('.stat-card strong');
    nums[0].textContent = stats.total;
    nums[1].textContent = stats.review + stats.docs_requested;
    nums[2].textContent = stats.approved;
    const tb = $('#bankTable tbody');
    tb.innerHTML = rows
        .map(
            (r) => `<tr>
        <td><strong>${esc(r.number)}</strong></td><td>${esc(r.company_name)}</td><td>${esc(r.inn)}</td><td>${money(r.requested_amount)}</td>
        <td><span class="status ${r.display.css}">${esc(r.display.label)}</span></td>
        <td><a class="table-action" href="${withId('bank-review.html', r.id)}">Рассмотреть →</a></td></tr>`,
        )
        .join('');
    const hint = $('.form-hint');
    if (hint) hint.textContent = 'Данные берутся из backend; решения сохраняются и видны клиенту.';
    window.applyTableFilters && window.applyTableFilters('bankTable');
};

pages['bank-review.html'] = async () => {
    let id = QUERY.get('id');
    if (!id) {
        const l = await api('/bank/applications');
        if (!l.length) return;
        id = (l.find((x) => x.status === 'MANUAL_REVIEW') || l[0]).id;
    }
    const a = await api('/bank/applications/' + id);
    $('.page-heading h1').textContent = 'Рассмотрение заявки';
    $('.page-heading p').textContent = a.number + ' · ' + (a.company ? a.company.name : '—');
    chip($('.page-heading .status'), a.display);
    const back = $('.page-heading .button-link');
    if (back) back.href = 'bank.html';
    const left = $('.detail-layout > section'),
        right = $('.detail-layout > aside');
    setInfo(left, 'Компания', a.company.name);
    setInfo(left, 'ИНН', a.company.inn);
    setInfo(left, 'Сумма', money(a.requested_amount));
    setInfo(left, 'Срок', months(a.term_months));
    setInfo(left, 'Продукт', a.product ? a.product.name : '—');
    setInfo(
        left,
        'Демо-скоринг',
        a.scoring ? `${a.scoring.score_100}/100 · ${a.scoring.risk_level_label} риск` : 'ещё не рассчитан',
    );
    replaceDocRows(left, a.documents, 'Клиент не приложил документы');

    // Блоки скоринга и данных ФНС/БКИ отсутствуют в вёрстке, поэтому вставляются перед «Документами».
    const docsHeading = $$('.section-heading', left)[0];
    const extra = document.createElement('div');
    const f = a.enrichment.FNS && a.enrichment.FNS.payload,
        b = a.enrichment.BKI && a.enrichment.BKI.payload;
    extra.innerHTML = `
        ${
            a.scoring
                ? `<div class="section-heading"><h2>Скоринг</h2></div>
          <ul class="check-list">${a.scoring.factors.map((x) => `<li><span class="checkmark ${x.points >= 0 ? 'done' : 'current'}">${x.points >= 0 ? '+' : '−'}</span>${esc(x.description)}<span class="pts ${x.points >= 0 ? 'pts-pos' : 'pts-neg'}">${x.points > 0 ? '+' : ''}${x.points}</span></li>`).join('')}
          <li style="font-weight:700"><span class="checkmark"></span>Итого<span class="pts">${a.scoring.risk_score} / 1000</span></li></ul>
          <div class="ai-box"><strong>Резюме для андеррайтера</strong><p>${esc(a.scoring.summary)}</p></div>`
                : ''
        }
        ${
            f && b
                ? `<div class="section-heading"><h2>Данные ФНС и БКИ</h2></div><div class="info-grid">
          <div class="info-item"><small>Выручка в месяц (ФНС)</small><strong>${money(f.revenue_monthly_avg)}</strong></div>
          <div class="info-item"><small>Дата регистрации</small><strong>${date(f.registration_date)}</strong></div>
          <div class="info-item"><small>ОКВЭД</small><strong>${esc(f.industry_code)}</strong></div>
          <div class="info-item"><small>Задолженность по налогам</small><strong>${money(f.tax_arrears)}</strong></div>
          <div class="info-item"><small>Рейтинг БКИ</small><strong>${b.credit_rating} / 1000</strong></div>
          <div class="info-item"><small>Действующих кредитов</small><strong>${b.active_loans} · долг ${money(b.total_debt)}</strong></div>
          <div class="info-item"><small>Просрочки за 12 мес.</small><strong>${b.has_overdue_last_12m ? 'Да, ' + b.overdue_count_last_12m + ' (до ' + b.max_overdue_days + ' дн.)' : 'Нет'}</strong></div></div>`
                : ''
        }`;
    docsHeading.before(...extra.children);
    const hist = document.createElement('div');
    hist.innerHTML = `<div class="section-heading"><h2>История и аудит</h2></div><ul class="check-list">${a.history
        .map(
            (h) =>
                `<li><span class="checkmark done">✓</span><span><strong>${esc(STATUS_RU[h.to] || h.to)}</strong> · ${esc(h.actor)}${h.comment ? '<br><span class="muted">' + esc(h.comment) + '</span>' : ''}</span><span class="when">${dateTime(h.timestamp)}</span></li>`,
        )
        .join('')}</ul>`;
    const hint = $('.form-hint', left);
    if (hist.children.length) hint ? hint.before(...hist.children) : left.append(...hist.children);

    const act = a.available_actions,
        canDecide = act.manual_decide || act.override_decision;
    let desc = $('.decision-description', right);
    if (!desc) {
        desc = document.createElement('p');
        desc.className = 'muted decision-description';
        $('.decision-actions', right).before(desc);
    }
    desc.textContent =
        a.status === 'DOCUMENTS_REQUESTED'
            ? 'Ждём документы от клиента: «' + (a.documents_request_comment || '') + '»'
            : a.decision
              ? `Решение: ${{ APPROVED: 'одобрено', REJECTED: 'отказ', COUNTER_OFFER: 'встречное предложение' }[a.decision]}${a.approved_amount ? ', ' + money(a.approved_amount) + ' под ' + ratePct(a.approved_rate) + '%' : ''}. ${a.decision_reason || ''}`
              : canDecide
                ? 'Заявка на ручной проверке. Примите решение или запросите документы.'
                : 'Идёт автоматическая проверка, обновите страницу через минуту.';
    const [bApprove, bDocs, bReject] = $$('.decision-actions a', right);
    [bApprove, bReject].forEach((x) => x.classList.toggle('hidden', !canDecide));
    bDocs.classList.toggle('hidden', !act.request_documents);
    [bApprove, bDocs, bReject].forEach((x) => {
        x.href = withId(x.getAttribute('href'), id);
    });
    const wrap = $('.decision-actions', right);
    if (canDecide) {
        const c = document.createElement('a');
        c.className = 'button button-secondary';
        c.setAttribute('data-popup', '');
        c.addEventListener('click', openInPopup);
        c.href = withId('popups/decision-counter.html', id);
        c.textContent = 'Встречное предложение';
        bReject.before(c);
    }
    if (act.rerun) {
        const r = document.createElement('button');
        r.className = 'button button-secondary';
        r.textContent = 'Пересчитать скоринг';
        wrap.appendChild(r);
        r.addEventListener('click', async () => {
            r.disabled = true;
            try {
                await api(`/bank/applications/${id}/rerun-scoring`, { method: 'POST' });
                await new Promise((x) => setTimeout(x, 700));
                location.reload();
            } catch (e) {
                flash(right, errorHtml(e));
                r.disabled = false;
            }
        });
    }
};

function appIdFromQuery() {
    return QUERY.get('id');
}

pages['credit-details.html'] = async () => {
    const pid = QUERY.get('product');
    if (!pid) return;
    const p = await api('/products/' + pid, { role: 'client' });
    const rate = (p.base_rate + '').replace('.', ',');
    const card = $('.detail-panel');
    setInfo(card, 'Ставка', `от ${rate}% годовых`);
    setInfo(card, 'Сумма', 'до ' + money(p.max_sum));
    setInfo(card, 'Срок', `${p.min_term}–${p.max_term} месяцев`);
    setInfo(card, 'Цель', p.purpose);
    $('.popup-header h1').textContent = 'Условия кредита «' + p.name + '»';
    const go = $('a.button-primary', card);
    const u = new URL('new-application.html', location.href);
    u.searchParams.set('product', pid);
    go.href = u.href;
};

pages['notifications.html'] = async () => {
    const list = await api('/notifications', { role: 'client' });
    $$('.document-row').forEach((r) => r.remove());
    const host = $('script');
    const html = list.length
        ? list
              .map(
                  (n) =>
                      `<div class="document-row"><span>◷</span><div><strong>${esc(n.title)}</strong><small>${dateTime(n.timestamp)}</small></div></div>`,
              )
              .join('')
        : '<p class="muted">Пока нет событий.</p>';
    host.insertAdjacentHTML('beforebegin', html);
};

pages['profile.html'] = async () => {
    const me = await api('/me');
    $('.popup-header h1').textContent = me.full_name;
    const card = $('.detail-panel');
    setInfo(card, 'Компания', me.company ? me.company.name : '—');
    setInfo(card, 'Роль', me.role === 'analyst' ? 'Кредитный аналитик' : 'Предприниматель');
    setInfo(card, 'Email', me.email);
    setInfo(card, 'Доступ', me.role === 'analyst' ? 'Кабинет банка' : 'Клиентский кабинет');
    const h = $('.form-hint', card);
    if (h) h.textContent = 'Вход выполнен автоматически под демо-пользователем. Изменение профиля не реализовано.';
};

pages['new-application.html'] = async () => {
    const form = $('form');
    const products = await api('/products', { role: 'client' });
    const byName = Object.fromEntries(products.map((p) => [p.name, p]));
    const el = {
        product: $('#product'),
        amount: $('#amount'),
        term: $('#term'),
        purpose: $('#purpose'),
        company: $('#company'),
        inn: $('#inn'),
    };
    const pre = QUERY.get('product');
    if (pre) {
        const p = products.find((x) => String(x.id) === pre);
        if (p) el.product.value = p.name;
    }
    const hint = $('.form-hint', form);
    if (hint)
        hint.textContent =
            'Заявку можно сохранить как черновик и вернуться к ней позже. Все суммы и ставки демонстрационные.';

    const gather = () => ({
        product_id: byName[el.product.value] ? byName[el.product.value].id : null,
        requested_amount: el.amount.value ? parseInt(el.amount.value, 10) : null,
        term_months: parseInt(el.term.value, 10) || null, // «24 месяца» -> 24
        purpose: el.purpose.value,
        inn: el.inn.value.trim() || null,
        company_name: el.company.value.trim() || null,
    });
    const fieldHost = {
        product_id: el.product,
        requested_amount: el.amount,
        term_months: el.term,
        purpose: el.purpose,
        inn: el.inn,
        company_name: el.company,
    };
    function showValidation(v) {
        $$('.field-error,.field-warn', form).forEach((e) => e.remove());
        [
            ...v.errors.map((e) => ({ ...e, cls: 'field-error' })),
            ...v.warnings.map((e) => ({ ...e, cls: 'field-warn' })),
        ].forEach((e) => {
            const t = fieldHost[e.field];
            if (!t) return;
            t.insertAdjacentHTML(
                'afterend',
                `<p class="${e.cls}">${esc(e.message)}${e.hint ? '<br>' + esc(e.hint) : ''}</p>`,
            );
        });
    }
    let timer;
    const live = () => {
        clearTimeout(timer);
        timer = setTimeout(async () => {
            try {
                showValidation(await api('/applications/validate', { method: 'POST', body: gather(), role: 'client' }));
            } catch (_) {}
        }, 350);
    };
    Object.values(el).forEach((x) => {
        x.addEventListener('input', live);
        x.addEventListener('change', live);
    });

    // Название компании подставляется по ИНН.
    el.inn.addEventListener('input', async () => {
        const v = el.inn.value.trim();
        if (!/^\d{10}(\d{2})?$/.test(v)) return;
        try {
            const c = await api('/companies/lookup/' + v, { role: 'client' });
            el.company.value = c.name;
            live();
        } catch (_) {
            /* компания не найдена: название введут вручную */
        }
    });

    const ai = document.createElement('div');
    ai.className = 'ai-box';
    ai.innerHTML =
        '<strong>Не знаете, что выбрать? Опишите задачу своими словами</strong><input class="form-control" id="aiText" placeholder="Например: нужно 5 миллионов на закупку оборудования на полгода" style="margin-top:8px"><button type="button" class="button button-secondary button-small" id="aiGo" style="margin-top:8px">Подобрать с помощью ИИ</button><div id="aiOut"></div>';
    form.prepend(ai);
    $('#aiGo').addEventListener('click', async () => {
        const text = $('#aiText').value.trim();
        if (!text) return;
        const out = $('#aiOut');
        try {
            const r = await api('/ai/assistant', { method: 'POST', body: { message: text }, role: 'client' });
            const p = products.find((x) => x.id === r.prefill.product_id);
            if (p) el.product.value = p.name;
            if (r.prefill.requested_amount) el.amount.value = r.prefill.requested_amount;
            if (r.prefill.term_months) {
                const opt = [...el.term.options].find((o) => parseInt(o.value, 10) === r.prefill.term_months);
                if (opt) el.term.value = opt.value;
            }
            if (r.prefill.purpose) el.purpose.value = r.prefill.purpose;
            out.innerHTML = `<p>${esc(r.reply)}</p>`;
            live();
        } catch (e) {
            out.innerHTML = errorHtml(e);
        }
    });

    const actions = $('.form-actions', form);
    const draft = document.createElement('button');
    draft.type = 'button';
    draft.className = 'button button-secondary';
    draft.textContent = 'Сохранить черновик';
    actions.insertBefore(draft, $('button[type=submit]', actions));
    const goDetail = (id) => {
        const url = new URL('../application-detail.html?id=' + id, location.href).href;
        IN_FRAME ? parent.postMessage({ type: 'popup-navigate', url }, location.origin) : (location.href = url);
    };

    draft.addEventListener('click', async () => {
        try {
            const a = await api('/applications', { method: 'POST', body: gather(), role: 'client' });
            notifyParentChanged();
            goDetail(a.id);
        } catch (e) {
            flash(form, errorHtml(e), actions);
        }
    });
    form.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const btn = $('button[type=submit]', form);
        btn.disabled = true;
        try {
            const a = await api('/applications', { method: 'POST', body: gather(), role: 'client' });
            try {
                await api(`/applications/${a.id}/submit`, { method: 'POST', role: 'client' });
            } catch (e) {
                flash(
                    form,
                    errorHtml(e) +
                        '<div class="alert alert-info">Черновик сохранён - его можно дописать в «Моих заявках».</div>',
                    actions,
                );
                btn.disabled = false;
                return;
            }
            notifyParentChanged();
            goDetail(a.id);
        } catch (e) {
            flash(form, errorHtml(e), actions);
            btn.disabled = false;
        }
    });
};

function gate(resultCard, formHtml, onSubmit) {
    // Готовый экран результата скрыт, пока аналитик не заполнит форму и не подтвердит решение.
    resultCard.classList.add('hidden');
    const form = document.createElement('form');
    form.innerHTML =
        formHtml +
        '<div class="form-actions"><a class="button button-secondary" href="../bank-review.html">Отмена</a><button class="button button-primary" type="submit">Подтвердить</button></div>';
    resultCard.before(form);
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = $('button[type=submit]', form);
        btn.disabled = true;
        try {
            await onSubmit(new FormData(form));
            form.remove();
            resultCard.classList.remove('hidden');
            notifyParentChanged();
        } catch (err) {
            flash(form, errorHtml(err), $('.form-actions', form));
            btn.disabled = false;
        }
    });
}
const field = (label, html) => `<label class="field-label">${label}</label>${html}`;

pages['decision-approved.html'] = async () => {
    const id = appIdFromQuery();
    const a = await api('/bank/applications/' + id);
    gate(
        $('.card.detail-panel'),
        `<div class="form-grid"><div>${field('Одобренная сумма, ₽', `<input name="amount" type="number" value="${a.requested_amount}" min="${a.product_limits.min_sum}" max="${a.product_limits.max_sum}" required>`)}</div>
         <div>${field('Ставка, % годовых', `<input name="rate" type="number" step="0.1" value="${a.product_limits.base_rate}" required>`)}</div></div>
         ${field('Комментарий', '<input name="comment" placeholder="Необязательно">')}`,
        (fd) =>
            api(`/bank/applications/${id}/approve`, {
                method: 'POST',
                body: { amount: +fd.get('amount'), rate: +fd.get('rate'), comment: fd.get('comment') || null },
            }),
    );
    $$('a[href="../bank-review.html"]').forEach((x) => (x.href = withId('../bank-review.html', id)));
};

pages['decision-counter.html'] = async () => {
    const id = appIdFromQuery();
    const a = await api('/bank/applications/' + id);
    const rate = (a.product_limits.base_rate + COUNTER_RATE_ADD).toFixed(1);
    gate(
        $('.card.detail-panel'),
        `<div class="form-grid"><div>${field('Предложить сумму, ₽', `<input name="amount" type="number" value="${Math.round((a.requested_amount * COUNTER_AMOUNT_FACTOR) / 1000) * 1000}" required>`)}</div>
         <div>${field('Ставка, % годовых', `<input name="rate" type="number" step="0.1" value="${rate}" required>`)}</div></div>
         ${field('Комментарий клиенту', '<input name="comment" placeholder="Например: нужен залог">')}`,
        (fd) =>
            api(`/bank/applications/${id}/counter-offer`, {
                method: 'POST',
                body: { amount: +fd.get('amount'), rate: +fd.get('rate'), comment: fd.get('comment') || null },
            }),
    );
};

pages['decision-rejected.html'] = async () => {
    const id = appIdFromQuery();
    gate(
        $('.card.detail-panel'),
        field(
            'Причина отказа (её увидит клиент)',
            '<input name="reason" placeholder="Например: недостаточная выручка для запрошенной суммы" required minlength="3">',
        ),
        (fd) => api(`/bank/applications/${id}/reject`, { method: 'POST', body: { reason: fd.get('reason') } }),
    );
};

pages['decision-documents.html'] = async () => {
    const id = appIdFromQuery();
    const form = $('form');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = $('button[type=submit]', form);
        btn.disabled = true;
        try {
            await api(`/bank/applications/${id}/request-documents`, {
                method: 'POST',
                body: { comment: $('#comment').value },
            });
            notifyParentChanged();
            IN_FRAME
                ? parent.postMessage({ type: 'popup-close' }, location.origin)
                : (location.href = withId('../bank-review.html', id));
        } catch (err) {
            flash(form, errorHtml(err), $('.form-actions', form));
            btn.disabled = false;
        }
    });
    const h = $('.form-hint', form);
    if (h) h.textContent = 'Комментарий увидит клиент, заявка перейдёт в статус «Нужны документы».';
};

// Окно действия открывается так же, как в app.js. Здесь это нужно для ссылок, созданных после загрузки страницы.
function openInPopup(event) {
    const dialog = $('#popupDialog');
    const frame = dialog && $('iframe', dialog);
    if (!frame || typeof dialog.showModal !== 'function') return;
    event.preventDefault();
    frame.src = event.currentTarget.href;
    dialog.showModal();
}

// Сообщения из popup-окон: закрыть окно, перейти на другую страницу, обновить данные после изменений.
let popupChanged = false;
window.addEventListener('message', (event) => {
    if (event.origin !== location.origin || IN_FRAME) return;
    const dialog = $('#popupDialog');
    const { type, url } = event.data || {};
    if (type === 'popup-changed') popupChanged = true;
    if (type === 'popup-close' && dialog) dialog.close();
    if (type === 'popup-navigate') location.href = url;
});
document.addEventListener(
    'close',
    (event) => {
        if (event.target.id === 'popupDialog' && popupChanged) location.reload();
    },
    true,
);

document.addEventListener('DOMContentLoaded', async () => {
    if (!IN_FRAME && !$('.popup-body')) hydrateHeader();
    // Ссылки из popup на bank-review.html сохраняют id заявки.
    const id = appIdFromQuery();
    if (id) $$('a[href^="../bank-review.html"]').forEach((a) => (a.href = withId(a.getAttribute('href'), id)));
    const run = pages[PAGE];
    if (!run) return;
    try {
        await run();
    } catch (e) {
        console.error(e);
        const host = $('.page-content') || $('.popup-body') || document.body;
        host.insertAdjacentHTML('afterbegin', errorHtml(e));
    }
});
