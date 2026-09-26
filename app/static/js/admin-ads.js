/* فرم تبلیغات پنل: پیش‌نمایش فایل، کنترل حجم، خواندن طول ویدیو و چیپ‌های روز هفته. */
(function () {
  "use strict";

  var form = document.querySelector("[data-ad-form]");
  if (!form) return;

  var input = form.querySelector("[data-ad-file]");
  var preview = form.querySelector("[data-ad-preview]");
  var drop = form.querySelector(".upload__drop");
  var holdField = form.querySelector('input[name="hold_seconds"]');
  var skipField = form.querySelector('input[name="skip_after"]');
  var skipAllowed = form.querySelector('input[name="skip_allowed"]');

  var MAX_IMAGE = 8 * 1024 * 1024;
  var MAX_VIDEO = 32 * 1024 * 1024;

  function human(bytes) {
    if (bytes < 1024) return bytes + " بایت";
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " کیلوبایت";
    return (bytes / 1024 / 1024).toFixed(1) + " مگابایت";
  }

  function faDigits(text) {
    return String(text).replace(/[0-9]/g, function (digit) {
      return "۰۱۲۳۴۵۶۷۸۹"[Number(digit)];
    });
  }

  /* پیام کوتاه بالای فرم؛ همان الگوی هشدارهای پنل. */
  function warn(message, kind) {
    var old = form.querySelector(".ad-form__note");
    if (old) old.remove();
    if (!message) return;
    var box = document.createElement("div");
    box.className = "alert " + (kind === "ok" ? "alert--ok" : "alert--error") + " ad-form__note";
    box.textContent = message;
    form.insertBefore(box, form.firstChild);
  }

  function clearPreview() {
    if (!preview) return;
    preview.hidden = true;
    preview.innerHTML = "";
  }

  function showPreview(file) {
    if (!preview) return;
    clearPreview();

    var video = file.type.indexOf("video") === 0;
    var limit = video ? MAX_VIDEO : MAX_IMAGE;

    if (file.size > limit) {
      warn("حجم فایل " + human(file.size) + " است و از سقف " + human(limit) + " بیشتر است.", "error");
      input.value = "";
      return;
    }
    warn("");

    var node = document.createElement(video ? "video" : "img");
    node.src = URL.createObjectURL(file);
    if (video) {
      node.muted = true;
      node.playsInline = true;
      node.controls = true;
      // طول ویدیو را از خود فایل می‌خوانیم تا مدیر عدد حدسی وارد نکند.
      node.addEventListener("loadedmetadata", function () {
        var seconds = Math.max(1, Math.round(node.duration || 0));
        if (holdField) {
          var current = Number(holdField.value || 0);
          if (!current || current < seconds) holdField.value = Math.min(180, seconds);
        }
        if (skipField) {
          var skip = Number(skipField.value || 0);
          if (skip > seconds) skipField.value = seconds;
        }
        info.appendChild(text("طول ویدیو: " + faDigits(seconds) + " ثانیه"));
      });
    } else {
      node.alt = "پیش‌نمایش تبلیغ";
    }

    var box = document.createElement("div");
    box.className = "upload__info";
    var strong = document.createElement("strong");
    strong.textContent = file.name;
    var size = text(human(file.size) + (video ? " • ویدیو" : " • عکس"));
    var info = document.createElement("div");
    info.className = "upload__info";
    info.appendChild(size);
    box.appendChild(strong);

    preview.appendChild(node);
    preview.appendChild(box);
    preview.appendChild(info);
    preview.hidden = false;

    if (drop) drop.classList.add("is-ready");
  }

  function text(value) {
    var el = document.createElement("small");
    el.className = "muted small";
    el.textContent = value;
    return el;
  }

  if (input) {
    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (file) showPreview(file);
    });
  }

  /* کشیدن و رهاکردن فایل روی کادر. */
  if (drop && input) {
    ["dragenter", "dragover"].forEach(function (name) {
      drop.addEventListener(name, function (event) {
        event.preventDefault();
        drop.classList.add("is-over");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      drop.addEventListener(name, function (event) {
        event.preventDefault();
        drop.classList.remove("is-over");
      });
    });
    drop.addEventListener("drop", function (event) {
      var files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) return;
      input.files = files;
      showPreview(files[0]);
    });
  }

  /* چیپ‌های روز هفته: مرورگرهای قدیمی `:has()` را نمی‌شناسند، پس کلاس را دستی می‌گذاریم. */
  function syncChips() {
    Array.prototype.forEach.call(document.querySelectorAll(".check--chip"), function (chip) {
      var box = chip.querySelector("input[type=checkbox]");
      if (!box) return;
      chip.classList.toggle("is-on", box.checked);
      box.addEventListener("change", function () {
        chip.classList.toggle("is-on", box.checked);
      });
    });
  }
  syncChips();

  /*
   * مقدار «از چند ثانیه بعد» همیشه فرستاده می‌شود، چون وقتی ردکردن خاموش است
   * همین عدد یعنی «چند ثانیه باید بماند». پس فیلد را غیرفعال نمی‌کنیم؛ فقط کم‌رنگ
   * می‌شود تا معلوم باشد معنی‌اش عوض شده.
   */
  function syncSkip() {
    if (!skipField || !skipAllowed) return;
    var apply = function () {
      skipField.classList.toggle("is-dim", !skipAllowed.checked);
    };
    apply();
    skipAllowed.addEventListener("change", apply);
  }
  syncSkip();
})();
