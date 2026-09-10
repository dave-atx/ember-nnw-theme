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
 * Runs against any rendered fixture. The provider-by-provider expectations below
 * only apply to test/footnote-providers.toml (detected by its negative control);
 * every other assertion is fixture-agnostic, so point it at a real captured
 * article — test/sixcolors-footnotes.toml — to check the adapter against markup
 * nobody wrote for us.
 *
 * Returns {pass, failed, total, failures[], checks[]}. `await` it: the popover
 * assertions let newsfoot settle between clicks. Keep the browser window
 * frontmost — a backgrounded tab throttles setTimeout hard enough to look hung.
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
		["7", "Easy Footnotes note."],
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

	// The provider fixture carries a negative control no real article has.
	const providerFixture = !!document.getElementById("ordinary-sup-link");

	// The note each marker actually points at — the yardstick for the popover
	// assertions on fixtures we have no hand-written expectations for.
	const noteFor = new Map();

	// 1. Every marker resolves to a normalized, non-empty note.
	check("found markers", markers.size > 0, "no a.footnote in the article");
	for (const [label, marker] of markers) {
		const href = marker.getAttribute("href") || "";
		const target = href.startsWith("#") && document.getElementById(href.slice(1));
		check(`${label}: target resolves`, target, `href ${href} resolves to nothing`);
		if (!target) continue;
		check(`${label}: target is normalized`, target.closest("[data-ember-footnotes]"),
			"target is not inside the adapter's normalized notes");
		const text = target.textContent.replace(/\s+/g, " ").trim();
		check(`${label}: note is not empty`, text.length > 0, "normalized note has no text");
		noteFor.set(label, text);
	}

	// 1b. On the provider fixture, each format must land on its own note.
	if (providerFixture) {
		for (const [label, expected] of EXPECTED) {
			const marker = markers.get(label);
			if (!marker) {
				check(`${label}: recognized`, false, "no a.footnote with this text");
				continue;
			}
			check(`${label}: recognized`, true);
			const text = noteFor.get(label);
			check(`${label}: note text`, text === expected,
				`expected ${JSON.stringify(expected)}, got ${JSON.stringify(text)}`);
		}
	}

	// 2. The numeral must be legible against the capsule it sits on. This is what
	//    catches `body a *` (and friends) repainting a nested <sup> accent-on-accent.
	const rgb = (value) => (value.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
	const rgba = (value) => {
		const n = (value.match(/[\d.]+/g) || []).map(Number);
		return n.length ? [n[0], n[1], n[2], n.length > 3 ? n[3] : 1] : [0, 0, 0, 0];
	};
	const distance = (a, b) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]);
	// The capsule's fill is a tint, so it is only as legible as what shows through
	// it — flatten it over its ancestors before measuring the contrast.
	const backdrop = (element) => {
		const layers = [];
		for (let node = element; node; node = node.parentElement) {
			const layer = rgba(getComputedStyle(node).backgroundColor);
			if (!layer[3]) continue;
			layers.push(layer);
			if (layer[3] === 1) break;
		}
		let base = layers.pop() || [255, 255, 255, 1];
		while (layers.length) {
			const top = layers.pop();
			base = [0, 1, 2].map(i => top[i] * top[3] + base[i] * (1 - top[3]));
		}
		return base.slice(0, 3);
	};
	for (const [label, marker] of markers) {
		const background = backdrop(marker);
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

	// 3. Every marker must present identically, whatever the provider wrote. The
	//    wrapper (<sup> or not) used to leak into both the size and the seat.
	//    Seat is measured against a probe glyph dropped on the marker's own line
	//    rather than against its block, so the metric still means something in a
	//    real article where markers sit on different lines of different lengths.
	const geometry = [...markers].map(([label, marker]) => {
		const box = marker.getBoundingClientRect();
		const probe = document.createElement("span");
		probe.textContent = "x";
		marker.after(probe);
		const seat = box.bottom - probe.getBoundingClientRect().bottom;
		probe.remove();
		return {label, marker, h: box.height, w: box.width, seat,
			size: parseFloat(getComputedStyle(marker).fontSize)};
	});
	if (geometry.length) {
		const first = geometry[0];
		for (const g of geometry) {
			check(`${g.label}: uniform height`, Math.abs(g.h - first.h) < 0.5,
				`${g.h}px vs ${first.label}'s ${first.h}px`);
			check(`${g.label}: uniform seat`, Math.abs(g.seat - first.seat) < 0.5,
				`sits ${g.seat}px off its line's baseline, ${first.label} sits ${first.seat}px`);
			check(`${g.label}: uniform size`, Math.abs(g.size - first.size) < 0.1,
				`font-size ${g.size}px vs ${first.label}'s ${first.size}px`);
			// Oblong, not a circle: a lone digit must still fill a capsule.
			check(`${g.label}: oblong`, g.w / g.h > 1.35, `${g.w}x${g.h} is too square`);
			check(`${g.label}: bare numeral`, !/[\[\]()]/.test(g.label), `marker reads ${JSON.stringify(g.label)}`);
		}
	}

	// 4. No stray space between a marker and the word it annotates.
	for (const [label, marker] of markers) {
		let box = marker;
		while (box.parentElement && !box.parentElement.matches(".articleBody") &&
			[...box.parentElement.childNodes].every(n => n === box || n.hidden || !n.textContent.trim())) box = box.parentElement;
		let before = box.previousSibling;
		while (before && !before.textContent) before = before.previousSibling;
		if (before && before.nodeType === Node.TEXT_NODE) {
			check(`${label}: no gap before marker`, !/\s$/.test(before.data),
				`preceded by ${JSON.stringify(before.data.slice(-12))}`);
		}
	}

	// 5. A plain superscript link is not a footnote and must be left alone.
	//    Only the provider fixture carries this control.
	if (providerFixture) {
		const ordinary = document.getElementById("ordinary-sup-link");
		check("ordinary sup link untouched",
			ordinary && !ordinary.classList.contains("footnote") && ordinary.getAttribute("href") === "#chapter",
			`href ${ordinary?.getAttribute("href")}, class ${ordinary?.className}`);
	}

	// 6. Cloning note content must not duplicate ids into the document.
	const seen = new Map();
	for (const el of document.querySelectorAll("[id]")) seen.set(el.id, (seen.get(el.id) || 0) + 1);
	const duplicates = [...seen].filter(([, n]) => n > 1).map(([id]) => id);
	check("no duplicate ids", duplicates.length === 0, `duplicated: ${duplicates.join(", ")}`);

	// 7. Return links stay in the document rather than opening the website.
	for (const backlink of article.querySelectorAll("a[data-ember-footnote-backlink]")) {
		const href = backlink.getAttribute("href") || "";
		check(`backlink ${href}`, href.startsWith("#") && document.getElementById(href.slice(1)),
			"backlink does not resolve to a local marker");
	}

	// 8. End to end: newsfoot opens a popover with the note in it. The yardstick
	//    is the note the marker resolves to, so this works on any fixture.
	if (typeof document.body.click === "function") {
		for (const [label, marker] of markers) {
			const expected = noteFor.get(label);
			if (expected === undefined) continue;
			const resting = marker.getBoundingClientRect();
			marker.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true, view: window}));
			await new Promise(r => setTimeout(r, 60));
			// Opening moves the anchor into a .newsfoot-footnote-container, which
			// takes it out from under any rule keyed on its original parent.
			const opened = marker.getBoundingClientRect();
			check(`${label}: capsule survives opening`,
				Math.abs(resting.width - opened.width) < 0.5 && Math.abs(resting.height - opened.height) < 0.5,
				`${resting.width}x${resting.height} became ${opened.width}x${opened.height}`);
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
