(() => {
    const loader = {};
    let cached;

    function stringifyId(raw) {
        if (raw && typeof raw === "object") {
            if ("id" in raw) return String(raw.id);
            if ("doc" in raw) return String(raw.doc);
        }
        return String(raw);
    }

    function normalizeDoc(doc) {
        const id = stringifyId(doc?.id ?? doc);
        const tags = Array.isArray(doc?.tags) ? doc.tags : [];
        const category_path = doc?.category_path || doc?.category || "";
        return {
            ...doc,
            id,
            tags,
            tags_text: tags.join(" "),
            category: category_path,
            category_path,
            category_name: doc?.category_name || "",
        };
    }

    async function fetchJson(path) {
        const res = await fetch(path);
        if (!res.ok) {
            throw new Error(`加载失败: ${path}`);
        }
        return res.json();
    }

    async function loadDocuments() {
        if (cached) return cached;
        cached = (async () => {
            const manifest = await fetchJson("/index/manifest.json");
            const documents = [];
            const docMap = new Map();
            for (const shard of manifest.shards || []) {
                const data = await fetchJson(`/index/${shard.file}`);
                for (const doc of data.items || []) {
                    const normalized = normalizeDoc(doc);
                    documents.push(normalized);
                    docMap.set(normalized.id, normalized);
                }
            }
            return { documents, docMap, manifest };
        })();
        return cached;
    }

    function buildFlexIndex(documents) {
        if (!globalThis.FlexSearch || !globalThis.FlexSearch.Document) return null;
        const index = new FlexSearch.Document({
            cache: true,
            tokenize: "forward",
            document: {
                id: "id",
                index: ["title", "summary", "category_name", "tags_text"],
                store: true,
            },
        });
        for (const doc of documents) {
            index.add(doc);
        }
        return index;
    }

    function collectDocsFromHits(hits, docMap) {
        const ids = new Set();
        const docs = [];
        for (const group of hits || []) {
            for (const res of group.result || []) {
                const key = stringifyId(res.doc);
                if (ids.has(key)) continue;
                ids.add(key);
                const doc = docMap.get(key);
                if (doc) docs.push(doc);
            }
        }
        return docs;
    }

    async function loadTaxonomy() {
        const [tags, categories] = await Promise.all([
            fetchJson("/index/tags.json").catch(() => null),
            fetchJson("/index/categories.json").catch(() => null),
        ]);
        return { tags, categories };
    }

    loader.loadDocuments = loadDocuments;
    loader.buildFlexIndex = buildFlexIndex;
    loader.collectDocsFromHits = collectDocsFromHits;
    loader.stringifyId = stringifyId;
    loader.loadTaxonomy = loadTaxonomy;

    globalThis.GhostIndexLoader = loader;
})();
