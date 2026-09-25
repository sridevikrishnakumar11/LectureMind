document.addEventListener("DOMContentLoaded", () => {
    const fileInput = document.querySelector("#audio");
    const fileLabel = document.querySelector("#file-label");
    const dropzone = document.querySelector(".dropzone");
    const form = fileInput ? fileInput.closest("form") : null;

    function showFileName() {
        if (!fileInput || !fileLabel || !fileInput.files.length) {
            return;
        }

        fileLabel.textContent = fileInput.files[0].name;
    }

    if (fileInput) {
        fileInput.addEventListener("change", showFileName);
    }

    if (dropzone && fileInput) {
        ["dragenter", "dragover"].forEach((eventName) => {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                dropzone.classList.add("drag-over");
            });
        });

        ["dragleave", "drop"].forEach((eventName) => {
            dropzone.addEventListener(eventName, () => {
                dropzone.classList.remove("drag-over");
            });
        });

        dropzone.addEventListener("drop", (event) => {
            event.preventDefault();
            if (!event.dataTransfer.files.length) {
                return;
            }

            fileInput.files = event.dataTransfer.files;
            showFileName();
        });
    }

    if (form) {
        form.addEventListener("submit", () => {
            const submitButton = form.querySelector("button[type='submit']");
            if (!submitButton || !fileInput.files.length) {
                return;
            }

            submitButton.disabled = true;
            submitButton.textContent = submitButton.dataset.processingText || "Processing...";
        });
    }

    document.querySelectorAll(".interactive-map").forEach((container) => {
        let graph;
        try { graph = JSON.parse(container.dataset.mindmap); } catch (_) { return; }
        const width = 900, height = 460, center = { x: width / 2, y: height / 2 };
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", `0 0 ${width} ${height}`); svg.setAttribute("role", "img");
        const viewport = document.createElementNS(svg.namespaceURI, "g"); svg.appendChild(viewport); container.appendChild(svg);
        const rootId = graph.nodes && graph.nodes[0] ? graph.nodes[0].id : null;
        if (!rootId) return;
        const positions = { [rootId]: center };
        (graph.nodes || []).slice(1).forEach((node, index, items) => {
            const angle = (Math.PI * 2 * index / Math.max(items.length, 1)) - Math.PI / 2;
            positions[node.id] = { x: center.x + Math.cos(angle) * 255, y: center.y + Math.sin(angle) * 160 };
        });
        (graph.edges || []).forEach((edge) => {
            const a = positions[edge.source], b = positions[edge.target]; if (!a || !b) return;
            const line = document.createElementNS(svg.namespaceURI, "line"); line.setAttribute("x1", a.x); line.setAttribute("y1", a.y); line.setAttribute("x2", b.x); line.setAttribute("y2", b.y); line.classList.add("map-edge"); line.dataset.target = edge.target; viewport.appendChild(line);
        });
        const detail = container.parentElement.querySelector("#mindmap-detail");
        (graph.nodes || []).forEach((node) => {
            const p = positions[node.id], group = document.createElementNS(svg.namespaceURI, "g"); group.classList.add("map-node"); group.dataset.id = node.id;
            group.dataset.label = node.label;
            const words = node.label.split(/\s+/), lines = []; let line = "";
            words.forEach((word) => { const next = `${line} ${word}`.trim(); if (next.length > 22 && line) { lines.push(line); line = word; } else { line = next; } });
            if (line) lines.push(line);
            const nodeWidth = Math.max(160, Math.min(290, Math.max(...lines.map((item) => item.length)) * 9 + 34));
            const nodeHeight = Math.max(52, lines.length * 20 + 28);
            const rect = document.createElementNS(svg.namespaceURI, "rect"); rect.setAttribute("x", p.x - nodeWidth / 2); rect.setAttribute("y", p.y - nodeHeight / 2); rect.setAttribute("width", nodeWidth); rect.setAttribute("height", nodeHeight); rect.setAttribute("rx", 12);
            const text = document.createElementNS(svg.namespaceURI, "text"); text.setAttribute("x", p.x); text.setAttribute("y", p.y - ((lines.length - 1) * 10) + 5); text.setAttribute("text-anchor", "middle");
            lines.forEach((item, index) => { const span = document.createElementNS(svg.namespaceURI, "tspan"); span.setAttribute("x", p.x); span.setAttribute("dy", index ? 20 : 0); span.textContent = item; text.appendChild(span); });
            group.append(rect, text); viewport.appendChild(group);
            group.addEventListener("pointerdown", (event) => event.stopPropagation());
            group.addEventListener("click", (event) => {
                event.stopPropagation();
                svg.querySelectorAll(".map-node,.map-edge").forEach((item) => item.classList.remove("selected"));
                group.classList.add("selected");
                svg.querySelectorAll(`[data-target='${node.id}']`).forEach((item) => item.classList.add("selected"));
                if (detail) {
                    detail.replaceChildren();
                    const heading = document.createElement("strong"); heading.textContent = `Concept: ${node.label}`;
                    const label = document.createElement("p"); label.textContent = "Explanation:";
                    const explanation = document.createElement("p"); explanation.textContent = node.description;
                    detail.append(heading, label, explanation);
                }
            });
            group.addEventListener("dblclick", () => {
                if (node.id === rootId) {
                    svg.querySelectorAll(`.map-node:not([data-id='${rootId}']), .map-edge`).forEach((item) => item.classList.toggle("hidden"));
                } else {
                    group.classList.toggle("collapsed"); svg.querySelectorAll(`[data-target='${node.id}']`).forEach((item) => item.classList.toggle("hidden"));
                }
            });
        });
        const selectedConcept = new URLSearchParams(window.location.search).get("concept");
        if (selectedConcept) {
            const selectedNode = Array.from(svg.querySelectorAll(".map-node")).find((item) => item.dataset.label.toLowerCase() === selectedConcept.toLowerCase());
            if (selectedNode) selectedNode.click();
        }
        let scale = 1, x = 0, y = 0, start;
        const render = () => viewport.setAttribute("transform", `translate(${x} ${y}) scale(${scale})`); render();
        container.closest(".lecture-section").querySelectorAll("[data-map-zoom]").forEach((button) => button.addEventListener("click", () => { const action = button.dataset.mapZoom; if (action === "in") scale = Math.min(2, scale + .15); else if (action === "out") scale = Math.max(.55, scale - .15); else { scale = 1; x = 0; y = 0; } render(); }));
        svg.addEventListener("pointerdown", (event) => { start = { x: event.clientX - x, y: event.clientY - y }; svg.setPointerCapture(event.pointerId); });
        svg.addEventListener("pointermove", (event) => { if (start) { x = event.clientX - start.x; y = event.clientY - start.y; render(); } });
        svg.addEventListener("pointerup", () => { start = null; });
    });

    const qaForm = document.querySelector("#lecture-qa-form");
    if (qaForm) {
        const answerBox = document.querySelector("#lecture-answer");
        const answerText = answerBox ? answerBox.querySelector("[data-answer-text]") : null;
        qaForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const button = qaForm.querySelector("button[type='submit']");
            const question = qaForm.querySelector("#question");
            if (!answerBox || !answerText || !question || !question.value.trim()) return;
            button.disabled = true;
            button.textContent = "Searching…";
            try {
                const response = await fetch(qaForm.action, {
                    method: "POST",
                    headers: { "Accept": "application/json", "X-Requested-With": "XMLHttpRequest" },
                    body: new FormData(qaForm),
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || "Could not search this lecture.");
                answerText.textContent = data.answer;
                answerBox.hidden = false;
                answerBox.scrollIntoView({ behavior: "smooth", block: "center" });
            } catch (error) {
                answerText.textContent = error.message || "Could not search this lecture.";
                answerBox.hidden = false;
                answerBox.scrollIntoView({ behavior: "smooth", block: "center" });
            } finally {
                button.disabled = false;
                button.textContent = "Ask";
            }
        });
    }

    document.querySelectorAll(".performance-chart").forEach((chart) => {
        const scores = JSON.parse(chart.dataset.scores || "[]");
        const values = scores.map(Number).filter(Number.isFinite).map((score) => Math.max(0, Math.min(100, score)));
        if (!values.length) { chart.textContent = "Complete a quiz to see your score trend."; return; }
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 600 220"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Quiz score trend");
        const points = values.slice().reverse().map((score, index, list) => `${30 + index * (540 / Math.max(1, list.length - 1))},${190 - score * 1.55}`).join(" ");
        const line = document.createElementNS(svg.namespaceURI, "polyline"); line.setAttribute("points", points); svg.appendChild(line);
        values.slice().reverse().forEach((score, index, list) => {
            const x = 30 + index * (540 / Math.max(1, list.length - 1));
            const y = 190 - score * 1.55;
            const point = document.createElementNS(svg.namespaceURI, "circle");
            point.setAttribute("cx", x); point.setAttribute("cy", y); point.setAttribute("r", 6); svg.appendChild(point);
            const label = document.createElementNS(svg.namespaceURI, "text");
            label.setAttribute("x", x); label.setAttribute("y", Math.max(18, y - 12)); label.setAttribute("text-anchor", "middle"); label.textContent = `${score}%`; svg.appendChild(label);
        });
        chart.replaceChildren(svg);
    });
});
