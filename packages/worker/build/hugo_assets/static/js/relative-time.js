(() => {
    const formatter = new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" });

    function formatRelative(targetDate) {
        const diffMs = targetDate.getTime() - Date.now();
        const absMs = Math.abs(diffMs);
        const minute = 60 * 1000;
        const hour = 60 * minute;
        const day = 24 * hour;
        const week = 7 * day;
        const month = 30 * day;
        const year = 365 * day;

        const to = (value, unit) => formatter.format(Math.round(value), unit);

        if (absMs < minute) return to(diffMs / 1000, "second");
        if (absMs < hour) return to(diffMs / minute, "minute");
        if (absMs < day) return to(diffMs / hour, "hour");
        if (absMs < week) return to(diffMs / day, "day");
        if (absMs < month) return to(diffMs / week, "week");
        if (absMs < year) return to(diffMs / month, "month");
        return to(diffMs / year, "year");
    }

    function updateAll() {
        const nodes = document.querySelectorAll("time.relative-time[datetime]");
        for (const node of nodes) {
            const raw = node.getAttribute("datetime") || "";
            const parsed = new Date(raw);
            if (!Number.isFinite(parsed.getTime())) continue;
            node.textContent = formatRelative(parsed);
        }
    }

    document.addEventListener("DOMContentLoaded", updateAll);
    document.addEventListener("ghost:rendered", updateAll);
})();
