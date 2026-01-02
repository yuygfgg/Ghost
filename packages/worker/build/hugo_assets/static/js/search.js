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
        const tags = Array.isArray(item.tags) ? item.tags.slice(0, 3) : [];
        const tagHtml = tags.length
            ? `<div class="title-tags">${tags.map((t) => `<a class="tag" href="/tags/${encodeURIComponent(t)}/">${escapeHtml(t)}</a>`).join("")}</div>`
            : "";
        const dlHtml = magnet
            ? `<a class="dl-link" href="${escapeHtml(magnet)}" title="打开 Magnet">
                <svg class="dl-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path fill="currentColor" d="M12 3a1 1 0 0 1 1 1v9.59l2.3-2.3a1 1 0 1 1 1.4 1.42l-4.01 4a1 1 0 0 1-1.38 0l-4.01-4a1 1 0 0 1 1.4-1.42L11 13.59V4a1 1 0 0 1 1-1Zm-7 16a1 1 0 0 1 1-1h12a1 1 0 1 1 0 2H6a1 1 0 0 1-1-1Z"/>
                </svg>
              </a>`
            : "";
        return `
          <tr>
            <td class="publisher">
              <div class="publisher-name">${publisher}</div>
              <div class="publisher-time">
                <time class="relative-time" datetime="${published}">${escapeHtml(published ? published.slice(0, 10) : "")}</time>
              </div>
            </td>
            <td class="title-cell">
              <a class="title-link" href="${url}">${title}</a>
              ${tagHtml}
            </td>
            <td class="dl">${dlHtml}</td>
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
