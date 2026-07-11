/**
 * Shared meal preference configuration UI and state.
 * Saved on preprocessing templates; badge designer uses it for preview only.
 */
const MealPreferenceConfig = (function () {
    const BADGE_PREFS_CACHE_KEY = 'badgeGenerator_preferences';

    let mappings = {};
    let sources = {};
    let cachedMealOptions = null;
    let onChangeCallback = null;

    function escapeXml(text) {
        if (text == null) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function loadCachedMealOptions() {
        try {
            const raw = localStorage.getItem(BADGE_PREFS_CACHE_KEY);
            if (!raw) return null;
            const prefs = JSON.parse(raw);
            return prefs.mealOptions || null;
        } catch (error) {
            console.error('Error loading cached meal options:', error);
            return null;
        }
    }

    function getCampaignIdFromPreferences() {
        try {
            const raw = localStorage.getItem(BADGE_PREFS_CACHE_KEY);
            if (!raw) return '';
            const prefs = JSON.parse(raw);
            return prefs.campaignId || '';
        } catch (error) {
            return '';
        }
    }

    function getPreprocessingTemplateIdFromPreferences() {
        try {
            const raw = localStorage.getItem(BADGE_PREFS_CACHE_KEY);
            if (!raw) return '';
            const prefs = JSON.parse(raw);
            return prefs.preprocessingTemplateId || '';
        } catch (error) {
            return '';
        }
    }

    async function fetchMealOptions(campaignId) {
        if (!campaignId) {
            cachedMealOptions = null;
            renderSection();
            return null;
        }
        try {
            const response = await fetch(
                `/api/badges/meal-options?campaign_id=${encodeURIComponent(campaignId)}`
            );
            if (!response.ok) {
                throw new Error(await response.text());
            }
            const data = await response.json();
            cachedMealOptions = data;
            const prefsRaw = localStorage.getItem(BADGE_PREFS_CACHE_KEY);
            const prefs = prefsRaw ? JSON.parse(prefsRaw) : {};
            prefs.mealOptions = data;
            localStorage.setItem(BADGE_PREFS_CACHE_KEY, JSON.stringify(prefs));
            renderSection();
            return data;
        } catch (error) {
            console.error('Failed to load meal options:', error);
            cachedMealOptions = loadCachedMealOptions();
            renderSection();
            return cachedMealOptions;
        }
    }

    function getMealPreferenceMappings() {
        const inputs = document.querySelectorAll('[data-meal-option]');
        if (!inputs.length) {
            return { ...mappings };
        }
        const result = {};
        inputs.forEach(input => {
            const raw = input.dataset.mealOption;
            const label = input.value;
            if (raw && label !== undefined) {
                result[raw] = label;
            }
        });
        return result;
    }

    function getMealPreferenceSources() {
        const inputs = document.querySelectorAll('[data-meal-source-column]');
        const result = { ...sources };
        if (!inputs.length) {
            return result;
        }
        inputs.forEach(input => {
            const column = input.dataset.mealSourceColumn;
            if (!column) return;
            result[column] = {
                ...(result[column] || {}),
                enabled: input.checked,
                column,
            };
        });
        return result;
    }

    function mergeMealSourceDefaults(questions, savedSources = {}) {
        const merged = {};
        (questions || []).forEach((q, index) => {
            const column = q.column || `${q.campaign_name} ~ ${q.question}`;
            const defaults = {
                enabled: q.default_enabled !== undefined ? q.default_enabled : !!q.is_banquet,
                is_banquet: !!q.is_banquet,
                order: q.order !== undefined ? q.order : index,
                campaign_name: q.campaign_name,
                question: q.question,
                column,
            };
            merged[column] = { ...defaults, ...(savedSources[column] || {}) };
        });
        return merged;
    }

    function mapMealValue(raw, mappingTable) {
        if (!raw) return '';
        const key = String(raw).trim();
        if (!key) return '';
        if (mappingTable && Object.prototype.hasOwnProperty.call(mappingTable, key)) {
            return mappingTable[key] ?? '';
        }
        return key;
    }

    function buildPreviewValue(sampleValues = {}) {
        const sourceConfig = getMealPreferenceSources();
        const mappingTable = getMealPreferenceMappings();
        const ordered = Object.entries(sourceConfig)
            .filter(([, cfg]) => cfg.enabled)
            .sort((a, b) => {
                const aBanquet = a[1].is_banquet ? 1 : 0;
                const bBanquet = b[1].is_banquet ? 1 : 0;
                if (aBanquet !== bBanquet) return aBanquet - bBanquet;
                return (a[1].order || 0) - (b[1].order || 0);
            });

        const nonBanquetParts = [];
        let banquetPart = '';
        ordered.forEach(([column, cfg]) => {
            const eventName = column.split(' ~ ')[0];
            const sampleEventValue = sampleValues[`{{SUBEVENT_SAMPLE_${eventName}}}`];
            const registered = sampleEventValue || (cfg.is_banquet ? 'Grand Banquet' : eventName);
            if (!registered) return;

            let raw = '';
            if (cfg.is_banquet) {
                raw = sampleValues['{{MEAL_PREFERENCE}}'] === 'Vegetarian' ? 'Yes' : 'No';
            } else if (column.includes('vegetarian')) {
                raw = 'Yes';
            }

            const mapped = mapMealValue(raw, mappingTable);
            if (!mapped) return;
            if (cfg.is_banquet) {
                if (!banquetPart) banquetPart = mapped;
            } else {
                nonBanquetParts.push(mapped);
            }
        });

        if (nonBanquetParts.length || banquetPart) {
            return [...nonBanquetParts, banquetPart].filter(Boolean).join(' ');
        }
        const fallback = sampleValues['{{MEAL_PREFERENCE}}'];
        return mapMealValue(
            fallback === 'Vegetarian' ? 'Yes' : fallback,
            mappingTable
        );
    }

    function renderSection() {
        const card = document.getElementById('mealPreferenceCard');
        const container = document.getElementById('mealPreferenceMappings');
        const summary = document.getElementById('mealQuestionsSummary');
        if (!card || !container) return;

        const data = cachedMealOptions || loadCachedMealOptions();
        if (!data || !data.has_meal_questions || !data.options?.length) {
            card.style.display = 'none';
            container.innerHTML = '';
            if (summary) summary.innerHTML = '';
            return;
        }

        card.style.display = 'block';
        const questions = data.questions || [];
        sources = mergeMealSourceDefaults(questions, sources);

        if (summary) {
            summary.innerHTML = questions.map(q => {
                const column = q.column || `${q.campaign_name} ~ ${q.question}`;
                const cfg = sources[column] || {};
                const checked = cfg.enabled ? 'checked' : '';
                const tag = q.is_banquet
                    ? '<span class="meal-source-tag">Banquet</span>'
                    : '<span class="meal-source-tag" style="background:#eef2ff;color:#3b4f9a;">Event</span>';
                return `
                    <div class="meal-source-row">
                        <label class="meal-source-toggle">
                            <input type="checkbox"
                                   data-meal-source-column="${escapeXml(column)}"
                                   ${checked}>
                            On badge
                        </label>
                        <div class="meal-source-label">
                            <strong>${escapeXml(q.campaign_name)}</strong>:
                            ${escapeXml(q.question)}
                            ${tag}
                        </div>
                    </div>
                `;
            }).join('');
            summary.querySelectorAll('[data-meal-source-column]').forEach(input => {
                input.addEventListener('change', () => {
                    sources = getMealPreferenceSources();
                    mappings = getMealPreferenceMappings();
                    if (onChangeCallback) onChangeCallback();
                });
            });
        }

        let html = '';
        data.options.forEach(option => {
            const saved = mappings[option] ?? '';
            html += `
                <div class="meal-mapping-row">
                    <div class="meal-option-source" title="CRM response">${escapeXml(option)}</div>
                    <input type="text"
                           data-meal-option="${escapeXml(option)}"
                           placeholder="Badge label (e.g. V, Steak)"
                           value="${escapeXml(saved)}">
                </div>
            `;
        });
        container.innerHTML = html;
        container.querySelectorAll('input[data-meal-option]').forEach(input => {
            input.addEventListener('input', () => {
                mappings = getMealPreferenceMappings();
                if (onChangeCallback) onChangeCallback();
            });
        });
    }

    async function init(options = {}) {
        onChangeCallback = options.onChange || null;
        cachedMealOptions = loadCachedMealOptions();
        const campaignId = getCampaignIdFromPreferences();
        if (campaignId && (!cachedMealOptions || cachedMealOptions.campaign_id !== campaignId)) {
            await fetchMealOptions(campaignId);
        } else {
            renderSection();
        }
    }

    function setSavedConfig(savedMappings = {}, savedSources = {}) {
        mappings = { ...savedMappings };
        const data = cachedMealOptions || loadCachedMealOptions();
        if (data?.questions?.length) {
            sources = mergeMealSourceDefaults(data.questions, savedSources);
        } else {
            sources = { ...savedSources };
        }
        renderSection();
    }

    function reset() {
        mappings = {};
        sources = {};
        cachedMealOptions = loadCachedMealOptions();
        renderSection();
    }

    function getConfigForSave() {
        return {
            meal_preference_mappings: getMealPreferenceMappings(),
            meal_preference_sources: getMealPreferenceSources(),
        };
    }

    function bindRefreshButton(buttonId, showToast) {
        const button = document.getElementById(buttonId);
        if (!button) return;
        button.addEventListener('click', async () => {
            const campaignId = getCampaignIdFromPreferences();
            if (!campaignId) {
                if (showToast) {
                    showToast('Select a main event on the Badge Generator page first', 'error');
                }
                return;
            }
            await fetchMealOptions(campaignId);
            if (showToast) showToast('Meal options refreshed', 'success');
        });
    }

    async function loadFromPreprocessingTemplate(templateId, options = {}) {
        if (options.onChange) {
            onChangeCallback = options.onChange;
        }

        let savedMappings = {};
        let savedSources = {};

        if (templateId) {
            try {
                const response = await fetch(`/api/preprocessing-templates/${templateId}`);
                if (!response.ok) throw new Error('Failed to load preprocessing template');
                const data = await response.json();
                const template = data.template || {};
                savedMappings = template.meal_preference_mappings || {};
                savedSources = template.meal_preference_sources || {};
            } catch (error) {
                console.error('Failed to load meal config from preprocessing template:', error);
                if (options.showToast) {
                    options.showToast('Could not load meal config from preprocessing template', 'error');
                }
            }
        }

        await init({ onChange: onChangeCallback });

        if (templateId) {
            setSavedConfig(savedMappings, savedSources);
        } else {
            reset();
        }

        if (onChangeCallback) {
            onChangeCallback();
        }
    }

    return {
        init,
        reset,
        renderSection,
        fetchMealOptions,
        getMealPreferenceMappings,
        getMealPreferenceSources,
        getConfigForSave,
        setSavedConfig,
        buildPreviewValue,
        bindRefreshButton,
        loadFromPreprocessingTemplate,
        getPreprocessingTemplateIdFromPreferences,
        getCampaignIdFromPreferences,
    };
})();
