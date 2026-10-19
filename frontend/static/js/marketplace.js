// 🌾 Dynamic Premium Marketplace Search & Filtering Engine

// Define searchCrop as a fallback for any inline keyup event triggers to prevent ReferenceErrors
window.searchCrop = function() {
    const form = document.getElementById("filterForm");
    if (form) {
        // Form is handled by input listeners, but we keep this as a safe no-op
    }
};

document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("filterForm");
    if (!form) return;

    // 1. Dropdown filter change events -> submit form to execute database-level query
    ["categoryFilter", "gradeFilter", "trustFilter"].forEach(id => {
        const selectEl = document.getElementById(id);
        if (selectEl) {
            selectEl.addEventListener("change", () => {
                form.submit();
            });
        }
    });

    // 2. Search input event with a 400ms debounce to prevent spamming the database
    const searchInput = document.getElementById("searchInput");
    if (searchInput) {
        let debounceTimeout;
        searchInput.addEventListener("input", () => {
            clearTimeout(debounceTimeout);
            debounceTimeout = setTimeout(() => {
                form.submit();
            }, 400);
        });
        
        // Also support pressing Enter key
        searchInput.addEventListener("keypress", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                form.submit();
            }
        });
        
        // Keep focus and put cursor at the end of the text on reload
        if (searchInput.value) {
            const val = searchInput.value;
            searchInput.focus();
            searchInput.value = "";
            searchInput.value = val;
        }
    }
});