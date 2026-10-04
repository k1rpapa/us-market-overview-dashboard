// 市場俯瞰ビュー: macro.json (fetch_macro.py が生成) を指標カードとして表示する。
// 総合スコアは算出しない。値は取得できたものだけを表示し、未取得は理由を明示する。

const MACRO_STATUS_LABELS = {
    ok: "取得済み",
    pending: "未接続",
    link_only: "リンクのみ",
    unavailable: "取得失敗",
    restricted: "再配布制限"
};

function escapeHtml(value) {
    return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

// 外部由来のURLは http(s) のみリンクとして許可する
function safeUrl(url) {
    return /^https?:\/\//i.test(url || "") ? url : "#";
}

function formatNumber(value) {
    if (typeof value !== "number" || !isFinite(value)) return "—";
    const abs = Math.abs(value);
    const digits = abs >= 1000 ? 0 : abs >= 100 ? 1 : 2;
    return value.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: digits });
}

function formatValue(value, unit) {
    const text = formatNumber(value);
    if (text === "—") return text;
    return unit === "%" ? `${text}%` : unit ? `${text} ${unit}` : text;
}

function percentileLabel(p) {
    if (typeof p !== "number") return "—";
    return p >= 50 ? `上位 ${(100 - p).toFixed(0)}%` : `下位 ${p.toFixed(0)}%`;
}

function buildSparkline(history, width = 240, height = 56) {
    const points = (history || []).filter(p => Array.isArray(p) && typeof p[1] === "number");
    if (points.length < 2) return "";
    const values = points.map(p => p[1]);
    const min = Math.min(...values);
    const range = (Math.max(...values) - min) || 1;
    const pad = 3;
    const coords = points.map((p, i) => {
        const x = pad + (i / (points.length - 1)) * (width - pad * 2);
        const y = height - pad - ((p[1] - min) / range) * (height - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const last = coords[coords.length - 1].split(",");
    return `<svg class="spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="長期推移">` +
        `<polyline points="${coords.join(" ")}" fill="none" stroke="currentColor" stroke-width="1.5" vector-effect="non-scaling-stroke"/>` +
        `<circle cx="${last[0]}" cy="${last[1]}" r="2.5" fill="currentColor"/></svg>`;
}

// レンジバー: 歴史的最小〜最大の中での現在位置
function buildRangeBar(stats, latestValue) {
    if (!stats || stats.max === stats.min) return "";
    const pos = Math.min(100, Math.max(0, ((latestValue - stats.min) / (stats.max - stats.min)) * 100));
    return `<div class="range-bar" title="歴史的レンジ内の位置"><span class="range-marker" style="left:${pos.toFixed(1)}%"></span></div>` +
        `<div class="range-labels"><span>${escapeHtml(formatNumber(stats.min))}</span><span>${escapeHtml(formatNumber(stats.max))}</span></div>`;
}

function renderIndicatorCard(ind) {
    const status = ind.status in MACRO_STATUS_LABELS ? ind.status : "unavailable";
    let body;
    if (status === "ok" && ind.latest) {
        const s = ind.stats || {};
        body = `
            <div class="macro-value">${escapeHtml(formatValue(ind.latest.value, ind.unit))}</div>
            <div class="macro-asof">最新観測日: ${escapeHtml(ind.latest.date)} ／ ${escapeHtml(ind.frequency)}</div>
            <div class="macro-spark">${buildSparkline(ind.history)}</div>
            ${buildRangeBar(s, ind.latest.value)}
            <div class="macro-stats">歴史的位置: <strong>${escapeHtml(percentileLabel(s.percentile))}</strong>
                （${escapeHtml(s.start)}〜 / 中央値 ${escapeHtml(formatNumber(s.median))}）</div>`;
    } else {
        body = `
            <div class="macro-unavailable">${escapeHtml(ind.reason || "データがありません。")}</div>
            <div class="macro-asof">更新頻度: ${escapeHtml(ind.frequency)}</div>`;
    }
    const formula = ind.formula ? `<p><strong>算式:</strong> ${escapeHtml(ind.formula)}</p>` : "";
    return `
        <article class="macro-card macro-${status}" data-indicator="${escapeHtml(ind.id)}">
            <div class="macro-card-head">
                <h3>${escapeHtml(ind.name)}</h3>
                <span class="macro-status status-${status}">${MACRO_STATUS_LABELS[status]}</span>
            </div>
            ${body}
            <details class="macro-details">
                <summary>定義・読み方・注意点</summary>
                <p><strong>定義:</strong> ${escapeHtml(ind.definition)}</p>
                <p><strong>読み方:</strong> ${escapeHtml(ind.reading)}</p>
                <p><strong>注意点:</strong> ${escapeHtml(ind.caution)}</p>
                ${formula}
            </details>
            <div class="macro-source">出典: <a href="${escapeHtml(safeUrl(ind.source_url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(ind.source)}</a></div>
        </article>`;
}

function renderMacroHtml(data) {
    const indicators = (data && data.indicators) || [];
    if (indicators.length === 0) {
        return `<p class="macro-message">表示できる指標がありません。</p>`;
    }
    const groups = (data.groups && data.groups.length) ? data.groups : [{ id: "all", name: "指標" }];
    const known = new Set(groups.map(g => g.id));
    const sections = groups.map(g => {
        const items = indicators.filter(i => i.group === g.id || (g.id === "all" && !known.has(i.group)));
        if (items.length === 0) return "";
        return `<section class="macro-group"><h3 class="macro-group-title">${escapeHtml(g.name)}</h3>` +
            `<div class="macro-grid">${items.map(renderIndicatorCard).join("")}</div></section>`;
    }).join("");
    const ok = indicators.filter(i => i.status === "ok").length;
    const summary = `<p class="macro-summary">取得済み ${ok} / ${indicators.length} 指標` +
        `（生成: ${escapeHtml(data.generated_at || "不明")}）。未接続・取得失敗の指標は値を表示していません。総合スコアは算出していません。</p>`;
    return summary + sections;
}

let macroLoaded = false;

async function loadMacro(force = false) {
    const el = document.getElementById("macroContent");
    if (!el || (macroLoaded && !force)) return;
    el.innerHTML = `<p class="macro-message">指標データを読み込み中...</p>`;
    try {
        const res = await fetch("macro.json?t=" + Date.now(), { cache: "no-store" });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        el.innerHTML = renderMacroHtml(data);
        macroLoaded = true;
    } catch (error) {
        console.error("Failed to load macro data:", error);
        el.innerHTML = `<p class="macro-message macro-error">指標データを読み込めませんでした。` +
            `<button class="reset-ai-btn" id="macroRetryBtn">再読み込み</button></p>`;
        const retry = document.getElementById("macroRetryBtn");
        if (retry) retry.addEventListener("click", () => loadMacro(true));
    }
}

if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", () => loadMacro());
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { escapeHtml, safeUrl, formatValue, formatNumber, percentileLabel,
        buildSparkline, buildRangeBar, renderIndicatorCard, renderMacroHtml };
}
