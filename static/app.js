/* ============ AnyVideo Downloader — frontend logic ============ */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const urlInput = $("urlInput");
  const fetchBtn = $("fetchBtn");
  const loader = $("loader");
  const errorBox = $("errorBox");
  const result = $("result");
  const toast = $("toast");
  const dlFrame = $("dlFrame");

  let currentInfo = null;
  let toastTimer = null;

  /* ---------------- toast ---------------- */
  function showToast(msg, opts = {}) {
    clearTimeout(toastTimer);
    toast.innerHTML = "";
    if (opts.loading) {
      const s = document.createElement("span");
      s.className = "spinner";
      toast.appendChild(s);
    }
    const span = document.createElement("span");
    span.textContent = msg;
    toast.appendChild(span);
    toast.classList.remove("hidden");
    requestAnimationFrame(() => toast.classList.add("show"));
    if (!opts.sticky) {
      toastTimer = setTimeout(hideToast, opts.ms || 4200);
    }
  }
  function hideToast() {
    toast.classList.remove("show");
    toastTimer = setTimeout(() => toast.classList.add("hidden"), 300);
  }

  /* ---------------- history ---------------- */
  const HKEY = "avd_history_v1";
  function getHistory() {
    try { return JSON.parse(localStorage.getItem(HKEY) || "[]"); } catch { return []; }
  }
  function pushHistory(info) {
    const list = getHistory().filter((h) => h.id !== info.id);
    list.unshift({
      id: info.id, title: info.title, url: info.webpage_url,
      thumb: info.thumbnail, when: Date.now(),
    });
    localStorage.setItem(HKEY, JSON.stringify(list.slice(0, 8)));
    renderHistory();
  }
  function renderHistory() {
    const list = getHistory();
    const section = $("historySection");
    if (!list.length) { section.classList.add("hidden"); return; }
    section.classList.remove("hidden");
    const box = $("historyList");
    box.innerHTML = "";
    list.forEach((h) => {
      const item = document.createElement("div");
      item.className = "h-item";
      const img = document.createElement("img");
      img.src = h.thumb || "";
      img.loading = "lazy";
      img.referrerPolicy = "no-referrer";
      img.onerror = () => { img.style.display = "none"; };
      const t = document.createElement("div");
      t.className = "h-title";
      t.textContent = h.title;
      item.append(img, t);
      item.addEventListener("click", () => { urlInput.value = h.url; fetchInfo(); });
      box.appendChild(item);
    });
  }

  /* ---------------- helpers ---------------- */
  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }
  function fmtViews(n) {
    if (!n) return "";
    if (n >= 1e9) return (n / 1e9).toFixed(1) + "B views";
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M views";
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "K views";
    return n + " views";
  }

  function showError(bn, en) {
    errorBox.innerHTML = "";
    const p = document.createElement("div");
    p.textContent = bn;
    errorBox.appendChild(p);
    if (en && en !== bn) {
      const e = document.createElement("span");
      e.className = "en";
      e.textContent = en;
      errorBox.appendChild(e);
    }
    errorBox.classList.remove("hidden");
  }

  function setLoading(on) {
    fetchBtn.disabled = on;
    loader.classList.toggle("hidden", !on);
    errorBox.classList.add("hidden");
  }

  /* ---------------- fetch info ---------------- */
  async function fetchInfo() {
    const url = urlInput.value.trim();
    if (!url) { urlInput.focus(); return; }
    setLoading(true);
    result.classList.add("hidden");
    try {
      const r = await fetch("/api/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await r.json();
      if (!data.ok) { showError(data.error || "সমস্যা হয়েছে।", data.error_en); return; }
      currentInfo = data;
      renderResult(data);
      pushHistory(data);
    } catch {
      showError("সার্ভারে কানেক্ট করা যায়নি। পরে আবার চেষ্টা করুন।", "Could not reach the server.");
    } finally {
      setLoading(false);
    }
  }

  /* ---------------- render ---------------- */
  function renderResult(info) {
    $("thumb").src = info.thumbnail || "";
    $("thumb").onerror = () => { $("thumb").style.visibility = "hidden"; };
    $("thumb").style.visibility = "visible";
    $("durationBadge").textContent = info.duration_string || "";
    $("platformBadge").textContent = info.extractor || "video";
    $("viewsBadge").textContent = fmtViews(info.view_count);
    $("videoTitle").textContent = info.title || "Untitled";
    $("uploader").textContent = info.uploader ? "👤 " + info.uploader : "";

    renderVideos(info);
    renderAudios(info);
    setTab("video");
    result.classList.remove("hidden");
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function dlLinkParams(info, mode, fid, q) {
    const p = new URLSearchParams({
      url: info.webpage_url || urlInput.value.trim(),
      mode, fid: fid || "", q: q || "", t: info.title || "video",
    });
    return "/download?" + p.toString();
  }

  function makeBtn({ label, ext, sub, badges, mp3, onClick }) {
    const b = document.createElement("button");
    b.className = "q-btn" + (mp3 ? " audio-mp3" : "");
    const top = document.createElement("div");
    top.className = "q-top";
    top.innerHTML = `<span class="q-label">${esc(label)}</span>` +
      (ext ? `<span class="q-ext">${esc(ext)}</span>` : "") +
      (badges || []).map((x) => `<span class="q-badge ${x.cls || ""}">${esc(x.txt)}</span>`).join("");
    const s = document.createElement("div");
    s.className = "q-sub";
    s.textContent = sub || "";
    b.append(top, s);
    b.addEventListener("click", onClick);
    return b;
  }

  function renderVideos(info) {
    const panel = $("panel-video");
    panel.innerHTML = "";
    const vids = info.video || [];
    if (!vids.length) {
      panel.innerHTML = `<div class="no-fmt">কোনো ভিডিও ফরম্যাট পাওয়া যায়নি।</div>`;
      return;
    }
    let hasMerge = false;
    vids.forEach((v) => {
      if (v.needs_merge) hasMerge = true;
      const badges = [];
      if (["720", "1080", "1440", "2160"].includes(String(v.height))) badges.push({ txt: "HD", cls: "" });
      if (v.needs_merge) badges.push({ txt: "MERGE", cls: "merge" });
      panel.appendChild(makeBtn({
        label: v.quality,
        ext: "MP4",
        sub: [v.filesize_string || null, v.fps ? v.fps + "fps" : null].filter(Boolean).join(" • "),
        badges,
        onClick: () => startDownload({
          mode: "video", fid: v.format_id, q: v.quality,
          needsMerge: v.needs_merge, quality: v.quality,
        }),
      }));
    });
    $("mergeNote").classList.toggle("hidden", !hasMerge);
  }

  function renderAudios(info) {
    const panel = $("panel-audio");
    panel.innerHTML = "";

    panel.appendChild(makeBtn({
      label: "MP3", ext: "192kbps",
      sub: "সেরা কোয়ালিটি • সব ডিভাইসে চলে",
      mp3: true,
      onClick: () => startDownload({ mode: "audio-mp3", fid: "", q: "", needsMerge: true, quality: "MP3" }),
    }));

    (info.audio || []).forEach((a) => {
      panel.appendChild(makeBtn({
        label: a.quality || a.ext.toUpperCase(),
        ext: a.ext.toUpperCase(),
        sub: a.filesize_string || "original audio",
        onClick: () => startDownload({
          mode: "audio", fid: a.format_id, q: a.quality,
          needsMerge: false, quality: a.ext.toUpperCase(),
        }),
      }));
    });
  }

  /* ---------------- tabs ---------------- */
  function setTab(name) {
    document.querySelectorAll(".tab").forEach((t) =>
      t.classList.toggle("active", t.dataset.tab === name)
    );
    $("panel-video").classList.toggle("hidden", name !== "video");
    $("panel-audio").classList.toggle("hidden", name !== "audio");
  }
  document.querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => setTab(t.dataset.tab))
  );

  /* ---------------- download ---------------- */
  function startDownload({ mode, fid, q, needsMerge, quality }) {
    if (!currentInfo) return;
    const href = dlLinkParams(currentInfo, mode, fid, q);
    if (needsMerge) {
      showToast(
        `${quality} প্রস্তুত হচ্ছে… সার্ভারে প্রসেস হচ্ছে (১০–৬০ সেকেন্ড)। ডাউনলোড শুরু হলে ব্রাউজার নিজেই সেভ করবে — এই পেজ বন্ধ করবেন না।`,
        { loading: true, sticky: true }
      );
      setTimeout(hideToast, 90000);
    } else {
      showToast(`${quality} ডাউনলোড শুরু হয়েছে ✓`, { ms: 3000 });
    }
    dlFrame.src = href; // hidden iframe → keeps page usable, triggers save dialog
  }

  /* ---------------- wire up ---------------- */
  fetchBtn.addEventListener("click", fetchInfo);
  urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") fetchInfo(); });
  urlInput.addEventListener("paste", () => setTimeout(fetchInfo, 60));

  $("pasteBtn").addEventListener("click", async () => {
    try {
      const txt = await navigator.clipboard.readText();
      if (txt) { urlInput.value = txt.trim(); fetchInfo(); }
    } catch {
      urlInput.focus();
      showToast("ব্রাউজার পারমিশন দিল না — Ctrl+V দিয়ে পেস্ট করুন", { ms: 3000 });
    }
  });

  renderHistory();
})();
