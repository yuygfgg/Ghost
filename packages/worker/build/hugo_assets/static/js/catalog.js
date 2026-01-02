(() => {
    const loader = globalThis.GhostIndexLoader;
    if (!loader) return;

    function parseTagsFromQuery() {
        const params = new URLSearchParams(window.location.search);
        const raw = params.get("tags");
        if (!raw) return [];
        return raw.split(",").map((s) => s.trim()).filter(Boolean);
    }

    function selectedCategoryFromQuery() {
        const params = new URLSearchParams(window.location.search);
        return params.get("category") || "";
    }

    function updateQueryParam(key, value) {
        const params = new URLSearchParams(window.location.search);
        if (value) {
            params.set(key, value);
        } else {
            params.delete(key);
        }
        const qs = params.toString();
        const suffix = qs ? `?${qs}` : "";
        history.replaceState({}, "", `${window.location.pathname}${suffix}`);
    }

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

    function encodeCategoryPath(path) {
        return encodeURIComponent(path || "").replaceAll("%2F", "/");
    }

    function initialTagsFromMeta() {
        const meta = document.querySelector('meta[name="ghost-initial-tags"]');
        if (!meta) return [];
        const raw = meta.getAttribute("content") || "";
        return raw.split(",").map((s) => s.trim()).filter(Boolean);
    }

    function initialCategoryFromMeta() {
        const meta = document.querySelector('meta[name="ghost-initial-category"]');
        return meta?.getAttribute("content") || "";
    }

    function sortDocs(docs) {
        return [...docs].sort((a, b) => new Date(b.published_at || 0) - new Date(a.published_at || 0));
    }

    function renderList(container, docs, metaEl) {
        const sorted = sortDocs(docs);
        if (metaEl) metaEl.textContent = `共发现 ${sorted.length} 个资源`;
        if (!sorted.length) {
            container.innerHTML = "<tr><td class='empty' colspan='3'>尚未发现匹配资源</td></tr>";
            return;
        }
        container.innerHTML = sorted.map((doc) => rowHtml(doc)).join("");
        document.dispatchEvent(new CustomEvent("ghost:rendered"));
    }

    function initTagsPage(documents, tagsData) {
        const tagCloud = document.getElementById("tag-cloud");
        const selectedWrap = document.getElementById("tag-selected");
        const meta = document.getElementById("tag-meta");
        const results = document.getElementById("tag-results");
        if (!tagCloud || !selectedWrap || !results) return;

        const counts = new Map();
        if (tagsData?.tags?.length) {
            for (const item of tagsData.tags) {
                counts.set(item.tag, item.count);
            }
        } else {
            for (const doc of documents) {
                for (const tag of doc.tags || []) {
                    counts.set(tag, (counts.get(tag) || 0) + 1);
                }
            }
        }
        const tags = Array.from(counts.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
        const fromQuery = parseTagsFromQuery();
        const fromMeta = initialTagsFromMeta();
        const selected = new Set(fromQuery.length ? fromQuery : fromMeta);

        function renderSelected() {
            selectedWrap.innerHTML = "";
            if (!selected.size) {
                selectedWrap.innerHTML = "<p class='meta'>未选择滤镜。点击标签云进行多维交叉筛选。</p>";
                return;
            }
            for (const tag of selected) {
                const span = document.createElement("span");
                span.className = "tag selected";
                span.style.cursor = "pointer";
                span.innerHTML = `${tag} <span class="remove" aria-label="移除">×</span>`;
                if (span.querySelector(".remove")) {
                    span.addEventListener("click", () => toggleTag(tag));
                }
                selectedWrap.appendChild(span);
            }
        }

        function renderCloud() {
            tagCloud.innerHTML = "";
            for (const [tag, count] of tags) {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = `tag${selected.has(tag) ? " selected" : ""}`;
                btn.style.cursor = "pointer";
                btn.style.border = "none";
                btn.style.fontFamily = "inherit";
                btn.textContent = `${tag} (${count})`;
                btn.addEventListener("click", () => toggleTag(tag));
                tagCloud.appendChild(btn);
            }
        }

        function filterDocs() {
            if (!selected.size) return documents;
            return documents.filter((doc) => {
                const tags = doc.tags || [];
                for (const tag of selected) {
                    if (!tags.includes(tag)) return false;
                }
                return true;
            });
        }

        function toggleTag(tag) {
            if (selected.has(tag)) {
                selected.delete(tag);
            } else {
                selected.add(tag);
            }
            updateQueryParam("tags", Array.from(selected).join(","));
            renderCloud();
            renderSelected();
            renderList(results, filterDocs(), meta);
        }

        renderCloud();
        renderSelected();
        renderList(results, filterDocs(), meta);
    }

    function initCategoriesPage(documents, categoryTree) {
        const treeRoot = document.getElementById("category-tree");
        const meta = document.getElementById("category-meta");
        const results = document.getElementById("category-results");
        if (!treeRoot || !results) return;

        let selected = selectedCategoryFromQuery() || initialCategoryFromMeta();

        function matchesCategory(doc, path) {
            const catPath = doc.category_path || doc.category || "";
            if (!path) return true;
            if (!catPath) return false;
            return catPath === path || catPath.startsWith(`${path}/`);
        }

        function renderActiveState() {
            treeRoot.querySelectorAll("a[data-category]").forEach((el) => {
                const path = el.getAttribute("data-category");
                el.classList.toggle("active", path === selected);
                if (path === selected) {
                    el.style.fontWeight = "700";
                    el.style.color = "var(--primary)";
                } else {
                    el.style.fontWeight = "500";
                    el.style.color = "var(--text-secondary)";
                }
            });
        }

        function renderTree(nodes) {
            const ul = document.createElement("ul");
            ul.style.listStyle = "none";
            ul.style.paddingLeft = "1.5rem";
            for (const node of nodes || []) {
                const li = document.createElement("li");
                const row = document.createElement("div");
                row.className = "category-node";
                const link = document.createElement("a");
                link.href = `/categories/${encodeCategoryPath(node.path)}/`;
                link.textContent = node.name;
                link.dataset.category = node.path;
                link.style.cursor = "pointer";
                link.addEventListener("click", (ev) => {
                    ev.preventDefault();
                    window.location.href = link.href;
                });
                const count = document.createElement("span");
                count.className = "count";
                count.textContent = node.count != null ? `(${node.count})` : "";
                row.appendChild(link);
                row.appendChild(count);
                li.appendChild(row);
                if (node.children?.length) {
                    li.appendChild(renderTree(node.children));
                }
                ul.appendChild(li);
            }
            return ul;
        }

        function selectCategory(path) {
            selected = path;
            updateQueryParam("category", selected);
            renderActiveState();
            renderList(
                results,
                documents.filter((doc) => matchesCategory(doc, selected)),
                meta,
            );
        }

        treeRoot.innerHTML = "";
        treeRoot.appendChild(renderTree(categoryTree?.categories || categoryTree || []));
        renderActiveState();
        selectCategory(selected);
    }

    document.addEventListener("DOMContentLoaded", async () => {
        const hasTagsPage = document.getElementById("tag-cloud");
        const hasCategoryPage = document.getElementById("category-tree");
        if (!hasTagsPage && !hasCategoryPage) return;
        let documents;
        let taxonomy;
        try {
            const loaded = await loader.loadDocuments();
            documents = loaded.documents;
            taxonomy = await loader.loadTaxonomy();
        } catch (err) {
            console.error("[catalog] Initialization failed", err);
            const meta = document.getElementById("tag-meta") || document.getElementById("category-meta");
            if (meta) meta.textContent = err.message || "索引加载异常";
            return;
        }
        if (hasTagsPage) {
            initTagsPage(documents, taxonomy?.tags || null);
        }
        if (hasCategoryPage) {
            initCategoriesPage(documents, taxonomy?.categories || []);
        }
    });
})();
