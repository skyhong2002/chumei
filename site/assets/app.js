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
    var state = { time: "upcoming", school: "all", campus: "all", cat: "all", org: "all", q: "" };

    var params = new URLSearchParams(location.search);
    ["time", "school", "campus", "cat", "org", "q"].forEach(function (k) {
      if (params.get(k)) state[k] = params.get(k);
    });

    var moreFilters = document.getElementById("more-filters");
    if (moreFilters && (window.innerWidth > 700 || state.school !== "all" || state.campus !== "all" || state.cat !== "all" || state.org !== "all")) {
      moreFilters.open = true;
    }
    window.addEventListener("resize", function () {
      if (moreFilters && window.innerWidth > 700) moreFilters.open = true;
    });

    var cats = {};
    bundle.events.forEach(function (e) { cats[e.category || "其他"] = 1; });

    var start = new Date();
    start = new Date(start.getFullYear(), start.getMonth(), start.getDate());
    var weekEnd = new Date(start);
    weekEnd.setDate(weekEnd.getDate() + 7);
    function md(d) { return (d.getMonth() + 1) + "/" + d.getDate(); }

    var chipGroups = {};
    buildChips("f-time", [["upcoming", md(start) + " 起"], ["week", md(start) + "–" + md(weekEnd)], ["all", "全部"]], "time");
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
      var t = todayStr();
      var day = (e.start_at || "").slice(0, 10);
      if (value("time") === "upcoming" && day < t) return false;
      if (value("time") === "week") {
        var endStr = weekEnd.getFullYear() + "-" + String(weekEnd.getMonth() + 1).padStart(2, "0") + "-" + String(weekEnd.getDate()).padStart(2, "0");
        if (day < t || day > endStr) return false;
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
      var npCls = e.school === "nthu" ? "np-nthu" : e.school === "nycu" ? "np-nycu" : "np-other";
      var media = e.poster_image
        ? '<img src="' + esc(e.poster_image) + '" alt="" loading="lazy">'
        : '<div class="no-poster ' + npCls + '">' + (e.school === "nthu" ? "梅" : e.school === "nycu" ? "竹" : "竹梅") + "</div>";
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
        mapState.ready = true;
        renderMap(mapState.pending);
      });
      window.addEventListener("chumei-theme", function () {
        if (!mapState.ready) return;
        var isDark = document.documentElement.dataset.theme === "dark";
        m.setPaintProperty("base-map", "raster-brightness-max", isDark ? 0.62 : 1);
        m.setPaintProperty("base-map", "raster-saturation", isDark ? -0.35 : 0);
        m.setPaintProperty("campus-buildings", "fill-extrusion-color", isDark ? "#566171" : "#9AA7B2");
        m.setPaintProperty("campus-buildings", "fill-extrusion-opacity", isDark ? 0.48 : 0.34);
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
      list.forEach(function (e) {
        if (!e.geo) return;
        located++;
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
      // 預設視角固定在光復＋清大本部核心區，不隨標記自動縮放（南大/陽明的活動自行拖曳查看）
      var note = document.getElementById("map-note");
      if (note) {
        var unlocated = list.length - located;
        note.textContent = "地圖顯示 " + located + " 場可定位的活動" +
          (unlocated > 0 ? "；另有 " + unlocated + " 場為線上活動或地點未定，請見下方活動卡片。" : "。");
      }
      var mapCount = document.getElementById("map-count");
      if (mapCount) mapCount.textContent = located + " 場可定位";
      setTimeout(function () { m.resize(); }, 60);
    }

    function syncUrl() {
      var qs = new URLSearchParams();
      Object.keys(state).forEach(function (k) {
        if (state[k] && state[k] !== "all" && !(k === "time" && state[k] === "upcoming")) qs.set(k, state[k]);
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
