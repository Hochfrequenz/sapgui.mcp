(args) => {
    // Note: findInputByLabel is provided by find_field_utils.js (concatenated before this file)
    const fields = args.fields;
    const results = { filled: [], notFound: [], ambiguous: [], errors: [], debug: [] };

    /**
     * Fill a single input element with a value, dispatching appropriate events.
     */
    function fillInput(el, value) {
        el.focus();
        el.value = value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.blur();
    }

    // Process each field
    for (const [key, value] of Object.entries(fields)) {
        try {
            let el;

            // Check if it's a CSS selector
            if (key.startsWith('#') || key.startsWith('.') || key.includes('[')) {
                // Use CSS.escape for SAP IDs containing special characters
                let escapedKey = key;
                if (key.startsWith('#') && !key.includes('\\')) {
                    escapedKey = '#' + CSS.escape(key.slice(1));
                }
                const matches = document.querySelectorAll(escapedKey);
                if (matches.length === 0) {
                    results.notFound.push(key);
                    continue;
                }
                if (matches.length > 1) {
                    results.ambiguous.push({
                        field: key,
                        error: `Selector matches ${matches.length} elements, expected 1`,
                        matchCount: matches.length,
                    });
                    continue;
                }
                el = matches[0];
            } else {
                // Treat as label text - use shared utility
                const result = findInputByLabel(key);

                if (result === null) {
                    // Add debug info about labels searched
                    const labels = document.querySelectorAll('label');
                    let labelsWithLsdata = 0;
                    let sampleLabelTexts = [];
                    for (const label of labels) {
                        const lsdata = label.getAttribute('lsdata');
                        if (lsdata) {
                            labelsWithLsdata++;
                            try {
                                const parsed = JSON.parse(lsdata);
                                if (parsed['3'] && sampleLabelTexts.length < 10) {
                                    sampleLabelTexts.push(parsed['3']);
                                }
                            } catch {}
                        }
                    }
                    results.debug.push({
                        field: key,
                        totalLabels: labels.length,
                        labelsWithLsdata: labelsWithLsdata,
                        sampleLabelTexts: sampleLabelTexts,
                    });
                    results.notFound.push(key);
                    continue;
                }

                // Check for ambiguous match
                if (result.ambiguous) {
                    const matchDescriptions = result.matches
                        .map((m) => {
                            if (m.lsdataField) {
                                return `${m.selector} (${m.lsdataField})`;
                            }
                            return m.selector;
                        })
                        .join(', ');

                    results.ambiguous.push({
                        field: key,
                        error:
                            `Label "${key}" matches ${result.count} fields. ` +
                            `Use a specific CSS selector instead: ${matchDescriptions}`,
                        matchCount: result.count,
                        matchingSelectors: result.matches,
                    });
                    continue;
                }

                el = result.element;
            }

            if (!el) {
                results.notFound.push(key);
                continue;
            }

            fillInput(el, value);
            results.filled.push(key);
        } catch (e) {
            results.errors.push({ field: key, error: e.message || String(e) });
        }
    }

    return results;
};
