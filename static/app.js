/* ──────────────────────────────────────────────────────────────
   Kirana AI — client glue + flagship motion + voice capture
   Talks to gr.Server (FastAPI) over plain fetch(). UI state is
   client-owned and round-trips with every dispatch.
   ────────────────────────────────────────────────────────────── */

(function () {

    function $(sel, root) { return (root || document).querySelector(sel); }
    function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

    function waitFor(selector, callback, timeout) {
        timeout = timeout || 15000;
        const found = $(selector);
        if (found) { callback(found); return; }
        const t0 = Date.now();
        const iv = setInterval(function () {
            const el = $(selector);
            if (el) { clearInterval(iv); callback(el); return; }
            if (Date.now() - t0 > timeout) {
                clearInterval(iv);
                console.warn("[kirana] timeout waiting for", selector);
            }
        }, 80);
    }

    /* Swap the page-host inner HTML with what the server rendered and
       persist the new client-owned state. The MutationObserver in init()
       will fire processAfterRender + wireDynamic on the new DOM. */
    function applyResponse(resp) {
        if (!resp) return;
        if (resp.state) window.kirana._state = resp.state;
        if (typeof resp.html === "string") {
            const host = $(".page-host");
            if (host) host.innerHTML = resp.html;
        }
    }

    function dispatch(action, params) {
        params = params || {};
        const body = JSON.stringify({
            action: action,
            params: params,
            state:  window.kirana._state || null,
        });
        return fetch("/api/dispatch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: body,
        })
            .then(function (r) { return r.json(); })
            .then(applyResponse)
            .catch(function (e) {
                console.error("[kirana] dispatch failed", e);
                toast("Network error", "danger");
            });
    }

    function readForm(container) {
        const root = (typeof container === "string") ? $(container) : container;
        if (!root) return {};
        const data = {};
        root.querySelectorAll("[name]").forEach(function (el) {
            if (el.type === "checkbox") data[el.name] = el.checked;
            else if (el.type === "radio") { if (el.checked) data[el.name] = el.value; }
            else data[el.name] = el.value;
        });
        return data;
    }

    function submitForm(formId, action, extra) {
        const data = readForm("#" + formId);
        if (extra) Object.assign(data, extra);
        dispatch(action, data);
    }

    function quickAction(action, params) {
        // Optimistic UI for slow async actions
        if (action === "refresh_insights" || action === "run_analysis") {
            const strip = $(".insight-strip");
            if (strip) strip.classList.add("is-processing");
            const btn = document.activeElement;
            if (btn && btn.tagName === "BUTTON") btn.classList.add("refresh-spinning");
        }
        dispatch(action, params || {});
    }
    function navigate(page) { dispatch("navigate", { to: page }); }

    function switchTab(group, name) {
        document.querySelectorAll('[data-tab-group="' + group + '"]').forEach(function (b) {
            b.classList.toggle("active", b.dataset.tab === name);
            if (b.getAttribute("role") === "tab") {
                b.setAttribute("aria-selected", b.dataset.tab === name ? "true" : "false");
                b.tabIndex = b.dataset.tab === name ? 0 : -1;
            }
        });
        document.querySelectorAll('[data-tab-pane="' + group + '"]').forEach(function (p) {
            p.style.display = (p.dataset.pane === name) ? "" : "none";
        });
    }

    function ensureToastHost() {
        let host = $(".toast-host");
        if (!host) {
            host = document.createElement("div");
            host.className = "toast-host";
            document.body.appendChild(host);
        }
        return host;
    }

    function toast(message, type) {
        type = type || "info";
        const host = ensureToastHost();
        const el = document.createElement("div");
        el.className = "toast " + type;
        el.setAttribute("role", type === "danger" ? "alert" : "status");
        el.innerHTML = '<div style="flex:1">' + message + '</div>';
        host.appendChild(el);
        setTimeout(function () {
            el.classList.add("is-leaving");
            setTimeout(function () { el.remove(); }, 260);
        }, 3200);
    }

    function applySidebarState() {
        const root = $(".k-app");
        if (!root) return;
        const collapsed = localStorage.getItem("kirana.sidebar") === "collapsed";
        root.classList.toggle("collapsed", collapsed);
        const btn = $(".k-collapse-btn");
        if (btn) {
            btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
            btn.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
            btn.setAttribute("title", collapsed ? "Expand sidebar" : "Collapse sidebar");
        }
    }

    /* ══════════════════════════════════════════════════════════
       Theme: dark default; light opt-in. Persisted to
       localStorage; first load respects prefers-color-scheme.
       ══════════════════════════════════════════════════════════ */
    function getStoredTheme() {
        const v = localStorage.getItem("kirana.theme");
        if (v === "light" || v === "dark") return v;
        const prefersLight = window.matchMedia &&
            window.matchMedia("(prefers-color-scheme: light)").matches;
        return prefersLight ? "light" : "dark";
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        const btn = $("#theme-toggle");
        if (btn) {
            const next = theme === "light" ? "dark" : "light";
            btn.setAttribute("aria-pressed", theme === "light" ? "true" : "false");
            btn.setAttribute("title", "Switch to " + next + " theme");
            btn.setAttribute("aria-label", "Switch to " + next + " theme");
        }
    }

    function toggleTheme() {
        const cur = document.documentElement.getAttribute("data-theme") || getStoredTheme();
        const next = cur === "light" ? "dark" : "light";
        localStorage.setItem("kirana.theme", next);
        applyTheme(next);
    }

    function toggleSidebar() {
        const root = $(".k-app");
        if (!root) return;
        const nowCollapsed = !root.classList.contains("collapsed");
        root.classList.toggle("collapsed", nowCollapsed);
        localStorage.setItem("kirana.sidebar", nowCollapsed ? "collapsed" : "expanded");
        const btn = $(".k-collapse-btn");
        if (btn) {
            btn.setAttribute("aria-expanded", nowCollapsed ? "false" : "true");
            btn.setAttribute("aria-label", nowCollapsed ? "Expand sidebar" : "Collapse sidebar");
            btn.setAttribute("title", nowCollapsed ? "Expand sidebar" : "Collapse sidebar");
        }
    }

    function openPhoto() {
        const input = $("#kirana-photo-input");
        if (input) input.click();
        else toast("Photo uploader not ready", "warn");
    }

    function uploadPhoto(file) {
        if (!file) return;
        const fd = new FormData();
        fd.append("image", file);
        fd.append("state", JSON.stringify(window.kirana._state || {}));
        toast("Analyzing photo…", "info");
        fetch("/api/photo", { method: "POST", body: fd })
            .then(function (r) { return r.json(); })
            .then(applyResponse)
            .catch(function (e) {
                console.error("[kirana] photo upload failed", e);
                toast("Photo upload failed", "danger");
            });
    }


    function transcribeAudio() {
        const input = $("#modal-speech-audio");
        if (!input || !input.files || !input.files[0]) {
            toast("Choose an audio file first.", "warn");
            return;
        }

        const fd = new FormData();
        fd.append("audio", input.files[0]);
        fd.append("state", JSON.stringify(window.kirana._state || {}));

        toast("Transcribing audio…", "info");
        fetch("/api/speech", { method: "POST", body: fd })
            .then(function (r) { return r.json(); })
            .then(function (payload) {
                applyResponse(payload);

                const transcript =
                    payload &&
                    payload.state &&
                    payload.state.voice_result &&
                    payload.state.voice_result.transcript;

                if (transcript) {
                    const inputText = $("#voice-text");
                    const transcriptBox = $("#voice-transcript");

                    if (inputText) inputText.value = transcript;
                    if (transcriptBox) transcriptBox.textContent = transcript;
                }

                toast("Speech transcribed", "success");
            })
            .catch(function (e) {
                console.error("[kirana] speech upload failed", e);
                toast("Speech transcription failed", "danger");
            });
    }

    /* ══════════════════════════════════════════════════════════
       Number count-up: scans elements with [data-count] and
       tweens from 0 → target. Honors reduced motion.
       ══════════════════════════════════════════════════════════ */
    function easeOutQuart(t) { return 1 - Math.pow(1 - t, 4); }

    function countUp(el) {
        if (el.dataset.counted === "1") return;
        el.dataset.counted = "1";
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const finalText = el.textContent.trim();
        // Parse: leading prefix (₹, etc.), digits/commas/dots, trailing suffix (%, etc.)
        const match = finalText.match(/^([^\d\-]*)(-?[\d,.]+)(.*)$/);
        if (!match) return;
        const prefix = match[1];
        const target = parseFloat(match[2].replace(/,/g, ""));
        const suffix = match[3];
        if (!isFinite(target) || reduce || target === 0) return;

        const decimals = (match[2].split(".")[1] || "").length;
        const dur = Math.min(900, 360 + Math.abs(target) * 0.6);
        const t0 = performance.now();

        function step(now) {
            const t = Math.min(1, (now - t0) / dur);
            const v = target * easeOutQuart(t);
            const display = decimals > 0
                ? v.toFixed(decimals)
                : Math.round(v).toLocaleString("en-IN");
            el.textContent = prefix + display + suffix;
            if (t < 1) requestAnimationFrame(step);
            else el.textContent = finalText;
        }
        requestAnimationFrame(step);
    }

    /* ══════════════════════════════════════════════════════════
       Health-bar reveal: read flex from inline style, replace
       with target custom-prop, then add .is-revealed.
       ══════════════════════════════════════════════════════════ */
    function revealHealthBar(bar) {
        if (bar.dataset.revealed === "1") return;
        bar.dataset.revealed = "1";
        $all(".health-seg", bar).forEach(function (seg) {
            const style = seg.getAttribute("style") || "";
            const m = style.match(/flex\s*:\s*([\d.]+)/);
            const target = m ? parseFloat(m[1]) : 1;
            seg.style.flex = "";
            seg.style.setProperty("--hb-target", target);
            seg.style.setProperty("--hb-grow", 0);
        });
        // force layout then flip
        void bar.offsetWidth;
        requestAnimationFrame(function () {
            bar.classList.add("is-revealed");
        });
    }

    /* ══════════════════════════════════════════════════════════
       Decorate dashboard: count-up KPIs, index list items for
       stagger, kick health-bar reveal once visible.
       ══════════════════════════════════════════════════════════ */
    function decorateDashboard() {
        // Index KPIs and cards for staggered entrance
        $all(".kpi-grid .kpi").forEach(function (el, i) { el.style.setProperty("--i", i); });
        $all(".reorder-list").forEach(function (list) {
            list.classList.add("stagger");
            $all(".reorder-row", list).forEach(function (el, i) { el.style.setProperty("--i", i); });
        });
        $all(".fest-strip").forEach(function (list) {
            list.classList.add("stagger");
            $all(".fest-step", list).forEach(function (el, i) { el.style.setProperty("--i", i); });
        });
        $all(".liquidation-list").forEach(function (list) {
            list.classList.add("stagger");
            $all(".liquidation-row", list).forEach(function (el, i) { el.style.setProperty("--i", i); });
        });
        $all(".alert-list, .alert-list-compact").forEach(function (list) {
            list.classList.add("stagger");
            $all(".alert", list).forEach(function (el, i) { el.style.setProperty("--i", i); });
        });
        $all(".seller-list").forEach(function (list) {
            list.classList.add("stagger");
            $all(".seller-row-v2", list).forEach(function (el, i) { el.style.setProperty("--i", i); });
        });
        $all(".chart-list").forEach(function (list) {
            list.classList.add("stagger");
            $all(".chart-row", list).forEach(function (el, i) { el.style.setProperty("--i", i); });
        });

        // KPI numbers + chip numbers
        $all(".kpi-value, .alert-chip-val").forEach(countUp);

        // Health bar reveal — observe in-view, but most dashboards have it above the fold
        $all(".health-bar").forEach(function (bar) {
            if ("IntersectionObserver" in window) {
                const io = new IntersectionObserver(function (entries) {
                    entries.forEach(function (e) {
                        if (e.isIntersecting) { revealHealthBar(bar); io.disconnect(); }
                    });
                }, { threshold: 0.2 });
                io.observe(bar);
                // Safety: reveal after 600ms regardless (handles tabs hidden / no IO trigger)
                setTimeout(function () { revealHealthBar(bar); }, 600);
            } else {
                revealHealthBar(bar);
            }
        });

        // Chart bars: animate width from 0 to target
        $all(".chart-bar-fill").forEach(function (fill) {
            if (fill.dataset.anim === "1") return;
            fill.dataset.anim = "1";
            const target = fill.style.width;
            fill.style.width = "0%";
            requestAnimationFrame(function () {
                fill.style.transition = "width 720ms var(--ease-out-quint, cubic-bezier(0.22,1,0.36,1))";
                fill.style.width = target;
            });
        });
        // Seller bars (background fill)
        $all(".seller-bar-bg").forEach(function (bar) {
            if (bar.dataset.anim === "1") return;
            bar.dataset.anim = "1";
            const target = bar.style.width;
            bar.style.width = "0%";
            requestAnimationFrame(function () {
                bar.style.transition = "width 720ms var(--ease-out-quint, cubic-bezier(0.22,1,0.36,1))";
                bar.style.width = target;
            });
        });
    }

    /* ══════════════════════════════════════════════════════════
       VOICE CAPTURE
       Web Speech API + getUserMedia analyser for mic level bars.
       ══════════════════════════════════════════════════════════ */
    const Voice = (function () {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        const state = {
            rec: null,
            listening: false,
            lang: "te-IN",
            audioCtx: null,
            analyser: null,
            stream: null,
            rafId: null,
            final: "",
            interim: "",
        };
        const BAR_COUNT = 18;

        function supported() { return !!SR; }

        function setStatus(msg, kind) {
            const el = $("#voice-status");
            if (!el) return;
            el.textContent = msg;
            el.classList.toggle("is-error", kind === "error");
        }

        function renderTranscript() {
            const el = $("#voice-transcript");
            if (!el) return;
            const finalPart = state.final;
            const interimPart = state.interim
                ? '<span class="interim">' + escapeHtml(state.interim) + '</span>'
                : "";
            el.innerHTML = escapeHtml(finalPart) +
                          (finalPart && interimPart ? " " : "") +
                          interimPart;
            el.classList.toggle("is-active", !!(finalPart || interimPart));
        }

        function escapeHtml(s) {
            return (s || "").replace(/[&<>"']/g, function (c) {
                return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
            });
        }

        function setLang(lang) {
            state.lang = lang;
            $all(".voice-lang button").forEach(function (b) {
                const on = b.dataset.lang === lang;
                b.setAttribute("aria-pressed", on ? "true" : "false");
            });
            const tr = $("#voice-transcript");
            if (tr) tr.setAttribute("lang", lang.split("-")[0]);
            if (state.rec) {
                try { state.rec.lang = lang; } catch (e) {}
            }
            if (state.listening) {
                stop();
                setTimeout(start, 120);
            }
        }

        async function startAnalyser() {
            try {
                if (!state.stream) {
                    state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                }
                const Ctx = window.AudioContext || window.webkitAudioContext;
                if (!state.audioCtx) state.audioCtx = new Ctx();
                if (!state.analyser) {
                    state.analyser = state.audioCtx.createAnalyser();
                    state.analyser.fftSize = 64;
                    state.analyser.smoothingTimeConstant = 0.78;
                    const src = state.audioCtx.createMediaStreamSource(state.stream);
                    src.connect(state.analyser);
                }
                if (state.audioCtx.state === "suspended") await state.audioCtx.resume();
                tickAnalyser();
                $("#voice-wave")?.classList.add("is-live");
            } catch (e) {
                // No mic permission for analyser — still allow speech recognition
                console.warn("[voice] analyser unavailable", e);
            }
        }

        function stopAnalyser() {
            if (state.rafId) cancelAnimationFrame(state.rafId);
            state.rafId = null;
            $("#voice-wave")?.classList.remove("is-live");
            // Drain bars to rest
            const bars = $all("#voice-wave span");
            bars.forEach(function (b) { b.style.setProperty("--lvl", 0); });
        }

        function tickAnalyser() {
            const bars = $all("#voice-wave span");
            if (!state.analyser || !bars.length) return;
            const data = new Uint8Array(state.analyser.frequencyBinCount);
            function loop() {
                state.analyser.getByteFrequencyData(data);
                // Map low → high frequencies to bars, mirrored for symmetry
                const half = Math.ceil(bars.length / 2);
                for (let i = 0; i < half; i++) {
                    const idx = Math.floor((i / half) * (data.length * 0.7));
                    const lvl = Math.min(1, (data[idx] || 0) / 200);
                    // Mirror around center
                    bars[half - 1 - i]?.style.setProperty("--lvl", lvl.toFixed(3));
                    bars[half + i]?.style.setProperty("--lvl", lvl.toFixed(3));
                }
                state.rafId = requestAnimationFrame(loop);
            }
            loop();
        }

        function start() {
            if (!supported()) {
                setStatus("Speech recognition not supported in this browser. Type the command instead.", "error");
                return;
            }
            if (state.listening) return;
            try {
                state.rec = new SR();
            } catch (e) {
                setStatus("Could not start microphone: " + e.message, "error");
                return;
            }
            state.rec.lang = state.lang;
            state.rec.interimResults = true;
            state.rec.continuous = false;
            state.rec.maxAlternatives = 1;

            state.rec.onstart = function () {
                state.listening = true;
                state.final = "";
                state.interim = "";
                renderTranscript();
                $(".voice-mic")?.classList.add("is-listening");
                const langLabel = state.lang === "te-IN" ? "Telugu" : "English";
                setStatus("Listening in " + langLabel + "…");
                startAnalyser();
            };
            state.rec.onresult = function (ev) {
                let interim = "";
                let final = state.final;
                for (let i = ev.resultIndex; i < ev.results.length; i++) {
                    const r = ev.results[i];
                    if (r.isFinal) final += r[0].transcript;
                    else           interim += r[0].transcript;
                }
                state.final = final;
                state.interim = interim;
                renderTranscript();
            };
            state.rec.onerror = function (ev) {
                if (ev.error === "no-speech") {
                    setStatus("Didn't catch that. Tap the mic and try again.");
                } else if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
                    setStatus("Microphone permission denied. Type the command below.", "error");
                } else if (ev.error === "language-not-supported") {
                    setStatus("This browser doesn't support " + state.lang + ". Try English.", "error");
                } else {
                    setStatus("Microphone error: " + ev.error, "error");
                }
            };
            state.rec.onend = function () {
                state.listening = false;
                $(".voice-mic")?.classList.remove("is-listening");
                stopAnalyser();
                const text = (state.final || state.interim || "").trim();
                if (text) {
                    const input = $("#voice-text");
                    if (input) input.value = text;
                    setStatus('Heard: "' + text + '". Submitting…');
                    setTimeout(function () { submitVoice(); }, 250);
                } else {
                    setStatus("Tap the mic and speak, or type below.");
                }
            };
            try { state.rec.start(); }
            catch (e) { setStatus("Could not start: " + e.message, "error"); }
        }

        function stop() {
            if (state.rec && state.listening) {
                try { state.rec.stop(); } catch (e) {}
            }
        }

        function toggle() {
            state.listening ? stop() : start();
        }

        function submitVoice() {
            const input = $("#voice-text");
            const text = input ? input.value.trim() : (state.final || "").trim();
            if (!text) {
                setStatus("Nothing to submit yet.");
                return;
            }
            submitForm("form-voice", "voice_command", { text: text, lang: state.lang });
        }

        function fillExample(text) {
            const input = $("#voice-text");
            const tr = $("#voice-transcript");
            if (input) input.value = text;
            if (tr) { tr.textContent = text; tr.classList.add("is-active"); }
            state.final = text; state.interim = "";
            setStatus('Loaded example. Submitting…');
            setTimeout(function () { submitVoice(); }, 200);
        }

        function init() {
            const stack = $(".voice-mic-stack");
            if (!stack || stack.dataset.wired === "1") return;
            stack.dataset.wired = "1";

            // Build the level bars
            const wave = $("#voice-wave");
            if (wave && !wave.children.length) {
                for (let i = 0; i < BAR_COUNT; i++) {
                    const s = document.createElement("span");
                    s.style.setProperty("--lvl", 0);
                    wave.appendChild(s);
                }
            }

            // Wire mic button
            const mic = $(".voice-mic");
            if (mic) mic.addEventListener("click", toggle);

            // Wire language pills
            $all(".voice-lang button").forEach(function (b) {
                b.addEventListener("click", function () { setLang(b.dataset.lang); });
            });

            // Wire examples
            $all(".voice-chip").forEach(function (c) {
                c.addEventListener("click", function () { fillExample(c.dataset.example || c.textContent.trim()); });
            });

            // Initial status
            if (!supported()) {
                setStatus("Speech recognition not available in this browser. Type the command below.", "error");
                mic && mic.setAttribute("disabled", "true");
            } else {
                setStatus("Tap the mic and speak in Telugu or English.");
            }

            // Default language: Telugu
            setLang("te-IN");
        }

        // Keyboard shortcut: hold Space when voice pane is visible
        document.addEventListener("keydown", function (e) {
            const pane = $("#pane-voice");
            if (!pane || pane.style.display === "none") return;
            if (e.code !== "Space" || e.repeat) return;
            if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
            e.preventDefault();
            if (window.kirana && window.kirana.voice && window.kirana.voice.start) {
                window.kirana.voice.start();
            }
        });

        return { init: init, start: start, stop: stop, toggle: toggle, submit: submitVoice, fillExample: fillExample, setLang: setLang };
    })();

    function processAfterRender() {
        const root = $(".k-app");
        if (!root) return;
        applySidebarState();
        const t = root.getAttribute("data-toast");
        if (t) {
            root.removeAttribute("data-toast");
            const idx = t.indexOf("|");
            if (idx >= 0) toast(t.slice(idx + 1), t.slice(0, idx));
            else          toast(t, "info");
        }
        decorateDashboard();
        if (window.kirana && window.kirana.voice && window.kirana.voice.init) window.kirana.voice.init();
    }

    function wirePulseChart() {
        const chart = $(".pulse-chart");
        if (!chart || chart.dataset.wired === "1") return;
        let points;
        try { points = JSON.parse(chart.dataset.pulsePoints || "[]"); }
        catch (e) { return; }
        if (!points.length) return;
        chart.dataset.wired = "1";
        const cursor = chart.querySelector(".pulse-cursor");
        const tip    = chart.querySelector(".pulse-tip");
        const tipDay = tip && tip.querySelector(".pulse-tip-day");
        const tipVal = tip && tip.querySelector(".pulse-tip-val");
        if (!cursor || !tip) return;

        const fmtINR = function (n) { return "₹" + Math.round(n).toLocaleString("en-IN"); };
        const fmtDate = function (iso) {
            const d = new Date(iso + "T00:00:00");
            return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
        };

        function onMove(ev) {
            const rect = chart.getBoundingClientRect();
            const x = ev.clientX - rect.left;
            const ratio = Math.max(0, Math.min(1, x / rect.width));
            // viewBox is 0..100 with PAD=2 — map ratio back to nearest point
            const vx = 2 + ratio * 96;
            let best = points[0], bestD = Infinity;
            for (let i = 0; i < points.length; i++) {
                const d = Math.abs(points[i].x - vx);
                if (d < bestD) { bestD = d; best = points[i]; }
            }
            const px = (best.x / 100) * rect.width;
            const py = (best.y / 36) * rect.height;
            cursor.style.transform = "translateX(" + px.toFixed(1) + "px)";
            cursor.classList.add("is-visible");
            tipDay.textContent = fmtDate(best.date);
            tipVal.textContent = fmtINR(best.rev);
            // Clamp tip within chart bounds (tip is ~120px wide)
            const tipW = 132;
            let tipX = px - tipW / 2;
            tipX = Math.max(4, Math.min(rect.width - tipW - 4, tipX));
            tip.style.transform = "translate(" + tipX.toFixed(1) + "px, " + Math.max(0, py - 56).toFixed(1) + "px)";
            tip.classList.add("is-visible");
        }
        function onLeave() {
            cursor.classList.remove("is-visible");
            tip.classList.remove("is-visible");
        }
        chart.addEventListener("mousemove", onMove);
        chart.addEventListener("mouseleave", onLeave);
        chart.addEventListener("touchstart", function (e) {
            if (e.touches[0]) onMove(e.touches[0]);
        }, { passive: true });
        chart.addEventListener("touchmove", function (e) {
            if (e.touches[0]) onMove(e.touches[0]);
        }, { passive: true });
        chart.addEventListener("touchend", onLeave);
    }

    function wireDynamic() {
        const trigger = $("#photo-trigger");
        if (trigger && !trigger.dataset.wired) {
            trigger.dataset.wired = "1";
            trigger.addEventListener("click", openPhoto);
        }
        wirePulseChart();
    }

    function wirePhotoInput() {
        const input = $("#kirana-photo-input");
        if (!input || input.dataset.wired === "1") return;
        input.dataset.wired = "1";
        input.addEventListener("change", function () {
            const file = input.files && input.files[0];
            if (file) uploadPhoto(file);
            input.value = "";
        });
    }

    function init() {
        if (window.__KIRANA_STATE__) {
            window.kirana._state = window.__KIRANA_STATE__;
        }
        wirePhotoInput();
        applyTheme(getStoredTheme());
        waitFor(".page-host", function (host) {
            applyTheme(getStoredTheme());
            processAfterRender();
            wireDynamic();

            let scheduled = false;
            let processing = false;
            function schedule() {
                if (scheduled || processing) return;
                scheduled = true;
                requestAnimationFrame(function () {
                    scheduled = false;
                    processing = true;
                    try {
                        wireDynamic();
                        processAfterRender();
                        applyTheme(getStoredTheme());
                    } finally {
                        // Drain any mutations our own processing produced before re-enabling
                        setTimeout(function () { processing = false; }, 0);
                    }
                });
            }

            const obs = new MutationObserver(function (mutations) {
                if (processing) return;
                // Only react to real content swaps (childList), not our own attribute writes
                for (let i = 0; i < mutations.length; i++) {
                    if (mutations[i].type === "childList" &&
                        (mutations[i].addedNodes.length || mutations[i].removedNodes.length)) {
                        schedule();
                        return;
                    }
                }
            });
            obs.observe(host, { childList: true, subtree: true });
        });
    }


    function createModalVoice() {
        let stream = null;
        let recorder = null;
        let chunks = [];
        let isRecording = false;

        function setStatus(msg) {
            const el = $("#voice-status");
            if (el) el.textContent = msg;
        }

        function setTranscript(msg) {
            const el = $("#voice-transcript");
            if (el) el.textContent = msg || "";
        }

        function setListening(on) {
            const mic = $("#voice-mic") || $(".voice-mic");
            if (mic) {
                mic.classList.toggle("is-listening", !!on);
                mic.setAttribute("aria-pressed", on ? "true" : "false");
                mic.setAttribute("aria-label", on ? "Stop recording" : "Start recording");
            }
            $("#voice-wave")?.classList.toggle("is-live", !!on);
        }

        async function start() {
            if (isRecording) {
                stop();
                return;
            }

            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                toast("Browser microphone recording is not available. Use audio upload.", "warn");
                setStatus("Mic recording unavailable. Use audio upload.");
                return;
            }

            try {
                stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                chunks = [];

                let mimeType = "";
                if (window.MediaRecorder && MediaRecorder.isTypeSupported("audio/webm")) {
                    mimeType = "audio/webm";
                } else if (window.MediaRecorder && MediaRecorder.isTypeSupported("audio/mp4")) {
                    mimeType = "audio/mp4";
                }

                recorder = mimeType
                    ? new MediaRecorder(stream, { mimeType: mimeType })
                    : new MediaRecorder(stream);

                recorder.ondataavailable = function (event) {
                    if (event.data && event.data.size > 0) chunks.push(event.data);
                };

                recorder.onstop = function () {
                    const type = recorder && recorder.mimeType ? recorder.mimeType : "audio/webm";
                    const ext = type.includes("mp4") ? "m4a" : "webm";
                    const blob = new Blob(chunks, { type: type });
                    cleanup();
                    sendBlob(blob, "voice-recording." + ext);
                };

                recorder.start();
                isRecording = true;
                setListening(true);
                setTranscript("");
                setStatus("Recording… click the mic again to stop.");
                toast("Recording audio…", "info");
            } catch (e) {
                console.error("[voice] mic recording failed", e);
                cleanup();
                setListening(false);
                setStatus("Microphone permission failed. Use audio upload.");
                toast("Microphone permission failed. Use audio upload.", "danger");
            }
        }

        function stop() {
            if (recorder && isRecording) {
                setStatus("Sending audio to Modal…");
                toast("Transcribing audio…", "info");
                recorder.stop();
            } else {
                cleanup();
            }
        }

        function cleanup() {
            isRecording = false;
            setListening(false);
            if (stream) {
                stream.getTracks().forEach(function (track) { track.stop(); });
            }
            stream = null;
            recorder = null;
        }

        function sendBlob(blob, filename) {
            if (!blob || blob.size === 0) {
                toast("No audio recorded.", "warn");
                setStatus("No audio recorded.");
                return;
            }

            const fd = new FormData();
            fd.append("state", JSON.stringify(window.kirana._state || {}));
            fd.append("audio", blob, filename || "voice-recording.webm");

            fetch("/api/speech", { method: "POST", body: fd })
                .then(function (r) {
                    if (!r.ok) throw new Error("Speech API failed: " + r.status);
                    return r.json();
                })
                .then(function (payload) {
                    applyResponse(payload);

                    const transcript =
                        payload &&
                        payload.state &&
                        payload.state.voice_result &&
                        payload.state.voice_result.transcript;

                    const inputText = $("#voice-text");
                    const transcriptBox = $("#voice-transcript");

                    if (transcript && inputText) inputText.value = transcript;
                    if (transcript && transcriptBox) transcriptBox.textContent = transcript;

                    setStatus(transcript ? "Transcribed with Modal." : "No transcript returned.");
                    toast(transcript ? "Speech transcribed" : "No transcript returned", transcript ? "success" : "warn");
                })
                .catch(function (e) {
                    console.error("[voice] Modal transcription failed", e);
                    setStatus("Speech transcription failed.");
                    toast("Speech transcription failed", "danger");
                });
        }

        function init() {
            const mic = $("#voice-mic") || $(".voice-mic");
            if (mic) {
                mic.removeAttribute("disabled");
                mic.onclick = function (event) {
                    event.preventDefault();
                    start();
                };
                mic.title = "Record audio and transcribe with Modal";
            }
            setStatus("Press the mic to record with Modal, then press again to stop.");
        }

        return {
            init: init,
            start: start,
            stop: stop,
        };
    }


    window.kirana = {
        _state: null,
        dispatch: dispatch,
        navigate: navigate,
        submitForm: submitForm,
        transcribeAudio: transcribeAudio,
        quickAction: quickAction,
        switchTab: switchTab,
        readForm: readForm,
        toast: toast,
        openPhoto: openPhoto,
        toggleSidebar: toggleSidebar,
        toggleTheme: toggleTheme,
        voice: createModalVoice(),
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
