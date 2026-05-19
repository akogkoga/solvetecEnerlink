const DEFAULT_API_BASE_URL = (
    ['localhost', '127.0.0.1'].includes(window.location.hostname)
    && ['5500', '5501'].includes(window.location.port)
) || window.location.protocol === 'file:'
    ? 'http://localhost:8000'
    : '';
const BASE_URL = window.ENERLINK_API_BASE_URL || DEFAULT_API_BASE_URL;
const API_URL = `${BASE_URL}/api/v1/leads/generate`;
const HEALTH_URL = `${BASE_URL}/health`;
const THEME_KEY = 'enerlink-theme';
const REQUEST_TIMEOUT_MS = 45000;
const VALID_UFS = new Set([
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG',
    'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
]);

const form = document.getElementById('lead-form');
const generateBtn = document.getElementById('generate-btn');
const leadsBody = document.getElementById('leads-body');
const statusBadge = document.getElementById('status-badge');
const metaSection = document.getElementById('meta-section');
const metaTime = document.getElementById('meta-time');
const metaFound = document.getElementById('meta-found');
const metaReturned = document.getElementById('meta-returned');
const metaProviders = document.getElementById('meta-providers');
const metaErrors = document.getElementById('meta-errors');
const progressSection = document.getElementById('progress-section');
const themeToggles = document.querySelectorAll('.theme-toggle');
const systemStatus = document.getElementById('system-status');
const fallbackBanner = document.getElementById('fallback-banner');
const fallbackMessage = document.getElementById('fallback-message');
const guidedSearch = document.getElementById('guided-search');
const searchTip = document.getElementById('search-tip');
const advancedFields = document.getElementById('advanced-fields');

let loadingTimers = [];

const DEMOS = {
    'tech-sp': { termo: 'tecnologia', nome: '', cnae: '', estado: 'SP', cidade: 'Sao Paulo', porte: '', natureza_juridica: '', situacao: '', quantidade: 20, pagina: 1 },
    'tech-rj': { termo: 'tecnologia', nome: '', cnae: '', estado: 'RJ', cidade: 'Rio de Janeiro', porte: '', natureza_juridica: '', situacao: '', quantidade: 20, pagina: 1 },
    'servicos-rj': { termo: 'servicos', nome: '', cnae: '', estado: 'RJ', cidade: 'Rio de Janeiro', porte: '', natureza_juridica: '', situacao: '', quantidade: 20, pagina: 1 },
    'mercados-mg': { termo: 'mercado', nome: '', cnae: '', estado: 'MG', cidade: '', porte: '', natureza_juridica: '', situacao: '', quantidade: 20, pagina: 1 },
    'clinicas-rs': { termo: 'clinica', nome: '', cnae: '', estado: 'RS', cidade: 'Porto Alegre', porte: '', natureza_juridica: '', situacao: '', quantidade: 20, pagina: 1 },
    'restaurantes-ba': { termo: 'restaurante', nome: '', cnae: '', estado: 'BA', cidade: 'Salvador', porte: '', natureza_juridica: '', situacao: '', quantidade: 20, pagina: 1 },
    'ltda-pr': { termo: 'LTDA', nome: '', cnae: '', estado: 'PR', cidade: 'Curitiba', porte: '', natureza_juridica: '', situacao: '', quantidade: 20, pagina: 1 },
    'mei-pe': { termo: 'MEI', nome: '', cnae: '', estado: 'PE', cidade: 'Recife', porte: 'MEI', natureza_juridica: '', situacao: '', quantidade: 20, pagina: 1 }
};

initTheme();
bindDemoButtons();
bindSearchForm();
updateSearchTip();

function bindDemoButtons(root = document) {
    root.querySelectorAll('[data-demo]').forEach((button) => {
        button.addEventListener('click', () => {
            const demo = DEMOS[button.dataset.demo];
            if (!demo || !form) return;
            fillForm(demo);
            updateSearchTip();
            form.requestSubmit();
        });
    });
}

function bindSearchForm() {
    if (!form) return;

    form.addEventListener('input', updateSearchTip);
    form.addEventListener('change', updateSearchTip);

    document.addEventListener('click', (event) => {
        const action = event.target.closest('[data-action]');
        if (action?.dataset.action === 'expand-search') amplifySearch();
        if (action?.dataset.action === 'clear-filters') clearFilters();
    });

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const payload = getPayload();
        syncFormFromPayload(payload);
        const startedAt = performance.now();
        logExecution('search:start', { filtros: payload });

        clearOperationalNotices();
        if (guidedSearch) guidedSearch.hidden = true;
        setLoading('Verificando sistema...', 'Preparando busca inteligente...');
        updateSystemStatus('checking', 'Validando motor');
        showProgress(0);

        if (!(await checkBackendHealth())) {
            statusBadge.textContent = 'Sistema aguardando';
            statusBadge.className = 'badge warning';
            updateSystemStatus('warning', 'Backend indisponível');
            renderSmartEmptyState(
                'Não consegui falar com o motor de busca agora.',
                'Assim que o backend estiver online, a Enerlink volta a consultar a base normalmente.'
            );
            resetButton();
            hideProgress();
            logExecution('search:offline', { filtros: payload, tempo_cliente_ms: elapsed(startedAt) });
            return;
        }

        showProgress(1);
        setLoading('Buscando leads...', 'Buscando empresas na base...');
        updateSystemStatus('searching', 'Buscando dados');
        renderSkeletonRows('Buscando empresas na base...');
        scheduleLoadingMessages();
        let timeoutId;

        try {
            const controller = new AbortController();
            timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            timeoutId = null;

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(getApiErrorMessage(response.status, errorData));
            }

            const data = await response.json();
            const sortedData = {
                ...data,
                leads: sortLeadsByScore(data.leads || [])
            };
            const adjusted = hasAdjustedResults(sortedData);

            clearLoadingTimers();
            showProgress(3);
            renderLeads(sortedData);
            renderMeta(sortedData);

            const hasResults = sortedData.total_returned > 0;
            statusBadge.textContent = hasResults
                ? (adjusted ? 'Busca ampliada' : `${sortedData.total_returned} leads encontrados`)
                : 'Busca sem resultado exato';
            statusBadge.className = adjusted || !hasResults ? 'badge warning' : 'badge success';
            updateSystemStatus(
                adjusted || !hasResults ? 'warning' : 'online',
                adjusted ? 'Busca inteligente ativa' : (hasResults ? 'Sistema online' : 'Ajuste sugerido')
            );

            logExecution('search:success', {
                filtros: payload,
                encontrados: sortedData.total_found,
                retornados: sortedData.total_returned,
                tempo_api_ms: sortedData.search_time_ms,
                tempo_cliente_ms: elapsed(startedAt),
                providers: sortedData.providers_used,
                top_leads: sortedData.leads.slice(0, 3).map((lead) => lead.empresa)
            });
        } catch (error) {
            clearLoadingTimers();
            statusBadge.textContent = 'Busca não concluída';
            statusBadge.className = 'badge warning';
            updateSystemStatus('warning', 'Tente novamente');
            renderSmartEmptyState(
                'Não consegui concluir esta busca.',
                getFriendlyErrorMessage(error)
            );
            hideProgress();
            logExecution('search:attention', {
                filtros: payload,
                tempo_cliente_ms: elapsed(startedAt),
                detalhe: error.message || 'Busca não concluída'
            });
        } finally {
            if (timeoutId) clearTimeout(timeoutId);
            resetButton();
        }
    });
}

function initTheme() {
    applyTheme(localStorage.getItem(THEME_KEY) || 'dark');
    themeToggles.forEach((button) => {
        button.addEventListener('click', () => {
            const next = document.body.classList.contains('theme-dark') ? 'light' : 'dark';
            applyTheme(next);
            localStorage.setItem(THEME_KEY, next);
        });
    });
}

function applyTheme(theme) {
    const isLight = theme === 'light';
    document.body.classList.toggle('theme-light', isLight);
    document.body.classList.toggle('theme-dark', !isLight);
    themeToggles.forEach((button) => {
        button.textContent = isLight ? '☾' : '☀';
    });
}

async function checkBackendHealth() {
    try {
        const response = await fetch(HEALTH_URL, { method: 'GET', cache: 'no-store' });
        if (!response.ok) return false;
        const data = await response.json();
        return data.status === 'online';
    } catch {
        return false;
    }
}

function getPayload() {
    const formData = new FormData(form);
    return {
        termo: cleanText(formData.get('termo')),
        nome: cleanText(formData.get('nome')),
        cnae: cleanText(formData.get('cnae')),
        estado: normalizeEstado(formData.get('estado')),
        cidade: cleanText(formData.get('cidade')),
        porte: cleanText(formData.get('porte')),
        natureza_juridica: cleanText(formData.get('natureza_juridica')),
        situacao: cleanText(formData.get('situacao')),
        quantidade: normalizeInteger(formData.get('quantidade'), 100, 1, 1000),
        pagina: normalizeInteger(formData.get('pagina'), 1, 1, 10000)
    };
}

function cleanText(value) {
    const cleaned = String(value ?? '').trim();
    return cleaned || null;
}

function normalizeEstado(value) {
    const cleaned = cleanText(value);
    return cleaned ? cleaned.toUpperCase() : null;
}

function normalizeInteger(value, fallback, min, max) {
    const parsed = parseInt(value, 10);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(min, Math.min(max, parsed));
}

function syncFormFromPayload(payload) {
    if (!form) return;
    if (form.elements.estado) form.elements.estado.value = payload.estado || '';
    if (form.elements.quantidade) form.elements.quantidade.value = payload.quantidade;
    if (form.elements.pagina) form.elements.pagina.value = payload.pagina;
}

function setLoading(buttonText, statusText) {
    if (!generateBtn || !statusBadge) return;
    generateBtn.disabled = true;
    generateBtn.textContent = buttonText;
    statusBadge.textContent = statusText;
    statusBadge.className = 'badge';
}

function resetButton() {
    if (!generateBtn) return;
    generateBtn.disabled = false;
    generateBtn.textContent = 'Gerar Leads';
}

function updateSystemStatus(state, label) {
    if (!systemStatus) return;
    systemStatus.className = `system-pill system-pill-${state}`;
    systemStatus.innerHTML = `<span></span>${escapeHtml(label)}`;
}

function clearOperationalNotices() {
    if (fallbackBanner) fallbackBanner.hidden = true;
    if (metaErrors) {
        metaErrors.hidden = true;
        metaErrors.innerHTML = '';
    }
}

function scheduleLoadingMessages() {
    clearLoadingTimers();
    loadingTimers = [
        setTimeout(() => {
            setLoading('Ampliando busca...', 'Ampliando busca para encontrar mais resultados...');
            updateSystemStatus('searching', 'Fallback ativo');
            renderSkeletonRows('Ampliando busca para encontrar mais resultados...');
            showProgress(2);
        }, 1400),
        setTimeout(() => {
            setLoading('Priorizando leads...', 'Pontuando oportunidades mais próximas...');
            updateSystemStatus('searching', 'Pontuando leads');
            renderSkeletonRows('Pontuando oportunidades mais próximas...');
            showProgress(2);
        }, 3200),
        setTimeout(() => {
            setLoading('Ainda buscando...', 'Consulta ampla em andamento...');
            updateSystemStatus('searching', 'Mantendo busca ativa');
            renderSkeletonRows('Algumas combinações exigem uma busca mais ampla. Ainda estamos procurando resultados úteis.');
            showProgress(2);
        }, 7000)
    ];
}

function clearLoadingTimers() {
    loadingTimers.forEach((timer) => clearTimeout(timer));
    loadingTimers = [];
}

function fillForm(values) {
    for (const [name, value] of Object.entries(values)) {
        const field = form.elements[name];
        if (field) field.value = value;
    }
    if (advancedFields) {
        advancedFields.open = Boolean(values.nome || values.porte || values.natureza_juridica || values.situacao);
    }
}

function showProgress(activeIndex) {
    if (!progressSection) return;
    progressSection.hidden = false;
    progressSection.querySelectorAll('.progress-step').forEach((step, index) => {
        step.classList.toggle('active', index <= activeIndex);
        step.classList.toggle('complete', index < activeIndex);
    });
}

function hideProgress() {
    if (progressSection) progressSection.hidden = true;
}

function renderLeads(data) {
    if (!data.leads || data.leads.length === 0) {
        renderSmartEmptyState(
            'Não encontramos resultados exatos nesta combinação.',
            'A Enerlink pode ampliar a busca removendo filtros muito específicos.'
        );
        return;
    }

    leadsBody.innerHTML = data.leads.map((lead, index) => `
        <tr class="result-row ${index === 0 ? 'best-lead' : ''} ${index > 0 && index < 3 ? 'top-lead' : ''}" style="--row-index: ${index}">
            <td class="company-cell">
                ${index === 0 ? '<span class="recommended-badge">Lead recomendado</span>' : ''}
                <strong>${index < 3 ? '<span class="lead-rank">★</span>' : ''}${escapeHtml(lead.empresa)}</strong>
                <span>${formatCnpj(lead.cnpj)}${lead.fonte ? ` · ${escapeHtml(lead.fonte)}` : ''}</span>
            </td>
            <td>${escapeHtml(lead.cidade || '-')}</td>
            <td>${escapeHtml(lead.estado || '-')}</td>
            <td>${escapeHtml(lead.cnae || '-')}</td>
            <td>${escapeHtml(lead.situacao || '-')}</td>
            <td>
                <span class="score-badge ${getScoreClass(lead.score)}">${getScoreIcon(lead.score)} ${lead.score}</span>
                <span class="score-meter"><span style="width: ${Math.max(4, Math.min(100, Number(lead.score) || 0))}%"></span></span>
            </td>
        </tr>
    `).join('');
}

function renderSkeletonRows(message = 'Buscando empresas na base...') {
    if (!leadsBody) return;
    const rows = Array.from({ length: 8 }, (_, index) => `
        <tr class="skeleton-row" style="--row-index: ${index}">
            <td><span class="skeleton skeleton-company"></span><span class="skeleton skeleton-small"></span></td>
            <td><span class="skeleton skeleton-medium"></span></td>
            <td><span class="skeleton skeleton-tiny"></span></td>
            <td><span class="skeleton skeleton-medium"></span></td>
            <td><span class="skeleton skeleton-small"></span></td>
            <td><span class="skeleton skeleton-score"></span></td>
        </tr>
    `).join('');
    leadsBody.innerHTML = `
        <tr class="loading-row">
            <td colspan="6">
                <strong>${escapeHtml(message)}</strong>
                <span>A Enerlink consulta a base local e amplia os filtros quando isso ajuda a encontrar melhores empresas.</span>
            </td>
        </tr>
        ${rows}
    `;
}

function renderSmartEmptyState(title, message) {
    if (!leadsBody) return;
    leadsBody.innerHTML = `
        <tr>
            <td colspan="6" class="empty-state">
                <div class="empty-card">
                    <strong>${escapeHtml(title)}</strong>
                    <span>${escapeHtml(message)}</span>
                    <div class="empty-actions">
                        <button type="button" class="btn btn-primary" data-action="expand-search">Ampliar busca</button>
                        <button type="button" class="demo-btn" data-demo="tech-sp">Tecnologia SP</button>
                        <button type="button" class="demo-btn" data-demo="restaurantes-ba">Restaurantes BA</button>
                    </div>
                </div>
            </td>
        </tr>
    `;
    bindDemoButtons(leadsBody);
}

function renderMeta(data) {
    if (!metaSection) return;
    metaSection.hidden = false;
    metaTime.textContent = `${data.search_time_ms || 0}ms`;
    metaFound.textContent = data.total_found || 0;
    metaReturned.textContent = data.total_returned || 0;
    metaProviders.textContent = (data.providers_used || []).join(', ') || '-';

    if (data.errors && data.errors.length > 0) {
        const adjustedNotice = data.errors.find((err) => String(err).includes('Resultados ajustados'));
        if (adjustedNotice && fallbackBanner && fallbackMessage) {
            fallbackBanner.hidden = false;
            fallbackMessage.textContent = formatAdjustedNotice(adjustedNotice);
        }

        const otherNotices = data.errors.filter((err) => !String(err).includes('Resultados ajustados'));
        if (otherNotices.length) {
            metaErrors.hidden = false;
            metaErrors.innerHTML = otherNotices
                .map((err) => `<span class="error-item">${formatOperationalNotice(err)}</span>`)
                .join('');
        } else {
            metaErrors.hidden = true;
            metaErrors.innerHTML = '';
        }
    } else {
        if (fallbackBanner) fallbackBanner.hidden = true;
        metaErrors.hidden = true;
        metaErrors.innerHTML = '';
    }
}

function hasAdjustedResults(data) {
    return (data.errors || []).some((message) => String(message).includes('Resultados ajustados'));
}

function getApiErrorMessage(status, errorData) {
    if (status === 422) {
        return 'Revise os filtros e tente novamente. A quantidade deve ficar entre 1 e 1000.';
    }

    if (typeof errorData.detail === 'string') return errorData.detail;
    return `O motor respondeu com status ${status}. Tente novamente em alguns segundos.`;
}

function getFriendlyErrorMessage(error) {
    if (error?.name === 'AbortError') {
        return 'A busca demorou mais que o esperado. Experimente remover cidade, CNAE ou filtros avançados e tente novamente.';
    }

    const message = error?.message || '';
    if (message.includes('Failed to fetch')) {
        return 'A conexão com o backend oscilou. Verifique se o servidor está online e tente novamente.';
    }

    return message || 'Tente novamente ou amplie os filtros para uma consulta mais resiliente.';
}

function formatOperationalNotice(message) {
    const text = String(message || '');
    return `Aviso operacional: ${escapeHtml(text)}`;
}

function formatAdjustedNotice(message) {
    const details = String(message || '')
        .replace('Resultados ajustados para ampliar a busca:', '')
        .trim();
    return details
        ? `Ajustamos sua busca automaticamente: ${details}. Assim você recebe empresas possíveis em vez de uma tela vazia.`
        : 'Ajustamos sua busca automaticamente para encontrar leads úteis.';
}

function getScoreClass(score) {
    if (score >= 80) return 'score-high';
    if (score >= 50) return 'score-mid';
    return 'score-low';
}

function getScoreIcon(score) {
    if (score >= 80) return '▲';
    if (score >= 50) return '◆';
    return '●';
}

function sortLeadsByScore(leads) {
    return [...leads].sort((a, b) => (b.score || 0) - (a.score || 0));
}

function updateSearchTip() {
    if (!form || !searchTip) return;
    const values = getPayload();
    const specificFilters = [values.cidade, values.cnae, values.nome, values.porte, values.natureza_juridica].filter(Boolean).length;
    const hasAnySearchFilter = [
        values.termo,
        values.nome,
        values.cnae,
        values.estado,
        values.cidade,
        values.porte,
        values.natureza_juridica,
        values.situacao
    ].some(Boolean);
    const hasInvalidUf = values.estado && !VALID_UFS.has(values.estado);
    let title = 'Dica inteligente';
    let text = 'Buscas por estado costumam revelar mais empresas qualificadas.';

    if (!hasAnySearchFilter) {
        title = 'Busca ampla';
        text = 'Sem filtros, a Enerlink retorna os melhores leads disponíveis na base.';
    } else if (hasInvalidUf) {
        title = 'UF não reconhecida';
        text = 'Confira a sigla do estado. Se ela não existir, a busca será ampliada automaticamente.';
    } else if (specificFilters >= 3) {
        title = 'Filtro bem específico';
        text = 'Se vierem poucos leads, a Enerlink amplia a busca automaticamente para ajudar.';
    } else if (values.cidade && values.termo) {
        title = 'Boa combinação';
        text = 'Cidade + segmento traz precisão; remover a cidade aumenta a cobertura.';
    } else if (!values.estado) {
        title = 'Cobertura ampla';
        text = 'Adicionar um estado ajuda a priorizar empresas mais próximas do seu mercado.';
    }

    searchTip.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(text)}</span>`;
}

function amplifySearch() {
    if (!form) return;
    ['cidade', 'cnae', 'nome', 'porte', 'natureza_juridica'].forEach((name) => {
        const field = form.elements[name];
        if (field) field.value = '';
    });
    updateSearchTip();
    form.requestSubmit();
}

function clearFilters() {
    if (!form) return;
    fillForm({
        termo: '',
        nome: '',
        cnae: '',
        estado: '',
        cidade: '',
        porte: '',
        natureza_juridica: '',
        situacao: '',
        quantidade: 20,
        pagina: 1
    });
    if (advancedFields) advancedFields.open = false;
    updateSearchTip();
    if (statusBadge) {
        statusBadge.textContent = 'Filtros limpos';
        statusBadge.className = 'badge';
    }
}

function logExecution(eventName, details) {
    console.info(`[Enerlink] ${eventName}`, details);
}

function elapsed(startedAt) {
    return Math.round(performance.now() - startedAt);
}

function formatCnpj(cnpj) {
    if (!cnpj || cnpj.length < 14) return cnpj || '-';
    return cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text ?? '');
    return div.innerHTML;
}
