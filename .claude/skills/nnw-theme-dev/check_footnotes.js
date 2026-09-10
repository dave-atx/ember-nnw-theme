/**
 * Ember footnote-adapter check — asserts that every provider shape in
 * test/footnote-providers.toml is normalized, reachable, and legible.
 *
 * The adapter lives inline in template.html and needs a real DOM (`:has()`,
 * `matches()`, computed styles, newsfoot's click handling), so this runs *in the
 * rendered page* rather than as a standalone script:
 *
 *   python3 .claude/skills/nnw-theme-dev/render.py test/footnote-providers.toml
 *   # then, against test/preview/footnote-providers.{mac,ios}.html:
 *   #   agents — Safari MCP `evaluate_javascript` with this file's contents
 *   #   humans — paste into the browser console
 *
 * Returns {pass, failed, total, failures[], checks[]}. `await` it: the popover
 * assertions let newsfoot settle between clicks.
 *
 * Run it against the light and dark renders of both platforms — the legibility
 * check is the one that catches accent-on-accent regressions, and it can only
 * fail in the scheme it is run in.
 */
(async () => {
	// Marker text as rendered -> the note text that marker must reveal.
	const EXPECTED = new Map([
		["1", "MultiMarkdown note."],
		["2", "CommonMark note."],
		["3", "Pandoc note."],
		["4", "remark note."],
		["5", "Substack note."],
		["6", "WordPress core note."],
		["[7]", "Easy Footnotes note."],
		["8", "Footnotes Made Easy note."],
		["9", "Modern Footnotes note."],
		["10", "Complete table-plugin note."],
		["11", "Jetpack note."]
	]);

	const checks = [];
	const check = (name, ok, detail) => checks.push({name, ok: !!ok, detail: ok ? undefined : detail});

	const article = document.querySelector(".articleBody");
	if (!article) return {pass: false, failures: ["no .articleBody — is this a rendered preview?"]};

	const markers = new Map();
	for (const a of article.querySelectorAll("a.footnote")) markers.set(a.textContent.trim(), a);

	// 1. Every provider is recognized, and its normalized note holds the right text.
	for (const [label, expected] of EXPECTED) {
		const marker = markers.get(label);
		if (!marker) {
			check(`${label}: recognized`, false, "no a.footnote with this text");
			continue;
		}
		check(`${label}: recognized`, true);

		const href = marker.getAttribute("href") || "";
		const target = href.startsWith("#") && document.getElementById(href.slice(1));
		check(`${label}: target resolves`, target, `href ${href} resolves to nothing`);
		if (!target) continue;

		check(`${label}: target is normalized`, target.closest("[data-ember-footnotes]"),
			"target is not inside the adapter's normalized notes");
		const text = target.textContent.replace(/\s+/g, " ").trim();
		check(`${label}: note text`, text === expected, `expected ${JSON.stringify(expected)}, got ${JSON.stringify(text)}`);
	}

	// 2. The numeral must be legible against the capsule it sits on. This is what
	//    catches `body a *` (and friends) repainting a nested <sup> accent-on-accent.
	const rgb = (value) => (value.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
	const distance = (a, b) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]);
	for (const [label, marker] of markers) {
		const background = rgb(getComputedStyle(marker).backgroundColor);
		// The deepest element actually carrying the numeral, which is what gets painted.
		const glyph = [...marker.querySelectorAll("*")].filter(e => e.textContent.trim()).pop() || marker;
		const foreground = rgb(getComputedStyle(glyph).color);
		check(`${label}: numeral legible`, distance(foreground, background) > 60,
			`text ${foreground} on background ${background} — capsule renders blank`);

		const box = marker.getBoundingClientRect();
		const glyphBox = glyph.getBoundingClientRect();
		const inside = glyphBox.top >= box.top - 1 && glyphBox.bottom <= box.bottom + 1;
		check(`${label}: numeral inside capsule`, inside,
			`glyph ${JSON.stringify([glyphBox.top, glyphBox.bottom])} escapes capsule ${JSON.stringify([box.top, box.bottom])}`);
	}

	// 3. A plain superscript link is not a footnote and must be left alone.
	const ordinary = document.getElementById("ordinary-sup-link");
	check("ordinary sup link untouched",
		ordinary && !ordinary.classList.contains("footnote") && ordinary.getAttribute("href") === "#chapter",
		`href ${ordinary?.getAttribute("href")}, class ${ordinary?.className}`);

	// 4. Cloning note content must not duplicate ids into the document.
	const seen = new Map();
	for (const el of document.querySelectorAll("[id]")) seen.set(el.id, (seen.get(el.id) || 0) + 1);
	const duplicates = [...seen].filter(([, n]) => n > 1).map(([id]) => id);
	check("no duplicate ids", duplicates.length === 0, `duplicated: ${duplicates.join(", ")}`);

	// 5. Return links stay in the document rather than opening the website.
	for (const backlink of article.querySelectorAll("a[data-ember-footnote-backlink]")) {
		const href = backlink.getAttribute("href") || "";
		check(`backlink ${href}`, href.startsWith("#") && document.getElementById(href.slice(1)),
			"backlink does not resolve to a local marker");
	}

	// 6. End to end: newsfoot opens a popover with the note in it.
	if (typeof document.body.click === "function") {
		for (const [label, expected] of EXPECTED) {
			const marker = markers.get(label);
			if (!marker) continue;
			marker.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true, view: window}));
			await new Promise(r => setTimeout(r, 60));
			const popover = document.querySelector(".newsfoot-footnote-popover");
			const text = popover ? popover.textContent.replace(/\s+/g, " ").trim() : null;
			check(`${label}: popover`, text === expected, `popover showed ${JSON.stringify(text)}`);
			document.body.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true, view: window}));
			await new Promise(r => setTimeout(r, 30));
		}
	}

	const failures = checks.filter(c => !c.ok);
	return {
		pass: failures.length === 0,
		failed: failures.length,
		total: checks.length,
		failures: failures.map(f => `${f.name} — ${f.detail}`)
	};
})()
