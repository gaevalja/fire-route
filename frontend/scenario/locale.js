(function (global) {
  "use strict";

  const storageKey = "fr-locale";
  let language = "ko";
  try {
    if (global.localStorage.getItem(storageKey) === "en") language = "en";
  } catch { /* The selected language still works for this page. */ }

  const listeners = new Set();
  const originals = new WeakMap();
  const t = (korean, english) => language === "en" ? english : korean;
  const getLanguage = () => language;

  function update(next) {
    if ((next !== "ko" && next !== "en") || next === language) return;
    language = next;
    for (const render of listeners) render();
  }

  function setLanguage(next) {
    if (next !== "ko" && next !== "en") return;
    try { global.localStorage.setItem(storageKey, next); } catch { /* Storage is optional. */ }
    update(next);
  }

  function localize(document) {
    document.documentElement.lang = language;
    for (const [data, attribute] of [["data-en", null], ["data-en-aria-label", "aria-label"], ["data-en-title", "title"]]) {
      for (const element of document.querySelectorAll(`[${data}]`)) {
        if (!originals.has(element)) originals.set(element, {});
        const labels = originals.get(element);
        labels[data] ??= attribute ? element.getAttribute(attribute) : element.textContent;
        const value = t(labels[data], element.getAttribute(data));
        if (attribute) element.setAttribute(attribute, value);
        else element.textContent = value;
      }
    }
  }

  function onChange(render) { listeners.add(render); }

  global.addEventListener?.("storage", (event) => {
    if (event.key === storageKey) update(event.newValue ?? "ko");
  });
  global.FireRouteLocale = Object.freeze({t, getLanguage, setLanguage, localize, onChange});
})(globalThis);
