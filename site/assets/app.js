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

    var cats = {};
    bundle.events.forEach(function (e) { cats[e.category || "其他"] = 1; });

    buildChips("f-time", [["upcoming", "即將登場"], ["week", "一週內"], ["all", "全部"]], "time");
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
      options.forEach(function (opt) {
        var b = document.createElement("button");
        b.className = "fchip";
        b.textContent = opt[1];
        b.dataset.value = opt[0];
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

    function matches(e) {
      var t = todayStr();
      var day = (e.start_at || "").slice(0, 10);
      if (state.time === "upcoming" && day < t) return false;
      if (state.time === "week") {
        var end = new Date(Date.now() + 7 * 864e5);
        var endStr = end.getFullYear() + "-" + String(end.getMonth() + 1).padStart(2, "0") + "-" + String(end.getDate()).padStart(2, "0");
        if (day < t || day > endStr) return false;
      }
      if (state.school !== "all" && e.school !== state.school && !(state.school !== "both" && e.school === "both")) return false;
      if (state.campus !== "all" && e.campus !== state.campus) return false;
      if (state.cat !== "all" && (e.category || "其他") !== state.cat) return false;
      if (state.org !== "all" && e.organizer_type !== state.org) return false;
      if (state.q) {
        var hay = (e.title + " " + (e.summary || "") + " " + (e.organizer || "") + " " + (e.venue || "")).toLowerCase();
        if (hay.indexOf(state.q.toLowerCase()) === -1) return false;
      }
      return true;
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

    function render() {
      var list = bundle.events.filter(matches);
      if (state.time === "all") list = list.slice().reverse();
      document.getElementById("count").textContent = list.length + " 場活動";
      listEl.innerHTML = list.length
        ? list.map(card).join("")
        : '<p class="empty">沒有符合條件的活動。試著放寬篩選，或到「全部」看看過去的活動。</p>';
      var qs = new URLSearchParams();
      Object.keys(state).forEach(function (k) {
        if (state[k] && state[k] !== "all" && !(k === "time" && state[k] === "upcoming")) qs.set(k, state[k]);
      });
      history.replaceState(null, "", qs.toString() ? "?" + qs.toString() : location.pathname);
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
