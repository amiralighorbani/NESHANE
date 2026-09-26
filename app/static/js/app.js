/* نشانه — لایهٔ تعاملی سبک (بدون فریم‌ورک) */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
  var AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";

  /* ارقام فارسی/عربی را به لاتین برمی‌گرداند تا ورودی کیبورد فارسی هم پذیرفته شود. */
  function toAsciiDigits(value) {
    return String(value == null ? "" : value)
      .replace(/[\u06F0-\u06F9]/g, function (ch) { return String(FA_DIGITS.indexOf(ch)); })
      .replace(/[\u0660-\u0669]/g, function (ch) { return String(AR_DIGITS.indexOf(ch)); });
  }

  /* فقط ارقام، مستقل از زبان کیبورد. */
  function digitsOnly(value) {
    return toAsciiDigits(value).replace(/\D/g, "");
  }

  /* ------------------------------------------------------------- ابزارها */

  /*
   * توست‌ها: هر پیام کوتاه از بالای صفحه سر می‌رسد، خودش می‌رود و با انگشت هم
   * کنار زده می‌شود. سه پیام بیشتر هم‌زمان نشان داده نمی‌شود تا صفحه شلوغ نشود.
   *
   *   toast("متن")                      → پیام اطلاعی
   *   toast("متن", "success")           → پیام موفقیت
   *   toast("متن", {kind: "error", title: "نشد", life: 6000})
   */
  var TOAST_TONES = {
    success: { icon: "fa-solid fa-circle-check", title: "انجام شد" },
    error: { icon: "fa-solid fa-circle-exclamation", title: "نشد" },
    warning: { icon: "fa-solid fa-triangle-exclamation", title: "حواست باشد" },
    info: { icon: "fa-solid fa-circle-info", title: "یک نکته" }
  };
  var MAX_TOASTS = 3;
  var recentToasts = [];
  // دفترچهٔ کوچکِ آخرین پیام‌ها؛ هم برای رفع اشکال و هم برای آزمون خودکار.
  var toastLog = [];

  function toastStack() {
    return document.getElementById("toast");
  }

  function dismissToast(item) {
    if (!item || item.dataset.leaving === "1") return;
    item.dataset.leaving = "1";
    clearTimeout(item._life);
    item.classList.add("is-out");
    window.setTimeout(function () {
      if (item.parentNode) item.parentNode.removeChild(item);
    }, reduceMotion ? 20 : 250);
  }

  /* مکث روی توست یعنی کاربر دارد می‌خواند؛ پس زمان‌سنج نگه می‌دارد. */
  function pauseToast(item) {
    item.classList.add("is-paused");
    clearTimeout(item._life);
    if (item._deadline && item._text) {
      item._remaining = Math.max(1200, item._deadline - Date.now());
    }
  }

  function resumeToast(item) {
    item.classList.remove("is-paused");
    var left = item._remaining || 0;
    if (left <= 0) return;
    item._deadline = Date.now() + left;
    item._life = window.setTimeout(function () { dismissToast(item); }, left);
  }

  /* کنار زدن با انگشت (به چپ یا پایین) — روی موبایل طبیعی‌ترین راه بستن. */
  function makeSwipeable(item) {
    var startX = 0, startY = 0, dx = 0, dy = 0, active = false;
    item.addEventListener(
      "touchstart",
      function (event) {
        if (event.touches.length !== 1) return;
        startX = event.touches[0].clientX;
        startY = event.touches[0].clientY;
        dx = dy = 0;
        active = true;
        item.classList.add("is-dragging");
      },
      { passive: true }
    );
    item.addEventListener(
      "touchmove",
      function (event) {
        if (!active) return;
        dx = event.touches[0].clientX - startX;
        dy = event.touches[0].clientY - startY;
        if (Math.abs(dx) < Math.abs(dy)) {
          dy = Math.max(0, dy);
          item.style.transform = "translateY(" + dy + "px)";
        } else {
          item.style.transform = "translateX(" + dx + "px)";
        }
        item.style.opacity = String(Math.max(0.25, 1 - Math.max(Math.abs(dx), Math.abs(dy)) / 140));
      },
      { passive: true }
    );
    item.addEventListener("touchend", function () {
      active = false;
      item.classList.remove("is-dragging");
      item.style.transform = "";
      item.style.opacity = "";
      if (Math.abs(dx) > 90 || dy > 50) dismissToast(item);
    });
  }

  function toast(message, kindOrOptions, title) {
    var stack = toastStack();
    if (!stack || !message) return null;

    var options = {};
    if (typeof kindOrOptions === "string") {
      options.kind = kindOrOptions;
      options.title = title;
    } else if (kindOrOptions && typeof kindOrOptions === "object") {
      options = kindOrOptions;
    }
    var kind = TOAST_TONES[options.kind] ? options.kind : "info";
    var tone = TOAST_TONES[kind];
    var text = String(options.message || message);

    // پیام تکراریِ پشت‌سرهم دوباره روی هم انبار نمی‌شود.
    var now = Date.now();
    recentToasts = recentToasts.filter(function (entry) { return now - entry.at < 6000; });
    if (
      recentToasts.some(function (entry) {
        return entry.kind === kind && entry.text === text;
      })
    ) {
      return null;
    }
    recentToasts.push({ kind: kind, text: text, at: now });
    toastLog.push({ kind: kind, text: text, title: options.title || tone.title, at: now });
    if (toastLog.length > 20) toastLog.shift();

    // سقف سه پیام: قدیمی‌ترین می‌رود تا تازه جا بیفتد.
    var existing = stack.querySelectorAll(".toast__item");
    if (existing.length >= MAX_TOASTS) dismissToast(existing[0]);

    var life = Math.round(options.life || Math.min(8000, Math.max(3400, 2200 + text.length * 55)));
    var item = document.createElement("div");
    item.className = "toast__item toast--" + kind;
    item.setAttribute("role", kind === "error" ? "alert" : "status");
    item.style.setProperty("--toast-life", life + "ms");

    var icon = document.createElement("span");
    icon.className = "toast__icon";
    icon.innerHTML = '<i class="' + (options.icon || tone.icon) + '" aria-hidden="true"></i>';

    var body = document.createElement("div");
    body.className = "toast__body";
    var heading = document.createElement("span");
    heading.className = "toast__title";
    heading.textContent = options.title || tone.title;
    var paragraph = document.createElement("span");
    paragraph.className = "toast__text";
    paragraph.textContent = text;
    body.appendChild(heading);
    body.appendChild(paragraph);

    var close = document.createElement("button");
    close.type = "button";
    close.className = "toast__close";
    close.setAttribute("aria-label", "بستن پیام");
    close.innerHTML = '<i class="fa-solid fa-xmark" aria-hidden="true"></i>';
    close.addEventListener("click", function () { dismissToast(item); });

    var bar = document.createElement("span");
    bar.className = "toast__bar";

    item.appendChild(icon);
    item.appendChild(body);
    item.appendChild(close);
    item.appendChild(bar);
    stack.appendChild(item);
    stack.classList.add("is-visible");

    // تور محافظ (مثل بقیهٔ صفحه): روی بعضی مرورگرهای موبایل انیمیشن ورودی اجرا
    // نمی‌شود و عنصر در حالت شفاف گیر می‌کند. اگر بعد از پایان انیمیشن هنوز
    // نامرئی بود، انیمیشن را کنار می‌گذاریم تا حتماً دیده شود.
    window.setTimeout(function () {
      if (item.dataset.leaving === "1" || !item.parentNode) return;
      var style = window.getComputedStyle(item);
      if (style.opacity === "0" || style.visibility === "hidden" || !item.getBoundingClientRect().height) {
        item.style.animation = "none";
        item.style.transform = "none";
        item.style.opacity = "1";
        item.style.visibility = "visible";
        var icon = item.querySelector(".toast__icon");
        if (icon) icon.style.animation = "none";
      }
    }, 900);

    item._text = text;
    item._remaining = life;
    item._deadline = Date.now() + life;
    item._life = window.setTimeout(function () { dismissToast(item); }, life);
    item.addEventListener("pointerenter", function () { pauseToast(item); });
    item.addEventListener("pointerleave", function () { resumeToast(item); });
    item.addEventListener("focusin", function () { pauseToast(item); });
    item.addEventListener("focusout", function () { resumeToast(item); });
    makeSwipeable(item);
    return item;
  }

  /* پیام‌هایی که سرور همراه صفحه فرستاده (نتیجهٔ یک فرم یا ریدایرکت). */
  function showServerToasts() {
    var holder = document.getElementById("flashData");
    if (!holder) return;
    var list;
    try {
      list = JSON.parse(holder.textContent || "[]");
    } catch (err) {
      return;
    }
    if (!Array.isArray(list)) return;
    list.forEach(function (entry, index) {
      if (!entry) return;
      var payload = typeof entry === "string" ? { message: entry } : entry;
      window.setTimeout(function () {
        toast(payload.message, { kind: payload.kind, title: payload.title });
      }, reduceMotion ? 0 : index * 140);
    });
  }

  window.NeshaneToast = {
    show: toast,
    dismiss: dismissToast,
    log: toastLog,
    visible: function () {
      var stack = toastStack();
      return stack ? stack.querySelectorAll(".toast__item").length : 0;
    }
  };
  window.toast = toast;

  /* ------------------------------------------------------------ پرده/انیمیشن */
  function showVeil(text, icon) {
    var veil = document.getElementById("veil");
    if (!veil) return;
    veil.innerHTML =
      '<div class="veil__inner">' +
      '<span class="veil__spark"><i class="' + (icon || "fa-solid fa-wand-magic-sparkles") + '"></i></span>' +
      '<p class="veil__text">' + (text || "در حال گشودن…") + "</p>" +
      "</div>";
    requestAnimationFrame(function () {
      veil.classList.add("is-visible");
    });
  }

  /* ---------------------------------------------------------------- OTP */
  /* خانه‌های کد همیشه چپ‌به‌راست پر می‌شوند (مطابق چیزی که در پیامک دیده می‌شود)،
     حتی وقتی کل صفحه راست‌به‌چپ است. ارقام فارسی هم پذیرفته می‌شوند. */
  function setupOtp() {
    var boxes = Array.prototype.slice.call(document.querySelectorAll(".otp__input"));
    var hidden = document.getElementById("otpValue");
    var submit = document.getElementById("otpSubmit");
    if (!boxes.length) return;

    boxes[0].setAttribute("autofocus", "autofocus");

    function sync() {
      var code = boxes
        .map(function (box) { return digitsOnly(box.value).slice(0, 1); })
        .join("");
      if (hidden) hidden.value = code;
      boxes.forEach(function (box) {
        box.value = digitsOnly(box.value).slice(0, 1);
        box.classList.toggle("is-filled", box.value.length === 1);
      });
      if (submit) submit.disabled = code.length !== boxes.length;
      return code;
    }

    function focusBox(position) {
      if (position < 0 || position >= boxes.length) return;
      boxes[position].focus();
      try { boxes[position].select(); } catch (err) { /* بی‌اهمیت */ }
    }

    boxes.forEach(function (box, index) {
      box.addEventListener("focus", function () {
        try { box.select(); } catch (err) { /* بی‌اهمیت */ }
      });

      box.addEventListener("input", function () {
        var digits = digitsOnly(box.value);
        // اگر کاربر چند رقم را یک‌جا وارد کرد، بین خانه‌ها پخش می‌شود.
        if (digits.length > 1) {
          digits.split("").forEach(function (digit, offset) {
            var target = boxes[index + offset];
            if (target) target.value = digit;
          });
          focusBox(Math.min(index + digits.length, boxes.length - 1));
          sync();
          return;
        }
        box.value = digits.slice(0, 1);
        if (box.value && index < boxes.length - 1) focusBox(index + 1);
        sync();
      });

      box.addEventListener("keydown", function (event) {
        if (event.key === "Backspace") {
          if (box.value) return; // پاک‌کردن همین خانه پیش‌فرض مرورگر
          if (index > 0) {
            event.preventDefault();
            boxes[index - 1].value = "";
            focusBox(index - 1);
            sync();
          }
          return;
        }
        // چیدمان چپ‌به‌راست است: فلش چپ به خانهٔ قبلی، فلش راست به خانهٔ بعدی.
        if (event.key === "ArrowLeft" && index > 0) { event.preventDefault(); focusBox(index - 1); }
        if (event.key === "ArrowRight" && index < boxes.length - 1) { event.preventDefault(); focusBox(index + 1); }
        if (event.key === "Home") { event.preventDefault(); focusBox(0); }
        if (event.key === "End") { event.preventDefault(); focusBox(boxes.length - 1); }
      });

      box.addEventListener("paste", function (event) {
        var text = (event.clipboardData || window.clipboardData).getData("text") || "";
        var digits = digitsOnly(text).split("");
        if (!digits.length) return;
        event.preventDefault();
        digits.slice(0, boxes.length - index).forEach(function (digit, offset) {
          boxes[index + offset].value = digit;
        });
        focusBox(Math.min(index + digits.length, boxes.length - 1));
        sync();
      });
    });

    var form = document.getElementById("otpForm");
    if (form) {
      form.addEventListener("submit", function () {
        // اطمینان از اینکه مقدار نهایی همیشه ارقام لاتین باشد.
        if (hidden) hidden.value = boxes.map(function (box) { return digitsOnly(box.value).slice(0, 1); }).join("");
        showVeil("در حال بررسی کد…", "fa-solid fa-shield-halved");
      });
    }
    sync();
    try { boxes[0].focus(); } catch (err) { /* بی‌اهمیت */ }
  }

  /* ------------------------------------------------------------- کپی متن */
  function setupCopy() {
    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        var text = button.getAttribute("data-copy") || "";
        var done = function () { toast("متن فال کپی شد"); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () { toast("کپی نشد"); });
        } else {
          var area = document.createElement("textarea");
          area.value = text;
          document.body.appendChild(area);
          area.select();
          try { document.execCommand("copy"); done(); } catch (err) { toast("کپی نشد"); }
          document.body.removeChild(area);
        }
      });
    });
  }

  /* ------------------------------------------------------ پردهٔ گشودن فال */
  function setupReveal() {
    document.querySelectorAll("[data-reveal]").forEach(function (button) {
      var form = button.closest("form");
      if (!form) return;
      form.addEventListener("submit", function () {
        if (form.dataset.busy) return;
        form.dataset.busy = "1";
        showVeil("در حال گشودن فالت…", "fa-solid fa-wand-magic-sparkles");
      });
    });
  }

  /* --------------------------------------------------------- شمارش اعداد */
  /* فقط عددهای خالص شمرده می‌شوند (با جداکنندهٔ هزار)؛ متن‌های ترکیبی
     مثل «۳۳ سال و ۲ ماه» دست‌نخورده می‌مانند تا عددشان خراب نشود. */
  var PURE_NUMBER = /^[0-9][0-9\u066c\u060c\u066b., ]*$/;

  function toPersianDigits(text) {
    return text.replace(/[0-9]/g, function (digit) {
      return FA_DIGITS.charAt(Number(digit));
    });
  }

  function countUp(el) {
    if (el.dataset.counted === "1") return;
    var ascii = toAsciiDigits(el.textContent.trim());
    if (!PURE_NUMBER.test(ascii)) return;
    var number = parseInt(ascii.replace(/[^0-9]/g, ""), 10);
    if (!number || reduceMotion) return;
    el.dataset.counted = "1";
    var start = performance.now();
    var duration = 1100;
    function frame(timestamp) {
      var progress = Math.min((timestamp - start) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      var value = Math.round(number * eased).toLocaleString("en-US");
      el.textContent = toPersianDigits(value).replace(/,/g, "٬");
      if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function setupCounters() {
    var selector = "[data-count], .stat-card__value, .stat-strip__item strong";
    document.querySelectorAll(selector).forEach(function (el, index) {
      setTimeout(function () { countUp(el); }, 120 + index * 90);
    });
  }

  /* ------------------------------------------------------ بازتاب لمس */
  function setupPress() {
    document.querySelectorAll(".btn, .option, .topic-card, .method-card--tap, .dock__item, .test-card, .history__item").forEach(function (el) {
      el.addEventListener("pointerdown", function () { el.classList.add("is-pressed"); });
      ["pointerup", "pointerleave", "pointercancel"].forEach(function (event) {
        el.addEventListener(event, function () { el.classList.remove("is-pressed"); });
      });
    });
  }

  /* --------------------------------------------------- ظاهر شدن با اسکرول */
  function setupScrollReveal() {
    var screen = document.getElementById("screen");
    if (!screen || reduceMotion) return;
    var targets = screen.querySelectorAll(".section, .panel, .history__item, .result-chip");
    if (!targets.length) return;
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.style.animation = "riseIn 0.55s var(--ease) both";
            observer.unobserve(entry.target);
          }
        });
      },
      { root: screen, threshold: 0.08 }
    );
    targets.forEach(function (target) {
      if (target.classList.contains("anim-in")) return;
      observer.observe(target);
    });
  }

  /* --------------------------------------------------- خطاها: لرزش نرم */
  function setupAlerts() {
    var alert = document.querySelector(".alert");
    if (!alert || reduceMotion) return;
    alert.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  /* ------------------------------------------------------- نصب PWA (اپ) */
  var INSTALL_KEY = "neshane_install_dismissed";
  var INSTALL_SEEN_KEY = "neshane_install_seen";
  var INSTALL_AGAIN_DAYS = 5;

  function storageGet(key) {
    try { return window.localStorage.getItem(key); } catch (err) { return null; }
  }

  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); } catch (err) { /* حالت خصوصی */ }
  }

  function isStandalone() {
    return (
      (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
      window.navigator.standalone === true
    );
  }

  /* سرویس‌ورکر فقط روی https یا localhost اجازه دارد؛ روی IP محلی خطا نمی‌دهیم. */
  function serviceWorkerAllowed() {
    var host = window.location.hostname;
    return (
      window.location.protocol === "https:" ||
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "::1"
    );
  }

  function setupServiceWorker() {
    if (!("serviceWorker" in navigator) || !serviceWorkerAllowed()) return;
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () { /* بی‌اهمیت */ });
    });
  }

  /* یک کارت کوچک بار اول نشان می‌دهیم؛ اگر کاربر ببندد، دیگر تکرار نمی‌شود. */
  function installSeenRecently() {
    var stamp = parseInt(storageGet(INSTALL_SEEN_KEY) || "0", 10);
    if (!stamp) return false;
    return Date.now() - stamp < INSTALL_AGAIN_DAYS * 24 * 60 * 60 * 1000;
  }

  function setupInstall() {
    var card = document.getElementById("installCard");
    if (!card || isStandalone() || storageGet(INSTALL_KEY) === "1") return;
    if (installSeenRecently()) return;

    var hint = document.getElementById("installHint");
    var go = document.getElementById("installGo");
    var close = document.getElementById("installClose");
    var prompt = null;
    var shown = false;
    var isIos = /iPad|iPhone|iPod/.test(window.navigator.userAgent);

    function show(text) {
      if (shown) return;
      shown = true;
      storageSet(INSTALL_SEEN_KEY, String(Date.now()));
      if (text && hint) hint.textContent = text;
      card.hidden = false;
    }

    function hide(remember) {
      if (remember) storageSet(INSTALL_KEY, "1");
      card.classList.add("is-out");
      setTimeout(function () { card.hidden = true; }, 260);
    }

    window.addEventListener("beforeinstallprompt", function (event) {
      event.preventDefault();
      prompt = event;
      setTimeout(function () {
        show("یک آیکون روی صفحهٔ اصلی می‌آید و بدون نوار آدرس باز می‌شود.");
      }, 2200);
    });

    window.addEventListener("appinstalled", function () {
      storageSet(INSTALL_KEY, "1");
      hide(false);
    });

    // آیفون و اندرویدِ بدون رویداد نصب: مسیر دستی را نشان می‌دهیم.
    var isMobile = isIos || /Android/i.test(window.navigator.userAgent);
    if (isIos) {
      setTimeout(function () {
        show("در Safari دکمهٔ اشتراک‌گذاری را بزن و «افزودن به صفحهٔ اصلی» را انتخاب کن.");
      }, 4200);
    } else if (isMobile) {
      setTimeout(function () {
        show("از منوی مرورگر «افزودن به صفحهٔ اصلی» (نصب اپ) را انتخاب کن.");
      }, 5200);
    }

    if (go) {
      go.addEventListener("click", function () {
        if (prompt) {
          prompt.prompt();
          var settled = prompt.userChoice;
          if (settled && settled.then) {
            settled.then(function () { prompt = null; hide(true); }, function () { hide(true); });
          } else {
            prompt = null;
            hide(true);
          }
          return;
        }
        show("از منوی مرورگر «افزودن به صفحهٔ اصلی» را انتخاب کن.");
      });
    }

    if (close) {
      close.addEventListener("click", function () { hide(true); });
    }
  }

  /* ------------------------------------------------ پاپ‌اپ امتیاز و نظر */
  /* مرحلهٔ یک: ستاره‌ها. مرحلهٔ دو: نوشتن نظر. اگر جاوااسکریپت نباشد، هر دو
     مرحله با هم دیده می‌شوند و فرم سادهٔ HTML کار را تمام می‌کند. */
  var RATE_THANKS_KEY = "neshane_rate_thanked";

  function setupRateModal() {
    var modal = document.querySelector("[data-rate-modal]");
    if (!modal) return;

    var form = document.getElementById("rateForm");
    var steps = modal.querySelectorAll("[data-rate-step]");
    var commentStep = modal.querySelector('[data-rate-step="2"]');
    var commentBox = commentStep ? commentStep.querySelector("textarea") : null;
    var titleEl = modal.querySelector("[data-rate-title]");
    var bodyEl = modal.querySelector("[data-rate-body]");
    var submitting = false;

    function close() {
      modal.classList.add("is-out");
      setTimeout(function () { modal.hidden = true; }, 260);
    }

    modal.querySelectorAll("[data-rate-close]").forEach(function (button) {
      button.addEventListener("click", close);
    });

    function pickStar(value) {
      modal.setAttribute("data-stars", String(value));
      // همهٔ ستاره‌های تا انتخاب‌شده روشن می‌شوند (تازه‌تر از انتخاب، خاموش می‌ماند).
      modal.querySelectorAll(".rate-star").forEach(function (label) {
        var input = label.querySelector("input[name=\"rating\"]");
        var star = input ? Number(input.value) : 0;
        label.classList.toggle("is-lit", star > 0 && star <= value);
        label.classList.toggle("is-picked", star === value);
      });
      if (commentStep) commentStep.hidden = false;
      // انتخاب ستاره، نظر را برای کاربر ضروری نمی‌کند؛ فقط تشویقش می‌کند.
      if (commentBox && !commentBox.dataset.focused) {
        commentBox.dataset.focused = "1";
        setTimeout(function () {
          try { commentBox.focus({ preventScroll: true }); } catch (err) { /* بی‌اهمیت */ }
        }, 240);
      }
    }

    modal.querySelectorAll('input[name="rating"]').forEach(function (input) {
      input.addEventListener("change", function () { pickStar(Number(input.value) || 0); });
      input.addEventListener("click", function () { pickStar(Number(input.value) || 0); });
    });

    if (form) {
      form.addEventListener("submit", function (event) {
        if (submitting) { event.preventDefault(); return; }
        var checked = form.querySelector('input[name="rating"]:checked');
        if (!checked) {
          event.preventDefault();
          if (titleEl) titleEl.textContent = "اول امتیازت را انتخاب کن، بقیه‌اش راحت است.";
          return;
        }
        var active = event.submitter;
        if (active && active.name === "comment") {
          // دکمهٔ «فقط امتیاز را ثبت کن»: نظر خالی می‌رود.
          var box = form.querySelector('textarea[name="comment"]');
          if (box) box.value = "";
        }
        if (!window.fetch) return; // مرورگر قدیمی: فرم ساده ادامه می‌دهد
        event.preventDefault();
        submitting = true;
        modal.classList.add("is-busy");
        var data = new FormData(form);
        fetch(form.action, {
          method: "POST",
          body: data,
          headers: { "Accept": "application/json", "X-Requested-With": "fetch" },
        })
          .then(function (response) { return response.json().catch(function () { return { ok: response.ok }; }); })
          .then(function (result) {
            if (result && result.ok) {
              try { window.localStorage.setItem(RATE_THANKS_KEY, "1"); } catch (err) { /* بی‌اهمیت */ }
              if (titleEl) titleEl.textContent = result.message || "ممنون که وقت گذاشتی!";
              if (bodyEl) bodyEl.textContent = "این بازخورد همین حالا در مسیر بعدی نشانه اثر می‌گذارد. حالت خوب باشد.";
              modal.querySelectorAll("[data-rate-step]").forEach(function (step) { step.hidden = true; });
              modal.classList.add("is-done");
              setTimeout(close, 1900);
              return;
            }
            submitting = false;
            modal.classList.remove("is-busy");
            if (titleEl) titleEl.textContent = (result && result.message) || "ثبت نشد؛ یک بار دیگر بزن.";
          })
          .catch(function () {
            // شبکه قطع بود: همان فرم سادهٔ HTML را ادامه می‌دهیم (بدون رویداد مجدد).
            modal.classList.remove("is-busy");
            form.submit();
          });
      });
    }

    /* متنِ ترغیب‌کننده را بعد از باز شدن پاپ‌اپ از مدل می‌گیریم؛ اگر نرسد، همان
       متنِ آماده می‌ماند. صفحه هرگز پشت این درخواست معطل نمی‌ماند. */
    if (window.fetch && titleEl && bodyEl) {
      fetch("/api/feedback/invite", { headers: { "Accept": "application/json" } })
        .then(function (response) { return response.ok ? response.json() : null; })
        .then(function (data) {
          var invite = data && data.invite;
          if (!invite || modal.hidden) return;
          if (invite.title && !modal.classList.contains("is-done")) titleEl.textContent = invite.title;
          if (invite.body && !modal.classList.contains("is-done")) bodyEl.textContent = invite.body;
        })
        .catch(function () { /* متن آماده می‌ماند */ });
    }
  }

  /* ------------------------------------------------------------ تبلیغ پاپ‌اپ */

  /*
   * تبلیغ را از سرور می‌گیریم (نه از HTML) تا خودِ سرور تصمیم بگیرد الان وقت
   * نمایش هست یا نه: بازهٔ تاریخ، ساعت، روز هفته، سهمیهٔ روزانه و «دیگر نشان نده».
   * اگر تبلیغی نبود، هیچ چیزی ساخته نمی‌شود.
   *
   * نکتهٔ مهم: پاپ‌اپ امتیاز اولویت دارد؛ اگر آن باز باشد، تبلیغ را حتی
   * نمی‌گیریم تا دو پنجره روی هم نیفتند و «نمایش» بی‌مورد ثبت نشود.
   */
  function setupAdPopup() {
    var modal = document.getElementById("adModal");
    if (!modal || !window.fetch) return;

    var mediaBox = modal.querySelector("[data-ad-media]");
    var titleEl = modal.querySelector("[data-ad-title]");
    var textEl = modal.querySelector("[data-ad-text]");
    var ctaEl = modal.querySelector("[data-ad-cta]");
    var skipBtn = modal.querySelector("[data-ad-skip]");
    var dismissBtn = modal.querySelector("[data-ad-dismiss]");
    var timerEl = modal.querySelector("[data-ad-timer]");
    var ad = null;
    var closed = false;
    var timers = [];

    // هم تایمر و هم شمارندهٔ تکرار در همین فهرست نگه داشته می‌شوند.
    function clearTimers() {
      timers.forEach(function (id) {
        clearTimeout(id);
        clearInterval(id);
      });
      timers = [];
    }

    function sendEvent(kind) {
      if (!ad) return;
      var body = new URLSearchParams();
      body.set("kind", kind);
      try {
        // keepalive می‌گذارد درخواست حتی هنگام بسته‌شدن صفحه کامل شود.
        fetch("/api/ad/" + ad.id + "/event", {
          method: "POST",
          body: body,
          headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "fetch" },
          keepalive: kind === "click"
        });
      } catch (err) {
        /* ثبت رویداد نباید تجربهٔ کاربر را خراب کند */
      }
    }

    function close(reason) {
      if (closed) return;
      closed = true;
      clearTimers();
      modal.classList.remove("is-open");
      modal.setAttribute("aria-hidden", "true");
      window.setTimeout(function () {
        modal.hidden = true;
        mediaBox.innerHTML = "";
        document.documentElement.style.removeProperty("overflow");
      }, reduceMotion ? 0 : 240);
      // اگر خودش بسته شد یا رد شد، «ردکردن» ثبت می‌شود تا آمار درست بماند.
      if (reason === "skip") sendEvent("skip");
    }

    function build(ad) {
      mediaBox.innerHTML = "";
      var node;
      if (ad.kind === "video") {
        node = document.createElement("video");
        node.src = ad.media;
        node.playsInline = true;
        node.autoplay = true;
        node.muted = true;
        node.controls = false;
        node.setAttribute("playsinline", "");
      } else {
        node = document.createElement("img");
        node.src = ad.media;
        node.alt = ad.title || "تبلیغ";
        node.loading = "eager";
      }
      mediaBox.appendChild(node);
      return node;
    }

    function open(ad, node) {
      titleEl.textContent = ad.title || "";
      textEl.textContent = ad.body || "";
      textEl.hidden = !ad.body;

      if (ad.link) {
        ctaEl.href = ad.link;
        ctaEl.innerHTML =
          '<i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i> ' +
          (ad.cta || "بیشتر بدانید");
        ctaEl.hidden = false;
        ctaEl.addEventListener("click", function () { sendEvent("click"); });
      } else {
        ctaEl.hidden = true;
      }

      if (ad.dismiss_days > 0) {
        dismissBtn.hidden = false;
        dismissBtn.addEventListener("click", function () {
          sendEvent("dismiss");
          close("dismiss");
        });
      }

      var waitSeconds = ad.skip_allowed ? ad.skip_after : ad.hold_seconds;
      var left = Math.max(0, waitSeconds);
      var total = Math.max(1, ad.hold_seconds);
      var elapsed = 0;

      function paint() {
        if (left > 0) {
          timerEl.innerHTML = "تا بستن <b>" + toFa(left) + "</b> ثانیه";
        } else {
          timerEl.innerHTML = "می‌توانی ببندی";
        }
        if (ad.skip_allowed) {
          skipBtn.hidden = false;
          skipBtn.disabled = left > 0;
          skipBtn.textContent = left > 0 ? "رد کردن (" + toFa(left) + ")" : "رد کردن";
        }
      }
      paint();

      // شمارش معکوسِ فعال‌شدن ردکردن (یا پایان زمانِ اجباری)
      var tick = setInterval(function () {
        if (closed) return clearInterval(tick);
        left -= 1;
        elapsed += 1;
        if (left <= 0) clearInterval(tick);
        paint();
        // وقتی امکان ردکردن نیست، خودش بعد از زمان تعیین‌شده می‌بندد.
        if (!ad.skip_allowed && left <= 0) close("auto");
      }, 1000);
      timers.push(tick);

      // اگر ردکردن آزاد نیست ولی ویدیو هست، به‌جاى زمان ثابت منتظر پایان ویدیو می‌مانیم.
      if (node && ad.kind === "video") {
        node.addEventListener("timeupdate", function () {
          if (ad.skip_allowed || closed) return;
          if (total > 0 && node.currentTime >= Math.min(total, node.duration || total)) close("auto");
        });
        // ویدیویی که مرورگر نمی‌تواند پخش کند (کدک ناسازگار یا فایل خراب) نباید
        // کاربر را پشت یک جعبهٔ سیاه نگه دارد: جای ویدیو را برمی‌داریم و انتظار را
        // کوتاه می‌کنیم تا کاربر بیهوده معطل نماند.
        node.addEventListener("error", function () {
          if (closed) return;
          mediaBox.hidden = true;
          mediaBox.innerHTML = "";
          if (!ad.skip_allowed && left > 5) {
            left = 5;
            paint();
          }
        });
      }

      skipBtn.addEventListener("click", function () { close("skip"); });
      modal.querySelectorAll("[data-ad-close]").forEach(function (el) {
        el.addEventListener("click", function () { close(ad.skip_allowed ? "skip" : "auto"); });
      });
      document.addEventListener("keydown", function (event) {
        if (closed || event.key !== "Escape") return;
        if (ad.skip_allowed) close("skip");
      });

      // لمس تمرکز را روی دکمهٔ اصلی نگه می‌داریم و اسکرول پشت صفحه را می‌بندیم.
      modal.hidden = false;
      modal.setAttribute("aria-hidden", "false");
      requestAnimationFrame(function () { modal.classList.add("is-open"); });
      document.documentElement.style.overflow = "hidden";
      if (ad.skip_allowed) skipBtn.focus({ preventScroll: true });
      // تور نهایی: اگر انیمیشن ورودی روی این دستگاه اجرا نشد، کارت را دستی
      // نمایان می‌کنیم تا هرگز پنجرهٔ خالی یا نیمه‌شفاف نبیند.
      window.setTimeout(revealHidden, reduceMotion ? 0 : 520);
    }

    function toFa(value) {
      return String(value).replace(/\d/g, function (digit) { return FA_DIGITS[Number(digit)]; });
    }

    // صبر کوتاه تا صفحه ساکن شود، بعد تازه سؤال می‌کنیم ببینیم تبلیغی هست یا نه.
    window.setTimeout(function () {
      var rateOpen = document.querySelector("[data-rate-modal]:not([hidden])");
      if (rateOpen && !rateOpen.hidden) return;
      fetch("/api/ad?placement=popup", { headers: { "X-Requested-With": "fetch" } })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (!data || !data.ad || !data.ad.media) return;
          ad = data.ad;
          var node = build(ad);
          open(ad, node);
          sendEvent("impression");
        })
        .catch(function () { /* خطای تبلیغ هیچ‌وقت به کاربر نشان داده نمی‌شود */ });
    }, 1600);
  }

  /* ------------------------------------------------ تضمین دیده‌شدن محتوا */
  /* روی بعضی مرورگرهای موبایل، انیمیشن ورودی اجرا نمی‌شود و عنصر با
     `animation-fill-mode: both` در حالت شفاف گیر می‌کند؛ نتیجه: جعبه‌های خالی.
     این تابع هر عنصر نامرئی را دستی نمایان می‌کند. */
  var CONTENT_SELECTOR =
    ".option, .test-card, .method-card, .card-list > *, .anim-in, .lp-tile, .topic-card, .stat-card, .life-card, .ad-modal__card, .ad-modal__backdrop, .rate-modal__card, .rate-modal__backdrop";

  function revealHidden() {
    document.querySelectorAll(CONTENT_SELECTOR).forEach(function (el) {
      if (!el.offsetHeight && !el.offsetWidth) return; // واقعاً پنهان است
      var style = window.getComputedStyle(el);
      if (style.opacity === "0" || style.visibility === "hidden") {
        el.style.animation = "none";
        el.style.opacity = "1";
        el.style.visibility = "visible";
        el.style.transform = "none";
        return;
      }
      // انیمیشنی که روی این دستگاه جلو نمی‌رود (تبِ پنهان، حالت کم‌مصرف،
      // شبیه‌ساز) را به حالت پایانی می‌بریم تا محتوا نیمه‌کاره نماند.
      if (typeof el.getAnimations !== "function") return;
      el.getAnimations().forEach(function (anim) {
        if (anim.playState !== "running") return;
        try { anim.finish(); } catch (err) { /* بی‌اهمیت */ }
      });
    });
  }

  function setupRevealSafety() {
    revealHidden();
    setTimeout(revealHidden, 700);
    setTimeout(revealHidden, 1600);
    window.addEventListener("load", function () {
      setTimeout(revealHidden, 400);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    // علامت آماده‌بودن: آزمون‌ها می‌فهمند که راه‌اندازی سمت کاربر انجام شده است.
    document.documentElement.setAttribute("data-neshane-ready", "1");
    showServerToasts();
    setupOtp();
    setupCopy();
    setupReveal();
    setupCounters();
    setupPress();
    setupScrollReveal();
    setupAlerts();
    setupRevealSafety();
    setupRateModal();
    setupAdPopup();
    setupInstall();
    setupServiceWorker();
  });
})();
