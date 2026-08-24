/* 竹梅前端：主題切換、活動河道篩選、日曆檢視。無相依套件。 */
(function () {
  "use strict";

  // ---- 外觀（Appearance，Threads 式子面板）：主題＋字標順序 ----
  (function () {
    function applyTheme(v) {
      var root = document.documentElement;
      try {
        if (v === "auto") { localStorage.removeItem("theme"); }
        else { localStorage.setItem("theme", v); }
      } catch (e) {}
      root.dataset.theme = v === "auto"
        ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
        : v;
      window.dispatchEvent(new CustomEvent("chumei-theme"));
    }
    function applyOrder(o) {
      try {
        if (o === "meichu") localStorage.setItem("brand-order", o);
        else localStorage.removeItem("brand-order");
      } catch (e) {}
      document.querySelectorAll(".brand").forEach(function (b) {
        var chu = b.querySelector(".brand-chu"), mei = b.querySelector(".brand-mei");
        if (!chu || !mei) return;
        if (o === "meichu") b.insertBefore(mei, chu); else b.insertBefore(chu, mei);
      });
    }
    function stored(k, dflt) { try { return localStorage.getItem(k) || dflt; } catch (e) { return dflt; } }
    applyOrder(stored("brand-order", "chumei"));
    // 自動模式下跟隨系統深淺色即時切換
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (e) {
      if (stored("theme", "") === "") {
        document.documentElement.dataset.theme = e.matches ? "dark" : "light";
        window.dispatchEvent(new CustomEvent("chumei-theme"));
      }
    });

    var toggle = document.getElementById("theme-toggle");
    if (!toggle) return;
    var menu = toggle.closest(".nav-more-menu");
    if (!menu) return;
    var CHEV = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6l-6 6"/></svg>';
    var BACK = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l14 0"/><path d="M5 12l6 6"/><path d="M5 12l6 -6"/></svg>';

    var main = document.createElement("div");
    while (menu.firstChild) main.appendChild(menu.firstChild);
    var open = document.createElement("button");
    open.className = "appear-open";
    open.innerHTML = "<span>外觀</span>" + CHEV;
    main.replaceChild(open, main.querySelector("#theme-toggle"));

    function seg(key, opts, cur) {
      return '<div class="appear-seg" data-key="' + key + '">' + opts.map(function (o) {
        return '<button data-v="' + o[0] + '" aria-pressed="' + (o[0] === cur) + '">' + o[1] + "</button>";
      }).join("") + "</div>";
    }
    var appear = document.createElement("div");
    appear.hidden = true;
    appear.innerHTML =
      '<div class="appear-head"><button class="appear-back" aria-label="返回">' + BACK + "</button><strong>外觀</strong></div>" +
      '<div class="appear-label">主題</div>' +
      seg("theme", [["light", "淺色"], ["dark", "深色"], ["auto", "自動"]], stored("theme", "auto")) +
      '<div class="appear-label">字標順序</div>' +
      seg("order", [["chumei", "竹梅"], ["meichu", "梅竹"]], stored("brand-order", "chumei"));
    menu.appendChild(main); menu.appendChild(appear);

    menu.addEventListener("click", function (ev) {
      if (ev.target.closest(".appear-open")) { main.hidden = true; appear.hidden = false; return; }
      if (ev.target.closest(".appear-back")) { appear.hidden = true; main.hidden = false; return; }
      var b = ev.target.closest(".appear-seg button");
      if (!b) return;
      var host = b.closest(".appear-seg");
      host.querySelectorAll("button").forEach(function (x) {
        x.setAttribute("aria-pressed", String(x === b));
      });
      if (host.dataset.key === "theme") applyTheme(b.dataset.v);
      else applyOrder(b.dataset.v);
    });
    // 收合更多選單時回到主選單視圖
    var more = menu.closest("details.nav-more");
    if (more) more.addEventListener("toggle", function () {
      if (!more.open) { appear.hidden = true; main.hidden = false; }
    });
  })();

  // ---- 桌機側欄：把常用工具拉出「更多」，手機仍維持原本底部導覽 ----
  (function () {
    var nav = document.querySelector(".site-nav");
    var more = nav && nav.querySelector(".nav-more");
    var menu = more && more.querySelector(".nav-more-menu");
    if (!nav || !more || !menu) return;
    var SVG_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';
    var items = [
      {
        href: "/notify/",
        label: "App 通知",
        icon: '<path d="M10 5a2 2 0 0 1 4 0a7 7 0 0 1 4 6v3l2 2H4l2-2v-3a7 7 0 0 1 4-6"/><path d="M9 19a3 3 0 0 0 6 0"/>'
      },
      {
        href: "/source/",
        label: "資料來源",
        icon: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>'
      }
    ];
    items.forEach(function (item) {
      var a = document.createElement("a");
      a.className = "nav-item nav-desktop-extra";
      a.href = item.href;
      a.innerHTML = SVG_OPEN + item.icon + '</svg><span class="nav-label">' + item.label + "</span>";
      nav.insertBefore(a, more);
      var duplicate = menu.querySelector('a[href="' + item.href + '"]');
      if (duplicate) {
        duplicate.textContent = item.label;
        duplicate.classList.add("nav-mobile-extra");
      }
    });
    document.querySelectorAll('a[href="/notify/"]').forEach(function (a) {
      if ((a.textContent || "").trim() === "推播與追蹤") a.textContent = "App 通知";
      if (a.getAttribute("aria-label") === "推播與追蹤") a.setAttribute("aria-label", "App 通知");
    });
  })();

  // ---- 分享按鈕（詳情頁）：行動裝置系統分享，桌機複製連結＋LINE ----
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest(".btn-share");
    if (!b) return;
    var url = b.dataset.url, title = b.dataset.title;
    if (navigator.share) {
      navigator.share({ title: title, url: url }).catch(function () {});
      return;
    }
    var existing = document.querySelector(".share-pop");
    if (existing) { existing.remove(); return; }
    var pop = document.createElement("div");
    pop.className = "share-pop";
    pop.innerHTML = '<button class="share-copy">複製連結</button>' +
      '<a href="https://social-plugins.line.me/lineit/share?url=' + encodeURIComponent(url) + '" target="_blank" rel="noopener">LINE 分享</a>';
    b.parentNode.insertBefore(pop, b.nextSibling);
    pop.querySelector(".share-copy").addEventListener("click", function () {
      navigator.clipboard.writeText(url).then(function () {
        pop.querySelector(".share-copy").textContent = "已複製 ✓";
        setTimeout(function () { pop.remove(); }, 1200);
      });
    });
    document.addEventListener("click", function close(e2) {
      if (!pop.contains(e2.target) && e2.target !== b) { pop.remove(); document.removeEventListener("click", close); }
    });
  });

  // ---- 導覽：當前頁高亮；details 彈出選單點外自動收合 ----
  (function () {
    var path = location.pathname;
    document.querySelectorAll(".site-nav a.nav-item").forEach(function (a) {
      var h = a.getAttribute("href");
      if (h === "/" ? path === "/" : path.indexOf(h) === 0) a.setAttribute("aria-current", "page");
    });
    document.addEventListener("click", function (e) {
      document.querySelectorAll("details.post-menu[open], details.feed-filters[open], details.nav-more[open], details.col-picker[open], details.addcol[open]").forEach(function (d) {
        // 手機上 .filters 內的篩選是行內展開（非 popover），不做點外收合
        if (window.innerWidth <= 700 && d.classList.contains("feed-filters") && d.closest(".filters")) return;
        if (!d.contains(e.target)) d.open = false;
      });
    });
    // 篩選 popover 打開時夾回可視範圍：錨點靠左時右對齊的面板會伸進固定左欄／視窗外
    document.addEventListener("toggle", function (e) {
      var d = e.target;
      if (!d || !d.classList || !d.classList.contains("feed-filters") || !d.open) return;
      var panel = d.querySelector(".feed-filters-panel");
      if (!panel || getComputedStyle(panel).position !== "absolute") return;
      panel.style.transform = "";
      var r = panel.getBoundingClientRect();
      var minLeft = 14, maxRight = window.innerWidth - 14;
      var header = document.querySelector(".site-header");
      if (window.innerWidth > 699 && header) minLeft = header.getBoundingClientRect().right + 14;
      var shift = 0;
      if (r.left < minLeft) shift = minLeft - r.left;
      else if (r.right > maxRight) shift = maxRight - r.right;
      if (shift) panel.style.transform = "translateX(" + shift + "px)";
    }, true);
  })();

  // ---- 手機全域搜尋（Threads 式）：頂欄右上 🔍 → 全螢幕搜尋層（單位＋活動） ----
  (function () {
    var header = document.querySelector(".site-header");
    if (!header) return;
    var SVGO = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';
    var btn = document.createElement("button");
    btn.className = "topbar-search";
    btn.setAttribute("aria-label", "搜尋");
    btn.innerHTML = SVGO + '<path d="M10 10m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0"/><path d="M21 21l-6 -6"/></svg>';
    header.appendChild(btn);

    var sdata = null, ov = null, sT;
    function loadData() {
      if (sdata) return Promise.resolve(sdata);
      return Promise.all([
        fetch("/data/posts.json").then(function (r) { return r.json(); }).catch(function () { return null; }),
        fetch("/data/sources.json").then(function (r) { return r.json(); }).catch(function () { return null; })
      ]).then(function (rs) {
        var seen = {}, events = [];
        (((rs[0] || {}).posts) || []).forEach(function (p) {
          p.events.forEach(function (e) { if (!seen[e.id]) { seen[e.id] = 1; events.push(e); } });
        });
        sdata = { events: events, orgs: ((rs[1] || {}).entries) || [] };
        return sdata;
      });
    }
    function evSchool(e) {
      return /nthu/.test(e.campus || "") ? "nthu" : /nycu|yangming/.test(e.campus || "") ? "nycu" : "";
    }
    function results(q) {
      var body = ov.querySelector(".search-ov-body");
      q = q.trim().toLowerCase();
      if (!q) { body.innerHTML = '<p class="empty">搜尋社團、單位或活動名稱。</p>'; return; }
      if (!sdata) { body.innerHTML = '<p class="empty">載入中…</p>'; return; }
      var orgs = sdata.orgs.filter(function (o) { return o.name.toLowerCase().indexOf(q) !== -1; }).slice(0, 6);
      var now = Date.now();
      var evs = sdata.events.filter(function (e) { return e.title.toLowerCase().indexOf(q) !== -1; });
      evs.sort(function (a, b) {
        var ta = new Date(a.start_at).getTime(), tb = new Date(b.start_at).getTime();
        var fa = ta >= now, fb = tb >= now;
        if (fa !== fb) return fa ? -1 : 1;   // 未來的排前
        return fa ? ta - tb : tb - ta;       // 未來近→遠；過去新→舊
      });
      evs = evs.slice(0, 10);
      var html = "";
      if (orgs.length) {
        html += '<p class="sr-sec">社團與單位</p>' + orgs.map(function (o) {
          var av = o.avatar
            ? '<img class="sr-avatar" src="' + esc(o.avatar) + '" alt="">'
            : '<span class="sr-avatar src-avatar-fallback av-' + esc(o.school) + '">' + esc(o.name.charAt(0)) + "</span>";
          return '<a class="sr-org" href="/org/' + o.id + '/">' + av +
            '<span class="sr-org-main"><strong>' + esc(o.name) + "</strong>" +
            '<span class="sub">' + (o.events ? o.events + " 場活動" : "尚無收錄活動") + "</span></span></a>";
        }).join("");
      }
      if (evs.length) {
        html += '<p class="sr-sec">活動</p><div class="col-agd">' + evs.map(function (e) {
          var d = new Date(e.start_at);
          var sc = evSchool(e);
          return '<a class="agd-ev' + (sc ? " ev-" + sc : "") + '" href="/event/' + e.id + '/">' +
            '<span class="agd-when">' + (d.getMonth() + 1) + "/" + d.getDate() + "</span>" +
            '<span class="agd-main"><span class="agd-title">' + esc(e.title) + "</span>" +
            (e.venue ? '<span class="agd-meta">' + esc(e.venue) + "</span>" : "") + "</span></a>";
        }).join("") + "</div>";
      }
      html += '<a class="sr-more" href="/events/?q=' + encodeURIComponent(q) + '">在活動總覽搜尋「' + esc(q) + '」→</a>';
      if (!orgs.length && !evs.length) html = '<p class="empty">沒有符合的社團或活動。</p>' + html;
      body.innerHTML = html;
    }
    function close() {
      if (!ov) return;
      ov.remove(); ov = null;
      document.body.style.overflow = "";
    }
    btn.addEventListener("click", function () {
      if (ov) return;
      ov = document.createElement("div");
      ov.className = "search-ov";
      ov.innerHTML = '<div class="search-ov-bar">' +
        '<input type="search" placeholder="搜尋社團、單位、活動…" aria-label="全站搜尋">' +
        '<button class="search-ov-cancel">取消</button></div>' +
        '<div class="search-ov-body"><p class="empty">搜尋社團、單位或活動名稱。</p></div>';
      document.body.appendChild(ov);
      document.body.style.overflow = "hidden";
      var input = ov.querySelector("input");
      input.focus();
      loadData().then(function () { if (ov && input.value) results(input.value); });
      input.addEventListener("input", function () {
        clearTimeout(sT);
        sT = setTimeout(function () { if (ov) results(input.value); }, 120);
      });
      ov.querySelector(".search-ov-cancel").addEventListener("click", close);
      input.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
    });
  })();

  // 更多篩選：舊式行內摺疊才在桌機自動展開；.feed-filters popover 一律預設收合
  (function () {
    var mf = document.getElementById("more-filters");
    if (!mf || mf.classList.contains("feed-filters")) return;
    if (window.innerWidth > 700) mf.open = true;
    window.addEventListener("resize", function () {
      if (window.innerWidth > 700) mf.open = true;
    });
  })();

  // 限動資料/燈箱的共享介面：首頁「限時動態」欄也要用（須在提前 return 前賦值）
  var storyShare = { data: null, open: null, hooks: [] };

  var listEl = document.getElementById("event-list");
  var calEl = document.getElementById("cal-months");
  initStories();
  initSources();
  initFeed();
  if (!listEl && !calEl) return;

  fetch("/data/events.json")
    .then(function (r) { return r.json(); })
    .then(function (bundle) {
      if (listEl) initList(bundle);
      if (calEl) initCalendar(bundle);
    })
    .catch(function (err) {
      console.error("chumei init failed:", err);
      var el = listEl || calEl;
      // SSR 已預渲染預設檢視；抓不到 events.json 就留著靜態內容
      if (!el.firstElementChild) el.innerHTML = '<p class="empty">活動資料載入失敗，請稍後再試。</p>';
    });

  // ---- 首頁貼文河道 ----
  function initFeed() {
    var feed = document.getElementById("post-feed");
    if (!feed) return;
    var PLAT = { instagram: "IG", facebook: "FB", threads: "Threads", x: "X", bulletin: "公告", api: "官方" };

    fetch("/data/posts.json").then(function (r) { return r.json(); }).then(function (data) {
      var posts = data.posts;
      // 手機單欄的全域篩選＋檢視切換；桌機欄位各自帶篩選（見 cols）
      var state = { school: "all", platform: "all", cat: "all", org: "all", q: "" };
      var params = new URLSearchParams(location.search);
      var seededFromUrl = false;
      Object.keys(state).forEach(function (k) { if (params.get(k)) { state[k] = params.get(k); seededFromUrl = true; } });
      var activeCol = 0;
      function pagerMode() { return window.innerWidth < 1080; }

      var groups = {};
      function chips(id, options, key, cls) {
        var host = document.getElementById(id);
        if (!host) return;
        groups[key] = { options: options, buttons: {} };
        options.forEach(function (opt) {
          var b = document.createElement("button");
          b.className = cls || "fchip";
          b.dataset.value = opt[0];
          b.innerHTML = '<span class="fchip-label">' + esc(opt[1]) + "</span>" +
            (cls ? "" : '<span class="fchip-count" aria-hidden="true"></span>');
          b.setAttribute("aria-pressed", String(state[key] === opt[0]));
          groups[key].buttons[opt[0]] = b;
          b.addEventListener("click", function () {
            state[key] = opt[0];
            host.querySelectorAll("[data-value]").forEach(function (x) {
              x.setAttribute("aria-pressed", String(x.dataset.value === opt[0]));
            });
            applyFilterToCol(key, opt[0]);
          });
          host.appendChild(b);
        });
      }
      var SCHOOL_OPTS = [["all", "全部"], ["nthu", "清大"], ["nycu", "陽明交大"], ["both", "兩校聯合"]];
      var PLAT_OPTS = [["all", "全部"], ["instagram", "IG"], ["facebook", "FB"], ["threads", "Threads"], ["bulletin", "公告"]];
      var ORG_OPTS = [["all", "全部主辦"], ["official", "校方"], ["department", "系所"], ["club", "社團"], ["external", "校外"]];
      var feedCats = {};
      posts.forEach(function (p) { p.events.forEach(function (e) { feedCats[e.category || "其他"] = 1; }); });
      var CAT_OPTS = [["all", "全部類型"]].concat(Object.keys(feedCats).sort().map(function (k) { return [k, k]; }));

      chips("pf-school", SCHOOL_OPTS, "school");
      chips("pf-platform", PLAT_OPTS, "platform");
      chips("pf-cat", CAT_OPTS, "cat");
      chips("pf-org", ORG_OPTS, "org");

      var search = document.getElementById("search");
      if (search) {
        search.value = state.q;
        search.addEventListener("input", function () { state.q = search.value.trim(); applyFilterToCol("q", state.q); });
      }

      // 手機分頁模式：頂欄篩選＝「這一欄」的篩選；桌機沿用整體重繪
      function applyFilterToCol(key, value) {
        var c = cols[activeCol];
        if (pagerMode() && c && c.t === "feed") {
          c[key] = value;
          saveCols(); updateBodies(); refreshMeta();
          return;
        }
        render();
      }
      function syncFilterUI() {
        var c = cols[activeCol];
        if (!c || c.t !== "feed") return;
        ["school", "platform", "cat", "org", "q"].forEach(function (k) { state[k] = c[k]; });
        Object.keys(groups).forEach(function (k) {
          Object.keys(groups[k].buttons).forEach(function (v) {
            groups[k].buttons[v].setAttribute("aria-pressed", String(state[k] === v));
          });
        });
        if (search && document.activeElement !== search) search.value = state.q;
      }

      function matches(p, f) {
        if (f.school && f.school !== "all" && p.school !== f.school && !(f.school !== "both" && p.school === "both")) return false;
        if (f.platform && f.platform !== "all" && p.platform !== f.platform) return false;
        if (f.cat && f.cat !== "all" && !p.events.some(function (e) { return (e.category || "其他") === f.cat; })) return false;
        if (f.org && f.org !== "all" && p.org_type !== f.org) return false;
        if (f.q) {
          var hay = ((p.source_name || "") + " " + (p.text || "") + " " +
            p.events.map(function (e) { return e.title; }).join(" ")).toLowerCase();
          if (hay.indexOf(f.q.toLowerCase()) === -1) return false;
        }
        return true;
      }

      function ago(iso) {
        var ms = Math.max(0, Date.now() - new Date(iso).getTime());
        var h = ms / 36e5;
        if (h < 1) return Math.max(1, Math.round(h * 60)) + " 分鐘前";
        if (h < 24) return Math.round(h) + " 小時前";
        var d = new Date(iso);
        return (d.getMonth() + 1) + "/" + d.getDate();
      }

      var SVG_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';
      var I = {
        dots: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/></svg>',
        cal: SVG_OPEN + '<path d="M4 5m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z"/><path d="M16 3l0 4"/><path d="M8 3l0 4"/><path d="M4 11l16 0"/><path d="M8 15h2v2h-2z"/></svg>',
        send: SVG_OPEN + '<path d="M10 14l11 -11"/><path d="M21 3l-6.5 18a.55 .55 0 0 1 -1 0l-3.5 -7l-7 -3.5a.55 .55 0 0 1 0 -1l18 -6.5"/></svg>',
        ext: SVG_OPEN + '<path d="M12 6h-6a2 2 0 0 0 -2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-6"/><path d="M11 13l9 -9"/><path d="M15 4h5v5"/></svg>',
        heart: SVG_OPEN + '<path d="M10 5a2 2 0 1 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3h-16a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6"/><path d="M9 17v1a3 3 0 0 0 6 0v-1"/></svg>'
      };

      function evChip(e) {
        var d = new Date(e.start_at);
        var when = (d.getMonth() + 1) + "/" + d.getDate() +
          (e.all_day ? "" : " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"));
        return '<a class="feed-ev" data-id="' + esc(e.id) + '" href="/event/' + e.id + '/">' +
          '<span class="feed-ev-date">' + esc(when) + '</span><span class="feed-ev-title">' + esc(e.title) + "</span></a>";
      }

      function row(p) {
        var avatar = p.avatar
          ? '<img class="feed-avatar" src="' + esc(p.avatar) + '" alt="">'
          : '<span class="feed-avatar src-avatar-fallback av-' + esc(p.school) + '">' +
            esc((p.source_name || "？").replace(/^(清大|交大|陽明|國立)/, "").charAt(0)) + "</span>";
        var orgHref = p.org_id ? '/org/' + p.org_id + '/' : null;
        var avatarEl = orgHref
          ? '<a class="feed-org-link" href="' + orgHref + '" aria-label="' + esc(p.source_name || "") + ' 的單位頁">' + avatar + "</a>"
          : avatar;
        var schoolLabel = (data.labels.school || {})[p.school] || "";
        var menuItems =
          (p.url ? '<a href="' + esc(p.url) + '" target="_blank" rel="noopener">查看原文（' + esc(PLAT[p.platform] || p.platform) + "）↗</a>" : "") +
          (orgHref ? '<a href="' + orgHref + '">單位頁面</a>' : "");
        var menu = menuItems
          ? '<details class="post-menu"><summary aria-label="更多選項">' + I.dots + '</summary><div class="post-menu-panel">' + menuItems + "</div></details>"
          : "";
        var head = '<div class="feed-head">' +
          '<strong class="feed-name">' + (orgHref ? '<a class="feed-org-link" href="' + orgHref + '">' + esc(p.source_name || "") + "</a>" : esc(p.source_name || "")) + "</strong>" +
          (schoolLabel ? '<span class="feed-topic"><span class="sep">›</span>' + esc(schoolLabel) + "</span>" : "") +
          '<span class="feed-time">' + esc(ago(p.posted_at)) + "</span>" + menu + "</div>";
        var body = (p.text ? '<p class="feed-text">' + esc(p.text) + "</p>" : "") +
          (p.image ? '<img class="feed-img" src="' + esc(p.image) + '" alt="" loading="lazy">' : "");
        var evs = p.events.length ? '<div class="feed-evs">' + p.events.map(evChip).join("") + "</div>" : "";
        var ev0 = p.events[0];
        var shareUrl = ev0 ? location.origin + "/event/" + ev0.id + "/" : (p.url || location.origin);
        var shareTitle = ev0 ? ev0.title : (p.source_name || "竹梅活動觀測站");
        var actions = '<div class="feed-actions">' +
          (p.org_id ? '<button class="feed-action heart-btn" data-org-id="' + p.org_id + '" data-org-name="' + esc(p.source_name || "") + '" aria-pressed="false" title="追蹤 ' + esc(p.source_name || "") + '">' + I.heart + "</button>" : "") +
          (ev0 ? '<a class="feed-action" href="/event/' + ev0.id + '/" title="活動詳情">' + I.cal +
            (p.events.length > 1 ? "<span>" + p.events.length + "</span>" : "") + "</a>" : "") +
          '<button class="feed-action btn-share" data-url="' + esc(shareUrl) + '" data-title="' + esc(shareTitle) + '" title="分享">' + I.send + "</button>" +
          (p.url ? '<a class="feed-action" href="' + esc(p.url) + '" target="_blank" rel="noopener" title="開啟原文">' + I.ext + "</a>" : "") +
          "</div>";
        return '<article class="feed-post">' + avatarEl + '<div class="feed-content">' + head + body + evs + actions + "</div></article>";
      }

      var shown = 30;
      // 欄位模型：欄就是「貼文」（篩選自帶：學校/平台/類型/主辦/搜尋）或「即將活動」
      var SCHOOL_L = { all: "全部", nthu: "清大", nycu: "陽明交大", both: "兩校聯合" };
      function feedCol(school) { return { t: "feed", school: school || "all", platform: "all", cat: "all", org: "all", q: "" }; }
      var cols = (function () {
        try {
          var s = JSON.parse(localStorage.getItem("chumei-cols") || "null");
          if (Array.isArray(s) && s.length) {
            var out = s.map(function (c) {
              if (typeof c === "string") return c === "events" ? { t: "events" } : (SCHOOL_L[c] ? feedCol(c) : null); // 舊格式遷移
              if (c && (c.t === "events" || c.t === "stories")) return { t: c.t };
              if (c && c.t === "feed") return {
                t: "feed", school: SCHOOL_L[c.school] ? c.school : "all",
                platform: c.platform || "all", cat: c.cat || "all",
                org: c.org || "all", q: typeof c.q === "string" ? c.q : ""
              };
              return null;
            }).filter(Boolean).slice(0, 6);
            if (out.length) return out;
          }
        } catch (e) {}
        return [feedCol("nthu"), feedCol("nycu"), { t: "events" }];
      })();
      function saveCols() { try { localStorage.setItem("chumei-cols", JSON.stringify(cols)); } catch (e) {} }

      var CARET = SVG_OPEN + '<path d="M6 9l6 6l6 -6"/></svg>';
      var ADD_RIVER_ICON = SVG_OPEN +
        '<path d="M4 5a2 2 0 0 1 2 -2h9a2 2 0 0 1 2 2v14a2 2 0 0 1 -2 2h-9a2 2 0 0 1 -2 -2z"/>' +
        '<path d="M9 3v18"/><path d="M14 12h6"/><path d="M17 9v6"/></svg>';
      function addColMenu() {
        return '<div class="addcol-menu"><div class="addcol-title">新增河道</div>' +
          '<button data-add="feed"><span class="feed-col-dot dot-all"></span>貼文</button>' +
          '<button data-add="events"><span class="feed-col-dot dot-events"></span>即將活動</button>' +
          '<button data-add="stories"><span class="feed-col-dot dot-stories"></span>限時動態</button></div>';
      }
      function deckAddHtml() {
        return '<details class="deck-add"><summary aria-label="新增河道">' + ADD_RIVER_ICON +
          '</summary>' + addColMenu() + '</details>';
      }
      function upcomingEvents() {
        var seen = {}, evs = [];
        posts.forEach(function (p) {
          p.events.forEach(function (e) { if (!seen[e.id]) { seen[e.id] = 1; evs.push(e); } });
        });
        var today = new Date(); today.setHours(0, 0, 0, 0);
        return evs.filter(function (e) {
          var t = new Date(e.start_at).getTime();
          return !isNaN(t) && t >= today.getTime();
        }).sort(function (a, b) { return new Date(a.start_at) - new Date(b.start_at); });
      }
      function colTitle(c) {
        if (c.t === "events") return { label: "即將活動", dot: "events" };
        if (c.t === "stories") return { label: "限時動態", dot: "stories" };
        return { label: c.school === "all" ? "貼文" : SCHOOL_L[c.school], dot: c.school === "all" ? "all" : c.school };
      }
      function colFilterActive(c) {
        return c.t === "feed" && (c.platform !== "all" || c.cat !== "all" || c.org !== "all" || !!c.q);
      }
      function menuRow(label, key, opts, cur) {
        return '<div class="filter-row"><span class="label">' + label + '</span><span class="fgroup">' +
          opts.map(function (o) {
            return '<button class="fchip" data-ck="' + key + '" data-cv="' + o[0] + '" aria-pressed="' + (o[0] === cur) + '">' +
              '<span class="fchip-label">' + esc(o[1]) + "</span></button>";
          }).join("") + "</span></div>";
      }
      function colMenu(c) {
        var inner = c.t !== "feed" ? "" :
          '<input class="cf-q" type="search" placeholder="搜尋貼文、社團…" aria-label="搜尋這一欄" value="' + esc(c.q) + '">' +
          menuRow("學校", "school", SCHOOL_OPTS, c.school) +
          menuRow("平台", "platform", PLAT_OPTS, c.platform) +
          menuRow("類型", "cat", CAT_OPTS, c.cat) +
          menuRow("主辦", "org", ORG_OPTS, c.org);
        return '<div class="col-picker-menu col-menu-filters">' + inner +
          (cols.length > 1 ? '<button class="col-remove">移除這一欄</button>' : "") + "</div>";
      }
      function computeBuckets() {
        // 兩校聯合貼文在「校別」貼文欄只出現一次（輪流分配）；其餘欄各自照篩選
        var buckets = cols.map(function () { return []; });
        var evs = null, schoolIdx = [];
        cols.forEach(function (c, i) {
          if (c.t === "feed" && (c.school === "nthu" || c.school === "nycu")) schoolIdx.push(i);
          if (c.t === "events" && !evs) evs = upcomingEvents();
        });
        var rr = 0;
        posts.forEach(function (p) {
          cols.forEach(function (c, i) {
            if (c.t !== "feed") return;
            if (c.school === "nthu" || c.school === "nycu") {
              if (p.school === c.school && matches(p, c)) buckets[i].push(p);
            } else if (matches(p, c)) buckets[i].push(p);
          });
          if (p.school === "both" && schoolIdx.length) {
            for (var t = 0; t < schoolIdx.length; t++) {
              var i2 = schoolIdx[(rr + t) % schoolIdx.length];
              if (matches(p, Object.assign({}, cols[i2], { school: "all" }))) {
                buckets[i2].push(p); rr++; break;
              }
            }
          }
        });
        cols.forEach(function (c, i) {
          if (c.t === "events") buckets[i] = evs || [];
          if (c.t === "stories") buckets[i] = storyShare.data ? storyShare.data.flat : [];
        });
        return buckets;
      }
      function moreBtn(list, unit) {
        return list.length > shown ? '<button class="fchip feed-more">載入更多（還有 ' + (list.length - shown) + unit + "）</button>" : "";
      }
      // 即將活動：日期分組的議程卡（時間｜標題｜校區・地點・類型），重用日曆頁樣式
      function evAgenda(list) {
        var labels = data.labels || {};
        var today = new Date(); today.setHours(0, 0, 0, 0);
        var out = "", lastDay = "";
        list.slice(0, shown).forEach(function (e) {
          var d = new Date(e.start_at);
          var day = (d.getMonth() + 1) + "/" + d.getDate();
          if (day !== lastDay) {
            lastDay = day;
            var d0 = new Date(d); d0.setHours(0, 0, 0, 0);
            var diff = Math.round((d0 - today) / 864e5);
            var tag = diff === 0 ? " ・ 今天" : diff === 1 ? " ・ 明天" : "";
            out += '<span class="agd-date">' + day + "（" + "日一二三四五六"[d.getDay()] + "）" + tag + "</span>";
          }
          var school = /nthu/.test(e.campus || "") ? "nthu" : /nycu|yangming/.test(e.campus || "") ? "nycu" : "";
          var when = e.all_day ? "全天" : String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
          var meta = [(labels.campus || {})[e.campus] || "", e.venue || "", e.category || ""].filter(Boolean).join(" ・ ");
          out += '<a class="agd-ev' + (school ? " ev-" + school : "") + '" data-id="' + esc(e.id) + '" href="/event/' + e.id + '/">' +
            '<span class="agd-when">' + esc(when) + '</span><span class="agd-main">' +
            '<span class="agd-title">' + esc(e.title) + "</span>" +
            (meta ? '<span class="agd-meta">' + esc(meta) + "</span>" : "") + "</span></a>";
        });
        return '<div class="col-agd">' + out + "</div>";
      }
      function storyCards(list) {
        if (!storyShare.data) return '<p class="empty">限時動態載入中…</p>';
        if (!list.length) return '<p class="empty">現在沒有進行中的限時動態。</p>';
        var ago = storyShare.data.ago;
        return '<div class="story-wall col-stories">' + list.slice(0, shown).map(function (s) {
          var i = storyShare.data.flat.indexOf(s);
          return '<button class="story-card" data-story="' + i + '">' +
            '<img src="' + esc(s.media) + '" alt="' + esc(s.name) + ' 的限時動態" loading="lazy">' +
            (s.is_video ? '<span class="sc-video">▶</span>' : "") +
            '<span class="sc-meta">' +
            (s.avatar ? '<img class="sc-avatar" src="' + esc(s.avatar) + '" alt="">' : "") +
            '<span class="sc-who"><strong>' + esc(s.name) + "</strong>" + ago(s.taken_at) + "</span></span></button>";
        }).join("") + "</div>";
      }
      function colBody(c, list) {
        if (c.t === "events") {
          return (list.length ? evAgenda(list) : '<p class="empty">近期沒有活動。</p>') + moreBtn(list, " 場");
        }
        if (c.t === "stories") return storyCards(list) + moreBtn(list, " 則");
        return (list.slice(0, shown).map(row).join("") || '<p class="empty">沒有符合的貼文。</p>') + moreBtn(list, " 則");
      }
      function colHtml(i, c, list) {
        var tt = colTitle(c);
        var picker = '<details class="col-picker' + (colFilterActive(c) ? " fon" : "") + '"><summary aria-label="這一欄的內容與篩選">' +
          '<span class="feed-col-dot dot-' + tt.dot + '"></span><h2>' + tt.label + '</h2><span class="caret">' + CARET + "</span></summary>" +
          colMenu(c) + "</details>";
        return '<section class="feed-col" data-idx="' + i + '"><header class="feed-col-head">' + picker +
          '<span class="result-count">' + list.length + (c.t === "events" ? " 場" : " 則") + "</span></header>" +
          '<div class="col-body">' + colBody(c, list) + "</div></section>";
      }
      // 調整欄內篩選時只更新內容，不重建選單（維持選單開啟）
      function updateBodies() {
        var buckets = computeBuckets();
        cols.forEach(function (c, i) {
          var el = feed.querySelector('.feed-col[data-idx="' + i + '"]');
          if (!el) return;
          el.querySelector(".col-body").innerHTML = colBody(c, buckets[i]);
          el.querySelector(".result-count").textContent = buckets[i].length + (c.t === "events" ? " 場" : " 則");
          var tt = colTitle(c);
          var sm = el.querySelector(".col-picker > summary");
          sm.querySelector(".feed-col-dot").className = "feed-col-dot dot-" + tt.dot;
          sm.querySelector("h2").textContent = tt.label;
          el.querySelector(".col-picker").classList.toggle("fon", colFilterActive(c));
        });
      }
      // 分頁指示列（手機）：圓點跳欄＋新增欄位
      var pagerBar = null;
      function ensurePagerBar() {
        if (pagerBar) return pagerBar;
        pagerBar = document.createElement("div");
        pagerBar.className = "feed-pager-bar";
        feed.parentNode.insertBefore(pagerBar, feed);
        pagerBar.addEventListener("click", function (ev) {
          var dot = ev.target.closest("[data-goto]");
          if (dot) { goToCol(+dot.dataset.goto, true); return; }
          var add = ev.target.closest("button[data-add]");
          if (!add || cols.length >= 6) return;
          cols.push(add.dataset.add === "feed" ? feedCol("all") : { t: add.dataset.add });
          saveCols();
          pagerBar.querySelector("details.pager-add").open = false;
          activeCol = cols.length - 1;
          render(true);
          goToCol(activeCol, true);
        });
        return pagerBar;
      }
      function renderPagerBar(wide) {
        var bar = ensurePagerBar();
        bar.hidden = wide || cols.length < 1;
        if (bar.hidden) return;
        var dots = cols.map(function (c, i) {
          var tt = colTitle(c);
          return '<button class="pdot' + (i === activeCol ? " on" : "") + '" data-goto="' + i +
            '" aria-label="' + esc(tt.label) + '" aria-current="' + (i === activeCol) + '">' +
            '<span class="feed-col-dot dot-' + tt.dot + '"></span></button>';
        }).join("");
        bar.innerHTML = '<div class="pager-dots">' + dots + "</div>" +
          (cols.length < 6
            ? '<details class="pager-add"><summary aria-label="新增河道">' + SVG_OPEN +
              '<path d="M12 5l0 14"/><path d="M5 12l14 0"/></svg></summary>' +
              addColMenu() + '</details>'
            : "");
      }
      function updatePagerActive() {
        if (!pagerBar || pagerBar.hidden) return;
        pagerBar.querySelectorAll(".pdot").forEach(function (d, i) {
          d.classList.toggle("on", i === activeCol);
          d.setAttribute("aria-current", String(i === activeCol));
        });
      }
      function goToCol(i, smooth) {
        var deck = feed.querySelector(".feed-cols");
        if (!deck) return;
        deck.scrollTo({ left: i * deck.clientWidth, behavior: smooth ? "smooth" : "auto" });
      }
      var pagerT;
      function bindStripAutoHide(deck) {
        var strip = document.getElementById("story-strip");
        if (!strip) return;
        deck.querySelectorAll(".feed-col").forEach(function (colEl) {
          colEl.addEventListener("scroll", function () {
            document.body.classList.toggle("strip-away", colEl.scrollTop > 40);
          }, { passive: true });
        });
      }
      // 觸控換頁：欄位是垂直捲動容器，橫向手勢不會自動鏈到外層捲動容器
      // （Chrome 不鏈、iOS Safari 會把 pointer 事件在判定捲動時取消），所以用
      // touch 事件自己接：判定為橫向時 preventDefault 搶下手勢再驅動 deck。
      function bindSwipe(deck) {
        var drag = null, snapT;
        // 診斷開關：?swipedebug=1 會在畫面上顯示手勢接收狀況（回報用，平時零成本）
        var dbg = null;
        if (/[?&]swipedebug=1/.test(location.search)) {
          dbg = document.createElement("div");
          dbg.style.cssText = "position:fixed;left:8px;right:8px;bottom:70px;z-index:99;padding:8px 10px;" +
            "background:#000d;color:#0f0;font:12px/1.5 monospace;border:1px solid #0f0;border-radius:8px;white-space:pre-wrap";
          document.body.appendChild(dbg);
          dbg.textContent = "swipe debug: 等待手勢…\ncols=" + cols.length +
            " deckW=" + deck.clientWidth + " scrollW=" + deck.scrollWidth +
            "\ntouch-action=" + getComputedStyle(deck.querySelector(".feed-col")).touchAction;
        }
        function log(s) { if (dbg) dbg.textContent = s; }
        function snapBack(delay) {
          clearTimeout(snapT);
          snapT = setTimeout(function () { deck.style.scrollSnapType = ""; }, delay);
        }
        deck.addEventListener("touchstart", function (e) {
          if (e.touches.length !== 1 || cols.length < 2) { drag = null; return; }
          var t0 = e.touches[0];
          drag = { x: t0.clientX, y: t0.clientY, left: deck.scrollLeft, t: Date.now(), on: false, dec: false };
          if (dbg) log("touchstart @" + Math.round(t0.clientX) + "," + Math.round(t0.clientY));
        }, { passive: true });
        deck.addEventListener("touchmove", function (e) {
          if (!drag || e.touches.length !== 1) return;
          var t0 = e.touches[0];
          var dx = t0.clientX - drag.x, dy = t0.clientY - drag.y;
          if (!drag.dec) {
            if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;   // 還看不出方向（門檻要低，趕在瀏覽器決定捲動前接手）
            drag.dec = true;
            drag.on = Math.abs(dx) > Math.abs(dy);              // 橫向優勢才接手
            if (drag.on) { clearTimeout(snapT); deck.style.scrollSnapType = "none"; }
          }
          if (dbg) log("move dx=" + Math.round(dx) + " dy=" + Math.round(dy) +
            " horiz=" + drag.on + " cancelable=" + e.cancelable +
            "\nscrollLeft=" + Math.round(deck.scrollLeft) + " / " + deck.scrollWidth);
          if (!drag.on) return;
          if (e.cancelable) e.preventDefault();                 // 不讓瀏覽器當成垂直捲動
          deck.scrollLeft = drag.left - dx;
          drag.dx = dx;
        }, { passive: false });
        function end() {
          if (!drag) return;
          var d = drag; drag = null;
          if (!d.on) return;
          var w = Math.max(1, deck.clientWidth);
          var dx = d.dx || 0;
          var from = Math.round(d.left / w);
          var v = Math.abs(dx) / Math.max(1, Date.now() - d.t);   // px/ms
          var target = (Math.abs(dx) > w * 0.25 || v > 0.35)
            ? from + (dx < 0 ? 1 : -1)
            : Math.round(deck.scrollLeft / w);
          target = Math.max(0, Math.min(cols.length - 1, target));
          if (deck.scrollTo) deck.scrollTo({ left: target * w, behavior: "smooth" });
          else deck.scrollLeft = target * w;
          snapBack(420);
        }
        deck.addEventListener("touchend", end, { passive: true });
        deck.addEventListener("touchcancel", function () {
          if (drag && drag.on) snapBack(0);
          drag = null;
        }, { passive: true });
      }
      // 桌機多欄：欄位是垂直捲動容器，shift+滾輪會被它吃掉、macOS 捲軸又是隱藏式的，
      // 一般滑鼠等於無法左右移動 → 補上左右箭頭與 shift/橫向滾輪。
      function bindDeckNav(deck) {
        var wrap = deck.parentNode;
        var dbg = null;
        if (/[?&]swipedebug=1/.test(location.search)) {
          dbg = document.getElementById("chumei-swipedebug");
          if (!dbg) {
            dbg = document.createElement("div");
            dbg.id = "chumei-swipedebug";
            dbg.style.cssText = "position:fixed;left:280px;bottom:12px;z-index:99;max-width:620px;padding:8px 10px;" +
              "background:#000d;color:#0f0;font:12px/1.5 monospace;border:1px solid #0f0;border-radius:8px;white-space:pre-wrap";
            document.body.appendChild(dbg);
          }
        }
        function dbgInit() {
          if (!dbg) return;
          dbg.textContent = "桌機 deck debug：在河道上用觸控板左右滑\ncols=" + cols.length +
            " deckW=" + deck.clientWidth + " scrollW=" + deck.scrollWidth +
            " 可捲=" + (deck.scrollWidth - deck.clientWidth) +
            "\n欄 overscroll-x=" + getComputedStyle(deck.querySelector(".feed-col")).overscrollBehaviorX +
            " 箭頭=" + (wrap.querySelector(".deck-next") ? "有" : "無");
        }
        var prev = wrap.querySelector(".deck-prev"), next = wrap.querySelector(".deck-next");
        if (!prev) {
          prev = document.createElement("button");
          next = document.createElement("button");
          prev.className = "deck-nav deck-prev"; next.className = "deck-nav deck-next";
          prev.setAttribute("aria-label", "看左邊的河道");
          next.setAttribute("aria-label", "看右邊的河道");
          prev.innerHTML = SVG_OPEN + '<path d="M15 6l-6 6l6 6"/></svg>';
          next.innerHTML = SVG_OPEN + '<path d="M9 6l6 6l-6 6"/></svg>';
          wrap.appendChild(prev); wrap.appendChild(next);
          [["deck-prev", -1], ["deck-next", 1]].forEach(function (pair) {
            wrap.querySelector("." + pair[0]).addEventListener("click", function () {
              var col = deck.querySelector(".feed-col");
              var step = col ? col.getBoundingClientRect().width + 12 : deck.clientWidth * 0.8;
              deck.scrollBy({ left: pair[1] * step, behavior: "smooth" });
            });
          });
        }
        function sync() {
          var max = deck.scrollWidth - deck.clientWidth;
          var overflow = max > 8;
          prev.hidden = !overflow; next.hidden = !overflow;
          prev.disabled = deck.scrollLeft <= 2;
          next.disabled = deck.scrollLeft >= max - 2;
        }
        deck.addEventListener("scroll", sync, { passive: true });
        window.addEventListener("resize", sync);
        sync(); dbgInit();
        // 觸控板左右滑：真實手勢前幾個事件常帶垂直雜訊，Chrome 會先把整個手勢
        // 軸鎖定到欄位的垂直捲動 → 這裡自己累積判定方向，橫向勝出就鎖定接手。
        var gx = 0, gy = 0, gt = 0, lock = null;
        deck.addEventListener("wheel", function (e) {
          var now = Date.now();
          if (now - gt > 180) { gx = 0; gy = 0; lock = null; }   // 間隔夠久＝新手勢
          gt = now;
          if (e.shiftKey && !e.deltaX) {                          // shift+滾輪＝左右移動
            lock = "x";
          } else {
            gx += Math.abs(e.deltaX); gy += Math.abs(e.deltaY);
            if (!lock && (gx > 6 || gy > 6)) lock = gx > gy ? "x" : "y";
          }
          if (dbg) {
            dbg.textContent = "wheel dX=" + Math.round(e.deltaX) + " dY=" + Math.round(e.deltaY) +
              " 累積x=" + Math.round(gx) + " 累積y=" + Math.round(gy) + " 鎖定=" + lock +
              " cancelable=" + e.cancelable +
              "\nscrollLeft=" + Math.round(deck.scrollLeft) + " / 可捲=" + (deck.scrollWidth - deck.clientWidth);
          }
          if (lock !== "x") return;
          var dx = e.deltaX || (e.shiftKey ? e.deltaY : 0);
          if (!dx) return;
          var max = deck.scrollWidth - deck.clientWidth;
          if (max <= 0) return;
          if ((dx < 0 && deck.scrollLeft <= 0) || (dx > 0 && deck.scrollLeft >= max)) return;
          e.preventDefault();
          deck.scrollLeft += dx;
        }, { passive: false });
      }
      function bindPager() {
        var deck = feed.querySelector(".feed-cols");
        if (!deck) return;
        bindStripAutoHide(deck);
        bindSwipe(deck);
        deck.scrollLeft = activeCol * deck.clientWidth;
        deck.addEventListener("scroll", function () {
          clearTimeout(pagerT);
          pagerT = setTimeout(function () {
            var i = Math.round(deck.scrollLeft / Math.max(1, deck.clientWidth));
            if (i === activeCol || i < 0 || i >= cols.length) return;
            activeCol = i;
            var colEl = deck.querySelectorAll(".feed-col")[i];
            document.body.classList.toggle("strip-away", !!colEl && colEl.scrollTop > 40);
            syncFilterUI(); updatePagerActive(); refreshMeta();
          }, 80);
        }, { passive: true });
      }
      // 篩選鈕狀態、各選項計數、網址參數
      function refreshMeta() {
        var wide = !pagerMode();
        var cur = cols[activeCol];
        var ff = document.querySelector(".feed-filters");
        if (ff) {
          // 桌機：篩選在各欄選單；手機：只有貼文欄能篩
          ff.hidden = wide || !cur || cur.t !== "feed";
          ff.classList.toggle("fon",
            state.school !== "all" || state.platform !== "all" || state.cat !== "all" || state.org !== "all" || !!state.q);
        }
        Object.keys(groups).forEach(function (key) {
          groups[key].options.forEach(function (opt) {
            var b = groups[key].buttons[opt[0]];
            var c = b && b.querySelector(".fchip-count");
            if (!c) return;
            var f = Object.assign({}, state); f[key] = opt[0];
            c.textContent = String(posts.filter(function (p) { return matches(p, f); }).length);
          });
        });
        var qs = new URLSearchParams();
        Object.keys(state).forEach(function (k) {
          if (state[k] && state[k] !== "all") qs.set(k, state[k]);
        });
        if (/[?&]swipedebug=1/.test(location.search)) qs.set("swipedebug", "1");  // 診斷旗標別被洗掉
        history.replaceState(null, "", qs.toString() ? "?" + qs.toString() : location.pathname);
      }
      function render(more) {
        if (!more) shown = 30;
        var fc = document.getElementById("feed-count");
        var wide = window.innerWidth >= 1080;
        if (activeCol >= cols.length) activeCol = Math.max(0, cols.length - 1);
        // 網址帶篩選參數時，套用到第一個貼文欄（深連結）
        if (seededFromUrl) {
          seededFromUrl = false;
          var ci = cols.findIndex(function (c) { return c.t === "feed"; });
          if (ci >= 0) {
            ["school", "platform", "cat", "org", "q"].forEach(function (k) { cols[ci][k] = state[k]; });
            activeCol = ci; saveCols();
          }
        }
        var buckets = computeBuckets();
        if (fc) fc.textContent = "";
        feed.classList.toggle("feed-wide", wide);
        feed.classList.toggle("feed-pager", !wide);
        // 欄位模式：鎖住外層捲動，只捲欄內（Threads 式）；手機為左右分頁的河道
        document.body.classList.add("feed-locked");
        // Threads deck：第 4 欄起欄寬降一階（實測 Threads 為 420px）
        var canAdd = wide && cols.length < 6;
        feed.innerHTML = '<div class="feed-cols' + (wide && cols.length > 3 ? " cols-many" : "") +
          (canAdd ? " has-deck-add" : "") +
          '" style="--ncols:' + cols.length + '">' +
          cols.map(function (c, i) { return colHtml(i, c, buckets[i]); }).join("") +
          (canAdd ? deckAddHtml() : "") + "</div>";
        if (!wide) { bindPager(); syncFilterUI(); }
        else { bindDeckNav(feed.querySelector(".feed-cols")); }
        renderPagerBar(wide);
        refreshMeta();
      }
      feed.addEventListener("click", function (ev) {
        var add = ev.target.closest(".deck-add button[data-add]");
        if (add && cols.length < 6) {
          cols.push(add.dataset.add === "feed" ? feedCol("all") : { t: add.dataset.add });
          activeCol = cols.length - 1;
          saveCols(); render(true);
          var newDeck = feed.querySelector(".feed-cols");
          if (newDeck) newDeck.scrollTo({ left: newDeck.scrollWidth, behavior: "smooth" });
          return;
        }
        if (ev.target.classList.contains("feed-more")) {
          shown += 30;
          var colEl = ev.target.closest(".feed-col");
          var keep = colEl ? colEl.scrollTop : 0;
          updateBodies();
          if (colEl) colEl.scrollTop = keep;   // 換內容不該把這一欄捲回頂端
          return;
        }
        var sc = ev.target.closest(".story-card[data-story]");
        if (sc && storyShare.open) { storyShare.open(parseInt(sc.dataset.story, 10)); return; }
        var chip = ev.target.closest(".col-picker-menu .fchip[data-ck]");
        if (chip) {
          var idx = +chip.closest(".feed-col").dataset.idx;
          cols[idx][chip.dataset.ck] = chip.dataset.cv;
          chip.closest(".fgroup").querySelectorAll(".fchip").forEach(function (x) {
            x.setAttribute("aria-pressed", String(x === chip));
          });
          saveCols(); updateBodies();
          return;
        }
        var rm = ev.target.closest(".col-picker-menu .col-remove");
        if (rm) {
          cols.splice(+rm.closest(".feed-col").dataset.idx, 1);
          saveCols(); render(true);
        }
      });
      // 欄內搜尋：即時過濾該欄，不重建選單
      var cfT;
      feed.addEventListener("input", function (ev) {
        var q = ev.target.closest(".cf-q");
        if (!q) return;
        var idx = +q.closest(".feed-col").dataset.idx;
        cols[idx].q = q.value.trim();
        clearTimeout(cfT);
        cfT = setTimeout(function () { saveCols(); updateBodies(); }, 200);
      });
      var resizeT;
      window.addEventListener("resize", function () {
        clearTimeout(resizeT);
        resizeT = setTimeout(function () { render(true); }, 200);
      });
      var feedEvById = {};
      posts.forEach(function (p) { p.events.forEach(function (e) { feedEvById[e.id] = e; }); });
      bindEventHover(feed, ".feed-ev", function (a) { return feedEvById[a.dataset.id]; }, data.labels || {});
      bindEventHover(feed, ".agd-ev", function (a) { return feedEvById[a.dataset.id]; }, data.labels || {});
      // 限動資料晚到時補繪限時動態欄
      if (!storyShare.data) storyShare.hooks.push(function () { updateBodies(); });
      render();
    }).catch(function (err) {
      console.error("chumei feed init failed:", err);
      // SSR 已預先渲染第一頁；抓不到 posts.json 就留著靜態內容
      if (!feed.firstElementChild) feed.innerHTML = '<p class="empty">貼文載入失敗。</p>';
    });
  }

  // ---- /source/ 機構名錄（表格＋篩選） ----
  function initSources() {
    var table = document.getElementById("source-table");
    if (!table) return;
    var KIND = { club: "社團", gov: "自治組織", dept: "系所", unit: "校方單位", bulletin: "公告系統", ext: "校外" };
    var PLAT = { instagram: "IG", facebook: "FB", threads: "Threads", x: "X", bulletin: "公告", website: "官網" };

    fetch("/data/sources.json").then(function (r) { return r.json(); }).then(function (data) {
      var entries = data.entries;
      var state = { follow: "all", school: "all", status: "all", kind: "all", platform: "all", sort: "events", dir: "desc", q: "" };
      var params = new URLSearchParams(location.search);
      Object.keys(state).forEach(function (k) { if (params.get(k)) state[k] = params.get(k); });
      function followed(id) {
        return !!(window.chumeiFollow && window.chumeiFollow.isFollowed(id));
      }

      var groups = {};
      function chips(id, options, key) {
        var host = document.getElementById(id);
        if (!host) return;
        groups[key] = { options: options, buttons: {} };
        options.forEach(function (opt) {
          var b = document.createElement("button");
          b.className = "fchip";
          b.dataset.value = opt[0];
          b.innerHTML = '<span class="fchip-label">' + esc(opt[1]) + '</span><span class="fchip-count" aria-hidden="true"></span>';
          b.setAttribute("aria-pressed", String(state[key] === opt[0]));
          groups[key].buttons[opt[0]] = b;
          b.addEventListener("click", function () {
            state[key] = opt[0];
            host.querySelectorAll(".fchip").forEach(function (x) {
              x.setAttribute("aria-pressed", String(x.dataset.value === opt[0]));
            });
            render();
          });
          host.appendChild(b);
        });
      }
      // 只在 /notify/ 出現（/source/ 沒有這個容器，chips 會直接略過）
      chips("sf-follow", [["all", "全部單位"], ["on", "只看已追蹤"]], "follow");
      chips("sf-school", [["all", "全部"], ["nthu", "清大"], ["nycu", "陽明交大"], ["nycu-guangfu", "交大校區"], ["nycu-yangming", "陽明校區"]], "school");
      chips("sf-status", [["all", "全部"], ["covered", "已收錄"], ["uncovered", "尚未收錄"]], "status");
      chips("sf-kind", [["all", "全部"]].concat(Object.keys(KIND).map(function (k) { return [k, KIND[k]]; })), "kind");
      chips("sf-platform", [["all", "全部"], ["instagram", "IG"], ["facebook", "FB"], ["threads", "Threads"], ["x", "X"]], "platform");

      var search = document.getElementById("search");
      if (search) {
        search.value = state.q;
        search.addEventListener("input", function () { state.q = search.value.trim(); render(); });
      }
      // 追蹤數會影響「只看已追蹤」的計數與清單內容
      window.addEventListener("chumei-follow-change", function () {
        if (groups.follow || state.sort === "follow") render();
      });

      function matches(e, ok, ov) {
        function v(k) { return ok === k ? ov : state[k]; }
        if (v("follow") === "on" && !followed(e.id)) return false;
        var sch = v("school");
        if (sch === "nycu-guangfu") { if (e.school !== "nycu" || e.campus === "yangming") return false; }
        else if (sch === "nycu-yangming") { if (e.school !== "nycu" || e.campus !== "yangming") return false; }
        else if (sch !== "all" && e.school !== sch) return false;
        if (v("status") === "covered" && !e.links.length) return false;
        if (v("status") === "uncovered" && e.links.length) return false;
        if (v("kind") !== "all" && e.kind !== v("kind")) return false;
        if (v("platform") !== "all" && !e.links.some(function (l) { return l.platform === v("platform"); })) return false;
        if (state.q) {
          var hay = (e.name + " " + (e.category || "") + " " + e.links.map(function (l) { return l.label; }).join(" ")).toLowerCase();
          if (hay.indexOf(state.q.toLowerCase()) === -1) return false;
        }
        return true;
      }

      function fmtUpdated(iso) {
        if (!iso) return "—";
        var d = new Date(iso);
        if (isNaN(d.getTime())) return "—";
        var days = (Date.now() - d.getTime()) / 864e5;
        if (days < 1) return "今天";
        if (days < 30) return Math.round(days) + " 天前";
        return d.getFullYear() + "/" + (d.getMonth() + 1) + "/" + d.getDate();
      }

      function row(e) {
        var links = e.links.map(function (l) {
          return '<a class="src-link" href="' + esc(l.url) + '" rel="noopener" target="_blank">' +
            esc(PLAT[l.platform] || l.platform) + (l.label && l.label !== "Facebook" && l.label !== "公告頁" ? " " + esc(l.label) : "") + "</a>";
        }).join("");
        var avatar = e.avatar
          ? '<img class="src-avatar src-c-ava" src="' + esc(e.avatar) + '" alt="" loading="lazy">'
          : '<span class="src-avatar src-c-ava src-avatar-fallback av-' + esc(e.school) + '">' + esc(e.name.replace(/^(清大|交大|陽明|國立)/, "").charAt(0) || "？") + "</span>";
        // 手機版：chips 行整個收掉，only 一顆迷你校別章（有校區時校區優先）
        var mLabel = e.school === "nthu" ? "清大"
          : e.school === "nycu" ? (e.campus === "yangming" ? "陽明" : e.campus === "guangfu" ? "交大" : "陽明交大")
          : "其他";
        return '<div class="src-row' + (e.links.length ? "" : " src-uncovered") + '">' +
          '<span class="src-id src-c-id" aria-label="名錄 ID ' + e.id + '">#' + e.id + "</span>" +
          '<span class="src-c-name">' + avatar +
          '<a class="src-name" href="/org/' + e.id + '/">' + esc(e.name) + "</a>" +
          '<span class="chip chip-m chip-' + esc(e.school) + '">' + mLabel + "</span></span>" +
          '<span class="chips src-c-chips">' +
          '<span class="chip chip-school chip-' + esc(e.school) + '">' + esc(e.school === "nthu" ? "清大" : e.school === "nycu" ? "陽明交大" : "其他") + "</span>" +
          (e.campus ? '<span class="chip chip-campus">' + (e.campus === "yangming" ? "陽明" : "交大") + "</span>" : "") +
          '<span class="chip chip-extra">' + esc(KIND[e.kind] || "") + "</span>" +
          (e.category ? '<span class="chip chip-extra">' + esc(e.category) + "</span>" : "") +
          "</span>" +
          '<div class="src-links">' + (links || '<span class="src-none">尚未找到公開帳號</span>') + "</div>" +
          '<div class="src-upd" title="' + esc(e.updated || "") + '">' + fmtUpdated(e.updated) + "</div>" +
          '<div class="src-ev">' + (e.events ? e.events + " 場" : "—") + "</div>" +
          '<button class="heart-btn heart-btn-label src-c-follow" data-org-id="' + e.id + '" data-org-name="' + esc(e.name) +
          '" aria-pressed="' + followed(e.id) + '" title="追蹤 ' + esc(e.name) + '">' +
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 5a2 2 0 1 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3h-16a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6"/><path d="M9 17v1a3 3 0 0 0 6 0v-1"/></svg>' +
          '<span class="hb-follow">追蹤</span><span class="hb-following">追蹤中</span></button>' +
          "</div>";
      }

      var SORTS = {
        events: function (a, b) { return (b.events - a.events) || (b.links.length - a.links.length) || a.name.localeCompare(b.name, "zh-Hant"); },
        updated: function (a, b) { return ((b.updated || "").localeCompare(a.updated || "")) || (b.events - a.events); },
        follow: function (a, b) { return Number(followed(b.id)) - Number(followed(a.id)) || (b.events - a.events) || a.name.localeCompare(b.name, "zh-Hant"); },
        name: function (a, b) { return a.name.localeCompare(b.name, "zh-Hant"); },
        id: function (a, b) { return a.id - b.id; }
      };
      var SORT_DEFAULT_DIR = { events: "desc", updated: "desc", follow: "desc", name: "asc", id: "asc" };
      var SORT_BASE_DESC = { events: true, updated: true, follow: true, name: false, id: false }; // SORTS 天然方向

      function headHtml() {
        function th(key, label, extraCls) {
          var arrow = state.sort === key ? (state.dir === "asc" ? " ↑" : " ↓") : " ↕";
          return '<button class="src-th' + (extraCls ? " " + extraCls : "") +
            (state.sort === key ? " src-th-on" : "") + '" data-sort="' + key + '">' + label + arrow + "</button>";
        }
        return '<div class="src-head">' +
          th("id", "ID") + th("name", "名稱", "src-th-left") +
          '<span class="src-th-plain">標籤</span><span class="src-th-plain src-th-links">連結</span>' +
          th("updated", "更新") + th("events", "收錄") +
          th("follow", "追蹤", "src-th-follow") + "</div>";
      }

      function render() {
        Object.keys(groups).forEach(function (key) {
          groups[key].options.forEach(function (opt) {
            var b = groups[key].buttons[opt[0]];
            if (b) b.querySelector(".fchip-count").textContent = String(entries.filter(function (e) { return matches(e, key, opt[0]); }).length);
          });
        });
        var list = entries.filter(function (e) { return matches(e); }).sort(SORTS[state.sort] || SORTS.events);
        var natural = SORT_BASE_DESC[state.sort] ? "desc" : "asc";
        if (state.dir !== natural) list.reverse();
        document.getElementById("src-count").textContent = "目前列出 " + list.length + " 個單位。";
        table.innerHTML = headHtml() + (list.map(row).join("") || '<p class="empty">沒有符合的單位。</p>');
        var qs = new URLSearchParams();
        Object.keys(state).forEach(function (k) {
          if (!state[k] || state[k] === "all") return;
          if (k === "sort" && state.sort === "events") return;
          if (k === "dir" && state.dir === (SORT_DEFAULT_DIR[state.sort] || "desc")) return;
          qs.set(k, state[k]);
        });
        history.replaceState(null, "", qs.toString() ? "?" + qs.toString() : location.pathname);
      }
      table.addEventListener("click", function (ev) {
        var th = ev.target.closest(".src-th");
        if (!th) return;
        var key = th.dataset.sort;
        if (state.sort === key) {
          state.dir = state.dir === "asc" ? "desc" : "asc";
        } else {
          state.sort = key;
          state.dir = SORT_DEFAULT_DIR[key];
        }
        render();
      });
      render();
    }).catch(function () {
      if (!table.firstElementChild) table.innerHTML = '<p class="empty">名錄載入失敗。</p>';
    });
  }

  // ---- IG 限時動態（首頁圓圈列＋動態牆＋燈箱） ----
  function initStories() {
    var strip = document.getElementById("story-strip");
    var wall = document.getElementById("story-wall");
    if (!strip && !wall) return;

    fetch("/data/stories.json")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var stories = data.stories || [];
        if (!stories.length) {
          if (wall) wall.innerHTML = '<p class="empty">現在沒有進行中的限時動態 — 限動 24 小時後就會消失，晚點再來看看。</p>';
          return;
        }
        // 依帳號分組，組序 = 該帳號最新限動時間
        var groups = {}, order = [];
        stories.forEach(function (s) {
          if (!groups[s.username]) { groups[s.username] = []; order.push(s.username); }
          groups[s.username].push(s);
        });
        var flat = [];
        order.forEach(function (u) { groups[u].forEach(function (s) { flat.push(s); }); });

        function ago(iso) {
          var h = Math.max(0, (Date.now() - new Date(iso).getTime()) / 36e5);
          return h < 1 ? Math.round(h * 60) + " 分鐘前" : Math.round(h) + " 小時前";
        }

        if (strip) {
          strip.hidden = false;
          strip.innerHTML = order.map(function (u) {
            var g = groups[u];
            return '<button class="story-item" data-user="' + esc(u) + '" aria-label="' + esc(g[0].name) + ' 的限時動態">' +
              '<span class="story-ring ring-' + esc(g[0].school) + '">' +
              '<img src="' + esc(g[0].media) + '" alt="">' +
              (g.length > 1 ? '<span class="story-count">' + g.length + "</span>" : "") +
              '</span><span class="story-name">' + esc(g[0].name) + "</span></button>";
          }).join("");
          strip.addEventListener("click", function (ev) {
            var b = ev.target.closest(".story-item");
            if (b) openLightbox(flat.indexOf(groups[b.dataset.user][0]));
          });
        }

        if (wall) {
          wall.innerHTML = flat.map(function (s, i) {
            return '<button class="story-card" data-i="' + i + '">' +
              '<img src="' + esc(s.media) + '" alt="' + esc(s.name) + ' 的限時動態" loading="lazy">' +
              (s.is_video ? '<span class="sc-video">▶</span>' : "") +
              '<span class="sc-meta">' +
              (s.avatar ? '<img class="sc-avatar" src="' + esc(s.avatar) + '" alt="">' : "") +
              '<span class="sc-who"><strong>' + esc(s.name) + "</strong>" + ago(s.taken_at) + "</span></span></button>";
          }).join("");
          wall.addEventListener("click", function (ev) {
            var b = ev.target.closest(".story-card");
            if (b) openLightbox(parseInt(b.dataset.i, 10));
          });
        }

        var lb = null, cur = 0, swipe = null;
        var storyWheel = { x: 0, y: 0, last: 0, handled: false };
        function openLightbox(i) {
          cur = i;
          if (!lb) {
            lb = document.createElement("div");
            lb.className = "story-lightbox";
            lb.innerHTML = '<button class="slb-close" aria-label="關閉">×</button>' +
              '<div class="slb-figure"><div class="slb-head"></div><div class="slb-media"></div>' +
              '<button class="slb-nav slb-prev" aria-label="上一則">‹</button>' +
              '<button class="slb-nav slb-next" aria-label="下一則">›</button></div>';
            document.body.appendChild(lb);
            lb.addEventListener("click", function (ev) {
              if (ev.target === lb || ev.target.classList.contains("slb-close")) close();
              else if (ev.target.classList.contains("slb-prev")) show(cur - 1);
              else if (ev.target.classList.contains("slb-next")) show(cur + 1);
            });
            lb.addEventListener("touchstart", function (ev) {
              if (ev.touches.length !== 1 || ev.target.closest("a, button")) { swipe = null; return; }
              var t = ev.touches[0];
              swipe = { x: t.clientX, y: t.clientY, dx: 0, dy: 0, decided: false, horizontal: false };
            }, { passive: true });
            lb.addEventListener("touchmove", function (ev) {
              if (!swipe || ev.touches.length !== 1) return;
              var t = ev.touches[0];
              swipe.dx = t.clientX - swipe.x;
              swipe.dy = t.clientY - swipe.y;
              if (!swipe.decided) {
                if (Math.abs(swipe.dx) < 6 && Math.abs(swipe.dy) < 6) return;
                swipe.decided = true;
                swipe.horizontal = Math.abs(swipe.dx) > Math.abs(swipe.dy) * 1.15;
              }
              if (swipe.horizontal && ev.cancelable) ev.preventDefault();
            }, { passive: false });
            lb.addEventListener("touchend", function (ev) {
              if (!swipe) return;
              if (ev.changedTouches.length) {
                swipe.dx = ev.changedTouches[0].clientX - swipe.x;
                swipe.dy = ev.changedTouches[0].clientY - swipe.y;
              }
              var move = swipe;
              swipe = null;
              if (move.horizontal && Math.abs(move.dx) >= 48 && Math.abs(move.dx) > Math.abs(move.dy) * 1.15)
                show(cur + (move.dx < 0 ? 1 : -1));
            }, { passive: true });
            lb.addEventListener("touchcancel", function () { swipe = null; }, { passive: true });
            // Desktop trackpads emit horizontal wheel events instead of touch events.
            // Keep this gesture state local to the lightbox so the Threads-style river
            // underneath cannot consume it; momentum from one gesture changes one story only.
            lb.addEventListener("wheel", function (ev) {
              var now = Date.now();
              if (now - storyWheel.last > 180) storyWheel = { x: 0, y: 0, last: now, handled: false };
              storyWheel.last = now;
              storyWheel.x += ev.deltaX || (ev.shiftKey ? ev.deltaY : 0);
              storyWheel.y += ev.shiftKey ? 0 : ev.deltaY;
              if (storyWheel.handled) {
                ev.preventDefault();
                ev.stopPropagation();
                return;
              }
              if (Math.abs(storyWheel.x) < 45 || Math.abs(storyWheel.x) <= Math.abs(storyWheel.y) * 1.15) return;
              ev.preventDefault();
              ev.stopPropagation();
              storyWheel.handled = true;
              show(cur + (storyWheel.x > 0 ? 1 : -1));
            }, { passive: false });
            document.addEventListener("keydown", onKey);
          }
          lb.style.display = "flex";
          document.body.style.overflow = "hidden";
          show(i);
        }
        function onKey(ev) {
          if (!lb || lb.style.display === "none") return;
          if (ev.key === "Escape") close();
          if (ev.key === "ArrowLeft") show(cur - 1);
          if (ev.key === "ArrowRight") show(cur + 1);
        }
        function close() {
          lb.style.display = "none";
          document.body.style.overflow = "";
          storyWheel = { x: 0, y: 0, last: 0, handled: false };
        }
        function show(i) {
          cur = (i + flat.length) % flat.length;
          var s = flat[cur];
          lb.querySelector(".slb-head").innerHTML =
            '<span class="who"><strong>' + esc(s.name) + '</strong><span class="sub">@' + esc(s.username) + " ・ " + ago(s.taken_at) + "</span></span>" +
            '<a href="' + esc(s.ig_url) + '" rel="noopener" target="_blank">在 IG 開啟 ↗</a>';
          lb.querySelector(".slb-media").innerHTML =
            '<img src="' + esc(s.media) + '" alt="">' +
            (s.is_video ? '<p class="slb-video-note">影片限動 — <a href="' + esc(s.ig_url) + '" rel="noopener" target="_blank">到 IG 觀看</a></p>' : "");
        }

        storyShare.data = { flat: flat, ago: ago };
        storyShare.open = openLightbox;
        storyShare.hooks.forEach(function (f) { f(); });
        storyShare.hooks = [];
      })
      .catch(function () { if (wall && !wall.firstElementChild) wall.innerHTML = '<p class="empty">限時動態載入失敗。</p>'; });
  }

  // ---- 共用活動 hover 預覽卡（日曆格／地圖 popup／河道 chips） ----
  var hoverPop = null;
  function bindEventHover(root, selector, resolve, labels) {
    if (!root || !window.matchMedia("(hover: hover)").matches) return;
    if (!hoverPop) {
      hoverPop = document.createElement("div");
      hoverPop.className = "cal-pop";
      hoverPop.hidden = true;
      document.body.appendChild(hoverPop);
      window.addEventListener("scroll", function () { hoverPop.hidden = true; }, { passive: true });
    }
    function fmtWhen(e) {
      var d = new Date(e.start_at);
      var base = (d.getMonth() + 1) + "/" + d.getDate() + "（" + "日一二三四五六"[d.getDay()] + "）";
      var t = "";
      if (!e.all_day) {
        t = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
        var en = e.end_at ? new Date(e.end_at) : null;
        if (en && !isNaN(en.getTime()) && en > d && en.toDateString() === d.toDateString())
          t += "–" + String(en.getHours()).padStart(2, "0") + ":" + String(en.getMinutes()).padStart(2, "0");
      }
      var ong = ongoingLabel(e);
      if (ong) return base + (t ? " " + t : "") + "・" + ong;
      return t ? base + " " + t : base + "・全天";
    }
    root.addEventListener("mouseover", function (ev) {
      var a = ev.target.closest(selector);
      if (!a) return;
      var e = resolve(a);
      if (!e) return;
      var cover = e.cover_image || e.poster_image;
      var where = [e.campus ? (labels.campus || {})[e.campus] : null, e.venue].filter(Boolean).join(" ");
      hoverPop.innerHTML =
        (cover ? '<img src="' + esc(cover) + '" alt="">' : "") +
        '<div class="cal-pop-body"><p class="chips">' +
        (e.school ? '<span class="chip chip-' + esc(e.school) + '">' + esc((labels.school || {})[e.school] || "") + "</span>" : "") +
        (e.category ? '<span class="chip">' + esc(e.category) + "</span>" : "") + "</p>" +
        "<strong>" + esc(e.title) + "</strong>" +
        '<span class="cal-pop-meta">' + esc(fmtWhen(e)) + (where ? "｜" + esc(where) : "") + "</span>" +
        (e.organizer ? '<span class="cal-pop-meta">' + esc(e.organizer) + "</span>" : "") + "</div>";
      hoverPop.hidden = false;
      var r = a.getBoundingClientRect();
      var pw = 280, ph = hoverPop.offsetHeight || 200;
      var x = Math.min(Math.max(8, r.left), window.innerWidth - pw - 12);
      var y = r.bottom + 8;
      if (y + ph > window.innerHeight - 8) y = Math.max(8, r.top - ph - 8);
      hoverPop.style.left = x + "px";
      hoverPop.style.top = y + "px";
    });
    root.addEventListener("mouseout", function (ev) {
      if (ev.target.closest(selector) && !(ev.relatedTarget && ev.relatedTarget.closest(selector))) hoverPop.hidden = true;
    });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function ongoingLabel(e) {
    // 跨日進行中的活動（展覽、申請期間）：顯示「進行中」而非幾個月前的開始日
    if (!e || !e.end_at) return null;
    var s = new Date(e.start_at), en = new Date(e.end_at), now = new Date();
    if (isNaN(s.getTime()) || isNaN(en.getTime()) || s > now || en < now) return null;
    return "進行中・至 " + (en.getMonth() + 1) + "/" + en.getDate() + "（" + "日一二三四五六"[en.getDay()] + "）";
  }

  // 活動列表依「下一個關鍵時間」排序：尚未開始看開始時間，進行中看截止時間。
  function eventSortTime(e, now) {
    var starts = new Date(e.start_at).getTime();
    var ends = e.end_at ? new Date(e.end_at).getTime() : NaN;
    return !isNaN(ends) && starts <= now && now <= ends ? ends : starts;
  }

  function todayStr() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  // ---- 活動河道 ----
  function initList(bundle) {
    var labels = bundle.labels;
    var state = { time: "7d", school: "all", campus: "all", cat: "all", org: "all", reg: "all", fee: "all", q: "" };

    var params = new URLSearchParams(location.search);
    ["time", "school", "campus", "cat", "org", "reg", "fee", "q"].forEach(function (k) {
      if (params.get(k)) state[k] = params.get(k);
    });
    if (state.time === "week") state.time = "7d";

    var moreFilters = document.getElementById("more-filters");
    function moreActive() {
      return state.school !== "all" || state.campus !== "all" || state.cat !== "all" ||
        state.org !== "all" || state.reg !== "all" || state.fee !== "all";
    }
    // 手機帶著篩選條件進來時直接展開；桌機 popover 用亮點提示
    if (moreFilters && window.innerWidth <= 700 && moreActive()) moreFilters.open = true;

    var cats = {};
    bundle.events.forEach(function (e) { cats[e.category || "其他"] = 1; });

    var rangeStart = new Date();

    var chipGroups = {};
    buildChips("f-time", [
      ["24h", "24 小時"], ["3d", "3 天"], ["7d", "7 天"], ["30d", "1 個月"],
      ["upcoming", "未來全部"], ["all", "全部"]
    ], "time");
    buildChips("f-school", [["all", "全部"], ["nthu", "清大"], ["nycu", "陽明交大"], ["both", "兩校聯合"]], "school");
    buildChips("f-campus", [["all", "全部校區"]].concat(Object.keys(labels.campus).map(function (k) { return [k, labels.campus[k]]; })), "campus");
    buildChips("f-cat", [["all", "全部類型"]].concat(Object.keys(cats).sort().map(function (k) { return [k, k]; })), "cat");
    buildChips("f-org", [["all", "全部主辦"], ["official", "校方"], ["department", "系所"], ["club", "社團"], ["external", "校外"]], "org");
    buildChips("f-reg", [["all", "全部"], ["required", "需報名"], ["free", "自由入場"]], "reg");
    buildChips("f-fee", [["all", "全部"], ["free", "免費"], ["paid", "付費"]], "fee");

    var search = document.getElementById("search");
    if (search) {
      search.value = state.q;
      search.addEventListener("input", function () { state.q = search.value.trim(); render(); });
    }

    function buildChips(id, options, key) {
      var host = document.getElementById(id);
      if (!host) return;
      chipGroups[key] = { host: host, options: options, buttons: {} };
      options.forEach(function (opt) {
        var b = document.createElement("button");
        b.className = "fchip";
        b.dataset.value = opt[0];
        b.dataset.label = opt[1];
        b.innerHTML = '<span class="fchip-label">' + esc(opt[1]) + '</span><span class="fchip-count" aria-hidden="true"></span>';
        chipGroups[key].buttons[opt[0]] = b;
        b.setAttribute("aria-pressed", String(state[key] === opt[0]));
        b.addEventListener("click", function () {
          state[key] = opt[0];
          host.querySelectorAll(".fchip").forEach(function (x) {
            x.setAttribute("aria-pressed", String(x.dataset.value === opt[0]));
          });
          render();
        });
        host.appendChild(b);
      });
    }

    function matches(e, overrideKey, overrideValue) {
      function value(key) { return overrideKey === key ? overrideValue : state[key]; }
      var timeRange = value("time");
      if (timeRange !== "all") {
        var starts = new Date(e.start_at);
        var ends = e.end_at ? new Date(e.end_at) : starts;
        if (isNaN(starts.getTime())) return false;
        if (ends < rangeStart && !e.all_day) return false;
        if (e.all_day && (e.start_at || "").slice(0, 10) < todayStr()) return false;
        if (timeRange !== "upcoming") {
          var rangeEnd = new Date(rangeStart);
          if (timeRange === "24h") rangeEnd.setHours(rangeEnd.getHours() + 24);
          if (timeRange === "3d") rangeEnd.setDate(rangeEnd.getDate() + 3);
          if (timeRange === "7d") rangeEnd.setDate(rangeEnd.getDate() + 7);
          if (timeRange === "30d") rangeEnd.setMonth(rangeEnd.getMonth() + 1);
          if (starts > rangeEnd) return false;
        }
      }
      if (value("school") !== "all" && e.school !== value("school") && !(value("school") !== "both" && e.school === "both")) return false;
      if (value("campus") !== "all" && e.campus !== value("campus")) return false;
      if (value("cat") !== "all" && (e.category || "其他") !== value("cat")) return false;
      if (value("org") !== "all" && e.organizer_type !== value("org")) return false;
      if (value("reg") !== "all" && e.reg !== value("reg")) return false;
      if (value("fee") !== "all" && e.fee !== value("fee")) return false;
      if (state.q) {
        var hay = (e.title + " " + (e.summary || "") + " " + (e.organizer || "") + " " + (e.venue || "")).toLowerCase();
        if (hay.indexOf(state.q.toLowerCase()) === -1) return false;
      }
      return true;
    }

    function updateChipCounts() {
      Object.keys(chipGroups).forEach(function (key) {
        var group = chipGroups[key];
        group.options.forEach(function (opt) {
          var count = bundle.events.filter(function (e) { return matches(e, key, opt[0]); }).length;
          var button = group.buttons[opt[0]];
          if (!button) return;
          button.querySelector(".fchip-count").textContent = String(count);
          button.setAttribute("aria-label", opt[1] + "，" + count + " 場活動");
        });
      });
    }

    // ---- 顯示模式：手機預設 compact 列表、桌機預設卡片；選擇記在 localStorage ----
    var displayMode = (function () {
      var p = params.get("mode");
      if (p === "list" || p === "cards") return p;
      try {
        var s = localStorage.getItem("chumei-mode");
        if (s === "list" || s === "cards") return s;
      } catch (e) {}
      return window.innerWidth <= 700 ? "list" : "cards";
    })();
    var modeBtns = { list: document.getElementById("mode-list"), cards: document.getElementById("mode-cards") };
    function syncModeBtns() {
      Object.keys(modeBtns).forEach(function (k) {
        if (modeBtns[k]) modeBtns[k].setAttribute("aria-pressed", String(displayMode === k));
      });
    }
    Object.keys(modeBtns).forEach(function (k) {
      if (modeBtns[k]) modeBtns[k].addEventListener("click", function () {
        displayMode = k;
        try { localStorage.setItem("chumei-mode", k); } catch (e) {}
        syncModeBtns();
        render();
      });
    });
    syncModeBtns();

    function listRow(e) {
      var d = new Date(e.start_at);
      var wd = "日一二三四五六"[d.getDay()];
      var when = ongoingLabel(e) || ((d.getMonth() + 1) + "/" + d.getDate() + "（" + wd + "）" +
        (e.all_day ? "" : " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0")));
      var where = [e.campus ? labels.campus[e.campus] : null, e.venue].filter(Boolean).join(" ");
      var thumb = e.poster_image
        ? '<img class="evr-thumb" src="' + esc(e.poster_image) + '" alt="" loading="lazy">'
        : '<span class="evr-thumb evr-thumb-txt np-' + esc(e.school === "nthu" ? "nthu" : e.school === "nycu" ? "nycu" : "other") + '">' +
          (e.school === "nthu" ? "梅" : e.school === "nycu" ? "竹" : "梅竹") + "</span>";
      var rowHeart = e.org_id
        ? '<button class="heart-btn ev-row-heart" data-org-id="' + e.org_id + '" data-org-name="' + esc(e.org_name || e.organizer || "") + '" aria-pressed="false" title="追蹤 ' + esc(e.org_name || e.organizer || "") + '">' +
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 5a2 2 0 1 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3h-16a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6"/><path d="M9 17v1a3 3 0 0 0 6 0v-1"/></svg></button>'
        : "";
      return '<div class="ev-row-wrap">' + rowHeart + '<a class="ev-row ev-row-' + esc(e.school) + '" href="/event/' + e.id + '/">' + thumb +
        '<span class="evr-main"><span class="evr-when">' + esc(when) +
        (e.reg === "required" ? '<span class="chip chip-reg-req">需報名</span>' : e.reg === "free" ? '<span class="chip chip-reg-free">自由入場</span>' : "") +
        (e.fee === "free" ? '<span class="chip chip-fee-free">免費</span>' : e.fee === "paid" ? '<span class="chip chip-fee-paid">$</span>' : "") +
        (e.extraction && e.extraction.needs_review ? '<span class="chip chip-review">待確認</span>' : "") +
        '</span><span class="evr-title">' + esc(e.title) + "</span>" +
        '<span class="evr-meta">' + esc([where, e.organizer].filter(Boolean).join("｜")) + "</span></span></a></div>";
    }

    function card(e) {
      var d = new Date(e.start_at);
      var cover = e.cover_image || e.poster_image || "/assets/fallback/event-cover.webp";
      var media = e.image_kind !== "illustration" && e.poster_image
        ? '<img src="' + esc(cover) + '" alt="" loading="lazy">'
        : e.image_kind === "source_screenshot"
          ? '<div class="source-cover source-cover-' + esc(e.school || "other") + '" role="img" aria-label="' + esc(e.title + " 原始公告網頁截圖") + '">' +
            '<div class="source-cover-shot"><img src="' + esc(cover) + '" alt="" loading="lazy"></div>' +
            '<div class="source-cover-caption"><span>原始網頁截圖 · ' + esc(e.category || "活動") + '</span>' +
            '<strong>' + esc(e.title) + '</strong></div></div>'
        : '<div class="event-cover event-cover-' + esc(e.school || "other") + '" role="img" aria-label="' +
          esc((e.category || "活動") + "活動示意封面") + '">' +
          '<img class="event-cover-bg" src="' + esc(cover) + '" alt="" loading="lazy">' +
          '<div class="event-cover-content"><span class="event-cover-kicker">竹梅活動</span>' +
          '<strong>' + esc(e.category || "其他") + '</strong><span class="event-cover-note">示意封面</span></div></div>';
      var ongoing = ongoingLabel(e);
      var when = ongoing || ((d.getMonth() + 1) + "/" + d.getDate() + (e.all_day ? "" : " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0")));
      var bd = ongoing ? new Date(e.end_at) : d;
      var badge = '<div class="date-badge"><span class="m">' + (ongoing ? "至" : "") + (bd.getMonth() + 1) + '月</span><span class="d">' + bd.getDate() + "</span></div>";
      var where = [e.campus ? bundle.labels.campus[e.campus] : null, e.venue].filter(Boolean).join(" ");
      var heart = e.org_id
        ? '<button class="heart-btn card-heart" data-org-id="' + e.org_id + '" data-org-name="' + esc(e.org_name || e.organizer || "") + '" aria-pressed="false" title="追蹤 ' + esc(e.org_name || e.organizer || "") + '">' +
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 5a2 2 0 1 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3h-16a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6"/><path d="M9 17v1a3 3 0 0 0 6 0v-1"/></svg></button>'
        : "";
      return '<div class="card">' + heart + '<a class="card-link" href="/event/' + e.id + '/">' +
        '<div class="card-media">' + media +
        badge + "</div>" +
        '<div class="card-body">' +
        '<p class="chips"><span class="chip chip-' + esc(e.school) + '">' + esc(labels.school[e.school] || e.school) + "</span>" +
        '<span class="chip">' + esc(e.category || "其他") + "</span>" +
        (e.reg === "required" ? '<span class="chip chip-reg-req">需報名</span>' : e.reg === "free" ? '<span class="chip chip-reg-free">自由入場</span>' : "") +
        (e.fee === "free" ? '<span class="chip chip-fee-free">免費</span>' : e.fee === "paid" ? '<span class="chip chip-fee-paid">' + esc(e.price || "付費") + "</span>" : "") +
        (e.extraction && e.extraction.needs_review ? '<span class="chip chip-review">待確認</span>' : "") +
        "</p>" +
        '<h2 class="card-title">' + esc(e.title) + "</h2>" +
        '<p class="card-meta">' + esc(when) + (where ? "｜" + esc(where) : "") + "</p>" +
        '<p class="card-meta">' + esc(e.organizer || "") + "</p>" +
        "</div></a></div>";
    }

    // ---- 地圖（預設顯示，卡片接在下方） ----
    var mapState = { map: null, markers: [], ready: false, pending: [] };

    function schoolColor(s) {
      return s === "nthu" ? "#8E24AA" : s === "nycu" ? "#0045F2" : "#0F766E";
    }

    function initMap() {
      if (mapState.map || typeof maplibregl === "undefined" || mapState.failed) return mapState.map;
      var dark = document.documentElement.dataset.theme === "dark";
      var m;
      try {
        m = buildMap(dark);
      } catch (e) {
        // 無 WebGL 等環境地圖起不來；列表與篩選照常
        mapState.failed = true;
        console.error("map init failed:", e);
        return null;
      }
      m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
      m.on("load", function () {
        mapState.ready = true;
        renderMap(mapState.pending);
        try {
          m.addSource("campuses", { type: "geojson", data: "/data/map/campuses.geojson" });
          m.addLayer({
            id: "campus-fill", type: "fill", source: "campuses",
            paint: {
              "fill-color": ["match", ["get", "campus"], "nthu-main", "#8E24AA", "#0045F2"],
              "fill-opacity": 0.1
            }
          });
          m.addLayer({
            id: "campus-line", type: "line", source: "campuses",
            paint: {
              "line-color": ["match", ["get", "campus"], "nthu-main", "#8E24AA", "#0045F2"],
              "line-width": 2.2, "line-opacity": 0.8
            }
          });
          m.addSource("buildings", { type: "geojson", data: "/data/map/buildings.geojson" });
          m.addLayer({
            id: "campus-buildings", type: "fill-extrusion", source: "buildings", minzoom: 14.5,
            paint: {
              "fill-extrusion-color": dark ? "#566171" : "#9AA7B2",
              "fill-extrusion-height": ["coalesce", ["get", "height"], 5],
              "fill-extrusion-base": 0,
              "fill-extrusion-opacity": dark ? 0.48 : 0.34
            }
          });
        } catch (e) {
          // 校界與 3D 建築是輔助圖層；即使失敗，活動標記仍照常顯示。
        }
      });
      window.addEventListener("chumei-theme", function () {
        if (!mapState.ready) return;
        var isDark = document.documentElement.dataset.theme === "dark";
        m.setPaintProperty("base-map", "raster-brightness-max", isDark ? 0.62 : 1);
        m.setPaintProperty("base-map", "raster-saturation", isDark ? -0.35 : 0);
        if (m.getLayer("campus-buildings")) {
          m.setPaintProperty("campus-buildings", "fill-extrusion-color", isDark ? "#566171" : "#9AA7B2");
          m.setPaintProperty("campus-buildings", "fill-extrusion-opacity", isDark ? 0.48 : 0.34);
        }
      });
      mapState.map = m;
      return m;
    }

    function buildMap(dark) {
      return new maplibregl.Map({
        container: "map",
        center: [120.9928, 24.7915],
        zoom: 15.2,
        pitch: 38,
        bearing: -12,
        maxZoom: 19,
        cooperativeGestures: true,
        antialias: true,
        style: {
          version: 8,
          sources: {
            nlsc: {
              type: "raster",
              tiles: ["https://wmts.nlsc.gov.tw/wmts/EMAP/default/GoogleMapsCompatible/{z}/{y}/{x}"],
              tileSize: 256,
              attribution: "&copy; <a href='https://maps.nlsc.gov.tw/'>國土測繪中心</a>"
            }
          },
          layers: [{
            id: "base-map", type: "raster", source: "nlsc",
            paint: { "raster-brightness-max": dark ? 0.62 : 1, "raster-saturation": dark ? -0.35 : 0 }
          }]
        }
      });
    }

    function renderMap(list) {
      mapState.pending = list;
      var m = initMap();
      if (!m) {
        var unavailable = document.getElementById("map-note");
        if (unavailable) unavailable.textContent = "地圖載入失敗，活動仍可在下方卡片查看。";
        return;
      }
      if (!mapState.ready) return;
      mapState.markers.forEach(function (marker) { marker.remove(); });
      mapState.markers = [];
      var groups = {};
      var located = 0;
      var approximate = 0;
      list.forEach(function (e) {
        if (!e.geo) return;
        located++;
        if (e.geo.approximate) approximate++;
        var key = e.geo.lat.toFixed(5) + "," + e.geo.lng.toFixed(5);
        (groups[key] = groups[key] || { geo: e.geo, events: [] }).events.push(e);
      });
      Object.keys(groups).forEach(function (k) {
        var g = groups[k];
        var schools = {};
        g.events.forEach(function (e) { schools[e.school] = 1; });
        var color = Object.keys(schools).length === 1 ? schoolColor(g.events[0].school) : "#0F766E";
        var pin = document.createElement("button");
        pin.className = "ev-pin";
        pin.type = "button";
        pin.style.background = color;
        pin.textContent = g.events.length > 1 ? g.events.length : "";
        pin.setAttribute("aria-label", g.geo.name + "，" + g.events.length + " 場活動");
        var items = g.events.slice(0, 6).map(function (e) {
          var d = new Date(e.start_at);
          return '<a class="pop-ev" data-id="' + esc(e.id) + '" href="/event/' + e.id + '/">' +
            '<span class="pop-date">' + (d.getMonth() + 1) + "/" + d.getDate() + "</span>" + esc(e.title) + "</a>";
        }).join("");
        if (g.events.length > 6) items += '<p class="pop-more">…還有 ' + (g.events.length - 6) + " 場</p>";
        var html = '<div class="pop"><p class="pop-venue">' + esc(g.geo.name) + "</p>" + items + "</div>";
        var popup = new maplibregl.Popup({ offset: 20, maxWidth: "300px" }).setHTML(html);
        mapState.markers.push(new maplibregl.Marker({ element: pin, anchor: "center" })
          .setLngLat([g.geo.lng, g.geo.lat]).setPopup(popup).addTo(m));
      });
      var visibleGroups = Object.keys(groups).map(function (k) { return groups[k]; });
      if (state.campus === "all") {
        var hsinchu = visibleGroups.filter(function (g) {
          return g.geo.lat > 24.75 && g.geo.lat < 24.85 && g.geo.lng > 120.9 && g.geo.lng < 121.05;
        });
        if (hsinchu.length) visibleGroups = hsinchu;
      }
      if (visibleGroups.length === 1) {
        m.easeTo({ center: [visibleGroups[0].geo.lng, visibleGroups[0].geo.lat], zoom: 15.5, duration: 350 });
      } else if (visibleGroups.length > 1) {
        var bounds = new maplibregl.LngLatBounds();
        visibleGroups.forEach(function (g) { bounds.extend([g.geo.lng, g.geo.lat]); });
        m.fitBounds(bounds, { padding: 64, maxZoom: 15.5, duration: 350 });
      }
      var note = document.getElementById("map-note");
      if (note) {
        var unlocated = list.length - located;
        note.textContent = "地圖顯示 " + located + " 場可定位的活動" +
          (approximate > 0 ? "（其中 " + approximate + " 場為校區約略位置）" : "") +
          (unlocated > 0 ? "；另有 " + unlocated + " 場為線上、地點未定或查無座標的校外店家，請見下方活動卡片。" : "。");
      }
      var mapCount = document.getElementById("map-count");
      if (mapCount) mapCount.textContent = located + " 場可定位";
      setTimeout(function () { m.resize(); }, 60);
    }

    function syncUrl() {
      var qs = new URLSearchParams();
      Object.keys(state).forEach(function (k) {
        if (state[k] && state[k] !== "all" && !(k === "time" && state[k] === "7d")) qs.set(k, state[k]);
      });
      history.replaceState(null, "", qs.toString() ? "?" + qs.toString() : location.pathname);
    }

    function render() {
      var list = bundle.events.filter(matches);
      if (state.time === "all") {
        list = list.slice().reverse();
      } else {
        var now = Date.now();
        list = list.slice().sort(function (a, b) {
          return eventSortTime(a, now) - eventSortTime(b, now) ||
            new Date(a.start_at) - new Date(b.start_at) ||
            String(a.title || "").localeCompare(String(b.title || ""), "zh-Hant");
        });
      }
      document.getElementById("count").textContent = list.length + " 場活動";
      var listCount = document.getElementById("list-count");
      if (listCount) listCount.textContent = list.length + " 場";
      listEl.className = displayMode === "list" ? "event-rows" : "grid";
      listEl.innerHTML = list.length
        ? list.map(displayMode === "list" ? listRow : card).join("")
        : '<p class="empty">沒有符合條件的活動。試著放寬篩選，或到「全部」看看過去的活動。</p>';
      updateChipCounts();
      if (moreFilters) moreFilters.classList.toggle("fon", moreActive());
      renderMap(list);
      syncUrl();
    }

    var eventsById = {};
    bundle.events.forEach(function (e) { eventsById[e.id] = e; });
    bindEventHover(document.getElementById("map"), ".pop-ev",
      function (a) { return eventsById[a.dataset.id]; }, labels);

    render();
  }

  // ---- 日曆 ----
  function initCalendar(bundle) {
    var labels = bundle.labels;
    var state = { school: "all", campus: "all", cat: "all", org: "all", reg: "all", fee: "all", q: "" };
    var params = new URLSearchParams(location.search);
    Object.keys(state).forEach(function (k) { if (params.get(k)) state[k] = params.get(k); });

    var cats = {};
    bundle.events.forEach(function (e) { cats[e.category || "其他"] = 1; });

    var chipGroups = {};
    function buildChips(id, options, key) {
      var host = document.getElementById(id);
      if (!host) return;
      chipGroups[key] = { options: options, buttons: {} };
      options.forEach(function (opt) {
        var b = document.createElement("button");
        b.className = "fchip";
        b.dataset.value = opt[0];
        b.innerHTML = '<span class="fchip-label">' + esc(opt[1]) + '</span><span class="fchip-count" aria-hidden="true"></span>';
        b.setAttribute("aria-pressed", String(state[key] === opt[0]));
        chipGroups[key].buttons[opt[0]] = b;
        b.addEventListener("click", function () {
          state[key] = opt[0];
          host.querySelectorAll(".fchip").forEach(function (x) {
            x.setAttribute("aria-pressed", String(x.dataset.value === opt[0]));
          });
          redraw();
        });
        host.appendChild(b);
      });
    }
    buildChips("f-school", [["all", "全部"], ["nthu", "清大"], ["nycu", "陽明交大"], ["both", "兩校聯合"]], "school");
    buildChips("f-campus", [["all", "全部校區"]].concat(Object.keys(labels.campus).map(function (k) { return [k, labels.campus[k]]; })), "campus");
    buildChips("f-cat", [["all", "全部類型"]].concat(Object.keys(cats).sort().map(function (k) { return [k, k]; })), "cat");
    buildChips("f-org", [["all", "全部主辦"], ["official", "校方"], ["department", "系所"], ["club", "社團"], ["external", "校外"]], "org");
    buildChips("f-reg", [["all", "全部"], ["required", "需報名"], ["free", "自由入場"]], "reg");
    buildChips("f-fee", [["all", "全部"], ["free", "免費"], ["paid", "付費"]], "fee");

    var search = document.getElementById("search");
    if (search) {
      search.value = state.q;
      search.addEventListener("input", function () { state.q = search.value.trim(); redraw(); });
    }

    var moreFilters = document.getElementById("more-filters");
    function moreActive() {
      return state.school !== "all" || state.campus !== "all" || state.cat !== "all" ||
        state.org !== "all" || state.reg !== "all" || state.fee !== "all";
    }
    if (moreFilters && window.innerWidth <= 700 && moreActive()) moreFilters.open = true;

    function matches(e, overrideKey, overrideValue) {
      function value(k) { return overrideKey === k ? overrideValue : state[k]; }
      if (value("school") !== "all" && e.school !== value("school") && !(value("school") !== "both" && e.school === "both")) return false;
      if (value("campus") !== "all" && e.campus !== value("campus")) return false;
      if (value("cat") !== "all" && (e.category || "其他") !== value("cat")) return false;
      if (value("org") !== "all" && e.organizer_type !== value("org")) return false;
      if (value("reg") !== "all" && e.reg !== value("reg")) return false;
      if (value("fee") !== "all" && e.fee !== value("fee")) return false;
      if (state.q) {
        var hay = (e.title + " " + (e.summary || "") + " " + (e.organizer || "") + " " + (e.venue || "")).toLowerCase();
        if (hay.indexOf(state.q.toLowerCase()) === -1) return false;
      }
      return true;
    }

    var monthStartStr = (function () {
      var n = new Date();
      return n.getFullYear() + "-" + String(n.getMonth() + 1).padStart(2, "0") + "-01";
    })();
    function fromThisMonth(e) {
      return (e.start_at || "").slice(0, 10) >= monthStartStr;
    }

    function updateChipCounts() {
      Object.keys(chipGroups).forEach(function (key) {
        chipGroups[key].options.forEach(function (opt) {
          var b = chipGroups[key].buttons[opt[0]];
          if (!b) return;
          var n = bundle.events.filter(function (e) { return fromThisMonth(e) && matches(e, key, opt[0]); }).length;
          b.querySelector(".fchip-count").textContent = String(n);
          b.setAttribute("aria-label", opt[1] + "，本月起 " + n + " 場活動");
        });
      });
    }

    // 連續月曆：目前月起往下堆疊，捲到底自動加月份
    var now = new Date();
    var firstMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    var monthsAfter = 0, monthsBefore = 0;
    var fullCurrentMonth = false; // 手機議程：當月是否已展開到 1 號
    var MAX_AHEAD = 12, MAX_BACK = 6;

    var byDay = {};
    function indexEvents() {
      byDay = {};
      bundle.events.filter(function (e) { return matches(e); }).forEach(function (e) {
        var day = (e.start_at || "").slice(0, 10);
        (byDay[day] = byDay[day] || []).push(e);
      });
    }

    function agendaMonthHtml(m) {
      // 手機：議程列表 — 只列有活動的日子
      var daysInMonth = new Date(m.getFullYear(), m.getMonth() + 1, 0).getDate();
      var t = todayStr();
      var monthTotal = 0;
      var body = "";
      // 當月從今天開始列，過去的日子不佔版面；按「更早」會先展開當月完整月份
      var startDay = 1;
      if (!fullCurrentMonth && m.getFullYear() === now.getFullYear() && m.getMonth() === now.getMonth()) startDay = now.getDate();
      for (var day = startDay; day <= daysInMonth; day++) {
        var key = m.getFullYear() + "-" + String(m.getMonth() + 1).padStart(2, "0") + "-" + String(day).padStart(2, "0");
        var dayEvents = byDay[key] || [];
        if (!dayEvents.length) continue;
        monthTotal += dayEvents.length;
        var d = new Date(m.getFullYear(), m.getMonth(), day);
        var wd = "日一二三四五六"[d.getDay()];
        body += '<div class="agd-day' + (key === t ? " today" : "") + '">' +
          '<span class="agd-date">' + (m.getMonth() + 1) + "/" + day + "（" + wd + "）</span>" +
          dayEvents.map(function (e) {
            var ed = new Date(e.start_at);
            var when = e.all_day ? "全天" : String(ed.getHours()).padStart(2, "0") + ":" + String(ed.getMinutes()).padStart(2, "0");
            var where = [e.campus ? labels.campus[e.campus] : null, e.venue].filter(Boolean).join(" ");
            return '<a class="agd-ev ev-' + esc(e.school) + '" href="/event/' + e.id + '/">' +
              '<span class="agd-when">' + esc(when) + "</span>" +
              '<span class="agd-main"><span class="agd-title">' + esc(e.title) + "</span>" +
              (where ? '<span class="agd-meta">' + esc(where) + "</span>" : "") + "</span></a>";
          }).join("") + "</div>";
      }
      return '<section class="cal-month" id="cal-' + m.getFullYear() + "-" + (m.getMonth() + 1) + '">' +
        '<h2 class="cal-month-title">' + m.getFullYear() + " 年 " + (m.getMonth() + 1) + " 月" +
        '<span class="cal-month-n">' + monthTotal + " 場</span></h2>" +
        (body || '<p class="agd-empty">這個月（在目前篩選下）沒有活動。</p>') + "</section>";
    }

    function monthHtml(m) {
      if (window.innerWidth <= 700) return agendaMonthHtml(m);
      var startDow = m.getDay(); // 週日起始
      var first = new Date(m);
      first.setDate(1 - startDow);
      var daysInMonth = new Date(m.getFullYear(), m.getMonth() + 1, 0).getDate();
      var totalCells = Math.ceil((startDow + daysInMonth) / 7) * 7; // 只畫需要的列
      var t = todayStr();
      var cells = ["日", "一", "二", "三", "四", "五", "六"].map(function (d) { return '<div class="cal-dow">' + d + "</div>"; }).join("");
      var monthTotal = 0;
      for (var i = 0; i < totalCells; i++) {
        var d = new Date(first);
        d.setDate(first.getDate() + i);
        var inMonth = d.getMonth() === m.getMonth();
        if (!inMonth) {
          cells += '<div class="cal-cell cal-empty" aria-hidden="true"></div>';
          continue;
        }
        var key = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
        var cls = "cal-cell" + (key === t ? " today" : "");
        var dayEvents = byDay[key] || [];
        monthTotal += dayEvents.length;
        var evs = dayEvents.map(function (e) {
          var ed = new Date(e.start_at);
          var tt = e.all_day ? "" : String(ed.getHours()).padStart(2, "0") + ":" + String(ed.getMinutes()).padStart(2, "0");
          return '<a class="cal-ev ev-' + esc(e.school) + '" data-id="' + esc(e.id) + '" href="/event/' + e.id + '/">' +
            (tt ? '<span class="cal-ev-t">' + tt + "</span>" : "") + esc(e.title) + "</a>";
        }).join("");
        cells += '<div class="' + cls + '"><span class="cal-day">' + d.getDate() + "</span>" + evs + "</div>";
      }
      return '<section class="cal-month" id="cal-' + m.getFullYear() + "-" + (m.getMonth() + 1) + '">' +
        '<h2 class="cal-month-title">' + m.getFullYear() + " 年 " + (m.getMonth() + 1) + " 月" +
        '<span class="cal-month-n">' + monthTotal + " 場</span></h2>" +
        '<div class="cal-grid">' + cells + "</div></section>";
    }

    function monthAt(offset) {
      return new Date(firstMonth.getFullYear(), firstMonth.getMonth() + offset, 1);
    }

    function redraw() {
      indexEvents();
      updateChipCounts();
      if (moreFilters) moreFilters.classList.toggle("fon", moreActive());
      var html = "";
      for (var i = -monthsBefore; i <= monthsAfter; i++) html += monthHtml(monthAt(i));
      calEl.innerHTML = html;
      var total = bundle.events.filter(function (e) { return fromThisMonth(e) && matches(e); }).length;
      var count = document.getElementById("cal-count");
      if (count) count.textContent = "目前篩選自本月起共 " + total + " 場活動。";
      var qs = new URLSearchParams();
      Object.keys(state).forEach(function (k) { if (state[k] && state[k] !== "all") qs.set(k, state[k]); });
      history.replaceState(null, "", qs.toString() ? "?" + qs.toString() : location.pathname);
    }

    var earlier = document.getElementById("cal-earlier");
    if (earlier) earlier.addEventListener("click", function () {
      // 手機議程模式下當月只列到今天：第一按先回到當月 1 號，再按才載入上個月
      if (window.innerWidth <= 700 && !fullCurrentMonth && now.getDate() > 1) {
        fullCurrentMonth = true;
        redraw();
        return;
      }
      if (monthsBefore < MAX_BACK) { monthsBefore++; redraw(); }
      if (monthsBefore >= MAX_BACK) earlier.disabled = true;
    });
    var todayBtn = document.getElementById("cal-today");
    if (todayBtn) todayBtn.addEventListener("click", function () {
      var el = document.getElementById("cal-" + now.getFullYear() + "-" + (now.getMonth() + 1));
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    var sentinel = document.getElementById("cal-sentinel");
    if (sentinel && "IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting && monthsAfter < MAX_AHEAD) {
          monthsAfter += 2;
          redraw();
        }
      }, { rootMargin: "600px" }).observe(sentinel);
    }

    var byIdCal = {};
    bundle.events.forEach(function (e) { byIdCal[e.id] = e; });
    bindEventHover(calEl, ".cal-ev", function (a) { return byIdCal[a.dataset.id]; }, labels);

    var calResizeT;
    window.addEventListener("resize", function () {
      clearTimeout(calResizeT);
      calResizeT = setTimeout(redraw, 200);
    });

    monthsAfter = 2;
    redraw();
  }
})();

/* PWA：service worker 註冊（推播與安裝性；sw.js 不做快取）。 */
(function () {
  "use strict";
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  });
})();

/* 追蹤（愛心）：追蹤單位＝push 偏好的 orgs。未開推播也先記在 localStorage，
   開啟推播後（/notify/）同一份偏好直接生效。 */
(function () {
  "use strict";
  function readPrefs() {
    try { return JSON.parse(localStorage.getItem("push-prefs") || "null") || {}; } catch (e) { return {}; }
  }
  function writePrefs(p) { try { localStorage.setItem("push-prefs", JSON.stringify(p)); } catch (e) {} }
  function isFollowed(id) {
    return (readPrefs().orgs || []).some(function (o) { return String(o.id) === String(id); });
  }
  var syncT;
  function syncServer() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    clearTimeout(syncT);
    syncT = setTimeout(function () {
      navigator.serviceWorker.getRegistration().then(function (reg) {
        return reg && reg.pushManager.getSubscription();
      }).then(function (sub) {
        if (!sub) return;
        var p = readPrefs();
        return fetch("/push/subscribe", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ subscription: sub.toJSON(), prefs: {
            schools: p.schools || [], cats: p.cats || [], orgs: p.orgs || [], keywords: p.keywords || []
          } })
        });
      }).catch(function () {});
    }, 500);
  }
  function toggle(id, name) {
    var p = readPrefs();
    p.orgs = p.orgs || [];
    var i = p.orgs.findIndex(function (o) { return String(o.id) === String(id); });
    var followed;
    if (i >= 0) { p.orgs.splice(i, 1); followed = false; }
    else { p.orgs.push({ id: isNaN(+id) ? id : +id, name: name }); followed = true; }
    writePrefs(p); syncServer(); refresh();
    window.dispatchEvent(new CustomEvent("chumei-follow-change", { detail: { id: id, followed: followed } }));
    return followed;
  }
  function refresh() {
    document.querySelectorAll(".heart-btn").forEach(function (b) {
      b.setAttribute("aria-pressed", String(isFollowed(b.dataset.orgId)));
    });
  }
  var toastT;
  function toast(html) {
    var el = document.querySelector(".chumei-toast");
    if (!el) { el = document.createElement("div"); el.className = "chumei-toast"; document.body.appendChild(el); }
    el.innerHTML = html;
    el.classList.add("show");
    clearTimeout(toastT);
    toastT = setTimeout(function () { el.classList.remove("show"); }, 3800);
  }
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest(".heart-btn");
    if (!b || !b.dataset.orgId) return;
    ev.preventDefault();
    var name = b.dataset.orgName || "這個單位";
    if (toggle(b.dataset.orgId, name)) {
      var pushOn = false;
      try { pushOn = "Notification" in window && Notification.permission === "granted"; } catch (e) {}
      toast("🔔 已追蹤 " + name + (pushOn ? "，有新活動會通知你" : "——<a href=\"/notify/\">開啟推播</a>才會收到通知"));
    } else {
      toast("已取消追蹤 " + name);
    }
  });
  // 河道/卡片重繪後補上愛心狀態（childList 觀察不會被 aria-pressed 自身觸發）
  new MutationObserver(refresh).observe(document.documentElement, { childList: true, subtree: true });
  if (document.readyState !== "loading") refresh();
  else document.addEventListener("DOMContentLoaded", refresh);
  window.chumeiFollow = { isFollowed: isFollowed, toggle: toggle, refresh: refresh, sync: syncServer };
})();
