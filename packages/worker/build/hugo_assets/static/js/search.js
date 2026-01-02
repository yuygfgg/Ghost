(() => {
    const loader = globalThis.GhostIndexLoader;
    if (!loader) return;
    const input = () => document.getElementById("search-input");
    const resultContainer = () => document.getElementById("search-results");
    const meta = () => document.getElementById("search-meta");
    let index;
    let documents = [];
    let docMap = new Map();
    let initialHtml = null;
    let initialMeta = "";

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function rowHtml(item) {
        const published = item.published_at || "";
        const publisher = escapeHtml(item.publisher || "");
        const title = escapeHtml(item.title || "");
        const url = item.url || "#";
        const magnet = item.magnet_uri || "";
        const dhtStatus = item.dht_status || "Unknown";
        const tags = Array.isArray(item.tags) ? item.tags.slice(0, 5) : [];
        const tagHtml = tags.length
            ? `<div class="resource-tags">${tags.map((t) => `<a class="tag" href="/tags/${encodeURIComponent(t)}/">${escapeHtml(t)}</a>`).join("")}</div>`
            : "";
        const dlHtml = magnet
            ? `<a class="btn-icon" href="${escapeHtml(magnet)}" title="Magnet Link">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              </a>`
            : "";

        let badgeClass = "badge-gray";
        if (dhtStatus === "Active") badgeClass = "badge-green";
        if (dhtStatus === "Stale") badgeClass = "badge-yellow";

        return `
          <tr>
            <td>
              <div class="meta-publisher">${publisher}</div>
              <div class="meta-date">
                <time class="relative-time" datetime="${published}">${escapeHtml(published ? published.slice(0, 10) : "")}</time>
              </div>
            </td>
            <td class="cell-title">
              <a class="resource-title" href="${url}">${title}</a>
              ${tagHtml}
            </td>
            <td style="text-align: center;">
                <span class="badge ${badgeClass}">${escapeHtml(dhtStatus)}</span>
            </td>
            <td style="text-align: center;">${dlHtml}</td>
          </tr>
        `;
    }

    function renderResults(items) {
        const container = resultContainer();
        container.innerHTML = "";
        if (!items.length) {
            container.innerHTML = "<tr><td class='empty' colspan='3'>尚未发现匹配资源</td></tr>";
            return;
        }
        container.innerHTML = items.slice(0, 50).map((item) => rowHtml(item)).join("");
        document.dispatchEvent(new CustomEvent("ghost:rendered"));
    }

    function onSearch(ev) {
        const term = ev.target.value.trim();
        if (!term) {
            if (initialHtml != null) resultContainer().innerHTML = initialHtml;
            meta().textContent = initialMeta || `已就绪，共 ${documents.length} 条记录`;
            document.dispatchEvent(new CustomEvent("ghost:rendered"));
            return;
        }
        if (!index) {
            meta().textContent = "正在构建搜索引擎...";
            return;
        }
        const hits = index.search(term, { enrich: true, limit: 50, index: ["title", "summary", "category_name", "tags_text"] });
        const docs = loader.collectDocsFromHits(hits, docMap);
        meta().textContent = `精准定位到 ${docs.length} 个匹配项`;
        renderResults(docs);
    }

    document.addEventListener("DOMContentLoaded", async () => {
        const el = input();
        if (!el) return;
        try {
            meta().textContent = "正在同步云端索引...";
            const loaded = await loader.loadDocuments();
            documents = loaded.documents;
            docMap = loaded.docMap;
            index = loader.buildFlexIndex(documents);
            if (!index) {
                meta().textContent = "本地计算单元未就绪";
                return;
            }
            initialHtml = resultContainer()?.innerHTML ?? "";
            const readyMeta = `已就绪，共 ${documents.length} 条记录`;
            initialMeta = readyMeta;
            meta().textContent = readyMeta;
        } catch (err) {
            console.error("[search] Initialization failed", err);
            meta().textContent = err.message || "索引加载异常";
            return;
        }
        el.addEventListener("input", onSearch);
    });
})();
