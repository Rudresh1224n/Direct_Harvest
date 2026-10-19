/**
 * DirectHarvest AI - Address Autocomplete & Detailed Breakdown Component
 * Features:
 * - Live Google Maps / OpenStreetMap Places Autocomplete suggestions as user types
 * - Enforces verified location selection to prevent non-existent addresses
 * - Detailed breakdown: House/Flat/Block, Apartment/Building, Street/Road, Landmark, City, State, Pincode
 * - Automatically keeps the primary combined `address` input synced for backend compatibility
 */

(function (window) {
    function setupDetailedAddress(options) {
        const houseInput = document.getElementById(options.houseId);
        const apartmentInput = document.getElementById(options.apartmentId);
        const streetInput = document.getElementById(options.streetId);
        const landmarkInput = document.getElementById(options.landmarkId);
        const cityInput = document.getElementById(options.cityId);
        const stateInput = document.getElementById(options.stateId);
        const pincodeInput = document.getElementById(options.pincodeId);
        const combinedInput = document.getElementById(options.combinedId) || document.querySelector(`[name="${options.combinedName || 'address'}"]`);
        const dropdown = document.getElementById(options.dropdownId);

        let activeSuggestionIndex = -1;
        let currentSuggestions = [];
        let debounceTimer = null;

        if (!streetInput || !dropdown) {
            console.warn("Address autocomplete: streetInput or dropdown not found.");
            return;
        }

        // Assemble combined address string whenever any field changes
        function syncCombinedAddress() {
            if (!combinedInput) return;

            const parts = [];
            const house = houseInput ? houseInput.value.trim() : "";
            const apt = apartmentInput ? apartmentInput.value.trim() : "";
            const street = streetInput ? streetInput.value.trim() : "";
            const landmark = landmarkInput ? landmarkInput.value.trim() : "";
            const city = cityInput ? cityInput.value.trim() : "";
            const state = stateInput ? stateInput.value.trim() : "";
            const pincode = pincodeInput ? pincodeInput.value.trim() : "";

            if (house) parts.push(house);
            if (apt) parts.push(apt);
            if (street) parts.push(street);
            if (landmark) parts.push(`Near ${landmark.replace(/^near\s+/i, '')}`);
            if (city) parts.push(city);
            if (state) parts.push(state);

            let assembled = parts.join(", ");
            if (pincode) {
                assembled += (assembled ? ` - ${pincode}` : pincode);
            }

            combinedInput.value = assembled;
        }

        // Listen for input on all subfields
        [houseInput, apartmentInput, streetInput, landmarkInput, cityInput, stateInput, pincodeInput].forEach(inp => {
            if (inp) {
                inp.addEventListener('input', syncCombinedAddress);
                inp.addEventListener('change', syncCombinedAddress);
            }
        });

        // Autocomplete API Fetch
        async function fetchSuggestions(query) {
            if (!query || query.length < 2) {
                dropdown.style.display = 'none';
                dropdown.innerHTML = '';
                currentSuggestions = [];
                return;
            }

            try {
                const res = await fetch(`/api/places/autocomplete?q=${encodeURIComponent(query)}&limit=8`);
                const data = await res.json();
                if (data.success && data.suggestions && data.suggestions.length > 0) {
                    currentSuggestions = data.suggestions;
                    renderDropdown(currentSuggestions, query);
                } else {
                    dropdown.style.display = 'none';
                    dropdown.innerHTML = '';
                    currentSuggestions = [];
                }
            } catch (err) {
                console.error("Autocomplete fetch error:", err);
            }
        }

        // Render Autocomplete Dropdown
        function renderDropdown(suggestions, query) {
            dropdown.innerHTML = '';
            activeSuggestionIndex = -1;

            suggestions.forEach((item, index) => {
                const itemEl = document.createElement('div');
                itemEl.className = 'autocomplete-item';
                itemEl.setAttribute('data-index', index);

                // Highlight matched query letters
                const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
                const primaryHighlighted = item.street.replace(regex, '<strong>$1</strong>');
                const secondaryFormatted = item.formatted || `${item.area}, ${item.city}, ${item.state}`;

                itemEl.innerHTML = `
                    <div class="autocomplete-icon">
                        <i class="fa fa-map-marker-alt"></i>
                    </div>
                    <div class="autocomplete-text">
                        <div class="autocomplete-primary">
                            ${primaryHighlighted}
                            <span class="autocomplete-badge-verified"><i class="fa fa-check-circle me-1"></i>Verified Map Place</span>
                        </div>
                        <div class="autocomplete-secondary">${secondaryFormatted}</div>
                    </div>
                `;

                itemEl.addEventListener('mousedown', function (e) {
                    e.preventDefault(); // prevent blur
                    selectSuggestion(item);
                });

                dropdown.appendChild(itemEl);
            });

            // Footer note
            const footer = document.createElement('div');
            footer.className = 'autocomplete-footer';
            footer.innerHTML = '<i class="fa fa-shield-alt text-success me-1"></i> Powered by Google Maps & Verified OpenStreetMap Data';
            dropdown.appendChild(footer);

            dropdown.style.display = 'block';
        }

        // Apply selected suggestion
        function selectSuggestion(item) {
            streetInput.value = item.street || item.formatted;
            if (apartmentInput && (!apartmentInput.value.trim() || apartmentInput.value === item.area)) {
                apartmentInput.value = item.area || "";
            }
            if (cityInput && item.city) {
                cityInput.value = item.city;
            }
            if (stateInput && item.state) {
                stateInput.value = item.state;
            }
            if (pincodeInput && item.pincode) {
                pincodeInput.value = item.pincode;
            }

            dropdown.style.display = 'none';
            dropdown.innerHTML = '';
            currentSuggestions = [];
            syncCombinedAddress();

            // Focus on house/flat number if empty
            if (houseInput && !houseInput.value.trim()) {
                houseInput.focus();
            }
        }

        // Street Input Event Listeners
        streetInput.addEventListener('input', function () {
            clearTimeout(debounceTimer);
            const val = this.value.trim();
            debounceTimer = setTimeout(() => {
                fetchSuggestions(val);
            }, 250);
        });

        streetInput.addEventListener('keydown', function (e) {
            if (dropdown.style.display !== 'block' || currentSuggestions.length === 0) return;

            const items = dropdown.querySelectorAll('.autocomplete-item');

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                activeSuggestionIndex = (activeSuggestionIndex + 1) % items.length;
                updateActiveItem(items);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                activeSuggestionIndex = (activeSuggestionIndex - 1 + items.length) % items.length;
                updateActiveItem(items);
            } else if (e.key === 'Enter') {
                if (activeSuggestionIndex >= 0 && activeSuggestionIndex < currentSuggestions.length) {
                    e.preventDefault();
                    selectSuggestion(currentSuggestions[activeSuggestionIndex]);
                }
            } else if (e.key === 'Escape') {
                dropdown.style.display = 'none';
            }
        });

        function updateActiveItem(items) {
            items.forEach((it, idx) => {
                if (idx === activeSuggestionIndex) {
                    it.classList.add('active');
                    it.scrollIntoView({ block: 'nearest' });
                } else {
                    it.classList.remove('active');
                }
            });
        }

        // Close dropdown when clicking outside
        document.addEventListener('click', function (e) {
            if (!streetInput.contains(e.target) && !dropdown.contains(e.target)) {
                dropdown.style.display = 'none';
            }
        });

        // Initialize from existing combined value if subfields are empty
        if (combinedInput && combinedInput.value.trim() && streetInput && !streetInput.value.trim()) {
            const raw = combinedInput.value.trim();
            const segments = raw.split(',').map(s => s.trim());
            if (segments.length >= 3) {
                if (houseInput) houseInput.value = segments[0] || "";
                if (apartmentInput) apartmentInput.value = segments[1] || "";
                streetInput.value = segments[2] || "";
                if (cityInput && segments.length >= 4) cityInput.value = segments[segments.length - 2] || "";
                if (stateInput && segments.length >= 5) stateInput.value = segments[segments.length - 1] || "";
            } else {
                streetInput.value = raw;
            }
        }

        syncCombinedAddress();
    }

    window.setupDetailedAddress = setupDetailedAddress;
})(window);
