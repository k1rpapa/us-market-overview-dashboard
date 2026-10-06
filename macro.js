// 市場俯瞰ビュー: macro.json (fetch_macro.py が生成) を指標カードとして表示する。
// 総合スコアは算出しない。値は取得できたものだけを表示し、未取得は理由を明示する。

const MACRO_STATUS_LABELS = {
    ok: "取得済み",
    pending: "未接続",
    link_only: "リンクのみ",
    unavailable: "取得失敗",
    restricted: "再配布制限",
    stale: "最終観測が古い"
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

function buildAdComparison(comparison) {
    const rows = (comparison && comparison.series) || [];
    if (rows.length < 2) {
        return `<p class="ad-reading">${escapeHtml(comparison && comparison.reading || "比較できる共通履歴がありません。")}</p>`;
    }
    const width = 480, height = 150, pad = 8;
    const project = column => {
        const values = rows.map(row => row[column]);
        const min = Math.min(...values), range = Math.max(...values) - min || 1;
        return values.map((value, index) => {
            const x = pad + index / (values.length - 1) * (width - pad * 2);
            const y = height - pad - (value - min) / range * (height - pad * 2);
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(" ");
    };
    const first = rows[0][0], last = rows[rows.length - 1][0];
    const indexLabel = comparison.comparison_type === "reference"
        ? `${comparison.index_name} (参考指数・基準日比%)`
        : `${comparison.index_name} (指数価格・基準日比%)`;
    return `<div class="ad-compare-chart">
        <div class="ad-legend"><span class="ad-legend-line">A/D累積差 (基準日比)</span><span class="ad-legend-index">${escapeHtml(indexLabel)}</span></div>
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="A/Dラインと${escapeHtml(comparison.index_name)}の同期間推移。縦軸はそれぞれ独立スケール">
            <line x1="${pad}" y1="${height / 2}" x2="${width - pad}" y2="${height / 2}" class="ad-zero"/>
            <polyline points="${project(1)}" class="ad-line-path"/>
            <polyline points="${project(2)}" class="ad-index-path"/>
        </svg>
        <div class="ad-chart-dates"><span>${escapeHtml(first)}</span><span>${escapeHtml(last)}</span></div>
        <p class="ad-reading">${escapeHtml(comparison.reading)} <small>A/Dは対象銘柄のbreadth、指数は株価です。縦軸は線ごとに独立スケールで、参考比較として見てください。</small></p>
    </div>`;
}

function buildAdDailyBars(dailyNet) {
    const rows = (dailyNet || []).filter(row => Array.isArray(row) && typeof row[1] === "number");
    if (!rows.length) return "";
    const width = 480, height = 92, pad = 4, zero = height / 2;
    const maxAbs = Math.max(1, ...rows.map(row => Math.abs(row[1])));
    const slot = (width - pad * 2) / rows.length;
    const bars = rows.map((row, i) => {
        const barHeight = Math.max(1, Math.abs(row[1]) / maxAbs * (zero - pad));
        const x = pad + i * slot + slot * 0.1;
        const y = row[1] >= 0 ? zero - barHeight : zero;
        return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1, slot * 0.8).toFixed(1)}" height="${barHeight.toFixed(1)}" class="${row[1] >= 0 ? "ad-bar-up" : "ad-bar-down"}"><title>${escapeHtml(row[0])}: ${escapeHtml(formatNumber(row[1]))}</title></rect>`;
    }).join("");
    return `<div class="ad-daily-chart"><strong>日次 advance − decline</strong>
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="直近の日次値上がり銘柄数から値下がり銘柄数を引いた棒グラフ">
            <line x1="${pad}" y1="${zero}" x2="${width - pad}" y2="${zero}" class="ad-zero"/>${bars}
        </svg>
        <div class="ad-chart-dates"><span>${escapeHtml(rows[0][0])}</span><span>${escapeHtml(rows[rows.length - 1][0])}</span></div>
    </div>`;
}

function buildAdDetails(ind) {
    if (!ind.breadth) return "";
    const b = ind.breadth;
    const latest = b.advance_pct == null ? "—" : `${formatNumber(b.advance_pct)}%`;
    const average = b.average_pct == null ? "—" : `${formatNumber(b.average_pct)}%`;
    const totalRatio = b.whole_universe_pct == null ? "算出不可 (unch/総数が不明)" : `${formatNumber(b.whole_universe_pct)}%`;
    return `<div class="ad-breadth">
        <p class="ad-absolute-note">A/Dラインの絶対値には意味がありません。傾きと指数との乖離を見ます。</p>
        <div><span>上昇比率 (値上がり+値下がり中)</span><strong>${escapeHtml(latest)}</strong></div>
        <div><span>直近${escapeHtml(String(b.average_window))}日平均 (値動き中)</span><strong>${escapeHtml(average)}</strong></div>
        <div><span>全銘柄ベース上昇比率</span><strong>${escapeHtml(totalRatio)}</strong></div>
        <p>${escapeHtml(b.reading)} 目安: 50%前後は拮抗、70%以上は強い、30%以下は弱い。</p>
    </div>
    ${buildAdComparison(ind.comparison)}
    ${buildAdDailyBars(ind.daily_net)}`;
}

const MIN_HISTORY_POINTS = 30;

function renderIndicatorCard(ind, localMode) {
    const status = ind.status in MACRO_STATUS_LABELS ? ind.status : "unavailable";
    let body;
    if ((status === "ok" || status === "stale") && ind.latest) {
        const s = ind.stats || {};
        const short = Number(s.count) < MIN_HISTORY_POINTS;
        const adLine = ind.id === "ad_line" || ind.id.startsWith("ad_line_");
        body = `
            <div class="macro-value">${escapeHtml(formatValue(ind.latest.value, ind.unit))}</div>
            <div class="macro-asof">最新観測日: ${escapeHtml(ind.latest.date)} ／ ${escapeHtml(ind.frequency)}</div>
            ${status === "stale" ? `<div class="macro-unavailable">${escapeHtml(ind.reason)}</div>` : ""}
            <div class="macro-spark">${buildSparkline(ind.history)}</div>
            ${short || adLine ? "" : buildRangeBar(s, ind.latest.value)}
            ${adLine
                ? `<div class="macro-stats">蓄積${escapeHtml(String(s.count))}日（${escapeHtml(s.start)}〜）。累積値の歴史的位置ではなく傾きと指数との乖離を確認してください。</div>`
                : short
                ? `<div class="macro-stats">蓄積${escapeHtml(String(s.count))}日（${escapeHtml(s.start)}〜）: 観測日数が少ないため歴史的位置は表示しません。</div>`
                : `<div class="macro-stats">歴史的位置: <strong>${escapeHtml(percentileLabel(s.percentile))}</strong>
                （${escapeHtml(s.start)}〜 / 中央値 ${escapeHtml(formatNumber(s.median))}）</div>`}`;
    } else {
        body = `
            <div class="macro-unavailable">${escapeHtml(ind.reason || "データがありません。")}</div>
            <div class="macro-asof">更新頻度: ${escapeHtml(ind.frequency)}</div>`;
    }
    const formula = ind.formula ? `<p><strong>算式:</strong> ${escapeHtml(ind.formula)}</p>` : "";
    const adDetails = localMode && (ind.id === "ad_line" || ind.id.startsWith("ad_line_")) &&
        (status === "ok" || status === "stale")
        ? buildAdDetails(ind) : "";
    return `
        <article class="macro-card macro-${status}" data-indicator="${escapeHtml(ind.id)}">
            <div class="macro-card-head">
                <h3>${escapeHtml(ind.name)}</h3>
                <span class="macro-status status-${status}">${MACRO_STATUS_LABELS[status]}</span>
            </div>
            ${body}
            ${adDetails}
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

function renderInsightBlock(title, entry, meta) {
    const head = `<summary>${escapeHtml(title)}</summary>`;
    if (!entry || entry.status !== "ok" || !entry.text) {
        const reason = entry && entry.reason ? `（${escapeHtml(entry.reason)}）` : "";
        return `<details class="macro-insight macro-insight-empty">${head}` +
            `<p class="macro-insight-text">未生成${reason}</p></details>`;
    }
    const stamp = entry.generated_at || (meta && meta.generated_at) || "不明";
    const model = entry.model || (meta && meta.model) || "不明";
    return `<details class="macro-insight">${head}` +
        `<p class="macro-insight-text">${escapeHtml(entry.text)}</p>` +
        `<p class="macro-insight-meta">生成: ${escapeHtml(stamp)} ／ モデル: ${escapeHtml(model)} ／ ` +
        `${escapeHtml((meta && meta.disclaimer) || "AI生成・投資助言ではありません。")}</p></details>`;
}

function renderMacroHtml(data, insights) {
    const indicators = (data && data.indicators) || [];
    if (indicators.length === 0) {
        return `<p class="macro-message">表示できる指標がありません。</p>`;
    }
    const groups = (data.groups && data.groups.length) ? data.groups : [{ id: "all", name: "指標" }];
    const known = new Set(groups.map(g => g.id));
    const sections = groups.map(g => {
        const items = indicators.filter(i => i.group === g.id || (g.id === "all" && !known.has(i.group)));
        if (items.length === 0) return "";
        const insight = renderInsightBlock(`AIアナリスト分析: ${g.name}`,
            insights && insights.categories && insights.categories[g.id], insights);
        return `<section class="macro-group"><h3 class="macro-group-title">${escapeHtml(g.name)}</h3>` + insight +
            `<div class="macro-grid">${items.map(item => renderIndicatorCard(item, Boolean(data.local_only))).join("")}</div></section>`;
    }).join("");
    const ok = indicators.filter(i => i.status === "ok").length;
    const summary = `<p class="macro-summary">取得済み ${ok} / ${indicators.length} 指標` +
        `（生成: ${escapeHtml(data.generated_at || "不明")}）。未接続・取得失敗の指標は値を表示していません。総合スコアは算出していません。</p>`;
    const overview = renderInsightBlock("AIアナリスト 全体俯瞰", insights && insights.summary, insights);
    return summary + overview + sections;
}

async function loadInsightsData(localOnly, fetchImpl = fetch) {
    try {
        const name = localOnly ? "insights.local.json" : "insights.json";
        const response = await fetchImpl(name + "?t=" + Date.now(), { cache: "no-store" });
        return response && response.ok ? await response.json() : null;
    } catch (_) {
        return null;
    }
}

let macroLoaded = false;

async function loadMacro(force = false) {
    const el = document.getElementById("macroContent");
    if (!el || (macroLoaded && !force)) return;
    el.innerHTML = `<p class="macro-message">指標データを読み込み中...</p>`;
    try {
        const data = await loadMacroData();
        const insights = await loadInsightsData(Boolean(data.local_only));
        el.innerHTML = renderMacroHtml(data, insights);
        if (data.local_only) {
            el.insertAdjacentHTML("afterbegin", `<p class="macro-local-notice">ローカル版: 再配布制限のあるデータを含みます。このファイルや画面を公開・共有しないでください。</p>`);
        }
        macroLoaded = true;
    } catch (error) {
        console.error("Failed to load macro data:", error);
        el.innerHTML = `<p class="macro-message macro-error">指標データを読み込めませんでした。` +
            `<button class="reset-ai-btn" id="macroRetryBtn">再読み込み</button></p>`;
        const retry = document.getElementById("macroRetryBtn");
        if (retry) retry.addEventListener("click", () => loadMacro(true));
    }
}

async function loadMacroData(fetchImpl = fetch) {
    let localResponse;
    try {
        localResponse = await fetchImpl("macro.local.json?t=" + Date.now(), { cache: "no-store" });
    } catch (_) {
        localResponse = null;
    }
    if (localResponse && localResponse.ok) {
        const localData = await localResponse.json();
        localData.local_only = true;
        return localData;
    }

    const publicResponse = await fetchImpl("macro.json?t=" + Date.now(), { cache: "no-store" });
    if (!publicResponse.ok) throw new Error("HTTP " + publicResponse.status);
    return publicResponse.json();
}

if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", () => loadMacro());
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { escapeHtml, safeUrl, formatValue, formatNumber, percentileLabel,
        buildSparkline, buildRangeBar, renderIndicatorCard, renderMacroHtml, loadMacroData,
        renderInsightBlock, loadInsightsData };
}
