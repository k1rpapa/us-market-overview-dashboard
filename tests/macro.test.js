const test = require("node:test");
const assert = require("node:assert");
const m = require("../macro.js");

const okInd = {
    id: "hy_oas", group: "credit", name: "HY <OAS>", status: "ok", unit: "%", frequency: "日次",
    definition: "d", reading: "r", caution: "c", source: "FRED", source_url: "https://fred.stlouisfed.org/",
    latest: { date: "2026-10-01", value: 3.24 },
    stats: { min: 2, max: 20, median: 4, percentile: 20, start: "1996-12-31" },
    history: [["a", 1], ["b", 3], ["c", 2]]
};
const pending = { id: "cape", group: "valuation", name: "CAPE", status: "pending", reason: "未接続です", frequency: "月次",
    definition: "d", reading: "r", caution: "c", source: "Shiller", source_url: "javascript:alert(1)" };

test("formatValue handles units and invalid numbers", () => {
    assert.strictEqual(m.formatValue(3.24, "%"), "3.24%");
    assert.strictEqual(m.formatValue(96.16, "$/bbl"), "96.16 $/bbl");
    assert.strictEqual(m.formatValue(null, "%"), "—");
});

test("percentileLabel", () => {
    assert.strictEqual(m.percentileLabel(20), "下位 20%");
    assert.strictEqual(m.percentileLabel(95), "上位 5%");
});

test("buildSparkline needs two points", () => {
    assert.strictEqual(m.buildSparkline([["a", 1]]), "");
    assert.match(m.buildSparkline(okInd.history), /<polyline/);
});

test("ok card shows value, date and escapes HTML", () => {
    const html = m.renderIndicatorCard(okInd);
    assert.match(html, /3\.24%/);
    assert.match(html, /2026-10-01/);
    assert.match(html, /HY &lt;OAS&gt;/);
});

test("pending card shows reason, no value, and unsafe URL neutralised", () => {
    const html = m.renderIndicatorCard(pending);
    assert.match(html, /未接続です/);
    assert.doesNotMatch(html, /macro-value/);
    assert.doesNotMatch(html, /javascript:/);
});

test("stale card preserves its last observed value and warns users", () => {
    const html = m.renderIndicatorCard({
        ...okInd, status: "stale", reason: "最終観測が古いです。", latest: { date: "2017-06-30", value: 8.11 }
    });
    assert.match(html, /8\.11%/);
    assert.match(html, /2017-06-30/);
    assert.match(html, /最終観測が古いです/);
    assert.match(html, /最終観測が古い/);
});

test("short accumulated history shows day count instead of historical position", () => {
    const short = m.renderIndicatorCard({ ...okInd, stats: { ...okInd.stats, count: 3, start: "2026-10-01" } });
    assert.match(short, /蓄積3日/);
    assert.doesNotMatch(short, /歴史的位置:/);
    assert.match(m.renderIndicatorCard({ ...okInd, stats: { ...okInd.stats, count: 400 } }), /歴史的位置:/);
});

test("renderMacroHtml empty state, grouping and no composite score", () => {
    assert.match(m.renderMacroHtml({ indicators: [] }), /表示できる指標がありません/);
    const html = m.renderMacroHtml({ generated_at: "T", groups: [{ id: "credit", name: "信用" }, { id: "valuation", name: "割高感" }], indicators: [okInd, pending] });
    assert.match(html, /取得済み 1 \/ 2/);
    assert.match(html, /信用/);
    assert.match(html, /総合スコアは算出していません/);
});

test("prefers local JSON and falls back to public JSON", async () => {
    const calls = [];
    const local = await m.loadMacroData(async url => {
        calls.push(url);
        return { ok: true, json: async () => ({ indicators: [] }) };
    });
    assert.strictEqual(local.local_only, true);
    assert.match(calls[0], /^macro\.local\.json/);
    assert.strictEqual(calls.length, 1);

    calls.length = 0;
    const publicData = await m.loadMacroData(async url => {
        calls.push(url);
        return url.startsWith("macro.local.json")
            ? { ok: false, status: 404 }
            : { ok: true, json: async () => ({ indicators: [] }) };
    });
    assert.strictEqual(publicData.local_only, undefined);
    assert.match(calls[1], /^macro\.json/);
});

test("renderInsightBlock shows text, model, disclaimer and escapes", () => {
    const html = m.renderInsightBlock("T", { status: "ok", text: "<b>x</b>", model: "m1", generated_at: "2026-01-01T00:00:00Z" }, { disclaimer: "AI生成" });
    assert.ok(html.includes("&lt;b&gt;"));
    assert.ok(html.includes("m1") && html.includes("AI生成"));
});

test("renderInsightBlock falls back to 未生成", () => {
    assert.ok(m.renderInsightBlock("T", null, null).includes("未生成"));
    assert.ok(m.renderInsightBlock("T", { status: "unavailable", reason: "キー未設定" }, {}).includes("キー未設定"));
});

test("loadInsightsData returns null on failure and picks local file", async () => {
    assert.equal(await m.loadInsightsData(false, async () => { throw new Error("x"); }), null);
    let url = "";
    await m.loadInsightsData(true, async (u) => { url = u; return { ok: false }; });
    assert.ok(url.startsWith("insights.local.json"));
});