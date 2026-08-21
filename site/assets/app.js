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

  var listEl = document.getElementById("event-list");
  var calEl = document.getElementById("cal-grid");
  initStories();
  if (!listEl && !calEl) return;

  fetch("/data/events.json")
    .then(function (r) { return r.json(); })
    .then(function (bundle) {
      if (listEl) initList(bundle);
      if (calEl) initCalendar(bundle);
    })
    .catch(function () {
      var el = listEl || calEl;
      el.innerHTML = '<p class="empty">活動資料載入失敗，請稍後再試。</p>';
    });

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
      listEl.innerHTML = list.length
        ? list.map(card).join("")
        : '<p class="empty">沒有符合條件的活動。試著放寬篩選，或到「全部」看看過去的活動。</p>';
      updateChipCounts();
      renderMap(list);
      syncUrl();
    }

    render();
  }

  // ---- 日曆 ----
  function initCalendar(bundle) {
    var cur = new Date();
    cur.setDate(1);
    var title = document.getElementById("cal-title");
    document.getElementById("cal-prev").addEventListener("click", function () { cur.setMonth(cur.getMonth() - 1); draw(); });
    document.getElementById("cal-next").addEventListener("click", function () { cur.setMonth(cur.getMonth() + 1); draw(); });

    var byDay = {};
    bundle.events.forEach(function (e) {
      var day = (e.start_at || "").slice(0, 10);
      (byDay[day] = byDay[day] || []).push(e);
    });

    function draw() {
      title.textContent = cur.getFullYear() + " 年 " + (cur.getMonth() + 1) + " 月";
      var startDow = (cur.getDay() + 6) % 7; // 週一起始
      var first = new Date(cur);
      first.setDate(1 - startDow);
      var t = todayStr();
      var html = ["一", "二", "三", "四", "五", "六", "日"].map(function (d) { return '<div class="cal-dow">' + d + "</div>"; }).join("");
      for (var i = 0; i < 42; i++) {
        var d = new Date(first);
        d.setDate(first.getDate() + i);
        var key = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
        var cls = "cal-cell" + (d.getMonth() !== cur.getMonth() ? " other-month" : "") + (key === t ? " today" : "");
        var evs = (byDay[key] || []).map(function (e) {
          return '<a class="cal-ev ev-' + esc(e.school) + '" href="/event/' + e.id + '/" title="' + esc(e.title) + '">' + esc(e.title) + "</a>";
        }).join("");
        html += '<div class="' + cls + '"><span class="cal-day">' + d.getDate() + "</span>" + evs + "</div>";
      }
      calEl.innerHTML = html;
    }
    draw();
  }
})();
