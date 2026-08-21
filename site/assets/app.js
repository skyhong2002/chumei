/* 竹梅前端：主題切換、活動河道篩選、日曆檢視。無相依套件。 */
(function () {
  "use strict";

  // ---- 主題切換 ----
  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var root = document.documentElement;
      var next = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) {}
      window.dispatchEvent(new CustomEvent("chumei-theme"));
    });
  }

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
      el.innerHTML = '<p class="empty">活動資料載入失敗，請稍後再試。</p>';
    });

  // ---- 首頁貼文河道 ----
  function initFeed() {
    var feed = document.getElementById("post-feed");
    if (!feed) return;
    var PLAT = { instagram: "IG", facebook: "FB", threads: "Threads", x: "X", bulletin: "公告", api: "官方" };

    fetch("/data/posts.json").then(function (r) { return r.json(); }).then(function (data) {
      var posts = data.posts;
      var state = { school: "all", platform: "all", q: "" };
      var params = new URLSearchParams(location.search);
      Object.keys(state).forEach(function (k) { if (params.get(k)) state[k] = params.get(k); });

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
      chips("pf-school", [["all", "全部"], ["nthu", "清大"], ["nycu", "陽明交大"], ["both", "兩校聯合"]], "school");
      chips("pf-platform", [["all", "全部"], ["instagram", "IG"], ["facebook", "FB"], ["threads", "Threads"], ["bulletin", "公告"]], "platform");

      var search = document.getElementById("search");
      if (search) {
        search.value = state.q;
        search.addEventListener("input", function () { state.q = search.value.trim(); render(); });
      }

      function matches(p, ok, ov) {
        function v(k) { return ok === k ? ov : state[k]; }
        if (v("school") !== "all" && p.school !== v("school") && !(v("school") !== "both" && p.school === "both")) return false;
        if (v("platform") !== "all" && p.platform !== v("platform")) return false;
        if (state.q) {
          var hay = ((p.source_name || "") + " " + (p.text || "") + " " +
            p.events.map(function (e) { return e.title; }).join(" ")).toLowerCase();
          if (hay.indexOf(state.q.toLowerCase()) === -1) return false;
        }
        return true;
      }

      function ago(iso) {
        var ms = Date.now() - new Date(iso).getTime();
        var h = ms / 36e5;
        if (h < 1) return Math.max(1, Math.round(h * 60)) + " 分鐘前";
        if (h < 24) return Math.round(h) + " 小時前";
        var d = new Date(iso);
        return (d.getMonth() + 1) + "/" + d.getDate();
      }

      function evChip(e) {
        var d = new Date(e.start_at);
        var when = (d.getMonth() + 1) + "/" + d.getDate() +
          (e.all_day ? "" : " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"));
        return '<a class="feed-ev" href="/event/' + e.id + '/">🗓 ' + esc(when) + "｜" + esc(e.title) + "</a>";
      }

      function row(p) {
        var avatar = p.avatar
          ? '<img class="feed-avatar" src="' + esc(p.avatar) + '" alt="">'
          : '<span class="feed-avatar src-avatar-fallback av-' + esc(p.school) + '">' +
            esc((p.source_name || "？").replace(/^(清大|交大|陽明|國立)/, "").charAt(0)) + "</span>";
        var head = '<div class="feed-head">' + avatar +
          '<span class="feed-who"><strong>' + esc(p.source_name || "") + "</strong>" +
          '<span class="feed-sub">' + esc(PLAT[p.platform] || p.platform) + " ・ " + esc(ago(p.posted_at)) +
          '<span class="chip chip-' + esc(p.school) + '">' + esc((data.labels.school || {})[p.school] || "") + "</span></span></span>" +
          (p.url ? '<a class="feed-orig" href="' + esc(p.url) + '" rel="noopener" target="_blank">原文 ↗</a>' : "") + "</div>";
        var body = '<div class="feed-body">' +
          (p.text ? '<p class="feed-text">' + esc(p.text) + "</p>" : "") +
          (p.image ? '<img class="feed-img" src="' + esc(p.image) + '" alt="" loading="lazy">' : "") + "</div>";
        var evs = '<div class="feed-evs">' + p.events.map(evChip).join("") + "</div>";
        return '<article class="feed-post">' + head + body + evs + "</article>";
      }

      var shown = 30;
      function render(more) {
        var list = posts.filter(function (p) { return matches(p); });
        if (!more) shown = 30;
        document.getElementById("feed-count").textContent = "共 " + list.length + " 則活動貼文。";
        feed.innerHTML = list.slice(0, shown).map(row).join("") +
          (list.length > shown ? '<button class="fchip feed-more">載入更多（還有 ' + (list.length - shown) + " 則）</button>" : "") ||
          '<p class="empty">沒有符合的貼文。</p>';
        Object.keys(groups).forEach(function (key) {
          groups[key].options.forEach(function (opt) {
            var b = groups[key].buttons[opt[0]];
            if (b) b.querySelector(".fchip-count").textContent =
              String(posts.filter(function (p) { return matches(p, key, opt[0]); }).length);
          });
        });
        var qs = new URLSearchParams();
        Object.keys(state).forEach(function (k) { if (state[k] && state[k] !== "all") qs.set(k, state[k]); });
        history.replaceState(null, "", qs.toString() ? "?" + qs.toString() : location.pathname);
      }
      feed.addEventListener("click", function (ev) {
        if (ev.target.classList.contains("feed-more")) { shown += 30; render(true); }
      });
      render();
    }).catch(function () {
      feed.innerHTML = '<p class="empty">貼文載入失敗。</p>';
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
      var state = { school: "all", status: "all", kind: "all", platform: "all", q: "" };
      var params = new URLSearchParams(location.search);
      Object.keys(state).forEach(function (k) { if (params.get(k)) state[k] = params.get(k); });

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
      chips("sf-school", [["all", "全部"], ["nthu", "清大"], ["nycu", "陽明交大"], ["nycu-guangfu", "交大校區"], ["nycu-yangming", "陽明校區"]], "school");
      chips("sf-status", [["all", "全部"], ["covered", "已收錄"], ["uncovered", "尚未收錄"]], "status");
      chips("sf-kind", [["all", "全部"]].concat(Object.keys(KIND).map(function (k) { return [k, KIND[k]]; })), "kind");
      chips("sf-platform", [["all", "全部"], ["instagram", "IG"], ["facebook", "FB"], ["threads", "Threads"], ["x", "X"]], "platform");

      var search = document.getElementById("search");
      if (search) {
        search.value = state.q;
        search.addEventListener("input", function () { state.q = search.value.trim(); render(); });
      }

      function matches(e, ok, ov) {
        function v(k) { return ok === k ? ov : state[k]; }
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
          ? '<img class="src-avatar" src="' + esc(e.avatar) + '" alt="" loading="lazy">'
          : '<span class="src-avatar src-avatar-fallback av-' + esc(e.school) + '">' + esc(e.name.replace(/^(清大|交大|陽明|國立)/, "").charAt(0) || "？") + "</span>";
        return '<div class="src-row' + (e.links.length ? "" : " src-uncovered") + '">' +
          '<div class="src-main">' + avatar +
          '<span class="src-id" aria-label="名錄 ID ' + e.id + '">#' + e.id + "</span>" +
          '<span class="chips">' +
          '<span class="chip chip-school chip-' + esc(e.school) + '">' + esc(e.school === "nthu" ? "清大" : e.school === "nycu" ? "陽明交大" : "其他") + "</span>" +
          (e.campus ? '<span class="chip chip-campus">' + (e.campus === "yangming" ? "陽明" : "交大") + "</span>" : "") +
          '<span class="chip chip-extra">' + esc(KIND[e.kind] || "") + "</span>" +
          (e.category ? '<span class="chip chip-extra">' + esc(e.category) + "</span>" : "") +
          '</span><strong><a class="src-name" href="/org/' + e.id + '/">' + esc(e.name) + "</a></strong></div>" +
          '<div class="src-links">' + (links || '<span class="src-none">尚未找到公開帳號</span>') + "</div>" +
          '<div class="src-upd" title="' + esc(e.updated || "") + '">' + fmtUpdated(e.updated) + "</div>" +
          '<div class="src-ev">' + (e.events ? e.events + " 場" : "—") + "</div></div>";
      }

      function render() {
        Object.keys(groups).forEach(function (key) {
          groups[key].options.forEach(function (opt) {
            var b = groups[key].buttons[opt[0]];
            if (b) b.querySelector(".fchip-count").textContent = String(entries.filter(function (e) { return matches(e, key, opt[0]); }).length);
          });
        });
        var list = entries.filter(function (e) { return matches(e); });
        document.getElementById("src-count").textContent = "目前列出 " + list.length + " 個單位。";
        table.innerHTML = list.map(row).join("") || '<p class="empty">沒有符合的單位。</p>';
        var qs = new URLSearchParams();
        Object.keys(state).forEach(function (k) { if (state[k] && state[k] !== "all") qs.set(k, state[k]); });
        history.replaceState(null, "", qs.toString() ? "?" + qs.toString() : location.pathname);
      }
      render();
    }).catch(function () {
      table.innerHTML = '<p class="empty">名錄載入失敗。</p>';
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
              '<span class="sc-meta"><strong>' + esc(s.name) + "</strong>" + ago(s.taken_at) + "</span></button>";
          }).join("");
          wall.addEventListener("click", function (ev) {
            var b = ev.target.closest(".story-card");
            if (b) openLightbox(parseInt(b.dataset.i, 10));
          });
        }

        var lb = null, cur = 0;
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
      })
      .catch(function () { if (wall) wall.innerHTML = '<p class="empty">限時動態載入失敗。</p>'; });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function todayStr() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  // ---- 活動河道 ----
  function initList(bundle) {
    var labels = bundle.labels;
    var state = { time: "7d", school: "all", campus: "all", cat: "all", org: "all", q: "" };

    var params = new URLSearchParams(location.search);
    ["time", "school", "campus", "cat", "org", "q"].forEach(function (k) {
      if (params.get(k)) state[k] = params.get(k);
    });
    if (state.time === "week") state.time = "7d";

    var moreFilters = document.getElementById("more-filters");
    if (moreFilters && (window.innerWidth > 700 || state.school !== "all" || state.campus !== "all" || state.cat !== "all" || state.org !== "all")) {
      moreFilters.open = true;
    }
    window.addEventListener("resize", function () {
      if (moreFilters && window.innerWidth > 700) moreFilters.open = true;
    });

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
      var when = (d.getMonth() + 1) + "/" + d.getDate() + "（" + wd + "）" +
        (e.all_day ? "" : " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"));
      var where = [e.campus ? labels.campus[e.campus] : null, e.venue].filter(Boolean).join(" ");
      var thumb = e.poster_image
        ? '<img class="evr-thumb" src="' + esc(e.poster_image) + '" alt="" loading="lazy">'
        : '<span class="evr-thumb evr-thumb-txt np-' + esc(e.school === "nthu" ? "nthu" : e.school === "nycu" ? "nycu" : "other") + '">' +
          (e.school === "nthu" ? "梅" : e.school === "nycu" ? "竹" : "梅竹") + "</span>";
      return '<a class="ev-row ev-row-' + esc(e.school) + '" href="/event/' + e.id + '/">' + thumb +
        '<span class="evr-main"><span class="evr-when">' + esc(when) +
        (e.extraction && e.extraction.needs_review ? '<span class="chip chip-review">待確認</span>' : "") +
        '</span><span class="evr-title">' + esc(e.title) + "</span>" +
        '<span class="evr-meta">' + esc([where, e.organizer].filter(Boolean).join("｜")) + "</span></span></a>";
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
      var when = (d.getMonth() + 1) + "/" + d.getDate() + (e.all_day ? "" : " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"));
      var where = [e.campus ? bundle.labels.campus[e.campus] : null, e.venue].filter(Boolean).join(" ");
      return '<div class="card"><a class="card-link" href="/event/' + e.id + '/">' +
        '<div class="card-media">' + media +
        '<div class="date-badge"><span class="m">' + (d.getMonth() + 1) + '月</span><span class="d">' + d.getDate() + "</span></div></div>" +
        '<div class="card-body">' +
        '<p class="chips"><span class="chip chip-' + esc(e.school) + '">' + esc(labels.school[e.school] || e.school) + "</span>" +
        '<span class="chip">' + esc(e.category || "其他") + "</span>" +
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
      if (mapState.map || typeof maplibregl === "undefined") return mapState.map;
      var dark = document.documentElement.dataset.theme === "dark";
      var m = new maplibregl.Map({
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
          return '<a class="pop-ev" href="/event/' + e.id + '/">' +
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
          (unlocated > 0 ? "；另有 " + unlocated + " 場為線上活動或地點未定，請見下方活動卡片。" : "。");
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
      if (state.time === "all") list = list.slice().reverse();
      document.getElementById("count").textContent = list.length + " 場活動";
      var listCount = document.getElementById("list-count");
      if (listCount) listCount.textContent = list.length + " 場";
      listEl.className = displayMode === "list" ? "event-rows" : "grid";
      listEl.innerHTML = list.length
        ? list.map(displayMode === "list" ? listRow : card).join("")
        : '<p class="empty">沒有符合條件的活動。試著放寬篩選，或到「全部」看看過去的活動。</p>';
      updateChipCounts();
      renderMap(list);
      syncUrl();
    }

    render();
  }

  // ---- 日曆 ----
  function initCalendar(bundle) {
    var labels = bundle.labels;
    var state = { school: "all", campus: "all", cat: "all", org: "all", q: "" };
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

    var search = document.getElementById("search");
    if (search) {
      search.value = state.q;
      search.addEventListener("input", function () { state.q = search.value.trim(); redraw(); });
    }

    function matches(e, overrideKey, overrideValue) {
      function value(k) { return overrideKey === k ? overrideValue : state[k]; }
      if (value("school") !== "all" && e.school !== value("school") && !(value("school") !== "both" && e.school === "both")) return false;
      if (value("campus") !== "all" && e.campus !== value("campus")) return false;
      if (value("cat") !== "all" && (e.category || "其他") !== value("cat")) return false;
      if (value("org") !== "all" && e.organizer_type !== value("org")) return false;
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
    var MAX_AHEAD = 12, MAX_BACK = 6;

    var byDay = {};
    function indexEvents() {
      byDay = {};
      bundle.events.filter(function (e) { return matches(e); }).forEach(function (e) {
        var day = (e.start_at || "").slice(0, 10);
        (byDay[day] = byDay[day] || []).push(e);
      });
    }

    function monthHtml(m) {
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
          return '<a class="cal-ev ev-' + esc(e.school) + '" data-id="' + esc(e.id) + '" href="/event/' + e.id + '/">' + esc(e.title) + "</a>";
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

    // hover 預覽卡（僅指標裝置）
    if (window.matchMedia("(hover: hover)").matches) {
      var byId = {};
      bundle.events.forEach(function (e) { byId[e.id] = e; });
      var pop = document.createElement("div");
      pop.className = "cal-pop";
      pop.hidden = true;
      document.body.appendChild(pop);

      function fmtWhen(e) {
        var d = new Date(e.start_at);
        var wd = "日一二三四五六"[d.getDay()];
        var base = (d.getMonth() + 1) + "/" + d.getDate() + "（" + wd + "）";
        return e.all_day ? base : base + " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
      }

      calEl.addEventListener("mouseover", function (ev) {
        var a = ev.target.closest(".cal-ev");
        if (!a) return;
        var e = byId[a.dataset.id];
        if (!e) return;
        var cover = e.cover_image || e.poster_image;
        var where = [e.campus ? labels.campus[e.campus] : null, e.venue].filter(Boolean).join(" ");
        pop.innerHTML =
          (cover ? '<img src="' + esc(cover) + '" alt="">' : "") +
          '<div class="cal-pop-body"><p class="chips"><span class="chip chip-' + esc(e.school) + '">' +
          esc(labels.school[e.school] || "") + '</span><span class="chip">' + esc(e.category || "其他") + "</span></p>" +
          "<strong>" + esc(e.title) + "</strong>" +
          '<span class="cal-pop-meta">' + esc(fmtWhen(e)) + (where ? "｜" + esc(where) : "") + "</span>" +
          '<span class="cal-pop-meta">' + esc(e.organizer || "") + "</span></div>";
        pop.hidden = false;
        var r = a.getBoundingClientRect();
        var pw = 280, ph = pop.offsetHeight || 200;
        var x = Math.min(Math.max(8, r.left), window.innerWidth - pw - 12);
        var y = r.bottom + 8;
        if (y + ph > window.innerHeight - 8) y = Math.max(8, r.top - ph - 8);
        pop.style.left = x + "px";
        pop.style.top = y + "px";
      });
      calEl.addEventListener("mouseout", function (ev) {
        if (ev.target.closest(".cal-ev") && !(ev.relatedTarget && ev.relatedTarget.closest(".cal-ev"))) pop.hidden = true;
      });
      window.addEventListener("scroll", function () { pop.hidden = true; }, { passive: true });
    }

    monthsAfter = 2;
    redraw();
  }
})();
